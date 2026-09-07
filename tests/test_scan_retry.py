"""Ein Retry je Signal, mit echten Ergebnis-/DB-Pfaden und ohne Netzwerk."""
import json
from unittest.mock import Mock

import pytest
import requests

from mqlkiscanner import db, pipeline
from mqlkiscanner.mql5.ratelimit import Mql5HardStopError, Mql5ThrottleError
from mqlkiscanner.mql5.session import Mql5Session


@pytest.fixture
def scan(monkeypatch, tmp_path):
    csv = tmp_path / "trades.csv"
    csv.write_text(
        "Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;Profit;Comment\n"
        "2024.01.01 10:00:00;Buy;0.01;XAUUSD;2000;1990;2010;2024.01.01 11:00:00;2001;0;0;1;\n"
        "2024.01.02 10:00:00;Buy;0.01;XAUUSD;2000;1990;2010;2024.01.02 11:00:00;1999;0;0;-1;\n",
        encoding="utf-8",
    )
    export = Mock(return_value=(str(csv), False))
    monkeypatch.setattr(pipeline.exporter, "export_positions", export)
    stats = Mock(return_value={"dd_equity_pct": 5, "monthly_growth_pct": 10})
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats", stats)
    monkeypatch.setattr(pipeline.time, "sleep", Mock())
    return pipeline.ScanPipeline(), stats, export


def test_retry_recovers_and_clears_persisted_error(scan):
    pipe, stats, export = scan
    stats.side_effect = [ConnectionError("temporary"), stats.return_value]
    logs = []
    result = pipe.analyze_candidate(None, {"id": 1}, logs.append)
    assert stats.call_count == 2
    assert export.call_count == 1
    assert result.forensik_vorhanden and not result.fehler
    stored = json.loads(db.get_signal(1)["stats_json"])
    assert stored["last_fehler"] is None and stored["forensik_ok"]
    assert any("Wiederholung erfolgreich" in line for line in logs)


def test_persistent_failure_stops_after_two_attempts(scan):
    pipe, stats, _ = scan
    stats.side_effect = ValueError("bad data")
    result = pipe.analyze_candidate(None, {"id": 1}, lambda _: None)
    assert stats.call_count == 2
    assert result.fehler == "ValueError: bad data"
    assert json.loads(db.get_signal(1)["stats_json"])["last_fehler"] == result.fehler


def test_success_is_not_repeated(scan):
    pipe, stats, _ = scan
    result = pipe.analyze_candidate(None, {"id": 1}, lambda _: None)
    assert result.forensik_vorhanden and not result.fehler
    assert stats.call_count == 1


@pytest.mark.parametrize("error", [Mql5HardStopError("stop"), Mql5ThrottleError("drosselt weiter")])
def test_hard_stop_is_not_retried(scan, error):
    pipe, stats, _ = scan
    pipe.fail_fast_after = 1
    stats.side_effect = error
    with pytest.raises(Mql5HardStopError):
        pipe.analyze_candidate(None, {"id": 1}, lambda _: None)
    assert stats.call_count == 1


def test_stop_during_pause_prevents_retry(scan):
    pipe, stats, _ = scan
    stats.side_effect = ValueError("temporary")
    stop = Mock(side_effect=[False, True])
    result = pipe.analyze_candidate(None, {"id": 1}, lambda _: None, should_stop=stop)
    assert result.fehler
    assert stats.call_count == 1


def test_export_hard_stop_bypasses_browser_and_retry(scan, monkeypatch):
    pipe, stats, export = scan
    export.side_effect = Mql5HardStopError("HTTP 403")
    browser = Mock(side_effect=AssertionError("Hard stop must not launch Chrome"))
    monkeypatch.setattr(
        "mqlkiscanner.mql5.browser_session.export_positions_via_browser", browser)
    with pytest.raises(Mql5HardStopError):
        pipe.analyze_candidate(None, {"id": 1}, lambda _: None)
    assert stats.call_count == 1 and export.call_count == 1
    browser.assert_not_called()


@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
def test_csv_bom_overrides_incorrect_http_charset(monkeypatch, bom):
    session = Mql5Session({})
    monkeypatch.setattr(session, "ensure_session_for_export", lambda: None)
    response = requests.Response()
    response.status_code = 200
    response._content = bom + b"Time;Type;Volume\n"
    response.encoding = "ISO-8859-1"
    get = Mock(return_value=response)
    monkeypatch.setattr(session, "get", get)
    assert session.export_positions_csv(2320903, platform="MT4") == "Time;Type;Volume\n"
    assert get.call_count == 1
    assert get.call_args.args[0].endswith("/history")
