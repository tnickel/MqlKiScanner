"""Isolierte Regressionstests für Quellenbindung, Abbruch und Portfolio-Archive."""
import json
import threading
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT, warte_auf_lauf
from mqlkiscanner import config, db, pipeline, secrets_store


def page(name="scan"):
    return AppTest.from_file(str(ROOT / f"app_pages/{name}.py"), default_timeout=30)


def finish(at, key):
    at.button(key=key).click().run()
    warte_auf_lauf(at)
    assert not at.exception


@pytest.mark.parametrize("crawl_fails", [False, True])
def test_new_list_invalidates_old_selection_even_on_failure(monkeypatch, crawl_fails):
    crawl = Mock(side_effect=ValueError("offline") if crawl_fails else None,
                 return_value=[{"id": 456}])
    analyze = Mock(side_effect=AssertionError("old selection must not run"))
    monkeypatch.setattr(pipeline.ScanPipeline, "crawl", crawl)
    monkeypatch.setattr(pipeline.ScanPipeline, "analyze_candidate", analyze)
    at = page()
    at.session_state["scan_candidates"] = [{"id": 123}]
    at.session_state["scan_signals"] = [{"id": 123}]
    at.run()
    finish(at, "step_btn_listen")
    assert at.session_state["scan_candidates"] == []
    assert at.session_state["scan_signals"] == ([] if crawl_fails else [{"id": 456}])
    finish(at, "step_btn_forensik")
    assert not analyze.called
    assert at.session_state["scan_workflow"]["steps"]["forensik"]["status"] == "skipped"


def test_local_stop_preserves_one_result_and_skips_remaining_files(monkeypatch, tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for name in ("one.csv", "two.csv", "three.csv"):
        (raw / name).write_text("stub", encoding="utf-8")
    monkeypatch.setattr(config, "RAW_DIR", raw)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def analyze(files, *args):
        calls.extend(files)
        entered.set()
        assert release.wait(10)
        return [pipeline.ScanResult(id=123, name="demo", source_kind="demo",
                                    forensik_vorhanden=True)]

    monkeypatch.setattr(pipeline.ScanPipeline, "analyze_local_files", analyze)
    at = page().run()
    try:
        at.button(key="scan_verify").click().run()
        assert entered.wait(5)
        at.button(key="scan_stop").click().run()
    finally:
        release.set()
    warte_auf_lauf(at)
    assert not at.exception
    assert len(calls) == len(at.session_state["scan_results"]) == 1
    step = at.session_state["scan_workflow"]["steps"]["forensik"]
    assert (step["status"], step["done"], step["total"]) == ("warning", 1, 3)


@pytest.mark.parametrize("archived_portfolio", [None, {"text": "ARCHIVED_TEXT", "model": "old-model"}])
def test_archive_never_substitutes_latest_live_portfolio(archived_portfolio):
    db.init_db()
    db.store_analysis(0, "portfolio", "new-model", 1, "LIVE_TEXT")
    archive = config.RUNS_DIR / "old" / "results.json"
    archive.parent.mkdir()
    data = {"ergebnisse": [{"id": 123, "name": "historical"}]}
    if archived_portfolio is not None:
        data["portfolio"] = archived_portfolio
    archive.write_text(json.dumps(data), encoding="utf-8")
    at = page("ergebnisse").run()
    at.selectbox(key="results_run").set_value(str(archive)).run()
    assert not at.exception
    text = "\n".join(item.value for item in at.markdown)
    assert "LIVE_TEXT" not in text
    assert ("ARCHIVED_TEXT" in text) == (archived_portfolio is not None)


def test_portfolio_storage_warning_is_archived_and_shown_in_session(monkeypatch):
    monkeypatch.setattr(secrets_store, "get_secret", lambda key: "test-key")
    summary = {"text": "SESSION_TEXT", "model": "test-model", "tokens": 42,
               "created_at": "2026-09-07 12:00:00", "storage_error": "database is locked",
               "reason": "DB-Speicherung fehlgeschlagen"}
    monkeypatch.setattr(pipeline.ScanPipeline, "run_portfolio", lambda *a, **k: summary)
    at = page()
    at.session_state["scan_results"] = [pipeline.ScanResult(id=123, name="live", forensik_vorhanden=True)]
    at.run()
    finish(at, "step_btn_portfolio")
    assert at.session_state["scan_workflow"]["steps"]["portfolio"]["status"] == "warning"
    assert at.session_state["portfolio_result"] == summary
    archived = json.loads(open(at.session_state["last_run_file"], encoding="utf-8").read())
    assert archived["portfolio"] == summary
    assert any("database is locked" in item.value for item in at.warning)
    results = page("ergebnisse")
    results.session_state["scan_results"] = at.session_state["scan_results"]
    results.session_state["portfolio_result"] = summary
    results.run()
    results.selectbox(key="results_run").set_value("Aktuelle Sitzung").run()
    assert not results.exception
    assert any("SESSION_TEXT" in item.value for item in results.markdown)
    assert any("database is locked" in item.value for item in results.warning)
