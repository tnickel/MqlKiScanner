"""Cache recovery and login safeguards, with isolated files and mocked HTTP/Chrome."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
import requests

from mqlkiscanner import pipeline, secrets_store
from mqlkiscanner.mql5 import browser_session, exporter
from mqlkiscanner.mql5.errors import Mql5CredentialsMissingError
from mqlkiscanner.mql5.ratelimit import Mql5HardStopError, Mql5ThrottleError
from mqlkiscanner.mql5.session import Mql5Session
from mqlkiscanner.parser import load_export


HEADER = "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
GOOD = (HEADER + "2025.12.31 00:00:00;Balance;;;;;;;;;1000\n"
        "2026.01.01 00:00:00;Buy;0.1;XAUUSD;2000;0.1;2026.01.01 01:00:00;2001;0;0;10\n")
BAD = HEADER + "2026.01.01 00:00:00;Buy;0.1;XAUUSD;2000;0.1;2026.01.01 01:00:00;2001;0;0\n"


@pytest.fixture
def isolated_exports(tmp_path, monkeypatch):
    trades = tmp_path / "exports"
    trades.mkdir()
    monkeypatch.setattr(exporter, "TRADES_DIR", trades)
    monkeypatch.setattr(browser_session, "TRADES_DIR", trades)
    monkeypatch.setattr(browser_session, "DOWNLOAD_DIR", trades / "download")
    return trades


def test_invalid_existing_cache_is_replaced_on_next_request(isolated_exports):
    path = isolated_exports / "123_positions.csv"
    path.write_text(BAD, encoding="utf8")
    remote = Mock(return_value=GOOD)
    result, cached = exporter.export_positions(SimpleNamespace(export_positions_csv=remote), 123)
    assert result == str(path) and not cached
    assert len(load_export(result).trades) == 1
    assert remote.call_count == 1


def test_new_bad_download_cannot_poison_retry_cache(isolated_exports):
    session = SimpleNamespace(export_positions_csv=Mock(side_effect=[BAD, GOOD]))
    with pytest.raises(ValueError, match="10 statt 11"):
        exporter.export_positions(session, 123)
    assert list(isolated_exports.iterdir()) == []
    path, cached = exporter.export_positions(session, 123)
    assert not cached and len(load_export(path).trades) == 1
    assert session.export_positions_csv.call_count == 2


def test_pipeline_retry_fetches_recovered_csv(isolated_exports, monkeypatch):
    remote = Mock(side_effect=[BAD, GOOD])
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats",
                        lambda *_: {"dd_equity_pct": 5, "monthly_growth_pct": 10})
    monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)
    result = pipeline.ScanPipeline().analyze_candidate(
        SimpleNamespace(export_positions_csv=remote), {"id": 123}, lambda _: None)
    assert not result.fehler and result.forensik_vorhanden
    assert remote.call_count == 2


def test_semantic_forensics_problem_does_not_invalidate_csv(isolated_exports):
    # Unknown contract is a forensic limitation, not a corrupt download.
    session = SimpleNamespace(export_positions_csv=Mock(return_value=GOOD.replace("XAUUSD", "CUSTOM")))
    exporter.export_positions(session, 123)
    path, cached = exporter.export_positions(session, 123)
    assert cached and load_export(path).trades[0].symbol == "CUSTOM"
    assert session.export_positions_csv.call_count == 1


@pytest.mark.parametrize("failure", ["invalid", "replace"])
def test_failed_refresh_preserves_previous_valid_cache(isolated_exports, monkeypatch, failure):
    path = isolated_exports / "123_positions.csv"
    path.write_text(GOOD, encoding="utf8")
    if failure == "replace":
        monkeypatch.setattr(exporter.os, "replace", Mock(side_effect=OSError("disk error")))
    session = SimpleNamespace(export_positions_csv=Mock(return_value=BAD if failure == "invalid" else GOOD))
    with pytest.raises(ValueError if failure == "invalid" else OSError):
        exporter.export_positions(session, 123, cache_stunden=0)
    assert path.read_text(encoding="utf8") == GOOD
    assert list(isolated_exports.iterdir()) == [path]


def test_browser_download_is_validated_before_cache_replacement(isolated_exports, monkeypatch):
    import selenium.webdriver.support.ui

    target = isolated_exports / "123_positions.csv"
    target.write_text(GOOD, encoding="utf8")
    monkeypatch.setattr(secrets_store, "get_secret", lambda _: "dummy")
    monkeypatch.setattr(browser_session.time, "sleep", lambda _: None)
    driver = Mock()
    driver.find_elements.side_effect = lambda by, query: [] if by == "id" else [Mock()]

    def download(*_):
        (browser_session.DOWNLOAD_DIR / "new.csv").write_text(BAD, encoding="utf8")

    driver.execute_script.side_effect = download
    monkeypatch.setattr(browser_session, "_start_driver", Mock(return_value=driver))
    monkeypatch.setattr(selenium.webdriver.support.ui, "WebDriverWait",
                        lambda *_: SimpleNamespace(until=lambda _: Mock()))
    with pytest.raises(ValueError, match="10 statt 11"):
        browser_session.export_positions_via_browser(123)
    assert target.read_text(encoding="utf8") == GOOD
    assert not list(browser_session.DOWNLOAD_DIR.iterdir())
    driver.quit.assert_called_once()


def response(status, text=""):
    result = requests.Response()
    result.status_code = status
    result._content = text.encode("utf8")
    return result


@pytest.fixture
def logged_session(monkeypatch):
    monkeypatch.setattr(secrets_store, "get_secret", lambda _: "dummy")
    session = Mql5Session({"rate_backoff_429_s": 2})
    session.logged_in = True
    monkeypatch.setattr(session.limiter, "wait", Mock())
    return session


def test_login_check_403_stops_before_browser(logged_session, monkeypatch):
    monkeypatch.setattr(logged_session.http, "get", Mock(return_value=response(403, "Forbidden")))
    browser = Mock()
    monkeypatch.setattr(browser_session, "ensure_mql5_cookies", browser)
    with pytest.raises(Mql5HardStopError, match="HTTP 403"):
        logged_session.ensure_session_for_export()
    browser.assert_not_called()


@pytest.mark.parametrize("status", [429, 503])
def test_login_check_recovers_after_shared_backoff(logged_session, monkeypatch, status):
    get = Mock(side_effect=[response(status), response(200, '<a href="/en/auth_logout">Logout</a>')])
    monkeypatch.setattr(logged_session.http, "get", get)
    sleep = Mock()
    monkeypatch.setattr("mqlkiscanner.mql5.session.time.sleep", sleep)
    assert logged_session.is_logged_in()
    assert get.call_count == 2
    assert sleep.call_args_list == [call(2)]


def test_persistent_login_throttle_propagates_without_browser(logged_session, monkeypatch):
    monkeypatch.setattr(logged_session.http, "get", Mock(return_value=response(429)))
    monkeypatch.setattr("mqlkiscanner.mql5.session.time.sleep", Mock())
    browser = Mock()
    monkeypatch.setattr(browser_session, "ensure_mql5_cookies", browser)
    with pytest.raises(Mql5ThrottleError):
        logged_session.ensure_session_for_export()
    assert logged_session.http.get.call_count == 3
    browser.assert_not_called()


@pytest.mark.parametrize("entrypoint", ["http", "browser_login", "browser_export"])
def test_missing_credentials_raise_typed_outcome_before_chrome(monkeypatch, entrypoint):
    monkeypatch.setattr(secrets_store, "get_secret", lambda _: "")
    start = Mock()
    monkeypatch.setattr(browser_session, "_start_driver", start)
    with pytest.raises(Mql5CredentialsMissingError):
        if entrypoint == "http":
            Mql5Session().ensure_session_for_export()
        elif entrypoint == "browser_login":
            browser_session._login_via_browser({}, Mql5Session())
        else:
            browser_session.export_positions_via_browser(123)
    start.assert_not_called()


def test_missing_login_gives_clean_pipeline_precheck(isolated_exports, monkeypatch):
    monkeypatch.setattr(secrets_store, "get_secret", lambda _: "")
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats",
                        lambda *_: {"dd_equity_pct": 5, "monthly_growth_pct": 10})
    browser = Mock()
    monkeypatch.setattr(browser_session, "_start_driver", browser)
    result = pipeline.ScanPipeline().analyze_candidate(Mql5Session(), {"id": 123}, lambda _: None)
    assert not result.fehler and not result.forensik_vorhanden
    assert result.dd_equity_pct == 5 and result.ertrag_monat_pct == 10
    browser.assert_not_called()
