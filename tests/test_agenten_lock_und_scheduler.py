# -*- coding: utf-8 -*-
"""Lauf-Lock (prozessübergreifend) und Scheduler-Takt (Phase A)."""
import json
import time

import pytest

from mqlkiscanner import config
from mqlkiscanner.agenten import journal, lock, scheduler
from datetime import datetime


def test_lock_erwerb_und_freigabe(tmp_path):
    with lock.lauf_lock(tmp_path, "test"):
        status = lock.lock_status(tmp_path, "test")
        assert not status["frei"]
        assert status["pid"] > 0
    assert lock.lock_status(tmp_path, "test")["frei"]


def test_lock_blockt_zweiten_erwerb(tmp_path):
    with lock.lauf_lock(tmp_path, "test"):
        with pytest.raises(lock.LockBesetzt):
            with lock.lauf_lock(tmp_path, "test"):
                pass


def test_lock_namen_trennen(tmp_path):
    with lock.lauf_lock(tmp_path, "agenten"):
        with lock.lauf_lock(tmp_path, "gui_scan"):  # anderes Lock: erlaubt
            pass


def test_verwaistes_lock_wird_uebernommen(tmp_path, monkeypatch):
    monkeypatch.setattr(lock, "STALE_S", -1)  # alles gilt sofort als verwaist
    datei = tmp_path / "alt.lock"
    datei.write_text(json.dumps({"pid": 1, "ts": time.time()}), encoding="utf-8")
    with lock.lauf_lock(tmp_path, "alt"):  # übernimmt das verwaiste Lock
        pass
    assert lock.lock_status(tmp_path, "alt")["frei"]


def test_lock_status_verwaist_ohne_uebernahme(tmp_path, monkeypatch):
    monkeypatch.setattr(lock, "STALE_S", -1)  # deterministisch: immer verwaist
    datei = tmp_path / "alt2.lock"
    datei.write_text(json.dumps({"pid": 1, "ts": time.time()}), encoding="utf-8")
    status = lock.lock_status(tmp_path, "alt2")
    assert status["verwaist"] and not status["frei"]


# ── Scheduler ──────────────────────────────────────────────────────

def _settings(**overrides):
    werte = config.load_settings()
    werte.update({"agenten_start_zeit": "06:30"}, **overrides)
    return werte


def test_wochenende_ruht():
    sonntag = datetime(2026, 9, 27, 7, 0)  # Sonntag
    assert scheduler.faellige_rollen(sonntag, _settings()) == []


def test_vor_startzeit_nichts_faellig():
    frueh = datetime(2026, 9, 22, 5, 0)  # Dienstag, 05:00
    assert scheduler.faellige_rollen(frueh, _settings()) == []


def test_nach_startzeit_dirigent_faellig():
    vormittag = datetime(2026, 9, 22, 7, 0)  # Dienstag, 07:00
    assert scheduler.faellige_rollen(vormittag, _settings()) == \
        ["dirigent", "markt", "betreuer"]


def test_deaktivierte_rolle_nicht_faellig():
    vormittag = datetime(2026, 9, 22, 7, 0)
    assert scheduler.faellige_rollen(
        vormittag, _settings(agenten_dirigent_aktiv=False)) == ["markt", "betreuer"]
    assert scheduler.faellige_rollen(
        vormittag, _settings(agenten_betreuer_aktiv=False)) == ["dirigent", "markt"]


def test_nach_erfolgreichem_lauf_nicht_erneut_faellig():
    vormittag = datetime(2026, 9, 22, 7, 0)
    for rolle in ("dirigent", "markt", "betreuer"):
        journal.lauf_abschliessen(journal.lauf_starten(rolle, quelle="daemon"), "ok")
    assert scheduler.faellige_rollen(vormittag, _settings()) == []


def test_ungueltige_startzeit_faellt_auf_0630_zurueck():
    assert scheduler._start_minute(_settings(agenten_start_zeit="kaputt")) == 6 * 60 + 30


def test_tick_ohne_freigabe_fuehrt_nichts_aus():
    # Isolierte Umgebung ohne gespeicherte Settings: Freigabe default False.
    ergebnis = scheduler.tick(jetzt=datetime(2026, 9, 22, 7, 0))
    assert ergebnis["ausgefuehrt"] == []
    assert ergebnis["gesamt_enabled"] is False
    assert journal.list_laeufe() == []  # kein Lauf geschrieben


def test_tick_mit_freigabe_fuehrt_dirigent_aus():
    config.save_settings({**config.load_settings(), "agenten_enabled": True})
    ergebnis = scheduler.tick(jetzt=datetime(2026, 9, 22, 7, 0))
    assert ergebnis["gesamt_enabled"] is True
    ausgefuehrt = {e["rolle"]: e for e in ergebnis["ausgefuehrt"]}
    assert set(ausgefuehrt) == {"dirigent", "markt", "betreuer"}
    assert ausgefuehrt["dirigent"]["status"] == "ok"
    # Ohne laufendes Terminal: Markt übersprungen (Standard-Politik).
    assert ausgefuehrt["markt"]["status"] == "skipped"
    # Leere DB: Betreuer-Lauf ohne Kandidaten sauber durch (0 Läufe geschrieben).
    assert ausgefuehrt["betreuer"]["signale"] == 0
    rollen_gelaufen = {l["rolle"] for l in journal.list_laeufe()}
    assert rollen_gelaufen == {"dirigent", "markt"}  # Betreuer: kein Kandidat
    # Herzschlag wurde gesetzt
    assert journal.steuerung_lesen()["letzter_tick"]


def test_tick_schreibt_herzschlag_auch_ohne_freigabe():
    scheduler.tick(jetzt=datetime(2026, 9, 27, 7, 0))  # Sonntag, aus
    assert journal.steuerung_lesen()["letzter_tick"]


def test_stopp_gewuenscht_liest_steuerung():
    assert not scheduler.stopp_gewuenscht()
    journal.steuerung_setzen("stop_wunsch", "1")
    assert scheduler.stopp_gewuenscht()


# ------------------------------ Review 29.09.: Lock-PID + Doppel-Lauf-Guard

def test_lock_mit_lebender_pid_blockiert_auch_ueber_stale(tmp_path):
    """Lebender Halter blockiert unabhängig vom Lock-Alter — ein echter
    langer Scan wird nicht mehr von der 1-h-STALLE-Schwelle weggerissen."""
    import json as _json
    import time as _time
    import os as _os
    from mqlkiscanner.agenten import lock as _lock

    datei = tmp_path / "agenten_lauff.lock"
    datei.write_text(_json.dumps(
        {"pid": _os.getpid(), "ts": _time.time() - 2 * _lock.STALE_S}),
        encoding="utf-8")
    try:
        with _lock.lauf_lock(tmp_path):
            raise AssertionError("lebender Halter muss blockieren")
    except _lock.LockBesetzt as exc:
        assert "lebend" in str(exc)


def test_lock_mit_toter_pid_wird_sofort_uebernommen(tmp_path):
    import json as _json
    import time as _time
    from mqlkiscanner.agenten import lock as _lock

    datei = tmp_path / "agenten_lauff.lock"
    # PID existiert nicht (psutil bestätigt) → sofort übernehmen, auch frisch
    datei.write_text(_json.dumps(
        {"pid": 9_999_999, "ts": _time.time() - 30}), encoding="utf-8")
    with _lock.lauf_lock(tmp_path):
        pass  # Übernahme erfolgreich


def test_daemon_tick_ueberspringt_rolle_mit_aktivem_gui_lauf():
    """Doppel-Lauf-Guard: Läuft die Rolle (z. B. aus der GUI), überspringt
    der Daemon-Tick sie dokumentiert statt doppelt zu exportieren."""
    from mqlkiscanner.agenten import journal, scheduler

    lauf = journal.lauf_starten("markt", quelle="gui")
    ergebnis = {"ausgefuehrt": []}
    scheduler._rolle_ausfuehren("markt", {}, ergebnis, log=lambda *_: None)
    eintrag = ergebnis["ausgefuehrt"][0]
    assert eintrag["rolle"] == "markt"
    assert eintrag["status"] == "skipped"
    assert "läuft bereits" in eintrag["grund"]
    journal.lauf_abschliessen(lauf, "ok")
