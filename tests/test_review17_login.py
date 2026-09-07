"""Rejected reauthentication must reach the existing counted fail-fast path."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mqlkiscanner import config, db, pipeline
from mqlkiscanner.mql5 import browser_session as browser, exporter
from mqlkiscanner.mql5.errors import Mql5AuthenticationError, Mql5CredentialsMissingError
from mqlkiscanner.mql5.ratelimit import Mql5HardStopError, is_hard_mql5_failure
from mqlkiscanner.mql5.session import Mql5Session


@pytest.fixture
def login_env(tmp_path, monkeypatch):
    credentials = {"mql5_user": "account-B", "mql5_pass": "invalid", "glm_api_key": ""}
    monkeypatch.setattr(browser.secrets_store, "get_secret", credentials.__getitem__)
    monkeypatch.setattr(config, "load_known_signals", lambda: {})
    for attribute, suffix in {
        "COOKIE_FILE": "cookies.json", "PROFILE_DIR": "profile",
        "TRADES_DIR": "trades", "DOWNLOAD_DIR": "download",
    }.items():
        monkeypatch.setattr(browser, attribute, tmp_path / suffix)
    monkeypatch.setattr(exporter, "TRADES_DIR", tmp_path / "trades")
    monkeypatch.setattr(browser.time, "sleep", lambda _: None)
    monkeypatch.setattr(browser, "_start_driver", Mock(side_effect=AssertionError("real Chrome forbidden")))
    return credentials


def rejected_browser(monkeypatch):
    driver = Mock(current_url="https://www.mql5.com/en/auth_login")
    driver.find_elements.return_value = [object()]
    start = Mock(return_value=driver)
    monkeypatch.setattr(browser, "_start_driver", start)
    # Simulate a submitted form that the remote site has rejected.
    monkeypatch.setattr(browser, "_driver_login", Mock())
    return driver, start


@pytest.mark.parametrize("prior_user", [None, "account-A", "account-B"])
def test_initial_changed_or_expired_account_rejection_is_typed(login_env, monkeypatch, prior_user):
    driver, start = rejected_browser(monkeypatch)
    session = Mql5Session()
    session.logged_in = prior_user is not None
    session._authenticated_user = prior_user
    session.http.cookies.set("session", "old", domain=".mql5.com")
    monkeypatch.setattr(session, "is_logged_in", lambda: False)
    with pytest.raises(Mql5AuthenticationError, match="Anmeldung im Browser nicht akzeptiert") as caught:
        session.ensure_session_for_export()
    assert isinstance(caught.value, RuntimeError)
    assert is_hard_mql5_failure(caught.value)
    assert not session.logged_in and session._authenticated_user is None
    assert session.http.cookies.get_dict() == {}
    start.assert_called_once_with(user="account-B")
    driver.quit.assert_called_once()


def test_unconfirmed_cookie_check_preserves_bool_api_and_session_raises_typed(login_env, monkeypatch):
    driver = Mock(current_url="https://www.mql5.com/en")
    driver.find_elements.return_value = []
    driver.get_cookies.return_value = [{"name": "session", "value": "unconfirmed", "domain": ".mql5.com"}]
    monkeypatch.setattr(browser, "_start_driver", Mock(return_value=driver))
    monkeypatch.setattr(browser, "_driver_login", Mock())
    session = Mql5Session()
    monkeypatch.setattr(session, "is_logged_in", lambda: False)
    assert browser.ensure_mql5_cookies({}, session) is False
    assert not browser.COOKIE_FILE.exists()
    with pytest.raises(Mql5AuthenticationError, match="MQL5-Browser-Login fehlgeschlagen"):
        session.ensure_session_for_export()
    assert not session.logged_in


def test_forced_login_without_form_is_typed(login_env, monkeypatch):
    import selenium.webdriver.support.ui

    monkeypatch.setattr(selenium.webdriver.support.ui, "WebDriverWait",
                        lambda driver, _: SimpleNamespace(until=lambda predicate: predicate(driver)))
    driver = Mock(current_url="https://www.mql5.com/en")
    driver.find_elements.return_value = []
    with pytest.raises(Mql5AuthenticationError, match="neue Anmeldung nicht bestätigt"):
        browser._driver_login(driver, "account-B", "invalid", force_login=True)
    driver.delete_all_cookies.assert_called_once()


@pytest.mark.parametrize("link", ["__cause__", "__context__"])
def test_fallback_chain_retains_authentication_type_without_message_matching(link):
    original = Mql5AuthenticationError("localized text with no legacy keywords")
    fallback = RuntimeError("history unavailable")
    setattr(fallback, link, original)
    assert is_hard_mql5_failure(fallback)
    assert not is_hard_mql5_failure(RuntimeError("malformed CSV"))
    assert not is_hard_mql5_failure(Mql5CredentialsMissingError("not configured"))
    assert is_hard_mql5_failure(RuntimeError("MQL5-Browser-Login fehlgeschlagen"))


def test_rejected_reauthentication_stops_at_limit_despite_browser_fallback(login_env, monkeypatch):
    _, start = rejected_browser(monkeypatch)
    stats = Mock(return_value={})
    fallback = Mock(side_effect=RuntimeError("History unavailable"))
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats", stats)
    monkeypatch.setattr(browser, "export_positions_via_browser", fallback)
    session = Mql5Session()
    # The UI already passed its initial login check; the credentials changed
    # before the next uncached export of the running station.
    session.logged_in = True
    session._authenticated_user = "account-A"
    pipe = pipeline.ScanPipeline({"mql5_fail_fast_after": 3})
    attempted = []
    for signal_id in (100, 101, 102):
        attempted.append(signal_id)
        try:
            result = pipe.analyze_candidate(session, {"id": signal_id}, lambda _: None)
        except Mql5HardStopError as exc:
            assert exc.result.id == 101 and exc.result.fehler
            assert is_hard_mql5_failure(exc.__cause__)
            break
        assert result.id == 100 and result.fehler
        assert pipe._mql5_hard_fails == 2  # First attempt plus single retry.
    else:
        pytest.fail("scan continued beyond the configured authentication failure limit")
    assert attempted == [100, 101]
    assert pipe._mql5_hard_fails == 3
    assert stats.call_count == start.call_count == fallback.call_count == 3
    catalog = {row["signal_id"]: row for row in db.list_catalog()}
    assert set(catalog) == {100, 101}
    assert all(not row["stats"]["forensik_ok"] and row["stats"]["last_fehler"]
               for row in catalog.values())
