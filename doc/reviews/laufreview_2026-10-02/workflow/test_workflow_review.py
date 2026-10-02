"""Isolated reproductions of the actual GUI worker and source selection.

Run with PYTHONPATH=src;tests and pytest pointing at this file. The imported
autouse fixture redirects storage to tmp_path and rejects all HTTP requests.
The worker AST is executed synchronously; no browser, process or model starts.
"""
from __future__ import annotations

import ast
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import isolated_app_storage
from test_review15_reports import live_reports
from mqlkiscanner import config, db, downloader_sync, fix_signale, pipeline, scan_state, scan_worker
from mqlkiscanner.agenten import lock, scan_launcher

ROOT = Path(__file__).resolve().parents[4]


class State(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class FakePipeline:
    calls = []
    candidates = []
    failed_results = False

    def __init__(self, settings=None, quelle="full"):
        self.llm = SimpleNamespace(has_key=False, usage=SimpleNamespace(total_tokens=0))

    def crawl(self, **kwargs):
        self.calls.append("crawl")
        return self.candidates.copy()

    def build_candidates(self, signals, log, begruendung=None):
        self.calls.append("build_candidates")
        if begruendung is not None:
            begruendung.extend(fix_signale.begruendungseintrag(s, "KANDIDAT", "fake")
                               for s in signals)
        return signals

    def analyze_candidate(self, session, candidate, log, should_stop=None):
        self.calls.append("analyze")
        return pipeline.ScanResult(id=candidate["id"], name=candidate["name"],
                                   forensik_vorhanden=not self.failed_results,
                                   fehler="Export failed" if self.failed_results else "")

    def kursdaten_beenden(self):
        self.calls.append("kursdaten_beenden")

    @staticmethod
    def save_run(results, logs, portfolio=None):
        return "isolated-results.json"


@pytest.fixture
def fake_pipeline(monkeypatch):
    FakePipeline.calls = []
    FakePipeline.candidates = []
    FakePipeline.failed_results = False
    monkeypatch.setattr(pipeline, "ScanPipeline", FakePipeline)
    monkeypatch.setattr(pipeline, "results_from_db", lambda cfg=None: [])
    monkeypatch.setattr(config, "load_known_signals", lambda: {})
    monkeypatch.setattr(downloader_sync, "konfiguriert", lambda: False)
    return FakePipeline


def gui_worker(monkeypatch, mode):
    """Extract the actual worker block, not a copy of its decision logic."""
    tree = ast.parse((ROOT / "app_pages/scan.py").read_text(encoding="utf-8"))
    worker_block = next(node for node in tree.body if isinstance(node, ast.If)
                        and isinstance(node.test, ast.Name) and node.test.id == "command"
                        and any(isinstance(child, ast.FunctionDef) and child.name == "_worker"
                                for child in node.body))
    helper_names = {"_new_workflow", "_stamped", "_station_kennzahlen"}
    helper_nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name in helper_names]
    captured = {}

    def capture(target, **kwargs):
        captured["target"] = target
        return SimpleNamespace(thread=None, **kwargs)

    monkeypatch.setattr(scan_worker, "start", capture)
    cfg = {**config.load_settings(), "llm_stufe1": False, "llm_stufe2": False,
           "top_n_export": 30}
    state = State(scan_logs={}, scan_results=[], scan_signals=[], scan_candidates=[])
    steps = tuple((key, key, "icon", "unit", "description") for key in
                  ("listen", "kandidaten", "forensik", "llm", "portfolio", "downloader"))
    ns = dict(st=SimpleNamespace(session_state=state), command={"mode": mode, "settings": cfg},
              run_settings=cfg, STEPS=steps, datetime=datetime, time=time, config=config,
              pipeline=pipeline, db=db, downloader_sync=downloader_sync,
              fix_signale=fix_signale, scan_worker=scan_worker,
              _attach_worker=lambda run: scan_state.attach_worker(state, run),
              _begruendung_speichern=lambda *a, **k: None)
    exec(compile(ast.Module(body=helper_nodes, type_ignores=[]), "actual-worker-helpers", "exec"), ns)
    ns["workflow"] = ns["_new_workflow"](mode)
    exec(compile(ast.Module(body=[worker_block], type_ignores=[]), "actual-worker-block", "exec"), ns)
    captured["target"]()
    return ns


def test_station6_runs_full_crawl_instead_of_only_sync(monkeypatch, fake_pipeline):
    ns = gui_worker(monkeypatch, "step_downloader")
    assert fake_pipeline.calls == ["crawl", "build_candidates"]
    assert ns["workflow"]["steps"]["listen"]["status"] == "complete"
    assert ns["workflow"]["status"] == "complete"


def test_source_only_gui_aborts_on_irrelevant_mql5_login(monkeypatch, fake_pipeline):
    fake_pipeline.candidates = [{"id": 9001, "name": "Source only", "quelle_kuerzel": "pelik"}]
    monkeypatch.setattr(pipeline.Mql5Session, "has_credentials", property(lambda self: True))
    login_calls = []
    monkeypatch.setattr("mqlkiscanner.mql5.browser_session.ensure_mql5_cookies",
                        lambda *a, **k: login_calls.append(True) or False)
    ns = gui_worker(monkeypatch, "scan")
    assert login_calls == [True]
    assert "analyze" not in fake_pipeline.calls
    assert ns["workflow"]["steps"]["forensik"]["status"] == "error"


def test_station1_session_data_does_not_follow_current_worker_control(monkeypatch, fake_pipeline):
    fake_pipeline.candidates = [{"id": 9001, "name": "Current run"}]
    ns = gui_worker(monkeypatch, "step_listen")
    assert ns["control"]["signals"] == fake_pipeline.candidates
    assert ns["st"].session_state["scan_signals"] == []


def test_gui_registry_ignores_existing_daemon_file_lock(monkeypatch):
    monkeypatch.setattr(scan_worker, "_REGISTRY_ATTR", "_isolated_workflow_review_registry")
    release = threading.Event()
    with lock.lauf_lock(config.DATA_DIR):
        run = scan_worker.start(release.wait, workflow={}, control={}, logs={}, results=[])
        try:
            assert run is not None and run.thread.is_alive()
        finally:
            release.set()
            run.thread.join(timeout=5)


def test_failed_autonomous_month_is_marked_as_success(fake_pipeline):
    fake_pipeline.candidates = [{"id": 9001, "name": "Source only", "quelle_kuerzel": "pelik"}]
    fake_pipeline.failed_results = True
    result = scan_launcher.starte_scan("full", quelle="isolated-review", log=lambda *a: None)
    assert result["geprueft"] == 0
    assert "endgültig fehlgeschlagen" in result["resultat"]
    assert result["status"] == "ok"
    assert scan_launcher.scan_monat_gestartet("full")


def test_unselected_partial_scan_row_is_claimed_selected():
    candidates = [{"id": sid, "name": str(sid), "abonnenten": 100 - sid,
                   "quelle_kuerzel": "source"} for sid in (1, 2)]
    reasons = []
    scope, _ = fix_signale.waehle_fuer_export(candidates, 1, {"fix_signal_ids": []},
                                             begruendung=reasons, modus="gelbgruen")
    assert [c["id"] for c in scope] == [1]
    omitted = next(r for r in reasons if r["id"] == 2)
    assert omitted["status"] == "AUSGEWAEHLT"
    assert "wird geprüft" in omitted["grund"]


def test_real_forensics_never_populates_retdd(live_reports, monkeypatch):
    monkeypatch.setattr(pipeline.ScanPipeline, "_kursanbieter_fuer", lambda *a: None)
    monkeypatch.setattr(pipeline.fx_rates, "status", lambda: {"geladen": False})
    pipe, _, scan = live_reports
    result = scan()
    assert result.forensik_vorhanden and result.ertrag_monat_pct_forensik > 0
    assert result.trading_dd_pct is not None and result.dd_equity_pct > 0
    assert result.retdd_monat is None
    assert result.retdd_jahr is None
    assert result.ertrag_monat_geom_pct is None
    assert result.cagr_jahr_pct is None
    sent = json.loads(pipeline._forensik_json(result))
    assert sent["retdd_monat"] is None and sent["ertrag_monat_geom_pct"] is None
    loaded = pipeline.results_from_db(pipe.settings)[0]
    assert loaded.retdd_monat is None and loaded.ertrag_monat_geom_pct is None
