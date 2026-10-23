"""Independent resume/snapshot regressions at synthetic backend boundaries."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from mqlkiscanner import abonnenten_analyse as analyse, client_updates, config, db
from mqlkiscanner import abonnenten_analyse_daten as data_module
from mqlkiscanner import abonnenten_analyse_ki as ki
from mqlkiscanner.abonnenten_analyse_store import Store
from mqlkiscanner.llm.client import LlmError


@pytest.fixture
def cached_run(monkeypatch, tmp_path):
    store = Store()
    store.create({"id": "review", "status": "geplant", "created_at": "test",
                  "quellen": ["mql5"], "retdd_gewicht": 70.0, "dd_grenze": None,
                  "snapshot_quellen": {"mql5": {"status": "fertig"}}, "logs": [],
                  "policy_version": analyse.POLICY_VERSION})
    entry = dict(signal_ref=1, id=811, quelle="mql5", quellen_uid="synthetic-owner",
                 name="Resume regression", abo_perzentil=50, data_done=False)
    store.save_task("review", entry)
    path = tmp_path / "snapshot.csv"
    original = b"immutable synthetic export\n"
    calls = {"data": 0, "short": 0, "deep": 0}
    rules = {"ausgeschlossen": []}
    monkeypatch.setattr(config, "load_known_signals", lambda: rules)
    monkeypatch.setattr(analyse, "_snapshot", lambda *args: None)

    class Data:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def berechne(self, entry, should_stop):
            calls["data"] += 1
            path.write_bytes(original)
            excluded = any(e["id"] == entry["id"] and e["quelle"] == entry["quelle"]
                           for e in rules["ausgeschlossen"])
            return dict(data_complete=True, eligible=not excluded, hard_excluded=excluded,
                        grund="Aktuelle Ausschlussliste" if excluded else "",
                        trades=50, dauer_monate=2.1, equity_dd_pct=60,
                        retdd_jahr=4, trades_path=str(path),
                        trades_sha256=hashlib.sha256(original).hexdigest(),
                        forensik={"forensics": {"martingale": {"flag": False}}}, equity={"ok": True})

    class AI:
        def __init__(self, *args, **kwargs):
            self.client = SimpleNamespace(has_key=True)
        def analyse(self, entry, *, deep=False, comparison=None):
            calls["deep" if deep else "short"] += 1
            if deep:
                return {"bericht_markdown": "# Prüfung\n\nBelegte Basis.", "neue_pruefhinweise": []}
            return {"strategietyp": "Synthetic", "kurzurteil": "Synthetic evidence", "pruefhinweise": []}

    monkeypatch.setattr(data_module, "AnalyseDaten", Data)
    monkeypatch.setattr(analyse, "AnalyseKI", AI)
    monkeypatch.setattr(analyse, "report_pdf", lambda *args: str(tmp_path / "synthetic.pdf"))
    return store, path, calls, rules


def test_corrupted_cached_input_is_reacquired_before_finished_reuse(cached_run):
    store, path, calls, rules = cached_run
    analyse._execute(store, "review", config.load_settings())
    assert store.read("review")["status"] == "abgeschlossen"
    assert calls["data"] == 1
    path.write_bytes(b"corrupted replacement\n")
    analyse._execute(store, "review", config.load_settings())
    assert calls["data"] == 2, "A cached completed row must not bypass input SHA verification"
    saved = store.tasks("review")[0]
    db.verify_trade_file(saved["trades_path"], saved["trades_sha256"])


def test_new_explicit_exclusion_invalidates_cached_eligibility(cached_run):
    store, path, calls, rules = cached_run
    analyse._execute(store, "review", config.load_settings())
    assert store.tasks("review")[0]["rang"] == 1
    rules["ausgeschlossen"] = [{"quelle": "mql5", "id": 811, "grund": "New proven exclusion"}]
    analyse._execute(store, "review", config.load_settings())
    saved = store.tasks("review")[0]
    assert saved["eligible"] is False and saved["hard_excluded"]
    assert saved["rang"] is None


def test_policy_change_recomputes_facts_and_dependent_reports(cached_run, monkeypatch):
    store, path, calls, rules = cached_run
    analyse._execute(store, "review", config.load_settings())
    first_basis = store.tasks("review")[0]["data_basis"]
    monkeypatch.setattr(analyse, "POLICY_VERSION", "review-new-policy")
    analyse._execute(store, "review", config.load_settings())
    assert calls == {"data": 2, "short": 2, "deep": 2}
    assert store.tasks("review")[0]["data_basis"] != first_basis


def test_failed_source_snapshot_does_not_pollute_resumed_membership(monkeypatch):
    qid = db.add_quelle("mql5", "Synthetic source", "http://synthetic-source:8199")
    source = db.get_quelle(qid)
    store = Store()
    store.create(dict(id="snapshot", quellen=["mql5"], snapshot_quellen={}, logs=[]))
    monkeypatch.setattr(client_updates, "starte_alle_updates", lambda *a, **k: {
        "mql5": {"status": client_updates.FERTIG, "job_id": "fresh-counters"}})
    monkeypatch.setattr(analyse.source_registry, "client_fuer_quelle", lambda q: SimpleNamespace(
        health=lambda: {"providerRefresh": True}))
    monkeypatch.setattr(analyse.ingest, "kandidaten", lambda q, raw: raw)

    def candidate(sid, platform="mt5"):
        return dict(id=sid, quelle_id=qid, quelle_version="mql5", platform=platform,
                    name=f"Provider {sid}", abonnenten=10, quellen_uid=source["quellen_uid"])

    catalogs = iter([[candidate(1), candidate(2, "")], [candidate(3), candidate(4)]])
    monkeypatch.setattr(analyse.ingest, "hole_katalog", lambda *a, **k: next(catalogs))
    analyse._snapshot(store, store.read("snapshot"), {}, lambda message: None, lambda: False)
    assert store.read("snapshot")["snapshot_quellen"]["mql5"]["status"] == "fehler"
    analyse._snapshot(store, store.read("snapshot"), {}, lambda message: None, lambda: False)
    assert {row["id"] for row in store.tasks("snapshot")} == {3, 4}, "Failed partial membership must never survive a new complete snapshot"


def test_partial_catalog_is_frozen_and_candidates_keep_selection_warning(monkeypatch):
    qid = db.add_quelle("vant", "Synthetic Vantage", "http://synthetic-source:8199")
    source = db.get_quelle(qid)
    store = Store()
    store.create(dict(id="partial", quellen=["vant"], snapshot_quellen={}, logs=[]))
    coverage = dict(complete=False, reached_end=True, scanned_providers=500,
                    skipped_positions=[1256], months=1, sort="2")
    monkeypatch.setattr(client_updates, "starte_alle_updates", lambda *a, **k: {
        "vant": {"status": client_updates.TEILWEISE, "job_id": "partial-counters",
                 "abonnenten_katalog": coverage}})
    monkeypatch.setattr(analyse.source_registry, "client_fuer_quelle", lambda q: SimpleNamespace(
        health=lambda: {"providerRefresh": True}))
    monkeypatch.setattr(analyse.ingest, "kandidaten", lambda q, raw: raw)
    monkeypatch.setattr(analyse.ingest, "hole_katalog", lambda *a, **k: [dict(
        id=1, quelle_id=qid, quelle_version="vantage", platform="mt4", name="Test",
        abonnenten=10, quellen_uid=source["quellen_uid"])])
    analyse._snapshot(store, store.read("partial"), {}, lambda message: None, lambda: False)
    checkpoint = store.read("partial")["snapshot_quellen"]["vant"]
    assert checkpoint["status"] == "fertig"
    assert checkpoint["abonnenten_katalog"] == coverage
    entry = store.tasks("partial")[0]
    assert entry["status"] == "wartet"
    assert entry["abo_referenz_vollstaendig"] is False
    assert entry["abo_ausgelassene_positionen"] == [1256]
    # A resume must retain the same membership, not silently replace its scope.
    monkeypatch.setattr(client_updates, "starte_alle_updates", lambda *a, **k: pytest.fail("refreshed frozen selection"))
    analyse._snapshot(store, store.read("partial"), {}, lambda message: None, lambda: False)


def test_long_history_keeps_every_occurrence_and_overlap_is_not_double_counted():
    rows = [{"trade_ref": f"snapshot:{i}", "profit": 1, "symbol": "XAUUSD"} for i in range(350)]
    blocks = ki.segments(rows, max_bytes=500, overlap=8)
    primary = [ref for block in blocks for ref in block["primary_refs"]]
    assert primary == [row["trade_ref"] for row in rows]
    assert len(primary) == len(set(primary)) == 350
    assert any(block["overlap_refs"] for block in blocks[1:])


def test_call_ledger_retains_all_invalid_paid_and_unknown_attempts():
    store = Store()
    store.create({"id": "costs"})
    store.reserve("costs", "input:0", 1000, 10_000)
    store.finish_call("costs", "input:0", response="invalid JSON", tokens=75, meta={})
    store.reserve("costs", "input:1", 1000, 10_000)
    store.finish_call("costs", "input:1", response="", tokens=None, meta={"error": "transport unknown"}, status="error")
    store.reserve("costs", "input:2", 1000, 10_000)
    store.finish_call("costs", "input:2", response="{}", tokens=80, meta={})
    assert Store().spent("costs") == 1155
    assert [row["response"] for row in Store().calls("costs", "input")] == ["invalid JSON", "", "{}"]


def test_model_cannot_label_martingale_as_code_proven_against_engine():
    entry = {"signal_ref": 1, "forensik": {"forensics": {"martingale": {"flag": False}}}}
    answer = {"schema_version": 1, "signal_ref": 1, "verarbeitung": "vollanalyse",
              "strategietyp": "Trendfolge", "strategie_sicherheit": "plausibel",
              "martingale_einordnung": "code_belegt", "kurzurteil": "Contradicts engine",
              "staerken": [], "risiken": [], "pruefhinweise": [], "datenluecken": []}
    with pytest.raises(LlmError):
        ki.validate(answer, entry)


def test_deep_segment_requires_an_actual_analysis_not_only_identity():
    entry = {"signal_ref": 1}
    answer = {"signal_ref": 1, "segment_id": 1, "beleg_refs": []}
    with pytest.raises(LlmError):
        ki.validate(answer, entry, deep=True, segment=True)
