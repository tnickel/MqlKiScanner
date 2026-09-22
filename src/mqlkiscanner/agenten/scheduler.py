# -*- coding: utf-8 -*-
"""Scheduler des Agenten-Daemons: Takte berechnen, Herzschlag, Stopp.

Phase A (doc/19 §13): ein Takt — der Dirigent-Tageslauf werktags zur
konfigurierten Startzeit. Weitere Rollen werden in den Phasen B–E an
dieser Stelle ergänzt; die Takt-Regeln bleiben Code.

Stopp-Mechanik: Die UI setzt 'stop_wunsch' in der Steuerungstabelle; der
Daemon sieht das beim nächsten Schleifendurchlauf (TICK_S) und beendet
sich sauber. 'agenten_enabled' in den Settings ist der Freigabeschalter —
ist er aus, läuft die Schleife leer bis zum Stopp.
"""
from __future__ import annotations

import time
from datetime import datetime

from .. import config
from . import journal


def _start_minute(settings: dict) -> int:
    """Konfigurierte Startzeit 'HH:MM' als Minute des Tages (Fehler: 6:30)."""
    try:
        stunde, minute = str(settings.get("agenten_start_zeit", "06:30")).split(":")
        return int(stunde) * 60 + int(minute)
    except ValueError:
        return 6 * 60 + 30


def faellige_rollen(jetzt: datetime, settings: dict) -> list[str]:
    """Welche Rollen sind JETZT fällig? Phasen A–C, werktags:
    Dirigent zur Startzeit, Marktbeobachter +5 min, Betreuer +15 min.

    Fällig heißt: Werktag, Zeitpunkt erreicht und heute noch kein
    erfolgreicher Daemon-Lauf der Rolle.
    """
    rollen: list[str] = []
    if jetzt.weekday() >= 5:
        return rollen  # Wochenende: Markt ruht (doc/19 §9)
    minute = jetzt.hour * 60 + jetzt.minute
    start = _start_minute(settings)
    if (nicht_deaktiviert(settings, "dirigent")
            and minute >= start
            and not journal.lauf_heute_erfolgreich("dirigent", "daemon")):
        rollen.append("dirigent")
    if (nicht_deaktiviert(settings, "markt")
            and minute >= start + 5
            and not journal.lauf_heute_erfolgreich("markt", "daemon")):
        rollen.append("markt")
    if (nicht_deaktiviert(settings, "betreuer")
            and minute >= start + 15
            and not journal.lauf_heute_erfolgreich("betreuer", "daemon")):
        rollen.append("betreuer")
    return rollen


def nicht_deaktiviert(settings: dict, rolle: str) -> bool:
    return bool(settings.get(f"agenten_{rolle}_aktiv", True))


def tick(jetzt: datetime | None = None, log=print) -> dict:
    """Ein Schleifendurchlauf: Herzschlag → fällige Rollen ausführen."""
    from . import dirigent  # spät: kein Kreisimport beim Paket-Import
    jetzt = jetzt or datetime.now()
    settings = config.load_settings()
    journal.steuerung_setzen("letzter_tick",
                             jetzt.isoformat(sep=" ", timespec="seconds"))
    ergebnis = {"tick": jetzt.isoformat(sep=" ", timespec="seconds"),
                "ausgefuehrt": [], "gesamt_enabled":
                bool(settings.get("agenten_enabled", False))}
    if not settings.get("agenten_enabled", False):
        return ergebnis
    from . import betreuer, markt  # spät: kein Kreisimport beim Paket-Import
    for rolle in faellige_rollen(jetzt, settings):
        if rolle == "dirigent":
            lauf = dirigent.tageslauf(quelle="daemon", log=log)
            ergebnis["ausgefuehrt"].append({"rolle": "dirigent",
                                            "status": lauf["status"]})
        elif rolle == "markt":
            lauf = markt.tageslauf(quelle="daemon", log=log,
                                   settings=settings)
            ergebnis["ausgefuehrt"].append(
                {"rolle": "markt", "status": lauf["status"],
                 "grund": lauf.get("grund", "")})
        elif rolle == "betreuer":
            lauf = betreuer.tageslauf(quelle="daemon", log=log,
                                      settings=settings)
            ergebnis["ausgefuehrt"].append(
                {"rolle": "betreuer", "signale": lauf["signale"],
                 "zusammenfassung": lauf["zusammenfassung"]})
    return ergebnis


def stopp_gewuenscht() -> bool:
    return journal.steuerung_lesen().get("stop_wunsch") == "1"


def schleife(tick_s: int = 30, log=print) -> None:
    """Dauerschleife des Daemons — kehrt nur bei Stopp-Wunsch zurück."""
    journal.steuerung_setzen("stop_wunsch", "0")
    journal.steuerung_setzen("pid", str(_eigene_pid()))
    journal.steuerung_setzen("gestartet",
                             datetime.now().isoformat(sep=" ", timespec="seconds"))
    log("Agenten-Daemon gestartet (Phase A: Dirigent-Takt).")
    try:
        while not stopp_gewuenscht():
            try:
                tick(log=log)
            except Exception as exc:  # ein Tick darf den Daemon nicht beenden
                log(f"Tick fehlgeschlagen (weiter im nächsten Intervall): {exc}")
            time.sleep(tick_s)
    finally:
        journal.steuerung_setzen("letzter_tick",
                                 datetime.now().isoformat(sep=" ",
                                                          timespec="seconds"))
        journal.steuerung_setzen("pid", "")
        log("Agenten-Daemon beendet.")


def _eigene_pid() -> int:
    import os
    return os.getpid()
