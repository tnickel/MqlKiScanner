"""Prozess-Worker überlebt neue Sitzungen, ohne parallele Workflows zuzulassen."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT, warte_auf_lauf
from mqlkiscanner import pipeline, scan_worker


def page():
    return AppTest.from_file(str(ROOT / "app_pages/scan.py"), default_timeout=30)


def test_new_session_reconnects_and_cannot_start_another_worker(monkeypatch):
    release = threading.Event()
    calls = []

    def crawl(*args, **kwargs):
        calls.append(threading.get_ident())
        assert release.wait(10)
        return [{"id": 123}]

    monkeypatch.setattr(pipeline.ScanPipeline, "crawl", crawl)
    first = page().run()
    second = None
    try:
        first.button(key="step_btn_listen").click().run()
        worker = first.session_state["scan_thread"]
        second = page()
        # Simuliert einen bereits gesendeten Start aus einer neuen Sitzung.
        second.session_state["scan_command"] = {"mode": "step_listen", "settings": None}
        second.run()
        assert not second.exception
        assert second.session_state["scan_thread"] is worker
        assert second.button(key="scan_start").disabled
        assert second.button(key="step_btn_listen").disabled
        assert len(calls) == 1
        assert any("wieder verbunden" in item.value for item in second.info)
        second.button(key="scan_stop").click().run()
        assert first.session_state["scan_control"]["stop"] is True
    finally:
        release.set()
        worker = first.session_state["scan_thread"]
        worker.join(10)
    warte_auf_lauf(first)
    assert second is not None
    second.run()  # Auch nach Übernahme durch Sitzung 1 separat übernehmen.
    assert first.session_state["scan_signals"] == second.session_state["scan_signals"] == [{"id": 123}]
    assert not second.button(key="scan_start").disabled
    assert scan_worker.active_run() is None


def test_atomic_guard_allows_only_one_simultaneous_start():
    release = threading.Event()
    gate = threading.Barrier(4)

    def contender():
        gate.wait(5)
        return scan_worker.start(lambda: release.wait(10), workflow={}, control={}, logs={}, results=[])

    runs = []
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            runs = list(pool.map(lambda _: contender(), range(4)))
        assert len([run for run in runs if run is not None]) == 1
    finally:
        release.set()
        for run in runs:
            if run is not None:
                run.thread.join(10)
    assert scan_worker.active_run() is None


def test_thread_start_failure_releases_guard(monkeypatch):
    with monkeypatch.context() as patch:
        def fail_start(self):
            raise RuntimeError("cannot start thread")
        patch.setattr(threading.Thread, "start", fail_start)
        with pytest.raises(RuntimeError, match="cannot start"):
            scan_worker.start(lambda: None, workflow={}, control={}, logs={}, results=[])
    assert scan_worker.active_run() is None
    next_run = scan_worker.start(lambda: None, workflow={}, control={}, logs={}, results=[])
    assert next_run is not None
    next_run.thread.join(10)
    assert scan_worker.active_run() is None


def test_worker_failure_releases_guard_for_next_session(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("crawl failed")
    monkeypatch.setattr(pipeline.ScanPipeline, "crawl", fail)
    at = page().run()
    at.button(key="step_btn_listen").click().run()
    warte_auf_lauf(at)
    assert at.session_state["scan_workflow"]["status"] == "error"
    assert scan_worker.active_run() is None
    new_session = page().run()
    assert not new_session.button(key="scan_start").disabled
