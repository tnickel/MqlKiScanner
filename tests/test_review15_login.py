"""Account isolation and shared browser lifetime, entirely offline."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mqlkiscanner.mql5 import browser_session as browser
from mqlkiscanner.mql5.session import Mql5Session


@pytest.fixture
def login_env(tmp_path, monkeypatch):
    credentials = {"mql5_user": "account-A", "mql5_pass": "password-A"}
    monkeypatch.setattr(browser.secrets_store, "get_secret", credentials.__getitem__)
    monkeypatch.setattr(browser, "COOKIE_FILE", tmp_path / "cookies.json")
    monkeypatch.setattr(browser, "PROFILE_DIR", tmp_path / "chrome_profile")
    monkeypatch.setattr(browser, "TRADES_DIR", tmp_path / "trades")
    monkeypatch.setattr(browser, "DOWNLOAD_DIR", tmp_path / "trades" / "download")
    monkeypatch.setattr(browser.time, "sleep", lambda _: None)
    monkeypatch.setattr(browser, "_start_driver", Mock(side_effect=AssertionError("real browser forbidden")))
    return credentials


@pytest.mark.parametrize("payload", [
    {"cookies": {"session": "legacy-A"}},
    {"account": browser._account_key("account-A"), "cookies": {"session": "A"}},
    {"account": browser._account_key("account-B"), "cookies": "invalid"},
])
def test_unbound_other_account_and_malformed_cookies_are_ignored(login_env, payload):
    browser.COOKIE_FILE.write_text(json.dumps(payload), encoding="utf8")
    assert browser.load_saved_cookies("account-B") is None
    assert json.loads(browser.COOKIE_FILE.read_text(encoding="utf8")) == payload


def test_matching_account_reuses_cookies_and_tracks_identity(login_env, monkeypatch):
    browser.save_cookies({"session": "A"}, "account-A")
    session = Mql5Session()
    session.http.cookies.set("old_host_cookie", "discard", domain="www.mql5.com")
    monkeypatch.setattr(session, "is_logged_in", lambda: True)
    assert browser.ensure_mql5_cookies({}, session)
    assert session.logged_in and session._authenticated_user == "account-A"
    assert session.http.cookies.get_dict() == {"session": "A"}
    browser._start_driver.assert_not_called()


def test_existing_http_session_switches_to_new_account(login_env, monkeypatch):
    browser.save_cookies({"session": "A"}, "account-A")
    session = Mql5Session()
    session.logged_in = True
    session._authenticated_user = "account-A"
    session.http.cookies.set("old_cookie", "A", domain="www.mql5.com")
    login_env.update(mql5_user="account-B", mql5_pass="password-B")
    driver = Mock(current_url="https://www.mql5.com/en")
    driver.find_elements.return_value = []
    driver.get_cookies.return_value = [{"name": "session", "value": "B", "domain": ".mql5.com"}]
    start = Mock(return_value=driver)
    form_login = Mock()
    check = Mock(return_value=True)
    monkeypatch.setattr(browser, "_start_driver", start)
    monkeypatch.setattr(browser, "_driver_login", form_login)
    monkeypatch.setattr(session, "is_logged_in", check)
    session.ensure_session_for_export()
    start.assert_called_once_with(user="account-B")
    form_login.assert_called_once_with(driver, "account-B", "password-B", force_login=False)
    check.assert_called_once()  # Only B's newly applied cookies are checked.
    assert session._authenticated_user == "account-B"
    assert session.http.cookies.get_dict() == {"session": "B"}
    assert browser.load_saved_cookies("account-A") is None
    assert browser.load_saved_cookies("account-B") == {"session": "B"}
    driver.quit.assert_called_once()


def test_profiles_use_distinct_account_paths_and_preserve_legacy(login_env, monkeypatch):
    from selenium import webdriver

    browser.PROFILE_DIR.mkdir()
    legacy = browser.PROFILE_DIR / "untouched.txt"
    legacy.write_text("old profile", encoding="utf8")
    chrome = Mock()
    monkeypatch.setattr(webdriver, "Chrome", chrome)
    # The fixture blocks the low-level entry point; obtain the actual function
    # through the saved original below to test Selenium options, never Chrome.
    ORIGINAL_START_DRIVER(user="account-A")
    ORIGINAL_START_DRIVER(user="account-B", download_dir=browser.DOWNLOAD_DIR)
    options = [call.kwargs["options"] for call in chrome.call_args_list]
    a, b = browser._profile_for_user("account-A"), browser._profile_for_user("account-B")
    assert a != b and a != browser.PROFILE_DIR and b != browser.PROFILE_DIR
    assert f"--user-data-dir={a}" in options[0].arguments
    assert f"--user-data-dir={b}" in options[1].arguments
    assert "account-A" not in str(a) and "account-B" not in str(b)
    assert legacy.read_text(encoding="utf8") == "old profile"


ORIGINAL_START_DRIVER = browser._start_driver


class ProfileDriver:
    """Profile initially logged in; clearing cookies exposes the login form."""
    def __init__(self, accept=True, ignore_clear=False):
        self.logged_in = True
        self.accept = accept
        self.ignore_clear = ignore_clear
        self.current_url = "https://www.mql5.com/en"
        self.inputs = {}
        self.quit = Mock()
        self.cleared = False

    def get(self, url):
        self.current_url = ("https://www.mql5.com/en" if self.logged_in else url)

    def delete_all_cookies(self):
        self.cleared = True
        if not self.ignore_clear:
            self.logged_in = False

    def find_elements(self, by, name):
        return [object()] if name == "Login" and not self.logged_in else []

    def find_element(self, by, name):
        return SimpleNamespace(clear=lambda: None,
                               send_keys=lambda value: self.inputs.update({name: value}))

    def execute_script(self, *args):
        self.logged_in = self.accept
        self.current_url = ("https://www.mql5.com/en" if self.accept
                            else "https://www.mql5.com/en/auth_login")

    def get_cookies(self):
        return [{"name": "session", "value": "fresh-B", "domain": ".mql5.com"}]


@pytest.mark.parametrize("outcome", ["success", "wrong_password", "no_form"])
def test_forced_login_submits_credentials_or_reports_failure(login_env, monkeypatch, outcome):
    import selenium.webdriver.support.ui

    def until(driver, predicate):
        result = predicate(driver)
        if not result:
            raise RuntimeError("simulated wait timeout")
        return result

    monkeypatch.setattr(selenium.webdriver.support.ui, "WebDriverWait",
                        lambda driver, _: SimpleNamespace(until=lambda f: until(driver, f)))
    login_env.update(mql5_user="account-B", mql5_pass="password-B")
    browser.save_cookies({"session": "old-B"}, "account-B")
    driver = ProfileDriver(accept=outcome != "wrong_password", ignore_clear=outcome == "no_form")
    monkeypatch.setattr(browser, "_start_driver", Mock(return_value=driver))
    session = Mql5Session()
    monkeypatch.setattr(session, "is_logged_in", lambda: True)
    if outcome == "success":
        assert browser.ensure_mql5_cookies({}, session, force_browser_login=True)
        assert browser.load_saved_cookies("account-B") == {"session": "fresh-B"}
        assert session._authenticated_user == "account-B"
    else:
        with pytest.raises(RuntimeError, match="nicht bestätigt|nicht akzeptiert"):
            browser.ensure_mql5_cookies({}, session, force_browser_login=True)
        assert not session.logged_in and session._authenticated_user is None
        assert browser.load_saved_cookies("account-B") == {"session": "old-B"}
    assert driver.cleared
    if outcome != "no_form":
        assert driver.inputs == {"Login": "account-B", "Password": "password-B"}
    driver.quit.assert_called_once()


def test_login_export_and_direct_login_wait_and_release_lock_on_failure(login_env, monkeypatch):
    entered, release = Event(), Event()
    second_started, third_started = Event(), Event()
    state_lock = Lock()
    starts = []
    browser.DOWNLOAD_DIR.mkdir(parents=True)
    staging = browser.DOWNLOAD_DIR / "pending.csv"
    staging.write_text("pending", encoding="utf8")

    def start(**kwargs):
        with state_lock:
            starts.append(kwargs)
            first = len(starts) == 1
        if first:
            entered.set()
            assert release.wait(5)
        raise RuntimeError("simulated Chrome launch failure")

    def export():
        second_started.set()
        return browser.export_positions_via_browser(1)

    def direct_login():
        third_started.set()
        return browser._login_via_browser({}, Mql5Session())

    monkeypatch.setattr(browser, "_start_driver", start)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(browser.ensure_mql5_cookies, {}, Mql5Session())
        assert entered.wait(3)
        second, third = pool.submit(export), pool.submit(direct_login)
        try:
            assert second_started.wait(3) and third_started.wait(3)
            assert not second.done() and not third.done()
            assert staging.exists()  # Export must not even clear staging yet.
            assert len(starts) == 1
        finally:
            release.set()
        for future in (first, second, third):
            with pytest.raises(RuntimeError, match="simulated Chrome launch failure"):
                future.result(timeout=5)
    assert len(starts) == 3
    assert not staging.exists()
    assert all(call["user"] == "account-A" for call in starts)
    # Another thread reached Chrome after each previous exception: no leaked lock.


def test_export_holds_lock_until_browser_has_closed(login_env, monkeypatch):
    import selenium.webdriver.support.ui

    quitting, allow_quit, login_started = Event(), Event(), Event()
    driver = Mock(current_url="https://www.mql5.com/en")
    driver.find_elements.side_effect = lambda by, query: [] if by == "id" else [Mock()]
    form_login = Mock()
    monkeypatch.setattr(browser, "_driver_login", form_login)
    monkeypatch.setattr(selenium.webdriver.support.ui, "WebDriverWait",
                        lambda *_: SimpleNamespace(until=lambda _: Mock()))

    def download(*_):
        (browser.DOWNLOAD_DIR / "new.csv").write_text(
            "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
            "2026.01.01 00:00:00;Buy;0.1;XAUUSD;2000;0.1;2026.01.01 01:00:00;2001;0;0;10\n",
            encoding="utf8")

    def quit_driver():
        quitting.set()
        assert allow_quit.wait(5)

    def login():
        login_started.set()
        return browser.ensure_mql5_cookies({}, Mql5Session())

    driver.execute_script.side_effect = download
    driver.quit.side_effect = quit_driver
    start = Mock(side_effect=[driver, RuntimeError("next login reached Chrome")])
    monkeypatch.setattr(browser, "_start_driver", start)
    with ThreadPoolExecutor(max_workers=2) as pool:
        export = pool.submit(browser.export_positions_via_browser, 123)
        assert quitting.wait(3)
        pending_login = pool.submit(login)
        try:
            assert login_started.wait(3)
            assert not pending_login.done() and start.call_count == 1
        finally:
            allow_quit.set()
        assert export.result(timeout=5) == str(browser.TRADES_DIR / "123_positions.csv")
        with pytest.raises(RuntimeError, match="next login reached Chrome"):
            pending_login.result(timeout=5)
    assert start.call_args_list[0].kwargs == {"download_dir": browser.DOWNLOAD_DIR, "user": "account-A"}
    assert start.call_args_list[1].kwargs == {"user": "account-A"}
    form_login.assert_called_once_with(driver, "account-A", "password-A")
    driver.quit.assert_called_once()
