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


# ------------------------------ Review Qwen 29.09.: M1/M2 Lock-Obergrenze

def test_lock_recycelte_pid_wird_uebernommen(tmp_path):
    """M1: Dieselbe PID, aber ein NEUER Prozess (Windows-PID-Recycling nach
    Crash) → sofort übernehmen, obwohl psutil die PID als lebend meldet."""
    import os as _os
    import time as _time
    import json as _json
    import psutil
    from mqlkiscanner.agenten import lock as _lock

    datei = tmp_path / "agenten_lauff.lock"
    start = psutil.Process(_os.getpid()).create_time() - 1000.0
    datei.write_text(_json.dumps(
        {"pid": _os.getpid(), "ts": _time.time() - 30, "start": start}),
        encoding="utf-8")
    with _lock.lauf_lock(tmp_path):
        pass  # Übernahme erfolgreich


def test_lock_ueber_max_s_wird_uebernommen(tmp_path):
    """M1: Auch ein verifiziert lebender, DERSELBE Halter blockiert nie über
    MAX_S (24 h) — kein Lock blockiert ewig (Crash + Recycling-Lücke)."""
    import os as _os
    import time as _time
    import json as _json
    import psutil
    from mqlkiscanner.agenten import lock as _lock

    datei = tmp_path / "agenten_lauff.lock"
    datei.write_text(_json.dumps(
        {"pid": _os.getpid(), "ts": _time.time() - _lock.MAX_S - 60,
         "start": psutil.Process(_os.getpid()).create_time()}),
        encoding="utf-8")
    with _lock.lauf_lock(tmp_path):
        pass


def test_lock_korrupte_datei_wird_uebernommen(tmp_path):
    """M1: Unlesbare Lock-Datei (Absturz mitten im Schreiben) → ts=0 → das
    Alter entscheidet → sofort übernehmen, nicht ewig blockieren."""
    from mqlkiscanner.agenten import lock as _lock

    (tmp_path / "agenten_lauff.lock").write_text("kein json", encoding="utf-8")
    with _lock.lauf_lock(tmp_path):
        pass


# ------------------------------ Review Qwen 29.09.: M4/M5 Guard

def test_guard_max_alter_betreuer_2h_andere_4h():
    """M4: Der Guard nutzt dieselbe Verwaisten-Grenze wie Digest/fällig-
    Prüfung (Betreuer 2 h), alle anderen Rollen 4 h."""
    assert scheduler._guard_max_alter_s("betreuer") == 2 * 3600
    for rolle in ("dirigent", "markt", "melder", "chef"):
        assert scheduler._guard_max_alter_s(rolle) == 4 * 3600


def test_guard_betreuer_3h_verwaist_laeuft_nochmal(monkeypatch):
    """M4: Ein 3 h alter Betreuer-'laeuft'-Row (Digest nennt das verwaist)
    blockiert den Daemon-Guard nicht mehr — die Rolle läuft wieder."""
    from datetime import timedelta
    from mqlkiscanner import db
    from mqlkiscanner.agenten import betreuer

    lauf_id = journal.lauf_starten("betreuer", quelle="gui")
    with db._connect() as conn:
        vor3h = (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE agenten_laeufe SET start=? WHERE id=?",
                     (vor3h, lauf_id))

    aufgerufen = {}

    def _fake_tageslauf(**kwargs):
        aufgerufen["ja"] = True
        return {"signale": 0, "zusammenfassung": "Test"}

    monkeypatch.setattr(betreuer, "tageslauf", _fake_tageslauf)
    ergebnis = {"ausgefuehrt": []}
    scheduler._rolle_ausfuehren("betreuer", {}, ergebnis, log=lambda *_: None)
    assert aufgerufen.get("ja") is True, "3 h alter Row darf den Guard nicht mehr blockieren"
    assert ergebnis["ausgefuehrt"][0]["rolle"] == "betreuer"


@pytest.fixture(autouse=True)
def _guard_vermerk_reset():
    """De-Dup-Speicher leeren — die Test-DB ist je Test neu (IDs starten bei
    1), der prozessweite Vermerk würde sonst den frischen Halter überspringen."""
    scheduler._guard_skip_vermerkt.clear()
    yield


def test_guard_skip_meldet_einmal_je_blockierendem_lauf():
    """M5: Der Guard-Skip landet im Postfach (sichtbar) — genau EINMAL je
    blockierendem Lauf trotz 30-s-Tick — und schreibt KEINE agenten_laeufe-
    Zeile ('skipped' zählt als Terminal-Status und würde die Rolle sonst
    für heute stilllegen)."""
    lauf = journal.lauf_starten("markt", quelle="gui")
    ergebnis = {"ausgefuehrt": []}
    scheduler._rolle_ausfuehren("markt", {}, ergebnis, log=lambda *_: None)
    scheduler._rolle_ausfuehren("markt", {}, ergebnis, log=lambda *_: None)

    meldungen = journal.meldungen_lesen(typ="laufsperre")
    assert len(meldungen) == 1, "eine Meldung je blockierendem Lauf, kein Tick-Spam"
    assert f"lauf#{lauf}" in str(meldungen[0].get("quellen", ""))
    # Kein Journal-Lauf für den Skip (der GUI-'laeuft'-Row ist der einzige):
    assert len(journal.list_laeufe()) == 1
