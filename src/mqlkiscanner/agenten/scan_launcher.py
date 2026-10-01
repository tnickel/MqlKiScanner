# -*- coding: utf-8 -*-
"""Autonome Scan-Anstöße (Phase E, doc/19 §9): der Dirigent startet Scans.

Der Launcher führt den GLEICHEN Pipeline-Code aus wie die Scan-Seite —
identische Modus-Verträge (Teilscan erzwingt alle KI-Stufen), identische
Persistenz in DB und Ampel-Chronik. Nur die Oberflächen-Stationen (Forts-
schritts-Rendering, Downloader-Abgleich als Station 6) entfallen; der
Abgleich bleibt der Ergebnisseite überlassen.

Läufe können STUNDEN dauern (Full-Scan mit Exporten und Berichten) — der
Launcher läuft deshalb in einem Daemon-Thread neben dem Scheduler, der
Herzschlag bleibt frisch, und der Chefermittler wartet auf den Abschluss.
"""
from __future__ import annotations

import threading
import time
from datetime import date

from .. import config, fix_signale, pipeline, scan_fortschritt
from ..mql5.session import Mql5Session
from . import journal, lock

# Scan-Abschluss als eigene Meldungsart im Postfach (Prio 1 = Info).
MELDUNG_TYP = "scan"


def scan_heute_gestartet(modus: str, tag: str | None = None) -> bool:
    """Lief der Modus an diesem Tag bereits? (Default: heute; der Scheduler
    übergibt den Tag des geprüften Zeitpunkts — Tests nutzen andere Tage.)"""
    return journal.steuerung_lesen().get(f"scan_{modus}_letzter") == \
        (tag or date.today().isoformat())


def _scan_vermerken(modus: str) -> None:
    journal.steuerung_setzen(f"scan_{modus}_letzter", date.today().isoformat())


def scan_monat_gestartet(modus: str, monat: str | None = None) -> bool:
    """Lief der Modus in diesem Monat bereits? (Full-Scan, einmal je Monat)"""
    return journal.steuerung_lesen().get(f"scan_{modus}_monat") == \
        (monat or date.today().strftime("%Y-%m"))


def _scan_monat_vermerken(modus: str) -> None:
    journal.steuerung_setzen(f"scan_{modus}_monat",
                             date.today().strftime("%Y-%m"))


def starte_scan(modus: str, quelle: str = "daemon", log=print) -> dict:
    """Ein vollständiger Scan-Lauf headless ('gelbgruen' | 'full').

    Synchron ausführbar (CLI-Test) — im Daemon-Betrieb über starte_scan_thread.
    """
    assert modus in ("gelbgruen", "full")
    settings = config.load_settings()
    if modus == "gelbgruen":
        # Modus-Vertrag (Nutzer-Vorgabe, identisch zur Scan-Seite): alle
        # KI-Stufen erzwingen, Laufzeit-Toggles gelten nicht.
        settings.update({"nur_neue": False, "berichte_neu": True,
                         "llm_stufe1": True, "llm_stufe2": True})
    lauf_id = journal.lauf_starten("dirigent", quelle=quelle)
    modus_name = "Teilscan (Gelb/Grün)" if modus in ("gelbgruen", "gelb_gruen") else "Full-Scan (Gesamtkatalog)"
    try:
        with lock.lauf_lock(config.DATA_DIR):
            ergebnis = _scan_innerhalb(modus, settings, lauf_id, log)
        resultat = ergebnis.get("resultat") or ergebnis["zusammenfassung"]
        # F4 (Fremd-Review 01.10.): Ein Login-Abbruch/leerer Scope ist KEIN
        # erfolgreicher Lauf — Status "skipped" darf den Tages-/Monats-
        # merker NICHT setzen, sonst gilt der Monat als versorgt, obwohl
        # null Prüfungen liefen (Gegenprobe bestätigte genau das).
        if ergebnis.get("status") == "skipped":
            aktion = f"Autonomer {modus_name} übersprungen"
            journal.lauf_abschliessen(lauf_id, "skipped", ergebnis["zusammenfassung"],
                                      aktion=aktion, resultat=resultat)
            journal.meldung_speichern(
                MELDUNG_TYP, f"Scan {modus} ({modus_name}) ÜBERSPRUNGEN",
                resultat, prioritaet=2, quellen=[f"lauf#{lauf_id}"])
            log(f"Scan {modus} übersprungen: {resultat} — Merker NICHT gesetzt.")
            return {"status": "skipped", "lauf_id": lauf_id, "aktion": aktion,
                    "resultat": resultat, **{k: v for k, v in ergebnis.items()
                                             if k != "status"}}
        aktion = f"Autonomer {modus_name} durchgeführt"
        journal.lauf_abschliessen(lauf_id, "ok", ergebnis["zusammenfassung"],
                                  aktion=aktion, resultat=resultat)
        journal.meldung_speichern(
            MELDUNG_TYP, f"Scan {modus} ({modus_name}) abgeschlossen",
            resultat, prioritaet=1,
            quellen=[f"lauf#{lauf_id}"])
        log(f"Scan {modus} abgeschlossen: {resultat}")
        _scan_vermerken(modus)
        if modus == "full":
            _scan_monat_vermerken(modus)
        return {"status": "ok", "lauf_id": lauf_id, "aktion": aktion,
                "resultat": resultat, **ergebnis}
    except lock.LockBesetzt as exc:
        pid_info = f" (PID {exc.pid})" if getattr(exc, "pid", None) else ""
        aktion = f"Autonomer {modus_name}"
        resultat = f"Übersprungen: Vorheriger Lauf{pid_info} war noch aktiv (Kollisionsschutz)."
        grund = f"Lauf-Lock belegt — Scan {modus} übersprungen: {exc}"
        journal.lauf_abschliessen(lauf_id, "skipped", grund,
                                  aktion=aktion, resultat=resultat)
        return {"status": "skipped", "grund": grund, "lauf_id": lauf_id,
                "aktion": aktion, "resultat": resultat}
    except Exception as exc:  # ein Scan-Fehler beendet den Daemon nicht
        journal.schritt_protokollieren(lauf_id, "dirigent", "scan",
                                       status="fehler",
                                       detail={"fehler": str(exc),
                                               "modus": modus})
        journal.lauf_abschliessen(lauf_id, "fehler", str(exc))
        journal.meldung_speichern(
            MELDUNG_TYP, f"Scan {modus} FEHLGESCHLAGEN", str(exc),
            prioritaet=2, quellen=[f"lauf#{lauf_id}"])
        log(f"Scan {modus} fehlgeschlagen: {exc}")
        # Tages-Merker auch im Fehlerfall: kein 30-Sekunden-Retry-Loop.
        # Der MONATS-Merker bleibt offen — ein fehlgeschlagener Full-Scan
        # wiederholt sich am nächsten Tag im 1.-Werktag-Fenster.
        _scan_vermerken(modus)
        return {"status": "fehler", "grund": str(exc), "lauf_id": lauf_id}


def _scan_innerhalb(modus: str, settings: dict, lauf_id: int, log) -> dict:
    """Die Stationen der Scan-Seite, headless: Listen → Kandidaten →
    Auswahl → Forensik → KI-Berichte → Portfolio."""
    pipe = pipeline.ScanPipeline(settings, quelle=modus)
    start_ts = time.time()

    def _f(station: str, done: int, total: int, detail: str = "") -> None:
        """Live-Fortschritt für die Agenten-Seite (Nutzer-Wunsch 30.09.:
        Balken + Schritt + Restanzeige) — atomar in die Statusdatei."""
        try:
            scan_fortschritt.aktualisieren(station, done, total, detail,
                                           start_ts, modus)
        except Exception:   # Anzeige darf den Scan nie brechen
            pass

    _f("listen", 0, 1, "Signallisten werden geholt …")
    journal.schritt_protokollieren(lauf_id, "dirigent", "scan",
                                   detail={"modus": modus, "station": "listen"})
    signale = pipe.crawl(on_progress=lambda *a: None,
                         log=lambda m: log(f"  [listen] {m}"))
    _f("kandidaten", 0, 1, "Vorfilter und Auswahl …")
    kandidaten = pipe.build_candidates(
        signale, log=lambda m: log(f"  [kandidaten] {m}"))

    if modus == "gelbgruen":
        # Modus-Vertrag: nur aktuell 🟢/🟡 laut DB-Stand — Ampel-Logik
        # exakt wie die Ergebnis-Ansicht (results_from_db). Fix-IDs sind
        # zusätzlich IMMER im Scope (fix_signale.teilscan_ziel_ids).
        alt = pipeline.results_from_db(settings)
        ziel_ids = fix_signale.teilscan_ziel_ids(alt, settings)
        vorher = len(kandidaten)
        kandidaten = [c for c in kandidaten if c["id"] in ziel_ids]
        log(f"Teilscan: {len(kandidaten)} von {vorher} Kandidaten "
            "sind aktuell 🟢/🟡 oder Fix-ID.")

    # Fix-Kandidaten vorne (Grenze trifft sie nie); JE Quelle die top_n
    # abonnentenstärksten Kandidaten (Nutzer-Wunsch 29.09.: „30 von jedem").
    scope, export_infos = fix_signale.waehle_fuer_export(
        kandidaten, int(settings.get("top_n_export", 30)), settings)
    log("Auswahl je Quelle: " + " · ".join(
        f"{i['quelle']}: {i['genommen']}/{i['angeboten']}" for i in export_infos))
    if not scope:
        grund = (f"Keine zu prüfenden Kandidaten (Modus {modus}) — "
                 "kein Login/Export nötig.")
        journal.schritt_protokollieren(lauf_id, "dirigent", "scan",
                                       status="skipped",
                                       detail={"grund": grund, "modus": modus})
        return {"status": "skipped", "zusammenfassung": grund,
                "geprueft": 0, "berichte": 0}

    # F6 (Fremd-Review 01.10.): MQL5-Login ist nur fuer Direkt-Exporte
    # noetig — Kandidaten aus Datenquellen (quelle_kuerzel gesetzt) kommen
    # ohne MQL5-Kontakt durch die Forensik. Ein reiner Quellenlauf darf
    # nicht an fehlenden Credentials scheitern.
    braucht_mql5 = any(not c.get("quelle_kuerzel") for c in scope)
    session = None
    if braucht_mql5:
        session = Mql5Session(settings)
        if not session.has_credentials:
            grund = ("Kein MQL5-Login konfiguriert — für MQL5-Direkt-Kandidaten "
                     "nicht möglich (reine Quellen-Kandidaten wären möglich).")
            journal.schritt_protokollieren(lauf_id, "dirigent", "scan",
                                           status="skipped",
                                           detail={"grund": grund})
            return {"status": "skipped", "zusammenfassung": grund,
                    "geprueft": 0, "berichte": 0}
        from ..mql5.browser_session import ensure_mql5_cookies
        if not ensure_mql5_cookies(settings, session,
                                   log=lambda m: log(f"  [login] {m}")):
            grund = "MQL5-Login fehlgeschlagen — Scan abgebrochen (Login prüfen)."
            journal.schritt_protokollieren(lauf_id, "dirigent", "scan",
                                           status="skipped",
                                           detail={"grund": grund})
            return {"status": "skipped", "zusammenfassung": grund,
                    "geprueft": 0, "berichte": 0}
    else:
        log("Keine MQL5-Direkt-Kandidaten im Scope — MQL5-Login nicht nötig "
            "(reiner Quellenlauf).")

    journal.schritt_protokollieren(
        lauf_id, "dirigent", "scan",
        detail={"modus": modus, "station": "forensik",
                "kandidaten": [c["id"] for c in scope]})
    ergebnisse = []
    try:
        # L12 (Review-Handoff 29.09.): jede unerwartete Exception
        # im Loop uebersprang kursdaten_beenden() -> MT5-Leak.
        for i, kandidat in enumerate(scope, 1):
            log(f"  [forensik {i}/{len(scope)}] "
                f"{kandidat.get('name')} #{kandidat['id']}")
            _f("forensik", i, len(scope),
               f"{kandidat.get('name')} #{kandidat['id']}")
            try:
                ergebnisse.append(
                    pipe.analyze_candidate(session, kandidat,
                                           log=lambda m: log(f"    {m}")))
            except pipeline.Mql5HardStopError as exc:
                if getattr(exc, "result", None) is not None:
                    ergebnisse.append(exc.result)
                log(f"  Fail-Fast zum Account-Schutz: {exc}")
                break


    finally:
        pipe.kursdaten_beenden()  # MT5-Terminal der Kursdaten schließen
    # KI-Berichte: Bedingungen wie die GUI (Key + geeignete Ergebnisse;
    # Teilscan erzwingt Neuerstellung über den Modus-Vertrag oben).
    jobs = [r for r in ergebnisse
            if r.forensik_vorhanden and not r.fehler
            and getattr(r, "source_kind", "live") == "live"]
    berichte = 0
    if pipe.llm.has_key and jobs:
        journal.schritt_protokollieren(
            lauf_id, "dirigent", "scan",
            detail={"modus": modus, "station": "ki", "signale": len(jobs)})
        _f("ki", 0, max(1, 3 * len(jobs)), "KI-Berichte starten …")
        zusammen = pipe.run_llm(
            jobs, log=lambda m: log(f"  [ki] {m}"),
            on_progress=lambda d, t, txt: _f("ki", d, max(1, t), str(txt)[:160]))
        berichte = int(zusammen.get("completed", 0))
    elif not pipe.llm.has_key:
        log("  [ki] Kein GLM-Key — Berichte entfallen (Engine-Ergebnisse "
            "stehen trotzdem in der DB).")

    portfolio = ""
    if pipe.llm.has_key and ergebnisse:
        journal.schritt_protokollieren(
            lauf_id, "dirigent", "scan",
            detail={"modus": modus, "station": "portfolio"})
        _f("portfolio", 0, 1, "Portfolio-Vorschlag wird erstellt …")
        zusammen = pipe.run_portfolio(
            ergebnisse, log=lambda m: log(f"  [portfolio] {m}"),
            on_progress=lambda d, t, txt: _f("portfolio", d, max(1, t),
                                             str(txt)[:160]))
        portfolio = str(zusammen.get("text") or "")[:200]
    try:
        scan_fortschritt.aktualisieren("portfolio", 1, 1, "abgeschlossen",
                                       start_ts, modus, status="fertig")
    except Exception:
        pass

    # Ampel-Wechsel sind bereits über analyze_candidate in der DB-Chronik —
    # der Wechsel-Watcher des Melders übernimmt sie beim nächsten Tick.
    entschieden = sum(1 for r in ergebnisse if r.forensik_vorhanden)
    # Fremd-Review 01.10.: Erfolgsmeldung nennt Versuche UND endgueltige
    # Fehlschlaege — „54 geprüft" allein verschwieg bisher 8 Ausfälle.
    fails = len(scope) - len(ergebnisse) + sum(
        1 for r in ergebnisse if not r.forensik_vorhanden)
    resultat = (f"{entschieden} von {len(scope)} Signalen geprüft"
                + (f", {fails} endgültig fehlgeschlagen" if fails else "")
                + f", {berichte} Berichte erstellt"
                + (", Portfolio aktualisiert." if portfolio else "."))
    zusammenfassung = f"{modus}: {resultat}"
    return {"zusammenfassung": zusammenfassung, "geprueft": entschieden,
            "berichte": berichte, "resultat": resultat}


def starte_scan_thread(modus: str, log=print) -> threading.Thread | None:
    """Scan im Hintergrund-Thread starten (Daemon-Takt bleibt frisch)."""
    thread = threading.Thread(target=starte_scan, args=(modus, "daemon", log),
                              name=f"mqlkiscanner-scan-{modus}", daemon=True)
    thread.start()
    return thread
