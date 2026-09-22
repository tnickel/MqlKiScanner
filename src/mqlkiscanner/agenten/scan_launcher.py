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
from datetime import date

from .. import config, pipeline
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
        aktion = f"Autonomer {modus_name} durchgeführt"
        resultat = ergebnis.get("resultat") or ergebnis["zusammenfassung"]
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
    journal.schritt_protokollieren(lauf_id, "dirigent", "scan",
                                   detail={"modus": modus, "station": "listen"})
    signale = pipe.crawl(on_progress=lambda *a: None,
                         log=lambda m: log(f"  [listen] {m}"))
    kandidaten = pipe.build_candidates(
        signale, log=lambda m: log(f"  [kandidaten] {m}"))

    if modus == "gelbgruen":
        # Modus-Vertrag: nur aktuell 🟢/🟡 laut DB-Stand — Ampel-Logik
        # exakt wie die Ergebnis-Ansicht (results_from_db).
        alt = pipeline.results_from_db(settings)
        ziel_ids = {r.id for r in alt
                    if r.ampel in ("🟢", "🟡")
                    and getattr(r, "source_kind", "live") == "live"}
        vorher = len(kandidaten)
        kandidaten = [c for c in kandidaten if c["id"] in ziel_ids]
        log(f"Teilscan: {len(kandidaten)} von {vorher} Kandidaten "
            "sind aktuell 🟢/🟡.")

    scope = kandidaten[:int(settings.get("top_n_export", 30))]
    if not scope:
        grund = (f"Keine zu prüfenden Kandidaten (Modus {modus}) — "
                 "kein Login/Export nötig.")
        journal.schritt_protokollieren(lauf_id, "dirigent", "scan",
                                       status="skipped",
                                       detail={"grund": grund, "modus": modus})
        return {"zusammenfassung": grund, "geprueft": 0, "berichte": 0}

    session = Mql5Session(settings)
    if not session.has_credentials:
        grund = "Kein MQL5-Login konfiguriert — autonomer Scan nicht möglich."
        journal.schritt_protokollieren(lauf_id, "dirigent", "scan",
                                       status="skipped",
                                       detail={"grund": grund})
        return {"zusammenfassung": grund, "geprueft": 0, "berichte": 0}
    from ..mql5.browser_session import ensure_mql5_cookies
    if not ensure_mql5_cookies(settings, session,
                               log=lambda m: log(f"  [login] {m}")):
        grund = "MQL5-Login fehlgeschlagen — Scan abgebrochen (Login prüfen)."
        journal.schritt_protokollieren(lauf_id, "dirigent", "scan",
                                       status="skipped",
                                       detail={"grund": grund})
        return {"zusammenfassung": grund, "geprueft": 0, "berichte": 0}

    journal.schritt_protokollieren(
        lauf_id, "dirigent", "scan",
        detail={"modus": modus, "station": "forensik",
                "kandidaten": [c["id"] for c in scope]})
    ergebnisse = []
    for i, kandidat in enumerate(scope, 1):
        log(f"  [forensik {i}/{len(scope)}] "
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
        zusammen = pipe.run_llm(jobs, log=lambda m: log(f"  [ki] {m}"))
        berichte = int(zusammen.get("completed", 0))
    elif not pipe.llm.has_key:
        log("  [ki] Kein GLM-Key — Berichte entfallen (Engine-Ergebnisse "
            "stehen trotzdem in der DB).")

    portfolio = ""
    if pipe.llm.has_key and ergebnisse:
        journal.schritt_protokollieren(
            lauf_id, "dirigent", "scan",
            detail={"modus": modus, "station": "portfolio"})
        zusammen = pipe.run_portfolio(
            ergebnisse, log=lambda m: log(f"  [portfolio] {m}"))
        portfolio = str(zusammen.get("text") or "")[:200]

    # Ampel-Wechsel sind bereits über analyze_candidate in der DB-Chronik —
    # der Wechsel-Watcher des Melders übernimmt sie beim nächsten Tick.
    entschieden = sum(1 for r in ergebnisse if r.forensik_vorhanden)
    resultat = (f"{entschieden} Signale geprüft, {berichte} Berichte erstellt"
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
