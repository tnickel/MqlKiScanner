"""Regressionen für Demo-Isolation, Export-Abbruch, KI und Laufarchive."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from mqlkiscanner import config, db, pipeline
from mqlkiscanner.llm.client import GlmClient, LlmError, LlmIncompleteResponseError
from mqlkiscanner.mql5.ratelimit import Mql5HardStopError, Mql5ThrottleError


def _response(text="Bericht vollständig", finish="stop"):
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps({
        "choices": [{"message": {"content": text}, "finish_reason": finish}],
        "usage": {"total_tokens": 25, "prompt_tokens": 10, "completion_tokens": 15},
    }).encode()
    return response


def test_demo_does_not_replace_live_drawdown_or_import_live_reports():
    db.init_db()
    sid = 2342895
    db.upsert_signal(sid, name="Live", platform="MT5",
                     stats={"eq_dd_pct": 39, "forensik_ok": True})
    db.store_forensik(sid, {"score": 8, "trading_dd": {"pct": 39}})
    db.store_analysis(sid, "gesamtbericht", "test", 0, "Live-Bericht")
    before = db.list_catalog()
    raw = config.RAW_DIR / "kiracat_2342895_positions.csv"
    demo = pipeline.ScanPipeline.analyze_local_files([str(raw)])[0]
    assert demo.source_kind == "demo"
    assert not demo.gesamtbericht
    assert db.list_catalog() == before
    live = pipeline.results_from_db()[0]
    assert live.dd_equity_pct == 39 and live.schranke_verletzt


def test_demo_never_creates_ki_or_portfolio_requests():
    pipe = pipeline.ScanPipeline()
    pipe.llm = SimpleNamespace(has_key=True, chat=Mock(), usage=SimpleNamespace(total_tokens=0))
    demo = pipeline.ScanResult(id=123, source_kind="demo", forensik_vorhanden=True)
    assert pipe.run_llm([demo], lambda _: None)["total"] == 0
    assert not pipe.run_portfolio([demo], lambda _: None)["text"]
    pipe.llm.chat.assert_not_called()


def test_old_csv_catalog_entry_is_identified_as_demo():
    db.init_db()
    db.upsert_signal(123, platform="CSV", stats={"forensik_ok": True})
    db.store_forensik(123, {"score": 2})
    assert pipeline.results_from_db()[0].source_kind == "demo"


@pytest.mark.parametrize("browser_error", [
    "MQL5 Browser-Login fehlgeschlagen", "Kein History-Export-Link", "target window already closed",
])
def test_public_stats_success_does_not_reset_export_fail_fast(monkeypatch, browser_error):
    from mqlkiscanner.mql5 import browser_session
    pipe = pipeline.ScanPipeline({"mql5_fail_fast_after": 3})
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats", lambda *_: {})
    export = Mock(side_effect=Mql5ThrottleError("HTTP 429"))
    monkeypatch.setattr(pipeline.exporter, "export_positions", export)
    monkeypatch.setattr(browser_session, "export_positions_via_browser",
                        Mock(side_effect=RuntimeError(browser_error)))
    monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)
    first = pipe.analyze_candidate(None, {"id": 123}, lambda _: None)
    assert first.fehler and pipe._mql5_hard_fails == 2
    with pytest.raises(Mql5HardStopError):
        pipe.analyze_candidate(None, {"id": 124}, lambda _: None)
    assert export.call_count == 3


def test_client_retries_transport_failure_once(monkeypatch):
    client = GlmClient("m1", "m2")
    monkeypatch.setattr(client, "_headers", lambda: {})
    monkeypatch.setattr("mqlkiscanner.llm.client.time.sleep", lambda _: None)
    post = Mock(side_effect=[requests.Timeout("timeout"), _response()])
    monkeypatch.setattr("mqlkiscanner.llm.client.requests.post", post)
    assert client.chat("prompt") == "Bericht vollständig"
    assert post.call_count == 2


def test_exhausted_network_retry_marks_signal_and_continues(monkeypatch):
    pipe = pipeline.ScanPipeline()
    monkeypatch.setattr("mqlkiscanner.secrets_store.get_secret", lambda _: "dummy")
    monkeypatch.setattr("mqlkiscanner.llm.client.time.sleep", lambda _: None)
    monkeypatch.setattr(pipeline.llm_prompts, "load_prompt", lambda _: "{kandidat_json}")
    calls = []

    def post(*args, **kwargs):
        content = json.loads(kwargs["data"])["messages"][-1]["content"]
        calls.append(content)
        if '"id": 123' in content:
            raise requests.Timeout("simulated timeout")
        return _response()

    monkeypatch.setattr("mqlkiscanner.llm.client.requests.post", post)
    db.init_db()
    results = [pipeline.ScanResult(id=sid, forensik_vorhanden=True) for sid in (123, 124)]
    summary = pipe.run_llm(results, lambda _: None)
    assert results[0].llm_fehler and "2 Versuchen" in results[0].llm_fehler
    assert results[1].gesamtbericht == "Bericht vollständig"
    assert summary["completed"] == 3
    assert len(calls) == 7  # 2 x 2 failed parallel calls, then 3 successful calls.
    assert db.get_latest_analysis(123, "gesamtbericht") is None


def test_truncated_summary_is_not_saved_as_complete(monkeypatch):
    pipe = pipeline.ScanPipeline()
    monkeypatch.setattr("mqlkiscanner.secrets_store.get_secret", lambda _: "dummy")
    monkeypatch.setattr(pipeline.llm_prompts, "load_prompt", lambda key: key)

    def post(*args, **kwargs):
        prompt = json.loads(kwargs["data"])["messages"][-1]["content"]
        return _response("Urteil: EMPFEH", "length") if prompt == "gesamtbericht" else _response()

    monkeypatch.setattr("mqlkiscanner.llm.client.requests.post", post)
    db.init_db()
    result = pipeline.ScanResult(id=123, forensik_vorhanden=True)
    summary = pipe.run_llm([result], lambda _: None)
    assert summary["completed"] == 2 and summary["failed"] == 1
    assert "Unvollständige Antwort" in result.llm_fehler
    assert not result.gesamtbericht
    assert db.get_latest_analysis(123, "gesamtbericht") is None
    assert pipe.llm.usage.total_tokens == 75  # Truncated output still used tokens.


def test_archives_do_not_collide_even_with_identical_clock(monkeypatch):
    from datetime import datetime
    clock = Mock()
    clock.now.return_value = datetime(2026, 9, 7, 12)
    monkeypatch.setattr(pipeline, "datetime", clock)
    a = pipeline.ScanPipeline.save_run([pipeline.ScanResult(id=1)], {"scan": ["first"]})
    b = pipeline.ScanPipeline.save_run([pipeline.ScanResult(id=2)], {"scan": ["second"]})
    assert a != b
    assert json.loads(Path(a).read_text(encoding="utf8"))["logs"]["scan"] == ["first"]
    assert json.loads(Path(b).read_text(encoding="utf8"))["ergebnisse"][0]["id"] == 2
    assert not list(config.RUNS_DIR.rglob("*.tmp"))


def test_failed_atomic_write_never_exposes_partial_results(monkeypatch):
    monkeypatch.setattr(pipeline.os, "replace", Mock(side_effect=OSError("disk error")))
    with pytest.raises(OSError):
        pipeline.ScanPipeline.save_run([pipeline.ScanResult(id=1)], {})
    assert not list(config.RUNS_DIR.rglob("results.json"))
    assert not list(config.RUNS_DIR.rglob("*.tmp"))
