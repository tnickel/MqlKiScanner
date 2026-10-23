"""Bounded independent strategy workers, durable drain, no model/network calls."""
from copy import deepcopy
from contextlib import nullcontext
from threading import Barrier, Event, Lock, Thread, current_thread
from time import monotonic, sleep
from types import SimpleNamespace

import pytest

from mqlkiscanner import abonnenten_analyse as analyse, config, db
from mqlkiscanner.abonnenten_analyse_store import Store
from mqlkiscanner.llm.client import LlmBudgetError, LlmError, LlmNoBalanceError, LlmRateLimitError


def entry(ref):
    return dict(signal_ref=ref, id=ref, quelle="mql5", quellen_uid="fixture",
                name=f"Strategy {ref}", abonnenten=100-ref, abo_perzentil=90-ref,
                eligible=True, retdd_jahr=10-ref/10, trades=60, dauer_monate=3,
                forensik={"forensics": {"martingale": {"flag": False}}},
                trades_path="fixture.csv", trades_sha256="fixture-sha", data_done=True,
                status="ki_offen")


@pytest.fixture
def short_run(monkeypatch):
    store = Store()
    store.create(dict(id="parallel", quellen=["mql5"], retdd_gewicht=70, dd_grenze=None,
                      logs=[], status="laeuft", stop_requested=False, ki_parallelitaet=2))
    rows = [entry(i) for i in range(1, 7)]
    for row in rows:
        store.save_task("parallel", row)
    monkeypatch.setattr(db, "verify_trade_file", lambda *args: None)
    profile = analyse._profile(store.read("parallel"))
    return store, rows, profile


def install_ai(monkeypatch, callback):
    instances = []
    instance_lock = Lock()

    class AI:
        def __init__(self, store, run_id, settings, profile, *, should_stop, log):
            self.client = SimpleNamespace(has_key=True)
            self.settings, self.profile = settings, profile
            self.should_stop, self.log = should_stop, log
            with instance_lock:
                instances.append(self)

        def analyse(self, row, *, deep=False, comparison=None):
            return callback(self, row, deep, comparison)

    monkeypatch.setattr(analyse, "AnalyseKI", AI)
    return instances


def background(call):
    outcome = {}

    def invoke():
        try:
            outcome["result"] = call()
        except BaseException as exc:
            outcome["exception"] = exc

    thread = Thread(target=invoke, name="fixture-coordinator", daemon=True)
    thread.start()
    return thread, outcome


def invoke_short(store, rows, profile, slots=2, stopped=lambda: False):
    return analyse._kurzanalysen(store, "parallel", rows, {}, profile,
                                stopped, lambda message: None, slots)


def test_concurrency_is_bounded_and_state_and_entries_are_private(short_run, monkeypatch):
    store, rows, profile = short_run
    lock, first_wave = Lock(), Barrier(3)
    state = {"active": 0, "peak": 0, "calls": []}

    def callback(ai, row, deep, comparison):
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            state["calls"].append(row["id"])
        try:
            ai._trade_refs = {f"snapshot-{row['id']}"}
            ai._last_evidence_register = {"F001": f"strategy-{row['id']}"}
            ai.settings["private"] = row["id"]
            ai.profile["private"] = row["id"]
            row["forensik"]["forensics"]["martingale"]["flag"] = True
            with ai.client.request_gate.slot():
                if row["id"] <= 3:
                    first_wave.wait(timeout=5)
            assert ai._trade_refs == {f"snapshot-{row['id']}"}
            assert ai._last_evidence_register == {"F001": f"strategy-{row['id']}"}
            return {"strategietyp": str(row["id"]), "pruefhinweise": []}
        finally:
            with lock:
                state["active"] -= 1

    instances = install_ai(monkeypatch, callback)
    assert invoke_short(store, rows, profile, slots=3) is False
    assert state["peak"] == 3 and sorted(state["calls"]) == list(range(1, 7))
    assert len(instances) == len({id(ai) for ai in instances}) == 6
    assert len({id(ai.client) for ai in instances}) == 6
    assert len({id(ai.settings) for ai in instances}) == 6
    assert len({id(ai.profile) for ai in instances}) == 6
    assert len({id(ai.client.request_gate) for ai in instances}) == 1
    assert "private" not in profile
    assert all(not row["forensik"]["forensics"]["martingale"]["flag"] for row in rows)
    assert all(row.get("kurztest") for row in store.tasks("parallel"))
    assert store.read("parallel")["ki_aktive_slots"] == 0
    assert store.read("parallel")["ki_http_aktiv"] == 0
    assert store.read("parallel")["ki_http_max_aktiv"] == 3


def test_stop_prevents_submission_and_drains_paid_successes(short_run, monkeypatch):
    store, rows, profile = short_run
    entered, release, stop = Barrier(3), Event(), Event()
    calls = []

    def callback(ai, row, deep, comparison):
        calls.append(row["id"])
        entered.wait(timeout=5)
        assert release.wait(timeout=5)
        return {"strategietyp": str(row["id"]), "pruefhinweise": []}

    install_ai(monkeypatch, callback)
    thread, outcome = background(lambda: invoke_short(store, rows, profile, stopped=stop.is_set))
    try:
        entered.wait(timeout=5)
        stop.set()
        assert thread.is_alive(), "A stop must not detach the active paid requests"
        release.set()
        thread.join(timeout=5)
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert isinstance(outcome.get("exception"), analyse.Angehalten)
    assert sorted(calls) == [1, 2]
    assert [row["id"] for row in store.tasks("parallel") if row.get("kurztest")] == [1, 2]
    assert store.read("parallel")["ki_aktive_slots"] == 0


@pytest.mark.parametrize("failure", [LlmBudgetError, LlmNoBalanceError, LlmRateLimitError, ValueError])
def test_fatal_error_stops_dispatch_and_preserves_other_inflight_result(short_run, monkeypatch, failure):
    store, rows, profile = short_run
    both_started, failure_returning, peer_stopped, release_peer = Barrier(2), Event(), Event(), Event()
    calls = []

    def callback(ai, row, deep, comparison):
        calls.append(row["id"])
        both_started.wait(timeout=5)
        if row["id"] == 1:
            failure_returning.set()
            raise failure("fixture interruption")
        assert failure_returning.wait(timeout=5)
        deadline = monotonic()+5
        while not ai.should_stop() and monotonic() < deadline:
            sleep(.002)
        if ai.should_stop():
            peer_stopped.set()
        # A peer simulates an already active HTTP request: it finishes after
        # the shared stop is visible, and its valid result must still persist.
        assert release_peer.wait(timeout=5)
        return {"strategietyp": "paid peer", "pruefhinweise": []}

    install_ai(monkeypatch, callback)
    thread, outcome = background(lambda: invoke_short(store, rows, profile))
    try:
        assert failure_returning.wait(timeout=5)
        assert peer_stopped.wait(timeout=5)
        assert thread.is_alive()
        release_peer.set()
        thread.join(timeout=5)
    finally:
        release_peer.set()
        thread.join(timeout=5)
    assert not thread.is_alive() and isinstance(outcome.get("exception"), failure)
    assert peer_stopped.is_set()
    assert sorted(calls) == [1, 2], "No queued backlog may start after the fatal failure"
    saved = store.tasks("parallel")
    assert not saved[0].get("kurztest") and saved[1]["kurztest"]["strategietyp"] == "paid peer"
    assert store.read("parallel")["ki_aktive_slots"] == 0


def test_nonfatal_invalid_answer_does_not_stop_other_strategies(short_run, monkeypatch):
    store, rows, profile = short_run

    def callback(ai, row, deep, comparison):
        if row["id"] == 1:
            raise LlmError("invalid evidence after repair")
        return {"strategietyp": "valid", "pruefhinweise": []}

    install_ai(monkeypatch, callback)
    assert invoke_short(store, rows, profile) is True
    saved = store.tasks("parallel")
    assert saved[0]["status"] == "ki_fehler"
    assert all(row.get("kurztest") for row in saved[1:])


def test_paid_report_survives_failing_hint_check_and_other_results_are_drained(short_run, monkeypatch):
    store, rows, profile = short_run
    rendezvous = Barrier(2)

    def callback(ai, row, deep, comparison):
        rendezvous.wait(timeout=5)
        return {"strategietyp": f"paid-{row['id']}",
                "pruefhinweise": [{"text": "new check"}] if row["id"] == 1 else []}

    install_ai(monkeypatch, callback)
    monkeypatch.setattr(db, "verify_trade_file", lambda *a: (_ for _ in ()).throw(ValueError("changed snapshot")))
    with pytest.raises(ValueError, match="changed snapshot"):
        invoke_short(store, rows[:2], profile)
    saved = store.tasks("parallel")
    assert saved[0]["kurztest"]["strategietyp"] == "paid-1"
    assert saved[1]["kurztest"]["strategietyp"] == "paid-2"
    assert store.read("parallel")["ki_aktive_slots"] == 0


def test_cache_hits_do_not_create_strategy_clients_and_hints_are_rechecked(short_run, monkeypatch):
    store, rows, profile = short_run
    hint = {"text": "unresolved", "beleg_refs": ["F001"]}
    for row in rows:
        row.update(kurz_basis=analyse.kurztest_basis(row, profile, {}),
                   kurztest={"pruefhinweise": [hint] if row["id"] == 1 else []})
    install_ai(monkeypatch, lambda *args: pytest.fail("Cached report triggered a model task"))
    assert invoke_short(store, rows, profile) is False
    assert store.tasks("parallel")[0]["review_pending"] is True


def test_missing_key_halts_once_without_marking_every_strategy_failed(short_run, monkeypatch):
    store, rows, profile = short_run
    instances = install_ai(monkeypatch, lambda *args: pytest.fail("Model called without credentials"))
    base = analyse.AnalyseKI

    class NoKeyAI(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.client.has_key = False

    monkeypatch.setattr(analyse, "AnalyseKI", NoKeyAI)
    with pytest.raises(LlmError, match="Kein GLM-Key"):
        invoke_short(store, rows, profile)
    assert 1 <= len(instances) <= 2
    assert not any(row.get("ki_fehler") for row in store.tasks("parallel"))


@pytest.mark.parametrize("value", [0, 11, -1, True, False, None, "2", 2.0])
def test_invalid_parallel_snapshot_is_rejected(value):
    with pytest.raises(ValueError, match="Parallelität"):
        analyse._ki_parallelitaet({"ki_parallelitaet": value}, {"abonnenten_analyse_parallelitaet": 2})


def test_snapshot_has_priority_and_old_runs_keep_serial_default():
    assert analyse._ki_parallelitaet({"ki_parallelitaet": 3}, {"abonnenten_analyse_parallelitaet": 10}) == 3
    assert analyse._ki_parallelitaet({}, {"abonnenten_analyse_parallelitaet": 10}) == 1
    assert analyse._ki_parallelitaet({}, {"abonnenten_analyse_parallelitaet": 4}, new_run=True) == 4


def test_invalid_snapshot_is_rejected_before_worker_launch(short_run, monkeypatch):
    store, _, _ = short_run
    store.update("parallel", ki_parallelitaet=0)
    monkeypatch.setattr(analyse.scan_worker, "start", lambda *a, **k: pytest.fail("Worker started"))
    with pytest.raises(ValueError, match="Parallelität"):
        analyse._launch("parallel")


def test_new_run_snapshots_explicit_parallel_setting_without_global_change(monkeypatch):
    original = deepcopy(config.load_settings())
    monkeypatch.setattr(db, "list_quellen", lambda **kw: [{"kuerzel": "mql5"}])
    monkeypatch.setattr(analyse, "_launch", lambda *a: None)
    run_id = analyse.starten(["mql5"], settings={"abonnenten_analyse_parallelitaet": 3})
    assert Store().read(run_id)["ki_parallelitaet"] == 3
    assert config.load_settings() == original


def test_full_execution_uses_frozen_data_parallel_short_and_serial_top5(short_run, monkeypatch, tmp_path):
    import mqlkiscanner.abonnenten_analyse_daten as data_module
    store, rows, profile = short_run
    store.update("parallel", snapshot_quellen={"mql5": {"status": "fertig"}})
    for row in rows:
        row["data_basis"] = analyse.eintrag_basis(row, analyse.daten_basis({}), {})
        store.save_task("parallel", row)
    monkeypatch.setattr(analyse, "_snapshot", lambda *a: None)
    monkeypatch.setattr(config, "load_known_signals", lambda: {"ausgeschlossen": []})

    class Data:
        def __init__(self, *a, **kw):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def berechne(self, *a, **kw):
            pytest.fail("Parallelizing KI must not redownload frozen strategy data")

    monkeypatch.setattr(data_module, "AnalyseDaten", Data)
    monkeypatch.setattr(analyse, "report_pdf", lambda row, rid: str(tmp_path / f"{row['id']}.pdf"))
    first_wave, lock = Barrier(2), Lock()
    active, deep_ids, short_threads = set(), [], set()
    owner = current_thread().ident

    def callback(ai, row, deep, comparison):
        if deep:
            assert not active and current_thread().ident == owner
            deep_ids.append(row["id"])
            return {"bericht_markdown": "fixture report", "neue_pruefhinweise": []}
        with lock:
            active.add(row["id"])
            short_threads.add(current_thread().ident)
        try:
            if row["id"] <= 2:
                first_wave.wait(timeout=5)
            return {"strategietyp": "fixture", "pruefhinweise": []}
        finally:
            with lock:
                active.remove(row["id"])

    install_ai(monkeypatch, callback)
    analyse._execute(store, "parallel", {"abonnenten_analyse_parallelitaet": 10})
    saved_run = store.read("parallel")
    assert saved_run["status"] == "abgeschlossen"
    assert saved_run["ki_parallelitaet"] == 2 and saved_run["ki_aktive_slots"] == 0
    assert len(short_threads) == 2 and owner not in short_threads
    assert deep_ids == [1, 2, 3, 4, 5]
    assert all(row.get("kurztest") for row in store.tasks("parallel"))


def test_cached_short_reports_and_missing_key_do_not_fail_each_open_top5(short_run, monkeypatch):
    import mqlkiscanner.abonnenten_analyse_daten as data_module
    store, rows, profile = short_run
    store.update("parallel", snapshot_quellen={"mql5": {"status": "fertig"}})
    monkeypatch.setattr(analyse, "_snapshot", lambda *a: None)
    monkeypatch.setattr(config, "load_known_signals", lambda: {"ausgeschlossen": []})
    monkeypatch.setattr(data_module, "AnalyseDaten", lambda *a, **kw: nullcontext(SimpleNamespace(
        berechne=lambda *a, **kw: pytest.fail("Frozen data must not be downloaded again"))))
    for row in rows:
        row["data_basis"] = analyse.eintrag_basis(row, analyse.daten_basis({}), {})
        row.update(kurz_basis=analyse.kurztest_basis(row, profile, {}),
                   kurztest={"strategietyp": "cached", "pruefhinweise": []})
        store.save_task("parallel", row)

    class NoKeyAI:
        def __init__(self, *a, **kw):
            self.client = SimpleNamespace(has_key=False)
        def analyse(self, *a, **kw):
            pytest.fail("No new model call is allowed without a key")

    monkeypatch.setattr(analyse, "AnalyseKI", NoKeyAI)
    analyse._execute(store, "parallel", {})
    saved_run, saved = store.read("parallel"), store.tasks("parallel")
    assert saved_run["status"] == "teilweise" and "Kein GLM-Key" in saved_run["fehler"]
    assert all(row["kurztest"]["strategietyp"] == "cached" for row in saved)
    assert not any(row.get("ki_fehler") or row["status"] == "ki_fehler" for row in saved)
    assert not any(row.get("bericht_markdown") for row in saved)
