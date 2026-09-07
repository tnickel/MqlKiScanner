"""Regressionen für synchrone Sitzungsstände, Render-Snapshots und Stop."""
import threading
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT, warte_auf_lauf
from mqlkiscanner import app_ui, db, pipeline, secrets_store


def scan_page():
    return AppTest.from_file(str(ROOT / "app_pages/scan.py"), default_timeout=30)


@pytest.mark.parametrize("fails", [False, True])
def test_reconnected_session_receives_invalidated_selection(fails, monkeypatch):
    release = threading.Event()

    def crawl(*args, **kwargs):
        assert release.wait(10)
        if fails:
            raise ValueError("crawl failed")
        return [{"id": 456}]

    monkeypatch.setattr(pipeline.ScanPipeline, "crawl", crawl)
    analyze = Mock(side_effect=AssertionError("old candidate must not run"))
    monkeypatch.setattr(pipeline.ScanPipeline, "analyze_candidate", analyze)
    first = scan_page().run()
    try:
        first.button(key="step_btn_listen").click().run()
        second = scan_page()
        second.session_state["scan_candidates"] = [{"id": 123}]
        second.session_state["scan_signals"] = [{"id": 123}]
        second.run()
        assert second.session_state["scan_candidates"] == []
    finally:
        release.set()
        first.session_state["scan_thread"].join(10)
    warte_auf_lauf(first)
    second.run()
    assert second.session_state["scan_signals"] == ([] if fails else [{"id": 456}])
    second.button(key="step_btn_forensik").click().run()
    warte_auf_lauf(second)
    assert not second.exception and not analyze.called


def test_results_page_receives_completed_worker_without_scan_revisit(monkeypatch):
    release, entered = threading.Event(), threading.Event()
    monkeypatch.setattr(secrets_store, "get_secret", lambda key: "dummy")

    def portfolio(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return {"text": "COMPLETED_PORTFOLIO", "reason": "", "model": "mock"}

    monkeypatch.setattr(pipeline.ScanPipeline, "run_portfolio", portfolio)
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30).run()
    at.session_state["scan_results"] = [pipeline.ScanResult(id=123, forensik_vorhanden=True)]
    at.run()
    try:
        at.button(key="step_btn_portfolio").click().run()
        assert entered.wait(5)
        worker = at.session_state["scan_thread"]
        at.switch_page("app_pages/ergebnisse.py").run()
    finally:
        release.set()
        worker.join(10)
    at.selectbox(key="results_run").set_value("Aktuelle Sitzung").run()
    assert not at.exception
    assert at.session_state["portfolio_bericht"] == "COMPLETED_PORTFOLIO"
    assert any("COMPLETED_PORTFOLIO" in item.value for item in at.markdown)
    assert at.session_state["last_run_file"]


def test_table_uses_one_snapshot_when_worker_appends(monkeypatch):
    ready, appended = threading.Event(), threading.Event()
    rows = [pipeline.ScanResult(id=123)]
    original = app_ui.results_to_dataframe

    def pause_after_frame(*args, **kwargs):
        frame = original(*args, **kwargs)
        ready.set()
        assert appended.wait(5)
        return frame

    monkeypatch.setattr(app_ui, "results_to_dataframe", pause_after_frame)

    def append():
        assert ready.wait(5)
        rows.append(pipeline.ScanResult(id=456))
        appended.set()

    worker = threading.Thread(target=append)
    worker.start()
    at = AppTest.from_string(
        "import streamlit as st\nfrom mqlkiscanner.app_ui import render_results_table\n"
        "render_results_table(st.session_state['rows'])", default_timeout=15)
    at.session_state["rows"] = rows
    at.run()
    worker.join(5)
    assert not at.exception
    assert list(at.dataframe[0].value["ID"]) == [123]
    assert len(rows) == 2


def test_stop_after_list_does_not_start_login_or_later_work(monkeypatch):
    from mqlkiscanner.mql5 import browser_session
    release, entered = threading.Event(), threading.Event()
    monkeypatch.setattr(secrets_store, "get_secret", lambda key: "dummy")

    def crawl(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return [{"id": 9001234, "wochen": 100, "abonnenten": 100}]

    monkeypatch.setattr(pipeline.ScanPipeline, "crawl", crawl)
    login = Mock(side_effect=AssertionError("login after stop"))
    monkeypatch.setattr(browser_session, "ensure_mql5_cookies", login)
    at = scan_page().run()
    try:
        at.button(key="scan_start").click().run()
        assert entered.wait(5)
        at.button(key="scan_stop").click().run()
    finally:
        release.set()
        at.session_state["scan_thread"].join(10)
    warte_auf_lauf(at)
    assert not at.exception and not login.called
    workflow = at.session_state["scan_workflow"]
    assert workflow["status"] == "warning"
    assert all(workflow["steps"][sid]["status"] == "skipped"
               for sid in ("kandidaten", "forensik", "llm", "portfolio"))


def test_database_portfolio_is_explicitly_a_historical_report():
    db.init_db()
    db.store_analysis(None, "portfolio", "mock", 1, "Historical portfolio")
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30).run()
    at.switch_page("app_pages/ergebnisse.py").run()
    assert not at.exception
    assert any("historischer Stand" in item.value for item in at.subheader)
    assert any("nicht mit den aktuellen Katalogbewertungen abgeglichen" in item.value
               for item in at.info)
