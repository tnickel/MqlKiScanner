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
- Fehlt eine belegte Kapitalbasis, wird die vereinbarte virtuelle
  10.000-USD-Basis verwendet und ausdrücklich als Annahme markiert.
  Ungültige echte Kapitaldaten werden dadurch nicht repariert.
"""
from __future__ import annotations

import time
import math
from collections import deque
from pathlib import Path

from . import config, db, katalog, pipeline, scan_worker, signal_statistik


def _neu_aufloesbare_kontrakte(res, studie: dict | None) -> bool:
    """Nur vormals ausgeschlossene Instrumente am ORIGINAL-Broker pruefen.

    Das Kursreferenzterminal belegt keine Kontraktgroesse des Signalanbieters.
    Ohne dessen Identitaet bleibt eine bestehende Teilmessung unveraendert.
    """
    from .forensics.exposure import _resolve_symbol

    report = (studie or {}).get("report") or {}
    fehlend = report.get("symbole_ohne_kontrakt")
    if not isinstance(fehlend, (list, tuple)):
        return False
    symbole = [s.strip() for s in fehlend if isinstance(s, str) and s.strip()]
    if not symbole:
        return False
    broker = report.get("original_broker") or getattr(res, "broker_server", None)
    if not isinstance(broker, str) or not broker.strip():
        broker = katalog.metrics_stats(res).get("broker_server")
    if not isinstance(broker, str) or not broker.strip():
        return False
    return any(_resolve_symbol(symbol, broker) is not None for symbol in symbole)


def luecken_sammeln(resultate: list, studien: dict, *,
                     trades_nachladen: bool) -> tuple[list, int]:
    """(Jobs, bereits_erledigt) — Jobs = Signale, die gerechnet werden wollen.

    Lücke = keine belastbare Equity-Messung am Resultat UND (nur_luecken)
    keine verlässliche, SHA-passende Studie in der DB. Rohmessungen mit
    Vorbehalt schließen die Lücke nicht. Signale ohne jeden Trade-Bezug und ohne
    Quellen-Referenz sind nicht rechenbar und werden bereits hier
    aussortiert (Zähler „ohne Quelle“ im Batch-Protokoll).
    """
    jobs: list = []
    erledigt = 0
    for res in resultate:
        studie = studien.get(int(res.id))
        spec_nachmessung = _neu_aufloesbare_kontrakte(res, studie)
        hat_messung = getattr(res, "max_drawdown_equity_pct", None) is not None
        if hat_messung and not spec_nachmessung:
            erledigt += 1
            continue
        if studie is not None:
            sha = studie.get("trades_sha") or ""
            report = studie.get("report") or {}
            dd = report.get("equity_dd_pct")
            if dd is None:
                dd = report.get("equity_dd_pct_raw")
            hat_dd = (isinstance(dd, (int, float)) and not isinstance(dd, bool)
                      and math.isfinite(dd) and dd >= 0)
            # Alte nur-USD-Studien (basislos) zählen NICHT als erledigt —
            # sie werden als virtuelle neu gerechnet. Und: Eine Studie mit
            # passendem SHA aber OHNE Drawdown-Wert (Status skipped/
            # unvollstaendig ohne dd, z. B. "Kursdaten fehlen") ist KEINE
            # gefüllte Lücke — sonst bleiben hunderte Signale für immer
            # "belegt", obwohl sie nie eine Messung geliefert haben
            # (Live-Fund 09.10.: Finisher hielt ~700 Kursdaten-Fehler für
            # erledigt).
            if (studie.get("basislos") or not hat_dd
                    or report.get("verlaesslich") is not True):
                pass
            elif (sha and res.trades_sha256 and sha == res.trades_sha256
                  and not spec_nachmessung):
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


class _AktuellerFeed:
    """Nur der aktuelle Feed; verhindert gemischte Bars beim Vergleich."""

    def __init__(self, anbieter):
        self.anbieter = anbieter

    @property
    def terminal_pfad(self):
        return getattr(self.anbieter, "terminal_pfad", None)

    @property
    def terminal_herkunft(self):
        return getattr(self.anbieter, "terminal_herkunft", {})

    def hole_h1(self, *args, **kwargs):
        return self.anbieter.hole_h1(*args, **kwargs)


def _rekonstruiere_mit_feed_fallback(parsed, anbieter, kapital, broker):
    """Auch Teilhistorie oder unbrauchbare Zeitbasis an weiteren Brokern pruefen.

    Der bisherige Symbolfallback bleibt der erste Versuch. Liefert er keine
    bestandene Messung, werden weitere Terminals als ganze, getrennte Feeds
    verglichen. Kein Zusammenkleben ihrer Zeitreihen, kein Auffuellen von Bars.
    """
    from .forensics import equity_rekonstruktion

    versuche = []
    best = None
    erster_fehler = None

    def qualitaet(report):
        dd = report.get("equity_dd_pct_raw", report.get("equity_dd_pct"))
        messbar = (isinstance(dd, (int, float)) and not isinstance(dd, bool)
                   and math.isfinite(dd) and dd >= 0)
        abdeckung = report.get("abdeckung_pct_raw", report.get("abdeckung_pct"))
        if (not isinstance(abdeckung, (int, float)) or isinstance(abdeckung, bool)
                or not math.isfinite(abdeckung) or abdeckung < 0):
            abdeckung = 0
        return (report.get("verlaesslich") is True and messbar, messbar,
                abdeckung, not bool(report.get("fx_luecke")), dd if messbar else 0)

    def erfasst(report, modus):
        feed = getattr(anbieter, "terminal_pfad", None)
        report = dict(report)
        report["kursdaten_terminal"] = feed
        report["original_broker"] = broker
        versuch = {"terminal": feed, "modus": modus, "status": report.get("status"),
                   "verlaesslich": report.get("verlaesslich", False),
                   "abdeckung_pct": report.get("abdeckung_pct"),
                   "grund": report.get("grund")}
        # Nur im Bericht bestaetigte, aktuell angefragte Handelssymbole:
        # alte Provenienz-Eintraege des langlebigen Anbieters aussparen.
        symbole = {t.symbol.strip().upper() for t in getattr(parsed, "trades", [])
                   if getattr(t, "symbol", None)}
        bestaetigt = {str(s).strip().upper() for s in (report.get("symbole_mit_kursen") or [])}
        herkunft = getattr(anbieter, "terminal_herkunft", {})
        mapping = {s: herkunft[s] for s in sorted(symbole & bestaetigt) if s in herkunft}
        if mapping:
            versuch["symbol_feeds"] = mapping
        versuche.append(versuch)
        return report

    def fehler(error, status):
        nonlocal erster_fehler
        if erster_fehler is None:
            erster_fehler = error
        versuche.append({"terminal": getattr(anbieter, "terminal_pfad", None),
                        "status": status, "grund": f"{type(error).__name__}: {error}"})

    def reset():
        if (getattr(anbieter, "terminal_idx", 0) != 0
                and hasattr(anbieter, "zurueck_zum_ersten_terminal")):
            try:
                ok, grund = anbieter.zurueck_zum_ersten_terminal()
                if not ok:
                    versuche.append({"terminal": getattr(anbieter, "terminal_pfad", None),
                                    "status": "reset_fehlgeschlagen", "grund": grund})
            except Exception as error:
                fehler(error, "reset_fehlgeschlagen")

    def feed_identitaet():
        return (getattr(anbieter, "terminal_idx", None),
                getattr(anbieter, "terminal_pfad", None))

    try:
        try:
            best = erfasst(equity_rekonstruktion.rekonstruiere(
                parsed, anbieter, kapital, broker=broker), "symbol_fallback")
        except Exception as error:
            fehler(error, "berechnung_fehlgeschlagen")
        if best is None or not qualitaet(best)[0]:
            # Auch nach einem Fehler innerhalb des ersten Symbolfallbacks
            # die weiteren Feeds von Quelle0 aus getrennt versuchen.
            reset()
        besucht = {feed_identitaet()}
        while ((best is None or not qualitaet(best)[0])
               and hasattr(anbieter, "hat_weiteren_terminal")
               and anbieter.hat_weiteren_terminal()):
            try:
                ok, grund = anbieter.wechsle_terminal()
            except Exception as error:
                fehler(error, "verbindung_fehlgeschlagen")
                ok, grund = False, None
            identitaet = feed_identitaet()
            if identitaet in besucht:
                versuche.append({"terminal": getattr(anbieter, "terminal_pfad", None),
                                "status": "kein_feed_fortschritt",
                                "grund": "Terminalwechsel hat keine neue Quelle erreicht"})
                break
            besucht.add(identitaet)
            if not ok:
                if grund is not None:
                    versuche.append({"terminal": getattr(anbieter, "terminal_pfad", None),
                                    "status": "verbindung_fehlgeschlagen", "grund": grund})
                continue
            try:
                kandidat = erfasst(equity_rekonstruktion.rekonstruiere(
                    parsed, _AktuellerFeed(anbieter), kapital, broker=broker), "einzelfeed")
            except Exception as error:
                fehler(error, "berechnung_fehlgeschlagen")
                continue
            if best is None or qualitaet(kandidat) > qualitaet(best):
                best = kandidat
    except Exception as error:
        fehler(error, "feed_fallback_fehlgeschlagen")
    finally:
        reset()
    if best is None:
        if erster_fehler is not None:
            raise erster_fehler
        raise RuntimeError("Keine Kursdatenquelle lieferte einen Rekonstruktionsbericht")
    best["kursdaten_versuche"] = versuche
    return best



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
    parsed = parser.load_export(res.trades_path,
                                plattform_positions=stats.get("trades"))
    erwartete_historie = any(
        isinstance(wert, (int, float)) and not isinstance(wert, bool)
        and math.isfinite(wert) and wert > 0
        for wert in (stats.get("quelle_trades_anzahl"),
                     stats.get("quelle_gewinne_anzahl"),
                     stats.get("quelle_verluste_anzahl"), stats.get("trades")))
    if (not parsed.trades and trades_nachladen
            and erwartete_historie
            and katalog.quellen_referenz(res)):
        # Eine Header-Datei beweist keinen vollstaendigen Download, wenn
        # die Quelle abgeschlossene Trades meldet. Genau ein Refresh je
        # Signal/Batch, ueber denselben Quellen-/SHA-Pfad wie beim Erstladen.
        pfad, _ = katalog.lade_signal_daten(res)
        res.trades_path = pfad
        artefakt = db.get_quellen_artefakt(int(res.quelle_id), int(res.id),
                                           str(res.quelle_version or ""), "trades")
        res.trades_sha256 = (artefakt or {}).get("sha256") or ""
        stats = katalog.metrics_stats(res)
        parsed = parser.load_export(res.trades_path,
                                    plattform_positions=stats.get("trades"))
    seitenbasis = getattr(res, "kapitalbasis_usd", None)
    if (stats.get("initial_deposit_usd") is None
            and isinstance(seitenbasis, (int, float)) and not isinstance(seitenbasis, bool)
            and math.isfinite(seitenbasis) and seitenbasis > 0):
        stats["initial_deposit_usd"] = seitenbasis
    if not (stats.get("initial_deposit_usd") or stats.get("kapitalbasis_virtual_usd")):
        stats["kapitalbasis_virtual_usd"] = 10_000.0
    statistik = signal_statistik.berechne(res.trades_path, stats) or {}
    # Die TATSAECHLICH verwendete Quelle entscheidet: Quellenannahmen sind
    # ebenfalls virtuell, echte CSV-Einzahlungen schlagen jeden Fallback.
    virtuell_basis = (statistik.get("kapitalbasis_quelle")
                      == pipeline.KAPITALBASIS_QUELLE_VIRTUELL)
    res.trades_sha256 = res.trades_sha256 or ""
    startkapital = statistik.get("kapitalbasis_usd")
    cagr = statistik.get("cagr_jahr_pct")
    geom = statistik.get("ertrag_monat_geom_pct")

    vorher = db.get_equity_studie(int(res.id)) or {}
    alter_report = vorher.get("report") or {}
    alter_broker = (alter_report.get("original_broker")
                   if res.trades_sha256 and vorher.get("trades_sha") == res.trades_sha256
                   else None)
    broker = (getattr(res, "broker_server", None) or stats.get("broker_server")
              or alter_broker or None)
    # Mit (echter ODER virtueller) Basis: volle Equity-Reko mit Prozenten —
    # virtuelle Studien flaggt der Store separat (Anzeige gekennzeichnet,
    # Workflow-Schranken bleiben unberührt).
    if startkapital:
        report = _rekonstruiere_mit_feed_fallback(
            parsed, anbieter, float(startkapital), broker)
        alter_dd = alter_report.get("equity_dd_pct")
        if alter_dd is None:
            alter_dd = alter_report.get("equity_dd_pct_raw")
        if (report.get("verlaesslich") is not True
                and alter_report.get("verlaesslich") is True
                and not vorher.get("basislos")
                and res.trades_sha256
                and vorher.get("trades_sha") == res.trades_sha256
                and isinstance(alter_dd, (int, float)) and not isinstance(alter_dd, bool)
                and math.isfinite(alter_dd) and alter_dd >= 0):
            control.setdefault("skipped_gruende", []).append(
                f"#{res.id} {getattr(res, 'name', '')}: Nachmessung nicht belastbar; "
                "bestehende SHA-passende verlaessliche Studie bleibt erhalten — "
                + str(report.get("grund") or report.get("status") or "ohne Freigabe"))
            return False
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
