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
    """Welche Rollen sind JETZT fällig?

    Werktags die Tageskette: Dirigent zur Startzeit, Markt +5, Betreuer
    +15, Melder-Digest +40. Sonntags abends der Chefermittler; monatlich
    zusätzlich am Full-Scan-Tag. Solange ein längerer Lauf arbeitet
    (Betreuer, autonomer Scan), bleiben Digest/Lagebericht UNFÄLLIG statt
    alle 30 s einen Skip-Lauf ins Journal zu schreiben — sie werden im
    nächsten Tick wieder geprüft.
    """
    rollen: list[str] = []
    minute = jetzt.hour * 60 + jetzt.minute
    start = _start_minute(settings)
    if jetzt.weekday() < 5:  # Werktagskette
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
        if (nicht_deaktiviert(settings, "melder")
                and minute >= start + 40
                and not journal.lauf_heute_erfolgreich("melder", "daemon")
                and not journal.aktive_laeufe("betreuer")):
            rollen.append("melder")
    # Chefermittler (Phase E): sonntags abends UND am Full-Scan-Tag des
    # Monats — er wartet auf laufende Scans (aktive Dirigent-Läufe).
    from . import chef  # spät: kein Kreisimport
    if nicht_deaktiviert(settings, "chef"):
        from . import scan_launcher
        chef_zeit = (jetzt.weekday() == 6 and jetzt.hour >= chef.ABEND_STUNDE)
        monats_tag = (scan_launcher.scan_heute_gestartet(
            "full", tag=jetzt.date().isoformat())
            and minute >= start + 150)
        if ((chef_zeit or monats_tag)
                and not journal.lauf_heute_erfolgreich("chef", "daemon")
                and not _aktiver_scan()):
            rollen.append("chef")
    return rollen


def _aktiver_scan() -> bool:
    """Läuft gerade ein autonomer Scan (Dirigent-Daemon-Lauf)?"""
    return any(l["quelle"] == "daemon"
               for l in journal.aktive_laeufe("dirigent"))


def faellige_scans(jetzt: datetime, settings: dict) -> list[str]:
    """Autonome Scan-Anstöße (Phase E): Sonntag Gelb/Grün, Monatserster
    Werktag Full — je einmal, mit Monats-Merker gegen Wiederholung."""
    from . import scan_launcher
    start = _start_minute(settings)
    minute = jetzt.hour * 60 + jetzt.minute
    tag = jetzt.date().isoformat()
    monat = jetzt.strftime("%Y-%m")
    modi: list[str] = []
    if (jetzt.weekday() == 6 and jetzt.hour >= 12
            and not scan_launcher.scan_heute_gestartet("gelbgruen", tag=tag)):
        modi.append("gelbgruen")
    if (jetzt.day <= 7 and jetzt.weekday() < 5 and minute >= start + 60
            and not scan_launcher.scan_monat_gestartet("full", monat=monat)):
        modi.append("full")
    return modi


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
    from . import betreuer, chef, markt, melder, scan_launcher  # spät: Kreisimporte
    # Ampelwechsel-Watcher: JEDER Tick (bemerkt auch Wechsel aus GUI-Scans),
    # idempotent über den letzten bearbeiteten Wechsel in der Steuerung.
    try:
        melder.pruefe_neue_wechsel(log=log)
    except Exception as exc:
        log(f"Wechsel-Watcher fehlgeschlagen (nächster Tick): {exc}")
    # Autonome Scans (Phase E): je ein Thread; nie zwei Scans parallel.
    try:
        modi = faellige_scans(jetzt, settings)
    except Exception as exc:
        modi = []
        log(f"Scan-Takt-Prüfung fehlgeschlagen (nächster Tick): {exc}")
    if modi and not _aktiver_scan():
        modus = modi[0]
        log(f"Dirigent stößt autonomen {modus}-Scan an …")
        scan_launcher.starte_scan_thread(modus, log=log)
        ergebnis["ausgefuehrt"].append({"rolle": "dirigent",
                                        "scan": modus,
                                        "status": "gestartet"})
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
        elif rolle == "melder":
            lauf = melder.tagesdigest(quelle="daemon", log=log,
                                      settings=settings)
            ergebnis["ausgefuehrt"].append(
                {"rolle": "melder", "status": lauf["status"]})
        elif rolle == "chef":
            lauf = chef.lagebericht(quelle="daemon", log=log,
                                    settings=settings)
            ergebnis["ausgefuehrt"].append(
                {"rolle": "chef", "status": lauf["status"]})
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
