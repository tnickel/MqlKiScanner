"""Hard stops retain current findings without permitting further network work."""
import json
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from mqlkiscanner import db, pipeline
from mqlkiscanner.mql5.ratelimit import Mql5HardStopError
from mqlkiscanner.mql5.session import Mql5Session
from test_review15_reports import live_reports as live_reports


@pytest.mark.parametrize("fail_at", ["stats", "export"])
def test_direct_http403_invalidates_current_catalog_and_preserves_exception_result(live_reports, monkeypatch, fail_at):
    pipe, _, scan = live_reports
    first = scan()
    assert first.persisted_this_run
    pipe.run_llm([first], lambda _: None)
    old_report = first.gesamtbericht
    session = Mql5Session()
    response = requests.Response()
    response.status_code = 403
    session.http.get = Mock(return_value=response)
    session.limiter.wait = Mock()

    def actual_http403(*args, **kwargs):
        session.get("/en/signals/123/export/history")

    stats = Mock(side_effect=actual_http403) if fail_at == "stats" else Mock(return_value={
        "dd_equity_pct": 95, "monthly_growth_pct": 10,
    })
    exporter = Mock(side_effect=actual_http403)
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats", stats)
    monkeypatch.setattr(pipeline.exporter, "export_positions", exporter)
    fallback = Mock(side_effect=AssertionError("Hard stop must not start Chrome"))
    monkeypatch.setattr("mqlkiscanner.mql5.browser_session.export_positions_via_browser", fallback)
    with pytest.raises(Mql5HardStopError, match="HTTP 403") as caught:
        pipe.analyze_candidate(session, {"id": 123, "name": "Example", "platform": "MT4"}, lambda _: None)
    failed = caught.value.result
    assert failed.id == 123 and failed.persisted_this_run
    assert not failed.forensik_vorhanden and "HTTP 403" in failed.fehler
    stats.assert_called_once()
    assert exporter.call_count == (1 if fail_at == "export" else 0)
    session.http.get.assert_called_once()
    fallback.assert_not_called()
    loaded = pipeline.results_from_db(pipe.settings)[0]
    assert not loaded.forensik_vorhanden and not loaded.persisted_this_run
    assert not loaded.gesamtbericht and loaded.bericht_hinweis
    assert loaded.ampel != "🟢" and "HTTP 403" in loaded.fehler
    if fail_at == "export":
        assert failed.dd_equity_pct == loaded.dd_equity_pct == 95
    assert db.get_latest_analysis(123, "gesamtbericht")["text"] == old_report
    archive = pipeline.ScanPipeline.save_run([failed], {})
    saved = json.loads(Path(archive).read_text(encoding="utf8"))["ergebnisse"]
    assert len(saved) == 1 and "HTTP 403" in saved[0]["fehler"]


def test_hard_stop_storage_failure_keeps_error_result_and_old_atomic_snapshot(live_reports, monkeypatch):
    pipe, _, scan = live_reports
    first = scan()
    before = db.list_catalog()
    stop = Mql5HardStopError("HTTP 403")
    export = Mock(side_effect=stop)
    store = Mock(side_effect=sqlite3.OperationalError("database is locked"))
    monkeypatch.setattr(pipeline.exporter, "export_positions", export)
    monkeypatch.setattr(db, "store_scan_result", store)
    with pytest.raises(Mql5HardStopError) as caught:
        pipe.analyze_candidate(None, {"id": first.id, "name": first.name}, lambda _: None)
    assert caught.value is stop
    result = caught.value.result
    assert not result.persisted_this_run and not result.forensik_vorhanden
    assert "HTTP 403" in result.fehler and "database is locked" in result.fehler
    assert db.list_catalog() == before
    export.assert_called_once()
    store.assert_called_once()


def test_first_scan_hard_stop_creates_visible_failed_signal(live_reports, monkeypatch):
    pipe, _, _ = live_reports
    assert db.list_catalog() == []
    monkeypatch.setattr(pipeline.exporter, "export_positions",
                        Mock(side_effect=Mql5HardStopError("HTTP 403")))
    with pytest.raises(Mql5HardStopError) as caught:
        pipe.analyze_candidate(None, {"id": 124, "name": "New"}, lambda _: None)
    assert caught.value.result.id == 124 and caught.value.result.persisted_this_run
    result = pipeline.results_from_db(pipe.settings)[0]
    assert result.id == 124 and result.dd_equity_pct == 5
    assert result.fehler and not result.forensik_vorhanden


@pytest.mark.parametrize("retry_outcome", ["scan", "hard_stop"])
def test_retry_keeps_actual_first_write_when_second_write_fails(live_reports, monkeypatch, retry_outcome):
    pipe, path, _ = live_reports
    second = ((str(path), False) if retry_outcome == "scan" else Mql5HardStopError("HTTP 403"))
    export = Mock(side_effect=[ValueError("transient export error"), second])
    monkeypatch.setattr(pipeline.exporter, "export_positions", export)
    original = db.store_scan_result
    calls = []

    def store(*args, **kwargs):
        calls.append(args[0])
        if len(calls) == 2:
            raise sqlite3.OperationalError("second write failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(db, "store_scan_result", store)
    if retry_outcome == "hard_stop":
        with pytest.raises(Mql5HardStopError) as caught:
            pipe.analyze_candidate(None, {"id": 123, "name": "Example"}, lambda _: None)
        result = caught.value.result
    else:
        result = pipe.analyze_candidate(None, {"id": 123, "name": "Example"}, lambda _: None)
    assert result.persisted_this_run and "second write failed" in result.fehler
    assert len(calls) == export.call_count == 2
    loaded = pipeline.results_from_db(pipe.settings)[0]
    assert "transient export error" in loaded.fehler and not loaded.forensik_vorhanden
