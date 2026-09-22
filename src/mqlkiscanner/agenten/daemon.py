# -*- coding: utf-8 -*-
"""Daemon-Steuerung aus der Streamlit-UI: Starten, Stoppen, Status.

Der Agenten-Daemon ist ein eigener Prozess (python -m mqlkiscanner.agenten).
Die UI startet ihn abgetrennt (DETACHED_PROCESS — er überlebt das Schließen
der App) und schreibt Stdout/Stderr in ein Logfile unter data/. Der Stopp
läuft kooperativ: Die UI setzt 'stop_wunsch' in der Steuerungstabelle, der
Daemon beendet sich beim nächsten Schleifendurchlauf sauber.

Der Aktivitätsstatus ist herzschlagbasiert (letzter_tick frisch?) statt
prozushackend — os.kill ist auf Windows zum Abfragen ungeeignet.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .. import config
from . import journal

LOG_DATEI = "agenten_daemon.log"

# Herzschlag gilt als frisch, wenn der letzte Tick nicht älter ist als
# dieser Wert (Scheduler-Tick 30 s → 3 Takte Puffer).
AKTIV_SCHWELLE_S = 120


def daemon_log_pfad() -> Path:
    return config.DATA_DIR / LOG_DATEI


def status() -> dict:
    """Aktueller Daemon-Zustand für die UI."""
    steuer = journal.steuerung_lesen()
    tick = steuer.get("letzter_tick") or ""
    # Leere PID nach sauberem Stopp: nicht aktiv, egal wie frisch der letzte
    # Herzschlag war (sonst zeigt ein beendeter Daemon bis zu 2 Minuten lang
    # 'läuft').
    pid = steuer.get("pid") or ""
    aktiv = False
    alter_s: int | None = None
    if pid and tick:
        try:
            delta = datetime.now() - datetime.fromisoformat(tick)
            alter_s = int(delta.total_seconds())
            aktiv = 0 <= alter_s <= AKTIV_SCHWELLE_S
        except ValueError:
            pass
    lauf = journal.letzter_lauf()
    return {
        "aktiv": aktiv,
        "alter_s": alter_s,
        "pid": pid,
        "gestartet": steuer.get("gestartet") or "",
        "letzter_tick": tick,
        "letzter_lauf": lauf,
        "log_pfad": str(daemon_log_pfad()),
    }


def starten(settings: dict | None = None) -> dict:
    """Daemon-Prozess abgetrennt starten; Settings-Freigabe setzen.

    Läuft bereits ein aktiver Daemon (frischer Herzschlag), passiert nichts
    (idempotent). Rückgabe beschreibt den Zustand nach dem Startversuch.
    """
    settings = settings if settings is not None else config.load_settings()
    st = status()
    if st["aktiv"]:
        return {"gestartet": False, "grund": "Daemon läuft bereits.",
                "pid": st["pid"]}
    settings["agenten_enabled"] = True
    config.save_settings(settings)
    log_pfad = daemon_log_pfad()
    log_pfad.parent.mkdir(parents=True, exist_ok=True)
    umgebung = dict(os.environ)
    # Wie die App selbst: src/ muss für '-m mqlkiscanner.agenten' liegen.
    quell_pfad = str(config.SRC)
    if quell_pfad not in umgebung.get("PYTHONPATH", "").split(os.pathsep):
        umgebung["PYTHONPATH"] = quell_pfad + os.pathsep + umgebung.get("PYTHONPATH", "")
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    with open(log_pfad, "ab") as log_handle:
        prozess = subprocess.Popen(
            [sys.executable, "-m", "mqlkiscanner.agenten"],
            cwd=str(config.ROOT), env=umgebung,
            stdout=log_handle, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    return {"gestartet": True, "pid": prozess.pid, "log": str(log_pfad)}


def stoppen(settings: dict | None = None) -> dict:
    """Kooperativer Stopp: Freigabe aus, Stopp-Wunsch setzen.

    Der Daemon beendet sich beim nächsten Tick (max. ~30 s). Läuft kein
    Daemon, wird nur der Zustand aufgeräumt.
    """
    settings = settings if settings is not None else config.load_settings()
    settings["agenten_enabled"] = False
    config.save_settings(settings)
    journal.steuerung_setzen("stop_wunsch", "1")
    return {"gestoppt": True,
            "hinweis": "Der Daemon beendet sich beim nächsten Tick (max. ~30 s)."}
