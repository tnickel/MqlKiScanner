# -*- coding: utf-8 -*-
"""Studien-Batch „Lücken füllen“ (Nutzer-Wunsch 08.10.2026).

Rechnet für Signale OHNE Equity-Messung den echten Max-Drawdown aus Kursen
(dieselbe equity_rekonstruktion wie der Workflow — nur ohne LLM-Schritte)
und persistiert ihn in equity_studien, damit die Tabelle „Alle Signale“ die
Spalten True-DD %/≈/USD und TrueRetDD überall füllt, wo es belegbar ist.

Laufprinzip:
- Hintergrund-Thread, registriert über scan_worker.start() → der Batch ist
  ein „Lauf“ wie ein Scan: Während er läuft, blockieren Scan-Start und
  manuelle Equity-Studie (beide brauchen das MT5-Referenzterminal
  exklusiv) und das dateibasierte Lauf-Lock schützt gegen den Daemon.
- Das MT5-Terminal wird EINMAL für den ganzen Batch gestartet (je Signal
  nur die H1-Kurs-Abfragen) — nicht je Studie neu.
- Fehlende Trade-Caches werden on demand von der Quelle nachgeladen
  (katalog.lade_signal_daten, SHA-geprüfter Cache).
- Fortschritt in einem plain dict (control): fertig/gesamt/aktuell/Ø-Dauer/
  Restzeit-Schätzung + Abbruch-Flag (geprüft zwischen zwei Signalen).
- Basislose Signale (keine belegbare Kapitalbasis, z. B. Vantage ohne
  Einzahlungszeilen) bekommen bewusst KEINEN %-Drawdown, nur True-DD USD.
"""
from __future__ import annotations

import time
from collections import deque
from pathlib import Path

from . import config, db, katalog, pipeline, scan_worker, signal_statistik


def luecken_sammeln(resultate: list, studien: dict, *,
                     trades_nachladen: bool) -> tuple[list, int]:
    """(Jobs, bereits_erledigt) — Jobs = Signale, die gerechnet werden wollen.

    Lücke = keine Equity-Messung am Resultat UND (nur_luecken) keine
    gültige Studie in der DB. Signale ohne jeden Trade-Bezug und ohne
    Quellen-Referenz sind nicht rechenbar und werden bereits hier
    aussortiert (Zähler „ohne Quelle“ im Batch-Protokoll).
    """
    jobs: list = []
    erledigt = 0
    for res in resultate:
        hat_messung = (getattr(res, "max_drawdown_equity_pct", None) is not None
                       or getattr(res, "equity_dd_rekon_roh_pct", None) is not None)
        if hat_messung:
            erledigt += 1
            continue
        studie = studien.get(int(res.id))
        if studie is not None:
            sha = studie.get("trades_sha") or ""
            report = studie.get("report") or {}
            hat_dd = (report.get("equity_dd_pct") is not None
                      or report.get("equity_dd_pct_raw") is not None)
            # Alte nur-USD-Studien (basislos) zählen NICHT als erledigt —
            # sie werden als virtuelle neu gerechnet. Und: Eine Studie mit
            # passendem SHA aber OHNE Drawdown-Wert (Status skipped/
            # unvollstaendig ohne dd, z. B. "Kursdaten fehlen") ist KEINE
            # gefüllte Lücke — sonst bleiben hunderte Signale für immer
            # "belegt", obwohl sie nie eine Messung geliefert haben
            # (Live-Fund 09.10.: Finisher hielt ~700 Kursdaten-Fehler für
            # erledigt).
            if studie.get("basislos") or not hat_dd:
                pass
            elif not sha or not res.trades_sha256 or sha == res.trades_sha256:
                erledigt += 1          # gültige Studie mit Messung vorhanden
                continue
        ref = katalog.quellen_referenz(res)
        if not (getattr(res, "trades_path", "") or ""):
            if not (trades_nachladen and ref):
                continue               # nicht rechenbar (kein Cache, keine Quelle)
        jobs.append(res)
    return jobs, erledigt


def starten(resultate: list, *, nur_luecken: bool = True,
            trades_nachladen: bool = True) -> scan_worker.WorkerRun | None:
    """Batch im Hintergrund-Thread starten; None = bereits ein Lauf aktiv.

    `resultate` ist die gemischte Liste (gescannt + Katalog) der Seite.
    Die Studientabelle wird EINMAL hier geladen — der Thread liest sie
    nicht mehr (kein DB-Churn je Signal).
    """
    settings = config.load_settings()
    studien = {} if not nur_luecken else db.list_equity_studien()
    if nur_luecken:
        jobs, erledigt = luecken_sammeln(resultate, studien,
                                          trades_nachladen=trades_nachladen)
    else:
        jobs, erledigt = list(resultate), 0
        studien = {}

    control: dict = {
        "typ": "studien_batch", "fertig": False, "abbruch": False,
        "gesamt": len(jobs), "aktuell": 0, "fertig_count": erledigt,
        "uebersprungen": 0, "gerechnet": 0, "fehler": [], "skipped_gruende": [],
        "phase": "startet", "aktuelles_signal": "",
        "restzeit_s": None, "dauer_je_s": None, "start_ts": time.time(),
        "summary": "",
        "nur_luecken": nur_luecken, "trades_nachladen": trades_nachladen,
    }
    try:
        run = scan_worker.start(
            lambda: _laufe(jobs, control, settings, trades_nachladen),
            workflow={"typ": "studien_batch", "gesamt": len(jobs)},
            control=control, logs=[], results=[],
            lock_basis=config.DATA_DIR)
    except RuntimeError:
        # Lauf-Lock des autonomen Daemons belegt (oder zweiter Prozess) —
        # wie "läuft bereits": None, der Aufrufer (UI/Finisher) wartet.
        return None
    return run


def _laufe(jobs: list, control: dict, settings: dict,
           trades_nachladen: bool) -> None:
    """Der Batch selbst (läuft im Worker-Thread)."""
    from . import kursdaten

    dauer_serie: deque[float] = deque(maxlen=8)
    anbieter = None
    control.setdefault("start_ts", time.time())   # direkte Aufrufe (Tests/Live)
    try:
        if jobs:
            control["phase"] = "Terminal verbinden"
            anbieter = kursdaten.KursDaten(settings)
            ok, grund = anbieter.starten()
            if not ok:
                control["phase"] = "fehler"
                control["fehler"].append(f"Kursdaten nicht verfügbar: {grund}")
                return

        for res in jobs:
            if control["abbruch"]:
                control["phase"] = "abgebrochen"
                break
            control["aktuelles_signal"] = (getattr(res, "name", "") or str(res.id))
            control["phase"] = "rechnet"
            t0 = time.time()
            try:
                if _rechne_ein_signal(res, control, anbieter, trades_nachladen):
                    control["gerechnet"] += 1
                else:
                    control["uebersprungen"] += 1
            except Exception as exc:  # ein Signal darf den Batch nie brechen
                control["fehler"].append(
                    f"#{res.id} {getattr(res, 'name', '')}: "
                    f"{type(exc).__name__}: {exc}")
            # Klebender Terminal-Fallback zurücksetzen: Der Wechsel eines
            # Signals (fehlende Symbole) darf nicht die Folge-Signale ans
            # falsche Terminal binden (08.10., NAS100FT-Fall).
            if getattr(anbieter, "terminal_idx", 0) != 0:
                anbieter.zurueck_zum_ersten_terminal()
            control["aktuell"] += 1
            dauer_serie.append(time.time() - t0)
            control["dauer_je_s"] = round(
                sum(dauer_serie) / len(dauer_serie), 1)
            verbleibend = len(jobs) - control["aktuell"]
            control["restzeit_s"] = (round(verbleibend * control["dauer_je_s"])
                                     if verbleibend > 0 else 0)
        control["phase"] = control["phase"] if control["abbruch"] else "fertig"
        control["fertig"] = True
        control["summary"] = (
            f"{control['gerechnet']} gerechnet · {control['uebersprungen']} "
            f"übersprungen · {len(control['fehler'])} Fehler · "
            f"Dauer {round(time.time() - control['start_ts'])} s"
            + (" — ABGEBROCHEN" if control["abbruch"] else ""))
    except Exception as exc:  # auch Fehler außerhalb der Signal-Schleife sichtbar machen
        control["fehler"].append(f"Batch abgebrochen: {type(exc).__name__}: {exc}")
        control["phase"] = "fehler"
    finally:
        if not control.get("summary"):
            control["summary"] = (
                f"{control['gerechnet']} gerechnet · {control['uebersprungen']} "
                f"übersprungen · {len(control['fehler'])} Fehler · "
                f"Dauer {round(time.time() - control['start_ts'])} s"
                + (" — ABGEBROCHEN" if control["abbruch"] else ""))
        if anbieter is not None:
            try:
                anbieter.beenden()
            except Exception:
                pass
        control["fertig"] = True
        control["restzeit_s"] = 0


def _rechne_ein_signal(res, control, anbieter, trades_nachladen: bool) -> None:
    """Ein Signal: Trades sicherstellen → Statistik → Equity-Reko → persistieren.
    Rückgabe True = Studie gespeichert, False = übersprungen (mit Grund in
    control["skipped_gruende"])."""
    from . import parser, signal_statistik
    from .forensics import drawdown, equity_rekonstruktion

    # 1) Trade-Cache sicherstellen (on demand von der Quelle)
    if not (getattr(res, "trades_path", "") or "") \
            or not Path(res.trades_path).exists():
        if not trades_nachladen:
            return False
        pfad, _ = katalog.lade_signal_daten(res)
        res.trades_path = pfad
        artefakt = db.get_quellen_artefakt(int(res.quelle_id), int(res.id),
                                           str(res.quelle_version or ""), "trades")
        res.trades_sha256 = (artefakt or {}).get("sha256") or ""

    # 2) Vorstufen-Statistik (Kapitalbasis, CAGR, Geom-Ertrag — ohne LLM).
    #    Ohne jede erkennbare Kapitalbasis (typisch Vantage: keine Ein-
    #    zahlungszeilen, kein Initial Deposit) rechnet der Batch mit der
    #    VIRTUELLEN 10.000-USD-Annahme — klar markiert (virtuell=True),
    #    dieselbe Konvention wie beim PelicanMonitor. Virtuelle Werte gehen
    #    NIE in die Workflow-Schranken (studie_anwenden trennt das).
    stats = katalog.metrics_stats(res)
    virtuell_basis = not (stats.get("initial_deposit_usd")
                          or stats.get("kapitalbasis_virtual_usd"))
    if virtuell_basis:
        stats["kapitalbasis_virtual_usd"] = 10_000.0
    statistik = signal_statistik.berechne(res.trades_path, stats) or {}
    res.trades_sha256 = res.trades_sha256 or ""
    startkapital = statistik.get("kapitalbasis_usd")
    cagr = statistik.get("cagr_jahr_pct")
    geom = statistik.get("ertrag_monat_geom_pct")

    parsed = parser.load_export(res.trades_path,
                                plattform_positions=stats.get("trades"))
    broker = getattr(res, "broker_server", None) or None
    # Mit (echter ODER virtueller) Basis: volle Equity-Reko mit Prozenten —
    # virtuelle Studien flaggt der Store separat (Anzeige gekennzeichnet,
    # Workflow-Schranken bleiben unberührt).
    if startkapital:
        report = equity_rekonstruktion.rekonstruiere(
            parsed, anbieter, float(startkapital), broker=broker)
        db.store_equity_studie(int(res.id), res.trades_sha256, report,
                               cagr_jahr_pct=cagr,
                               ertrag_monat_geom_pct=geom,
                               dd_usd=report.get("equity_dd_usd"),
                               basislos=False, virtuell=virtuell_basis)
        return True
    control["skipped_gruende"].append(
        f"#{res.id} {getattr(res, 'name', '')}: keine Kapitalbasis — "
        + str(statistik.get("fehler") or "Statistik ohne Basis"))
    return False
