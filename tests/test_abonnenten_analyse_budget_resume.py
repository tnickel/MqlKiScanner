"""One explicit budget restart retains failed work without claiming completeness."""
from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from mqlkiscanner import abonnenten_analyse as analyse, abonnenten_analyse_daten as data_module, config
from mqlkiscanner.abonnenten_analyse_store import Store


@pytest.fixture
def attempt(monkeypatch, tmp_path):
    store = Store()
    store.create({"id": "budget-resume", "status": "angehalten", "quellen": ["mql5"],
                  "retdd_gewicht": 70, "dd_grenze": None, "logs": [],
                  "snapshot_quellen": {"mql5": {"status": "fertig"}}, "budget_resume_refs": [8]})
    settings = {**config.load_settings(), "llm_max_total_tokens": 50_000_000,
                "agenten_tagesbudget_tokens": 50_000_000, "agenten_monatsbudget_tokens": 60_000_000,
                "fake_secret_not_for_audit": "never persist this"}
    path = tmp_path / "verified.csv"
    path.write_bytes(b"immutable trade snapshot\n")
    entry = {"id": 81, "signal_ref": 8, "quelle": "mql5", "name": "Synthetic gap",
             "abonnenten": 1, "abo_perzentil": 50, "status": "datenluecke",
             "data_done": False, "data_complete": False, "eligible": False,
             "grund": "Kapitalbasis fehlt", "trades_path": str(path),
             "trades_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "forensik": {}}
    entry["data_basis"] = analyse.eintrag_basis(entry, analyse.daten_basis(settings), {})
    store.save_task("budget-resume", entry)
    calls = []
    class Data:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def berechne(self, entry, should_stop):
            calls.append(entry["signal_ref"])
            return {"data_complete": False, "eligible": False, "grund": "Erneut geprüft; Kapitalbasis fehlt"}
    class AI:
        def __init__(self, *args, **kwargs): self.client = SimpleNamespace(has_key=False)
        def analyse(self, *args, **kwargs): pytest.fail("No usable material, no model call")
    monkeypatch.setattr(data_module, "AnalyseDaten", Data)
    monkeypatch.setattr(analyse, "AnalyseKI", AI)
    monkeypatch.setattr(analyse, "_snapshot", lambda *args: None)
    monkeypatch.setattr(config, "load_known_signals", lambda: {"ausgeschlossen": []})
    return store, settings, entry, path, calls


def test_budget_checkpoint_preserves_gap_then_is_consumed_and_audits_effective_limits(attempt):
    store, settings, entry, path, calls = attempt
    analyse._execute(store, "budget-resume", settings)
    saved = store.tasks("budget-resume")[0]
    assert calls == []
    assert saved["data_done"] is False and saved["data_complete"] is False
    assert saved["grund"] == "Kapitalbasis fehlt" and saved["status"] == "datenluecke"
    run = store.read("budget-resume")
    assert run["status"] == "teilweise"
    assert run["budget_resume_refs"] == []
    assert run["budget_applied"] == {"llm_max_total_tokens": 50_000_000,
                                     "agenten_tagesbudget_tokens": 50_000_000,
                                     "agenten_monatsbudget_tokens": 60_000_000}
    analyse._execute(store, "budget-resume", settings)
    assert calls == [8], "A later explicit retry must retry the unresolved data gap normally"


@pytest.mark.parametrize("problem", ["new_basis", "tampered", "missing_sha", "rechnet", "abgebrochen"])
def test_checkpoint_cannot_skip_changed_or_unfinished_material(attempt, problem):
    store, settings, entry, path, calls = attempt
    if problem == "new_basis":
        entry["data_basis"] = "old analysis policy"
    elif problem == "tampered":
        path.write_bytes(b"changed input\n")
    elif problem == "missing_sha":
        entry["trades_sha256"] = ""
    elif problem == "rechnet":
        entry["status"] = "rechnet"
    else:
        entry["abgebrochen"] = True
    store.save_task("budget-resume", entry)
    analyse._execute(store, "budget-resume", settings)
    assert calls == [8]
    assert store.tasks("budget-resume")[0]["data_done"] is False
    assert store.read("budget-resume")["budget_resume_refs"] == []


def test_checkpoint_without_trade_material_preserves_a_completed_failed_attempt(attempt):
    store, settings, entry, path, calls = attempt
    entry.update(trades_path="", trades_sha256="", grund="Gezielter Quellenabruf fehlgeschlagen")
    store.save_task("budget-resume", entry)
    analyse._execute(store, "budget-resume", settings)
    assert calls == []
    assert store.tasks("budget-resume")[0]["data_done"] is False
    assert store.tasks("budget-resume")[0]["grund"] == "Gezielter Quellenabruf fehlgeschlagen"
