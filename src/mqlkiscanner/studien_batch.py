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
- Benötigte MT5-Terminals werden beim ersten Zugriff gestartet und bleiben
  während des Batches offen. Quellenwechsel trennen nur die SDK-Verbindung;
  erst am Laufende werden alle verwendeten Terminals geschlossen.
- Fehlende Trade-Caches werden on demand von der Quelle nachgeladen
  (katalog.lade_signal_daten, SHA-geprüfter Cache).
- Fortschritt in einem plain dict (control): fertig/gesamt/aktuell/Ø-Dauer/
  Restzeit-Schätzung + Abbruch-Flag (geprüft zwischen zwei Signalen).
- Fehlt eine belegte Kapitalbasis, folgen die gemeinsame Lotschätzung,
  grobe Lotschätzung und zuletzt der markierte 10.000-USD-Fallback.
  Ungültige echte Kapitaldaten werden dadurch nicht repariert.
"""
from __future__ import annotations

import time
import threading
from concurrent.futures import ThreadPoolExecutor
from .signal_identity import identity_key
import math
from collections import deque
from pathlib import Path

from . import config, db, katalog, pipeline, scan_worker, signal_statistik
from .forensics.feed_auswahl import Einzelfeed as _AktuellerFeed


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
        studie = studien.get(identity_key(res))
        if studie:
            try:
                pipeline.require_usd_account(res)
            except ValueError:
                studie = None
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
    studien = {} if not nur_luecken else db.list_equity_studien(identitaeten=True)
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
        "vorladen_gesamt": 0, "vorladen_fertig": 0,
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


def _trades_vorladen(jobs: list, control: dict) -> dict:
    """Fehlende Trade-Caches VOR dem Rechnen parallel nachladen — ein
    Thread je Quelle (Nutzer-Wunsch 28.10.: „5 Anbieter, 5 Downloads
    parallel").

    Die fünf Monitor-Clients sind getrennte REST-Dienste; innerhalb einer
    Quelle bleibt es bewusst serial, weil der Monitor seine Provider-Abrufe
    selbst nacheinander abarbeitet und deckelt. ingest sichert je Artefakt
    per RLock ab. Erfolg setzt trades_path/sha256 direkt aufs Resultat —
    der serielle Rechen-Loop (ein MT5-Terminal pro Prozess, klebender
    Fallback) bleibt unangetastet. Rückgabe: Identität → Fehlermeldung;
    der Loop überspringt diese Signale ohne zweiten Serien-Fetch. Fehlende
    native Währungsbelege werden im Quellen-Worker erneuert; neue native
    CSVs benötigen aktuelle USD-Metrics statt eines Offline-Altbelegs.
    """
    auftraege: dict[str, list] = {}
    for res in jobs:
        pfad = getattr(res, "trades_path", "") or ""
        if pfad and Path(res.trades_path).exists():
            continue
        try:
            pipeline.require_usd_account(res)
        except ValueError:
            currency = str(getattr(res, "account_currency", None) or "").strip().casefold()
            if currency not in {"", "unknown", "unbekannt", "uneindeutig", "unbekannt/uneindeutig"}:
                continue  # Bekanntes Nicht-USD bleibt gesperrt, ohne Fetch.
        auftraege.setdefault(str(identity_key(res)[0]), []).append(res)
    if not auftraege:
        return {}
    control["vorladen_gesamt"] = sum(len(v) for v in auftraege.values())
    control["vorladen_fertig"] = 0
    control["phase"] = "Trades nachladen"
    fehler: dict = {}
    fort = threading.Lock()

    def _arbeit(kuerzel: str, liste: list) -> None:
        for res in liste:
            if control["abbruch"]:
                return
            control["aktuelles_signal"] = (
                f"{kuerzel}:#{getattr(res, 'id', '?')} Trade-Load")
            try:
                try:
                    pipeline.require_usd_account(res)
                except ValueError:
                    katalog.require_studienwaehrung(res)
                if control["abbruch"]:
                    return
                # Resolve the actual export version, including older results
                # without quelle_version. Only native MQL requires fresh
                # metrics here; converting monitors retain their contract.
                ref = katalog.quellen_referenz(res)
                native_mql = bool(ref and ref[1] in {"mql4", "mql5"})
                pfad, _ = katalog.lade_signal_daten(
                    res, **({"allow_offline_cache": False} if native_mql else {}))
                # lade_signal_daten updates currency from this download's
                # metrics. An old USD flag must not survive missing/non-USD
                # evidence and then be revived by a serial metrics retry.
                pipeline.require_usd_account(res)
                res.trades_path = pfad
                artefakt = db.get_quellen_artefakt(
                    int(res.quelle_id), int(res.id),
                    str(res.quelle_version or ""), "trades")
                res.trades_sha256 = (artefakt or {}).get("sha256") or ""
            except Exception as exc:
                fehler[identity_key(res)] = (
                    f"[{kuerzel}] #{getattr(res, 'id', '?')} "
                    f"{getattr(res, 'name', '')}: {type(exc).__name__}: {exc}")
            with fort:
                control["vorladen_fertig"] += 1

    with ThreadPoolExecutor(max_workers=min(len(auftraege), 6)) as pool:
        for kuerzel, liste in auftraege.items():
            pool.submit(_arbeit, kuerzel, liste)
    return fehler


def _laufe(jobs: list, control: dict, settings: dict,
           trades_nachladen: bool) -> None:
    """Der Batch selbst (läuft im Worker-Thread)."""
    from . import kursdaten

    dauer_serie: deque[float] = deque(maxlen=8)
    anbieter = None
    control.setdefault("start_ts", time.time())   # direkte Aufrufe (Tests/Live)
    # Trade-Lücken VOR dem Rechnen parallel je Quelle holen — der MT5-
    # Kursteil bleibt serial (ein Terminal pro Prozess, klebender Fallback).
    vorlad_fehler: dict = (
        _trades_vorladen(jobs, control) if trades_nachladen else {})
    try:
        for res in jobs:
            if control["abbruch"]:
                control["phase"] = "abgebrochen"
                break
            control["aktuelles_signal"] = (
                f"{identity_key(res)[0]}:{res.id} · {getattr(res, 'name', '')}")
            control["phase"] = "rechnet"
            t0 = time.time()
            try:
                fehl = vorlad_fehler.pop(identity_key(res), None)
                if fehl is not None:
                    control["fehler"].append(fehl)
                    control.setdefault("skipped_gruende", []).append(
                        f"[{identity_key(res)[0]}] #{getattr(res, 'id', '?')} "
                        f"{getattr(res, 'name', '')}: Trade-Nachladen "
                        "fehlgeschlagen — übersprungen")
                else:
                    katalog.require_studienwaehrung(res)
                    # Connect only after the first eligible account. A batch of
                    # unknown / non-USD MQL exports must not start a terminal.
                    if anbieter is None:
                        control["phase"] = "Terminal verbinden"
                        anbieter = kursdaten.KursDaten(settings)
                        ok, grund = anbieter.starten()
                        if not ok:
                            control["phase"] = "fehler"
                            control["fehler"].append(f"Kursdaten nicht verfügbar: {grund}")
                            return
                        control["phase"] = "rechnet"
                    if _rechne_ein_signal(res, control, anbieter, trades_nachladen):
                        control["gerechnet"] += 1
                    else:
                        control["uebersprungen"] += 1
            except Exception as exc:  # ein Signal darf den Batch nie brechen
                control["fehler"].append(
                    f"[{identity_key(res)[0]}] #{res.id} {getattr(res, 'name', '')}: "
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


def _rekonstruiere_mit_feed_fallback(parsed, anbieter, kapital, broker):
    """Auch Teilhistorie oder unbrauchbare Zeitbasis an weiteren Brokern pruefen.

    Der bisherige Symbolfallback bleibt der erste Versuch. Liefert er keine
    bestandene Messung, werden weitere Terminals als ganze, getrennte Feeds
    verglichen. Kein Zusammenkleben ihrer Zeitreihen, kein Auffuellen von Bars.
    """
    from .forensics import equity_rekonstruktion, feed_auswahl
    from .equity_studie import _KursProvenienz
    from copy import deepcopy

    versuche = []
    best = None
    erster_fehler = None
    provenienz = None

    def erfasst(report, modus, provenienz):
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
        metadata = provenienz.metadaten(symbole & bestaetigt)
        report.update(deepcopy(metadata))
        versuch.update(deepcopy(metadata))
        versuche.append(versuch)
        return report

    def fehler(error, status):
        nonlocal erster_fehler
        if erster_fehler is None:
            erster_fehler = error
        versuch = {"terminal": getattr(anbieter, "terminal_pfad", None),
                   "status": status, "grund": f"{type(error).__name__}: {error}"}
        if status == "berechnung_fehlgeschlagen" and provenienz is not None:
            versuch.update(provenienz.metadaten(
                t.symbol for t in getattr(parsed, "trades", []) if getattr(t, "symbol", None)))
        versuche.append(versuch)

    def reset():
        feed_auswahl.reset_feed(anbieter, meldung=versuche.append, fehler=fehler)

    try:
        try:
            provenienz = _KursProvenienz(anbieter)
            best = erfasst(equity_rekonstruktion.rekonstruiere(
                parsed, provenienz, kapital, broker=broker), "symbol_fallback", provenienz)
        except Exception as error:
            fehler(error, "berechnung_fehlgeschlagen")
        if best is None or not feed_auswahl.ausreichend(best):
            # Auch nach einem Fehler innerhalb des ersten Symbolfallbacks
            # die weiteren Feeds von Quelle0 aus getrennt versuchen.
            reset()
            for _ in feed_auswahl.iteriere_weitere_feeds(
                    anbieter, weiter_nach_verbindungsfehler=True,
                    meldung=versuche.append, fehler=fehler):
                try:
                    provenienz = _KursProvenienz(anbieter)
                    kandidat = erfasst(equity_rekonstruktion.rekonstruiere(
                        parsed, _AktuellerFeed(provenienz), kapital, broker=broker), "einzelfeed", provenienz)
                except Exception as error:
                    fehler(error, "berechnung_fehlgeschlagen")
                    continue
                if best is None or feed_auswahl.qualitaet(kandidat) > feed_auswahl.qualitaet(best):
                    best = kandidat
                if feed_auswahl.ausreichend(best):
                    break
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
    from . import kapitalbasis, parser, signal_statistik
    from .forensics import drawdown, equity_rekonstruktion
    pipeline.require_usd_account(res)

    # 1) Trade-Cache sicherstellen (on demand von der Quelle)
    if not (getattr(res, "trades_path", "") or "") \
            or not Path(res.trades_path).exists():
        if not trades_nachladen:
            return False
        pfad, _ = katalog.lade_signal_daten(res)
        pipeline.require_usd_account(res)
        res.trades_path = pfad
        artefakt = db.get_quellen_artefakt(int(res.quelle_id), int(res.id),
                                           str(res.quelle_version or ""), "trades")
        res.trades_sha256 = (artefakt or {}).get("sha256") or ""

    # 2) Vorstufen-Statistik (Kapitalbasis, CAGR, Geom-Ertrag — ohne LLM).
    #    Gemeinsame Kapitalmethodik; geschätzte Werte bleiben virtuell und
    #    gehen nie in die Workflow-Schranken (studie_anwenden trennt das).
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
        pipeline.require_usd_account(res)
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
    stats = {**stats, "quelle": identity_key(res)[0],
             "broker_server": getattr(res, "broker_server", None) or stats.get("broker_server")}
    stats.setdefault("account_currency", getattr(res, "account_currency", None))
    for key in ("id", "quellen_uid", "signal_ref", "trades_sha256"):
        stats[key] = getattr(res, key, None)
    statistik = signal_statistik.berechne(res.trades_path, stats) or {}
    # Die TATSAECHLICH verwendete Quelle entscheidet: Quellenannahmen sind
    # ebenfalls virtuell, echte CSV-Einzahlungen schlagen jeden Fallback.
    virtuell_basis = kapitalbasis.ist_modellquelle(statistik.get("kapitalbasis_quelle"))
    res.trades_sha256 = res.trades_sha256 or ""
    startkapital = statistik.get("kapitalbasis_usd")
    cagr = statistik.get("cagr_jahr_pct")
    geom = statistik.get("ertrag_monat_geom_pct")

    vorher = db.get_equity_studie(int(res.id), quelle=identity_key(res)[0]) or {}
    alter_report = vorher.get("report") or {}
    if (virtuell_basis and vorher and not vorher.get("virtuell") and not vorher.get("basislos")
            and res.trades_sha256 and vorher.get("trades_sha") == res.trades_sha256):
        control.setdefault("skipped_gruende", []).append(
            f"[{identity_key(res)[0]}] #{res.id}: bestehende echte SHA-passende Studie "
            "bleibt erhalten; eine Modellbasis ersetzt keinen Kontobeleg.")
        return False
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
        report["account_currency"] = getattr(res, "account_currency", None)
        report["kapitalbasis_details"] = statistik.get("kapitalbasis_details") or {}
        report["kapitalbasis_modell"] = virtuell_basis
        report["startkapital_quelle"] = statistik.get("kapitalbasis_quelle")
        report["startkapital"] = startkapital
        report["kapitalbasis_usd"] = startkapital
        if virtuell_basis:
            report["methodik"] = ("Modellkurve mit geschätztem Startkapital und vorhandenen Kapitalflüssen; "
                                  "realisiertes Netto und Floating an H1-Bar-Schlüssen, keine belegte Kontokurve")
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
                f"[{identity_key(res)[0]}] #{res.id} {getattr(res, 'name', '')}: Nachmessung nicht belastbar; "
                "bestehende SHA-passende verlaessliche Studie bleibt erhalten — "
                + str(report.get("grund") or report.get("status") or "ohne Freigabe"))
            return False
        db.store_equity_studie(int(res.id), res.trades_sha256, report,
                               cagr_jahr_pct=cagr,
                               ertrag_monat_geom_pct=geom,
                               dd_usd=report.get("equity_dd_usd"),
                               basislos=False, virtuell=virtuell_basis, quelle=identity_key(res)[0])
        return True
    control["skipped_gruende"].append(
        f"[{identity_key(res)[0]}] #{res.id} {getattr(res, 'name', '')}: keine Kapitalbasis — "
        + str(statistik.get("fehler") or "Statistik ohne Basis"))
    return False
