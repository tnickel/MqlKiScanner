"""Durable source-update evidence, including unexpected aborts; no real network."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from mqlkiscanner import client_updates as cu, config, db


def source(monkeypatch, poll):
    db.init_db()
    row = db.get_quelle(db.add_quelle("proof", "Synthetic", "http://synthetic:8199"))
    client = SimpleNamespace(health=lambda: {"status": "ok"},
                             update_starten=lambda **kw: {"jobId": "accepted-job"},
                             update_status=poll)
    monkeypatch.setattr(cu.quellen, "client_fuer_quelle", lambda *a, **kw: client)
    return row


def run(row, callback=None, stopped=lambda: False):
    return cu._update_eine_quelle(row, settings={}, log=None, on_fortschritt=callback,
                                 gestopft=stopped, bereit_warten_s=0, poll_s=0,
                                 backoff_s=0, timeout_s=1, login_timeout_s=0)


def done():
    return {"state": "done", "jobId": "accepted-job", "done": 10, "total": 10,
            "ergebnis": {"signaleGeliefert": 10, "tradelistenAktualisiert": 10}}


def test_keyboard_interrupt_has_durable_final_state_and_keeps_accepted_job(monkeypatch):
    def interrupted():
        raise KeyboardInterrupt("synthetic operator interruption")
    row = source(monkeypatch, interrupted)
    with pytest.raises(KeyboardInterrupt):
        run(row)
    events = db.list_client_updates()
    assert events and events[0]["status"] == cu.ABGEBROCHEN
    assert events[0]["job_id"] == "accepted-job"
    assert "KeyboardInterrupt" in events[0]["fehler"]


def test_accepted_job_is_already_durable_before_first_status_poll(monkeypatch):
    evidence = []
    def poll():
        evidence.extend(db.list_client_updates())
        assert db.letzte_client_updates_je_quelle()["proof"]["status"] == cu.LAEUFT
        return done()
    row = source(monkeypatch, poll)
    result = run(row)
    assert evidence and evidence[0]["job_id"] == "accepted-job"
    assert evidence[0]["status"] == cu.LAEUFT
    assert result["status"] == cu.FERTIG


def test_unexpected_failure_retains_job_and_partial_counts(monkeypatch):
    calls = 0
    def poll():
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"state": "running", "phase": "tradelisten", "done": 3, "total": 10,
                    "ergebnis": {"tradelistenAktualisiert": 3}}
        raise ValueError("synthetic protocol failure")
    row = source(monkeypatch, poll)
    result = run(row)
    assert result["status"] == cu.FEHLER
    assert result["job_id"] == "accepted-job"
    event = db.list_client_updates()[0]
    assert event["job_id"] == "accepted-job" and event["tradelisten_aktualisiert"] == 3
    assert "ValueError" in event["fehler"]


def test_early_stop_is_persisted_and_final_callback_receives_it(monkeypatch):
    row = source(monkeypatch, done)
    updates = []
    result = run(row, callback=updates.append, stopped=lambda: True)
    assert result["status"] == cu.ABGEBROCHEN
    assert updates[-1]["status"] == cu.ABGEBROCHEN
    event = db.list_client_updates()[0]
    assert event["status"] == cu.ABGEBROCHEN
    assert any("Stop-Button" in text for text in event["hinweise"])


def test_db_failure_writes_durable_ignored_fallback_without_hiding_it(monkeypatch, caplog):
    row = source(monkeypatch, done)
    def unavailable(**kw):
        raise OSError("synthetic database unavailable")
    monkeypatch.setattr(cu.db, "store_client_update", unavailable)
    result = run(row)
    assert result["status"] == cu.FERTIG
    path = config.DATA_DIR / "client_updates_fallback.log"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert events[-1]["status"] == cu.FERTIG
    assert events[-1]["job_id"] == "accepted-job"
    assert "Chronik" in caplog.text


def test_success_has_one_terminal_record_and_a_start_trace(monkeypatch):
    row = source(monkeypatch, done)
    run(row)
    events = db.list_client_updates()
    assert sum(event["status"] in cu._TERMINAL for event in events) == 1
    assert any(event["status"] == cu.WARTET for event in events)


def test_system_exit_during_client_setup_is_recorded_and_still_propagates(monkeypatch):
    row = source(monkeypatch, done)
    def terminated(*a, **kw):
        raise SystemExit(7)
    monkeypatch.setattr(cu.quellen, "client_fuer_quelle", terminated)
    with pytest.raises(SystemExit) as error:
        run(row)
    assert error.value.code == 7
    assert db.list_client_updates()[0]["status"] == cu.ABGEBROCHEN


def test_final_callback_cannot_replace_original_interruption(monkeypatch):
    def interrupted():
        raise KeyboardInterrupt("original interruption")
    row = source(monkeypatch, interrupted)
    def callback(state):
        if state["status"] == cu.ABGEBROCHEN:
            raise SystemExit("secondary callback failure")
    with pytest.raises(KeyboardInterrupt, match="original interruption"):
        run(row, callback=callback)
    assert db.list_client_updates()[0]["status"] == cu.ABGEBROCHEN


def test_stop_after_acceptance_keeps_last_known_state_without_claiming_remote_cancellation(monkeypatch):
    polls = []
    def poll():
        polls.append(1)
        return {"state": "running", "phase": "tradelisten", "done": 4, "total": 10}
    row = source(monkeypatch, poll)
    result = run(row, stopped=lambda: bool(polls))
    assert result["status"] == cu.ABGEBROCHEN and result["done"] == 4
    event = db.list_client_updates()[0]
    assert event["job_id"] == "accepted-job" and not event["datenstand"]
    assert any("Client-Job kann weiterlaufen" in text for text in event["hinweise"])
