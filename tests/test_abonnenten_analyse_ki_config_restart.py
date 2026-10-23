"""Explicit KI-only restart keeps completed data attempts without source work."""
from __future__ import annotations

import copy
import hashlib
import os
from types import SimpleNamespace

import psutil
import pytest

from mqlkiscanner import abonnenten_analyse as analyse, abonnenten_analyse_daten as data_module, config
from mqlkiscanner.abonnenten_analyse_store import Store


@pytest.fixture
def restart(monkeypatch, tmp_path):
    store = Store()
    run = dict(id="ki-restart", status="angehalten", quellen=["mql5", "robo", "vant"],
               retdd_gewicht=70, dd_grenze=None, policy_version=analyse.POLICY_VERSION,
               snapshot_quellen={"mql5": {"status": "fertig", "anzahl": 5},
                                 "robo": {"status": "fertig", "anzahl": 1},
                                 "vant": {"status": "fehler", "grund": "API 1223"}},
               logs=[], budget_resume_refs=[91], budget_checkpoint={"historical": True})
    store.create(run)
    settings = {**config.load_settings(), "equity_test_basis": "fixed", "llm_model": "old"}
    path = tmp_path / "frozen.csv"
    path.write_bytes(b"synthetic immutable trades\n")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    entries = []
    for ref, status in enumerate(("ki_fehler", "datenluecke", "datenluecke", "quellenwerte",
                                  "ausgeschlossen", "fertig"), 1):
        entry = dict(signal_ref=ref, id=100+ref, quelle="robo" if ref == 4 else "mql5",
                     quellen_uid="robo-uid" if ref == 4 else "mql-uid", name=f"Synthetic {ref}",
                     status=status, data_done=ref not in (2, 3), data_complete=ref not in (2, 3),
                     eligible=ref in (1, 6), retdd_jahr=3 if ref in (1, 6) else None,
                     equity_dd_pct=12 if ref in (1, 6) else None, abo_perzentil=50,
                     dauer_monate=3, trades=60 if ref in (1, 6) else 0,
                     trades_path=str(path) if ref not in (3, 4) else "",
                     trades_sha256=sha if ref not in (3, 4) else "",
                     forensik={"forensics": {"martingale": {"flag": False}}} if ref in (1, 6) else {},
                     grund="Kapitalbasis fehlt" if ref in (2, 3) else "", ki_fehler="old KI error" if ref == 1 else "")
        if ref == 4:
            entry.update(auswertung_typ="quellenprofitabilitaet", gewinn_usd=12, trades=None)
        entry["data_basis"] = analyse.eintrag_basis(entry, analyse.daten_basis(settings), {})
        entries.append(entry)
    entries[-1].update(kurztest={"kurzurteil": "existing", "pruefhinweise": []},
                       kurz_basis=analyse.kurztest_basis(entries[-1], analyse._profile(run), settings))
    for entry in entries:
        store.save_task(run["id"], entry)
    monkeypatch.setattr(config, "load_known_signals", lambda: {"ausgeschlossen": []})
    monkeypatch.setattr(analyse.scan_worker, "active_run", lambda: None)
    calls = {"snapshot": 0, "data": 0, "ai_init": 0, "short": [], "deep": []}

    def snapshot(*args, **kwargs):
        calls["snapshot"] += 1
        raise AssertionError("No source refresh during controlled KI restart")

    class Data:
        def __init__(self, *args, **kwargs):
            calls["data"] += 1
            raise AssertionError("Do not even construct the data provider")

    class AI:
        def __init__(self, *args, **kwargs):
            calls["ai_init"] += 1
            self.client = SimpleNamespace(has_key=True)

        def analyse(self, entry, *, deep=False, comparison=None):
            calls["deep" if deep else "short"].append(entry["signal_ref"])
            if deep:
                return {"bericht_markdown": "Synthetic report", "neue_pruefhinweise": []}
            return {"kurzurteil": "Synthetic short analysis", "pruefhinweise": []}

    monkeypatch.setattr(analyse, "_snapshot", snapshot)
    monkeypatch.setattr(data_module, "AnalyseDaten", Data)
    monkeypatch.setattr(analyse, "AnalyseKI", AI)
    monkeypatch.setattr(analyse, "report_pdf", lambda *args: str(tmp_path / "synthetic.pdf"))
    return store, run, settings, entries, path, calls


def prepare(restart):
    store, run, settings, entries, path, calls = restart
    checkpoint = analyse.prepare_ki_config_restart_checkpoint(
        store.read(run["id"]), store.tasks(run["id"]), settings, prepared_at="synthetic time")
    store.update(run["id"], **{analyse.KI_CONFIG_RESTART_FIELD: checkpoint})
    return checkpoint


def test_pure_preparation_and_mixed_attempts_reused_with_failed_source_unchanged(restart):
    store, run, settings, entries, path, calls = restart
    original_run, original_entries = copy.deepcopy(run), copy.deepcopy(entries)
    checkpoint = analyse.prepare_ki_config_restart_checkpoint(run, entries, settings, prepared_at="test")
    assert run == original_run and entries == original_entries
    assert store.read(run["id"]) == original_run
    assert checkpoint["refs"] == [1, 2, 3, 4, 5, 6]
    assert checkpoint["state"] == "prepared"
    store.update(run["id"], **{analyse.KI_CONFIG_RESTART_FIELD: checkpoint})
    # A client/model setting correction does not alter objective data basis.
    settings = {**settings, "llm_model": "new", "glm_base_url": "https://synthetic.invalid"}
    analyse._execute(store, run["id"], settings)
    saved_run, saved = store.read(run["id"]), store.tasks(run["id"])
    # Short strategy tasks own a private client; the sequential Top5 phase
    # uses a separate one. Neither phase repeats completed data attempts.
    assert calls == {"snapshot": 0, "data": 0, "ai_init": 2, "short": [1], "deep": [1, 6]}
    assert saved_run["snapshot_quellen"] == run["snapshot_quellen"]
    assert saved_run["budget_resume_refs"] == [91]
    assert saved_run["budget_checkpoint"] == {"historical": True}
    assert saved_run["status"] == "teilweise"  # Old source failure and real data gaps stay visible.
    audit = saved_run[analyse.KI_CONFIG_RESTART_FIELD]
    assert audit == {**checkpoint, "state": "consumed", "consumed_at": audit["consumed_at"]}
    assert audit["consumed_at"]
    for index in (1, 2, 3, 4):
        assert saved[index]["data_done"] == entries[index]["data_done"]
        assert saved[index]["grund"] == entries[index]["grund"]
        assert saved[index]["data_basis"] == entries[index]["data_basis"]
        assert saved[index]["status"] == entries[index]["status"]
    assert saved[0]["status"] == "fertig" and saved[0]["ki_fehler"] == ""


@pytest.mark.parametrize("change", ["file", "missing_sha", "basis", "contracts", "kurs_settings",
                                  "forensics_version", "policy", "exclusion", "uid", "provider_id", "ref", "task_removed",
                                  "task_added", "source_snapshot", "source_roster", "profile", "counter"])
def test_checkpoint_mismatch_aborts_before_sources_data_or_paid_work(restart, monkeypatch, change):
    store, run, settings, entries, path, calls = restart
    checkpoint = prepare(restart)
    entry = store.tasks(run["id"])[0]
    if change == "file":
        path.write_bytes(b"tampered")
    elif change == "missing_sha":
        entry["trades_sha256"] = ""
    elif change == "basis":
        entry["data_basis"] = "old"
    elif change == "contracts":
        config.CONTRACT_SPECS_FILE.write_text('{"different": true}', encoding="utf-8")
    elif change == "kurs_settings":
        settings["equity_test_basis"] = "changed"
    elif change == "forensics_version":
        monkeypatch.setattr(analyse, "FORENSICS_VERSION", analyse.FORENSICS_VERSION + 1)
    elif change == "policy":
        monkeypatch.setattr(analyse, "POLICY_VERSION", "next_policy")
    elif change == "exclusion":
        monkeypatch.setattr(config, "load_known_signals", lambda: {"ausgeschlossen": [
            {"quelle": "mql5", "id": entry["id"], "grund": "new"}]})
    elif change in ("uid", "provider_id", "ref", "counter"):
        entry[{"uid": "quellen_uid", "provider_id": "id", "ref": "signal_ref", "counter": "abo_perzentil"}[change]] = (
            "another-uid" if change == "uid" else 999)
    elif change == "task_removed":
        # An explicit fixture Store facade simulates an omitted task without production SQL.
        original = store.tasks
        monkeypatch.setattr(store, "tasks", lambda run_id: original(run_id)[1:])
    elif change == "task_added":
        extra = {**entry, "signal_ref": 99, "id": 199}
        store.save_task(run["id"], extra)
    elif change == "source_snapshot":
        store.update(run["id"], snapshot_quellen={"vant": {"status": "fertig"}})
    elif change == "source_roster":
        store.update(run["id"], quellen=["mql5", "robo"])
    elif change == "profile":
        store.update(run["id"], dd_grenze=10)
    if change not in ("task_removed",):
        store.save_task(run["id"], entry)
    analyse._execute(store, run["id"], settings)
    saved = store.read(run["id"])
    assert saved["status"] == "teilweise"
    assert "KI-Konfigurationsneustart" in saved["fehler"]
    assert saved[analyse.KI_CONFIG_RESTART_FIELD] == checkpoint
    assert calls == {"snapshot": 0, "data": 0, "ai_init": 0, "short": [], "deep": []}


@pytest.mark.parametrize("problem", ["laeuft", "geplant", "pending", "rechnet", "abgebrochen", "duplicate_ref",
                                   "duplicate_owner", "missing_uid", "invalid_ref", "success_no_snapshot", "half_pair",
                                   "no_entries", "old_basis", "local_worker", "live_pid", "unknown_process"])
def test_preparation_rejects_live_unfinished_or_unproved_attempts_without_mutation(restart, monkeypatch, problem):
    store, run, settings, entries, path, calls = restart
    if problem in ("laeuft", "geplant"):
        run["status"] = problem
    elif problem in ("pending", "rechnet"):
        entries[0]["status"] = "wartet" if problem == "pending" else "rechnet"
    elif problem == "abgebrochen":
        entries[0]["abgebrochen"] = True
    elif problem == "duplicate_ref":
        entries[1]["signal_ref"] = entries[0]["signal_ref"]
    elif problem == "duplicate_owner":
        entries[1]["id"] = entries[0]["id"]
    elif problem == "missing_uid":
        entries[0].pop("quellen_uid")
    elif problem == "invalid_ref":
        entries[0]["signal_ref"] = True
    elif problem == "success_no_snapshot":
        entries[0].update(trades_path="", trades_sha256="")
    elif problem == "half_pair":
        entries[0]["trades_sha256"] = ""
    elif problem == "no_entries":
        entries = []
    elif problem == "old_basis":
        entries[0]["data_basis"] = "old"
    elif problem == "local_worker":
        monkeypatch.setattr(analyse.scan_worker, "active_run", lambda: SimpleNamespace(workflow={"abonnenten_id": run["id"]}))
    elif problem == "live_pid":
        run.update(pid=os.getpid(), process_start=psutil.Process().create_time())
    elif problem == "unknown_process":
        run.update(pid=os.getpid(), process_start=None)
    before = copy.deepcopy((run, entries))
    with pytest.raises(ValueError, match="KI-Konfigurationsneustart"):
        analyse.prepare_ki_config_restart_checkpoint(run, entries, settings)
    assert (run, entries) == before
    assert analyse.KI_CONFIG_RESTART_FIELD not in store.read(run["id"])
    assert calls == {"snapshot": 0, "data": 0, "ai_init": 0, "short": [], "deep": []}


@pytest.mark.parametrize("change", ["foreign_run", "wrong_version", "wrong_purpose", "wrong_state", "bad_object", "not_paused"])
def test_malformed_checkpoint_never_falls_back_to_normal_refresh(restart, change):
    store, run, settings, entries, path, calls = restart
    checkpoint = prepare(restart)
    if change == "foreign_run": checkpoint["run_id"] = "another"
    elif change == "wrong_version": checkpoint["version"] = 2
    elif change == "wrong_purpose": checkpoint["purpose"] = "budget_restart"
    elif change == "wrong_state": checkpoint["state"] = "unknown"
    elif change == "bad_object": checkpoint = []
    elif change == "not_paused": store.update(run["id"], status="teilweise")
    store.update(run["id"], **{analyse.KI_CONFIG_RESTART_FIELD: checkpoint})
    analyse._execute(store, run["id"], settings)
    assert "KI-Konfigurationsneustart" in store.read(run["id"])["fehler"]
    assert calls == {"snapshot": 0, "data": 0, "ai_init": 0, "short": [], "deep": []}


def test_consumed_checkpoint_retained_but_does_not_authorize_another_data_skip(restart):
    store, run, settings, entries, path, calls = restart
    prepare(restart)
    analyse._execute(store, run["id"], settings)
    audit = copy.deepcopy(store.read(run["id"])[analyse.KI_CONFIG_RESTART_FIELD])
    assert analyse._validate_ki_config_restart(store.read(run["id"]), store.tasks(run["id"]), settings) is None
    analyse._execute(store, run["id"], settings)
    assert calls["snapshot"] == 1, "Only a new explicit checkpoint may authorize another KI-only restart"
    assert store.read(run["id"])[analyse.KI_CONFIG_RESTART_FIELD] == audit


def test_reordered_task_input_has_same_checkpoint_and_dead_or_reused_pid_is_safe(restart, monkeypatch):
    store, run, settings, entries, path, calls = restart
    run.update(pid=999999, process_start=100.0)
    def gone(pid): raise psutil.NoSuchProcess(pid)
    monkeypatch.setattr(psutil, "Process", gone)
    first = analyse.prepare_ki_config_restart_checkpoint(run, entries, settings, prepared_at="test")
    monkeypatch.setattr(psutil, "Process", lambda pid: SimpleNamespace(create_time=lambda: 200.0))
    second = analyse.prepare_ki_config_restart_checkpoint(run, list(reversed(entries)), settings, prepared_at="test")
    assert first == second


def test_shared_short_basis_matches_existing_formula_and_detects_selection_caveat(restart):
    store, run, settings, entries, path, calls = restart
    entry, profile = entries[0], analyse._profile(run)
    expected = analyse.digest({"data": entry.get("data_basis"), "sha": entry.get("trades_sha256"),
                              "facts_payload_version": analyse.FACTS_PAYLOAD_VERSION,
                              "facts": entry.get("forensik"), "equity": entry.get("equity"), "profile": profile,
                              "prompt": analyse.prompts.prompt_fingerprint(("abonnenten_kurztest",)),
                              "model": analyse.prompts.prompt_model("abonnenten_kurztest", settings)})
    assert analyse.kurztest_basis(entry, profile, settings) == expected
    caveat = {**entry, "abo_referenz_vollstaendig": False, "abo_ausgelassene_positionen": [1256]}
    assert analyse.kurztest_basis(caveat, profile, settings) != expected


@pytest.mark.parametrize("outcome", ["success", "eur_gap", "new_abort"])
def test_new_regular_data_attempt_does_not_inherit_previous_abort_but_preserves_current_abort(
        restart, monkeypatch, outcome):
    store, run, settings, entries, path, calls = restart
    # A retryable prior attempt, with the stale cancellation flag reproduced.
    entry = entries[0]
    entry.update(status="datenluecke", data_done=False, data_complete=False, abgebrochen=True,
                 eligible=False, trades=0, forensik={})
    store.save_task(run["id"], entry)
    monkeypatch.setattr(analyse, "_snapshot", lambda *args: None)
    seen = []

    class Data:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def berechne(self, task, should_stop):
            seen.append((task["signal_ref"], task.get("abgebrochen")))
            if task["signal_ref"] != entry["signal_ref"]:
                return {"data_complete": False, "eligible": False, "grund": "Synthetic other gap"}
            if outcome == "new_abort":
                store.update(run["id"], stop_requested=True)
                return {"data_complete": False, "eligible": False, "grund": "Abbruch angefordert", "abgebrochen": True}
            # Real AnalyseDaten returns neither abgebrochen=False nor this key
            # on ordinary success / a completed validation failure.
            return {"data_complete": outcome == "success", "eligible": False,
                    "grund": "Ordinary success" if outcome == "success" else
                             "ValueError: Belegte USD-Kontowährung fehlt (geliefert: EUR)."}

    monkeypatch.setattr(data_module, "AnalyseDaten", Data)
    analyse._execute(store, run["id"], settings)
    saved = next(task for task in store.tasks(run["id"]) if task["signal_ref"] == entry["signal_ref"])
    assert seen[0] == (entry["signal_ref"], False)
    assert saved["abgebrochen"] is (outcome == "new_abort")
    assert saved["data_done"] is (outcome == "success")
    if outcome == "new_abort":
        assert store.read(run["id"])["status"] == "angehalten"
        # The strict checkpoint data validator still rejects a genuine abort.
        with pytest.raises(ValueError, match="nicht abgeschlossen"):
            analyse._restart_tasks(run, [saved], settings)
    elif outcome == "eur_gap":
        assert saved["status"] == "datenluecke" and "EUR" in saved["grund"]
        assert saved["eligible"] is False
