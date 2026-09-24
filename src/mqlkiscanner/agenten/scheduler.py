# -*- coding: utf-8 -*-
"""Scheduler des Agenten-Daemons: Takte berechnen, Herzschlag, Stopp.

Tag und Uhrzeit je Job kommen aus den Settings (agenten_{job}_tag/_zeit,
editierbar über die Automatik-Seite „Konfiguration → Automatik" — Muster
Goldscanner); ohne explizite Keys gilt das bisherige Verhalten (werktags
zur Startzeit, Chef/Teilscan sonntags, Full-Scan am ersten Werktag).
Der Daemon liest den Plan je Tick neu — Änderungen greifen ohne Neustart.

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


# Wochentag-Wörter der Automatik-Seite (Muster Goldscanner: Tag + Zeit je Job).
WOCHENTAGE = {"Montag": 0, "Dienstag": 1, "Mittwoch": 2, "Donnerstag": 3,
              "Freitag": 4, "Samstag": 5, "Sonntag": 6}
TAG_AUSWAHL = ["Werktags", "Täglich"] + list(WOCHENTAGE)


def _normalisiere_tag(tag: str) -> str:
    """Settings-Wert → Modus 'werktags'/'taeglich'/'montag'…/'sonntag'
    ('' oder Unbekanntes → '')."""
    wert = str(tag).strip().lower().replace("ä", "ae")
    if wert in ("werktags", "taeglich"):
        return wert
    if wert in {k.lower() for k in WOCHENTAGE}:
        return wert
    return ""


def _minute_aus_zeit(zeit: str, fallback: int) -> int:
    """'HH:MM' als Minute des Tages; ungültige Werte → fallback."""
    try:
        stunde, minute = str(zeit).strip().split(":")
        return int(stunde) * 60 + int(minute)
    except ValueError:
        return fallback


def job_termin(settings: dict, job: str) -> tuple[str, int]:
    """Wochentag-Modus + Termin (Minute des Tages) je Job.

    Ohne explizite Settings gilt das bisherige Taktverhalten: Rollen
    werktags zur Startzeit mit festen Abständen (Dirigent +0, Markt +5,
    Betreuer +15, Melder +40), Chef und Teilscan sonntags, Full-Scan am
    ersten Werktag des Monats. Explizite Keys `agenten_{job}_tag` /
    `agenten_{job}_zeit` (Automatik-Seite) überschreiben das; ungültige
    Werte fallen auf die Defaults zurück. Wird je Tick neu gelesen —
    Änderungen greifen ohne Daemon-Neustart.
    """
    start = _start_minute(settings)
    defaults = {
        "dirigent": ("werktags", start),
        "markt": ("werktags", start + 5),
        "betreuer": ("werktags", start + 15),
        "melder": ("werktags", start + 40),
        "chef": ("sonntag", 18 * 60),
        "teilscan": ("sonntag", 12 * 60),
        "fullscan": ("monatserster", start + 60),
    }
    default_tag, default_minute = defaults[job]
    tag = _normalisiere_tag(settings.get(f"agenten_{job}_tag", ""))
    minute = default_minute
    roh = settings.get(f"agenten_{job}_zeit")
    if roh:
        minute = _minute_aus_zeit(roh, default_minute)
    return (tag or default_tag), minute


def _tag_passt(jetzt: datetime, modus: str) -> bool:
    if modus == "werktags":
        return jetzt.weekday() < 5
    if modus == "taeglich":
        return True
    wt = WOCHENTAGE.get(modus.capitalize())
    return wt is not None and jetzt.weekday() == wt


def faellige_rollen(jetzt: datetime, settings: dict) -> list[str]:
    """Welche Rollen sind JETZT fällig?

    Tag und Uhrzeit je Rolle kommen aus job_termin (Defaults: werktags
    Kette zur Startzeit, Chef sonntags abends). Solange ein längerer Lauf
    arbeitet (Betreuer, autonomer Scan), bleiben Digest/Lagebericht
    UNFÄLLIG statt alle 30 s einen Skip-Lauf ins Journal zu schreiben —
    sie werden im nächsten Tick wieder geprüft.
    """
    rollen: list[str] = []
    minute = jetzt.hour * 60 + jetzt.minute
    for rolle in ("dirigent", "markt", "betreuer", "melder"):
        if not nicht_deaktiviert(settings, rolle):
            continue
        modus, termin = job_termin(settings, rolle)
        if not _tag_passt(jetzt, modus) or minute < termin:
            continue
        if journal.lauf_heute_erfolgreich(rolle, "daemon"):
            continue
        if rolle == "melder" and journal.aktive_laeufe("betreuer"):
            continue
        rollen.append(rolle)
    # Chefermittler (Phase E): sonntags abends UND am Full-Scan-Tag des
    # Monats (fest: Startzeit + 150) — er wartet auf laufende Scans
    # (aktive Dirigent-Läufe).
    from . import scan_launcher
    if nicht_deaktiviert(settings, "chef"):
        modus, termin = job_termin(settings, "chef")
        chef_zeit = modus != "monatserster" and _tag_passt(jetzt, modus) \
            and minute >= termin
        start = _start_minute(settings)
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
    return any(eintrag["quelle"] == "daemon"
               for eintrag in journal.aktive_laeufe("dirigent"))


def faellige_scans(jetzt: datetime, settings: dict) -> list[str]:
    """Autonome Scan-Anstöße (Phase E): Teilscan am konfigurierten Wochentag
    (Default Sonntag ab 12:00), Full-Scan am ersten Werktag des Monats
    (Tag fest, Uhrzeit konfigurierbar) — je einmal, mit Monats-/Tages-Merker
    gegen Wiederholung."""
    from . import scan_launcher
    start = _start_minute(settings)
    minute = jetzt.hour * 60 + jetzt.minute
    tag = jetzt.date().isoformat()
    monat = jetzt.strftime("%Y-%m")
    modi: list[str] = []
    teil_modus, teil_termin = job_termin(settings, "teilscan")
    if (_tag_passt(jetzt, teil_modus) and minute >= teil_termin
            and not scan_launcher.scan_heute_gestartet("gelbgruen", tag=tag)):
        modi.append("gelbgruen")
    _, full_termin = job_termin(settings, "fullscan")
    if (jetzt.day <= 7 and jetzt.weekday() < 5 and minute >= full_termin
            and not scan_launcher.scan_monat_gestartet("full", monat=monat)):
        modi.append("full")
    return modi


def nicht_deaktiviert(settings: dict, rolle: str) -> bool:
    return bool(settings.get(f"agenten_{rolle}_aktiv", True))


def tick(jetzt: datetime | None = None, log=print) -> dict:
    """Ein Schleifendurchlauf: Herzschlag → fällige Rollen ausführen."""
    jetzt = jetzt or datetime.now()
    settings = config.load_settings()
    journal.steuerung_setzen("letzter_tick",
                             jetzt.isoformat(sep=" ", timespec="seconds"))
    ergebnis = {"tick": jetzt.isoformat(sep=" ", timespec="seconds"),
                "ausgefuehrt": [], "gesamt_enabled":
                bool(settings.get("agenten_enabled", False))}
    if not settings.get("agenten_enabled", False):
        return ergebnis
    from . import melder, scan_launcher  # spät: Kreisimporte
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
        try:
            _rolle_ausfuehren(rolle, settings, ergebnis, log)
        except Exception as exc:  # eine Rolle darf die anderen nicht blockieren
            log(f"Rolle {rolle} fehlgeschlagen (nächster Tick): {exc}")
            ergebnis["ausgefuehrt"].append({"rolle": rolle,
                                            "status": "fehler",
                                            "grund": str(exc)})
    return ergebnis


def _rolle_ausfuehren(rolle: str, settings: dict, ergebnis: dict, log) -> None:
    from . import betreuer, chef, dirigent, markt, melder  # spät: Kreisimporte
    if rolle == "dirigent":
        lauf = dirigent.tageslauf(quelle="daemon", log=log)
        ergebnis["ausgefuehrt"].append({"rolle": "dirigent",
                                        "status": lauf["status"]})
    elif rolle == "markt":
        lauf = markt.tageslauf(quelle="daemon", log=log, settings=settings)
        ergebnis["ausgefuehrt"].append(
            {"rolle": "markt", "status": lauf["status"],
             "grund": lauf.get("grund", "")})
    elif rolle == "betreuer":
        lauf = betreuer.tageslauf(quelle="daemon", log=log, settings=settings)
        ergebnis["ausgefuehrt"].append(
            {"rolle": "betreuer", "signale": lauf["signale"],
             "zusammenfassung": lauf["zusammenfassung"]})
    elif rolle == "melder":
        lauf = melder.tagesdigest(quelle="daemon", log=log, settings=settings)
        ergebnis["ausgefuehrt"].append(
            {"rolle": "melder", "status": lauf["status"]})
    elif rolle == "chef":
        lauf = chef.lagebericht(quelle="daemon", log=log, settings=settings)
        ergebnis["ausgefuehrt"].append(
            {"rolle": "chef", "status": lauf["status"]})


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
