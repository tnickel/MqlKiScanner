# -*- coding: utf-8 -*-
"""Scan-Pipeline: Liste -> Kandidaten -> Daten+Forensik -> LLM (Phase 2/3).

Die Engine rechnet ALLE Zahlen; das LLM bekommt nur fertige Befunde als
JSON (AGENTS.md Design-Regel 1). Jeder Schritt meldet Fortschritt ueber
Callbacks, damit die GUI ihn visualisieren kann.

Lauf-Ergebnisse landen in data/runs/{zeitstempel}/results.json.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
import traceback
from uuid import uuid4
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import requests

from . import ampel_verlauf, config, fix_signale, portfolio_statistik, scoring
from . import db
from . import downloader_client
from . import fx_rates
from .ampel_matrix import matrix_payload
from .analysis_version import FORENSICS_VERSION
from .engine import analyze as analyze_export
from .llm import client as llm_client
from .llm import prompt_fill
from .mql5 import crawler, exporter, signal_stats
from .mql5.errors import Mql5CredentialsMissingError
from .mql5.ratelimit import Mql5HardStopError, is_hard_mql5_failure
from .mql5.session import Mql5Session

ProgressCb = Callable[[int, int, str], None]
LogCb = Callable[[str], None]

# Quellen-Label der virtuellen Kapitalbasis (Nutzer-Wunsch 28.09.2026): Ein
# Monitor ohne Initial-Deposit-Daten (z. B. PelicanMonitor) kann eine klar
# markierte Annahme liefern ("InitialDepositVirtual"). Sie gibt der Forensik
# ein Startkapital (DD-/Schock-Prozente), gilt aber ausdrücklich NICHT als
# belegtes Initial Deposit: kein Cent-Abgleich gegen die Web-Balance, keine
# rote Kapitalbasis-Regel, transparent im Urteil.
KAPITALBASIS_QUELLE_VIRTUELL = "virtuelle_annahme"
# B3 (Intensiv-Review 29./30.09.2026): Bei Quellen-Signalen ohne echtes
# Initial Deposit ist die beste belegbare Basis die IMPLIZITE: Web-Balance
# minus Summe der Trade-Nettoergebnisse (= Startkapital, das die heutige
# Balance zusammen mit der Handelsleistung erklärt). Die starre 10.000-USD-
# Annahme (InitialDepositVirtual) verzerrte DD-/Schock-Prozente um Faktor
# 2–20 (SafeGold: real 998 USD, MicroJump 530 USD) — die implizite Basis
# kommt vor den Virtual-Fallback und bleibt im Forensik-JSON gekennzeichnet.
KAPITALBASIS_QUELLE_IMPLIZIT = "implizit_aus_balance"


def _implizite_kapitalbasis(balance, trade_pfad: str,
                            log: LogCb | None = None,
                            plattform_positions: float | None = None
                            ) -> float | None:
    """Startkapital = Web-Balance − Σ Trade-Netto (nur positive Ergebnisse).

    Keine Messung, aber eine belegte Ableitung aus zwei Plattformwerten —
    deutlich näher an der Realbalance als die starre Virtual-Annahme.
    Parse-Fehler oder nicht-positive Ergebnisse liefern None (dann greift
    der Virtual-Fallback bzw. bleibt die Forensik ohne Basis).
    """
    if isinstance(balance, bool) or not isinstance(balance, (int, float)):
        return None
    balance = float(balance)
    if not math.isfinite(balance) or balance <= 0:
        return None
    try:
        from .parser import load_export
        parsed = load_export(trade_pfad,
                             plattform_positions=plattform_positions)
        netto = sum(t.net for t in parsed.trades)
    except Exception as exc:  # grobe Schaetzung darf den Lauf nie brechen
        if log:
            log(f"Kapitalbasis: implizite Basis nicht berechenbar ({exc}) — "
                "nächste Stufe (virtuelle Annahme).")
        return None
    implizit = balance - netto
    if implizit <= 0:
        if log:
            log(f"Kapitalbasis: implizite Basis {implizit:,.0f} USD nicht "
                "positiv (Gewinne übersteigen die Balance — Ein-/Auszahlungen "
                "unbekannt) — nächste Stufe (virtuelle Annahme).")
        return None
    if log:
        log(f"Kapitalbasis: implizite Annahme {implizit:,.0f} USD "
            f"(Web-Balance {balance:,.0f} − Trade-Netto {netto:,.0f}) — "
            "DD-/Schock-Prozente damit gerechnet.")
    return implizit


def _virtuelle_kapitalbasis(wert, log: LogCb | None = None) -> float | None:
    """InitialDepositVirtual strikt pruefen: endliche, positive JSON-Zahl.

    Der Quellen-Vertrag (z. B. PelicanMonitor) liefert eine JSON-Zahl.
    Infinity (JSON 1e309 parst als inf) wuerde jede DD-/Schock-Prozent-
    Rechnung zu 0 machen und damit eine vollstaendige, risikofreie
    Forensik vortaeuschen; Strings (auch numerische) sind ein Vertrags-
    verstoess und werden abgewiesen statt geraten. Ungueltige Werte
    liefern None — dann gibt es KEINE Basis und die Forensik bleibt
    unvollständig (keine positive Bewertung aus einer Annahme).
    """
    if isinstance(wert, bool) or not isinstance(wert, (int, float)):
        if log and wert is not None:
            log(f"Kapitalbasis: InitialDepositVirtual ist keine JSON-Zahl "
                f"({wert!r}) — Annahme ignoriert, Forensik ohne Basis.")
        return None
    zahl = float(wert)
    if not math.isfinite(zahl) or zahl <= 0:
        if log:
            log(f"Kapitalbasis: InitialDepositVirtual ungueltig ({wert!r}) — "
                "Annahme ignoriert, Forensik ohne Basis.")
        return None
    if log:
        log(f"Kapitalbasis: virtuelle Annahme {zahl:,.0f} USD aus der Datenquelle "
            "(kein Plattformwert — DD-/Schock-Prozente damit gerechnet).")
    return zahl


@dataclass
class StepLog:
    """Sammelt Log-Zeilen je Schritt fuer die GUI-Anzeige."""
    lines: list[str] = field(default_factory=list)

    def __call__(self, text: str) -> None:
        self.lines.append(text)


@dataclass
class ScanResult:
    """Ein Ergebnis-Datensatz je Signal fuer die GUI-Tabelle."""
    id: int
    name: str = ""
    platform: str = ""
    url: str = ""
    autor: str = ""
    abonnenten: float | None = None
    abo_preis_usd: float | None = None
    wochen: float | None = None
    growth_pct: float | None = None
    ertrag_monat_pct: float | None = None
    # B2 (Intensiv-Review 29./30.09.2026): Ertrag/Monat aus der EIGENEN
    # Trade-Kurve auf der Kapitalbasis, gegen die auch DD/Schock gerechnet
    # werden (netto_gesamt / startkapital / Monate). Die Plattformzahl
    # (ertrag_monat_pct) bleibt als Selbstauskunft daneben stehen.
    ertrag_monat_pct_forensik: float | None = None
    # Nutzer-Wunsch 01.10.2026: Rendite-Risiko-EFFIZIENZ (RetDD) —
    # niedriges Risiko allein bringt nichts ohne Gewinn. RetDD =
    # Eigene geometrische Monatsrendite je Prozent GEMESSENEM Equity-DD.
    # Niemals Trading-/Balance-DD als Ersatz. Mindestqualität ist 1,0;
    # jährlicher Wert = Jahres-CAGR / gemessener Equity-DD (nicht ×12).
    retdd_monat: float | None = None
    retdd_jahr: float | None = None
    # Geometrisches Monatsmittel auf der gesamten Export-Zeitspanne;
    # Jahreswert = virtueller CAGR / gemessener Equity-DD. Bei abweichenden
    # Kapitalbasen kein belegter kapitalflussneutraler Konto-Calmar.
    ertrag_monat_geom_pct: float | None = None
    cagr_jahr_pct: float | None = None
    effizienz_befund: dict = field(default_factory=dict)
    pf: float | None = None
    dd_equity_pct: float | None = None     # Plattform "By Equity"
    dd_balance_pct: float | None = None    # Plattform "By Balance"
    # Forensik (nur mit Trade-Export)
    forensik_vorhanden: bool = False
    forensik_version: int | None = None
    trading_dd_pct: float | None = None
    trading_dd_usd: float | None = None
    winrate_pct: float | None = None
    identische_tradezeilen: int = 0
    duplikate_entfernt: int = 0
    # Signalseiten-Angabe "Trades:" — der Plattform-Beweis für/against
    # doppelte Lieferung identischer Zeilen (beweisbasiertes Parser-Dedup).
    plattform_trades: float | None = None
    max_verlustserie: int | None = None
    verlustserie_usd: float | None = None
    peak_positionen: int | None = None
    peak_netto_lots: float | None = None
    shock_usd: float | None = None
    shock_pct_max: float | None = None
    shock_pct_peak_time: str | None = None
    shock_pct_peak_account: float | None = None
    shock_pct_peak_usd: float | None = None
    martingale_flag: bool | None = None
    martingale_evidenz: list | None = None
    stop_nachweis: str = ""
    stop_evidence: str | None = None  # direct | cluster | partial | none; nie aus Freitext ableiten
    # Full code evidence, including SL executions and coordinated loss exits.
    # Behavioural hints never turn into the direct/cluster proof flag.
    stop_befund: dict | None = None
    kapitalbasis_usd: float | None = None  # Signalseite "Initial Deposit" (kann negativ sein)
    # Von der Forensik TATSÄCHLICH verwendete Kapitalbasis (Engine-Befund,
    # nicht die Lauf-Absicht): csv_einzahlungen schlägt jede Injektion. Wird
    # durch Persistenz, DB-Laden und Prompt-JSON geführt — die KI muss wissen,
    # ob DD-/Schock-Prozente gegen eine Annahme gerechnet sind.
    kapitalbasis_verwendet_usd: float | None = None
    # Equity-DD-Rekonstruktion aus Kursdaten (nur bei verlässlicher Abdeckung
    # gesetzt; geht dann als viertes Maximum in die Drawdown-Schranke ein)
    equity_dd_rekonstruiert_pct: float | None = None
    equity_dd_rekonstruiert_usd: float | None = None
    equity_rekon_gmt_h: int | None = None
    equity_rekon_status: str = ""
    equity_rekon_grund: str = ""
    equity_rekon_abdeckung_pct: float | None = None
    equity_rekon_methodik: str = ""
    equity_rekon_zeitbasis: dict = field(default_factory=dict)
    # Fehlende Kurs-/Kontraktsbasis der Equity-Nachmessung (Nutzer-Wunsch
    # 03.10.: im BERICHT sichtbar machen — "wissen, woran man arbeiten
    # kann"). Ohne Kurse: Symbol im Referenzterminal nicht verfügbar;
    # ohne Kontrakt: Kontraktgröße in contract_specs.json nicht belegt.
    equity_rekon_ohne_kurse: list = field(default_factory=list)
    equity_rekon_ohne_kontrakt: list = field(default_factory=list)
    # Vom Datenquellen-Monitor (Pelican/Robo/Vantage/Zulu) aus der vollen
    # Trade-Kurve nachgemessener Max-EQ-DD (metrics "TradeEqDrawdownPct") —
    # unabhängige Zweitmessung auf denselben Trades. Geht seit B1
    # (Intensiv-Review 29./30.09.2026) als FÜNFTES Maximum in die Drawdown-
    # Schranke (floating-inclusive; davor war sie für Quellen-Signale ohne
    # harte floating-Messung, weil die Kursdaten-Reko bei vorhandenem
    # Monitorwert geskippt wird). Basis-Vorbehalt: Der Monitor rechnet gegen
    # seine eigene (ggf. rückgerechnete) Kapitalbasis.
    monitor_trade_eq_dd_pct: float | None = None
    kapitalbasis_verwendet_quelle: str = ""
    broker_server: str | None = None
    symbole: str = ""               # gehandelte Assets ("XAUUSD, US30, ...")
    # Bewertung
    score: float | None = None
    forensik_stale: bool = False        # R2: Forensik älter als letzter Lauf/fehlerhaft
    forensik_aktualisiert: str = ""     # R2: Zeitstempel der Forensik (REST-Altersmarker)
    schranke_verletzt: bool = False
    ampel: str = "⚪"
    urteil: str = "Vorprüfung (ohne Forensik)"
    # LLM-Teilergebnisse (Nutzer-Prinzip: 2 Analysen + 1 Gesamtauswertung)
    trades_path: str = ""           # Quelldatei der Trades (fuer Prompt 1)
    trades_sha256: str = ""         # Inhalt des unveränderlichen Trade-Snapshots
    berichte_basis: str = ""        # Datengrundlage der im Ergebnis enthaltenen KI-Texte
    bericht_hinweis: str = ""
    pdf_fehler: str = ""
    trade_analyse: str = ""         # Prompt 1: Strategie aus den Trades (glm-5.3)
    trade_analyse_at: str = ""
    trade_analyse_model: str = ""
    risiko_analyse: str = ""        # Prompt 2: Risiko-Profil aus Forensik (Flash)
    risiko_analyse_at: str = ""
    risiko_analyse_model: str = ""
    gesamtbericht: str = ""         # Prompt 3: ausfuehrlicher Gesamtbericht (glm-5.3)
    gesamtbericht_at: str = ""      # Erstellungszeitpunkt des enthaltenen Gesamtberichts
    gesamtbericht_model: str = ""
    kurzfassung: str = ""           # Kurzzeile aus dem Gesamtbericht (fuer Tabelle)
    tiefenanalyse: str = ""         # Prompt 5: Erweiterte KI-Analyse (manuell, mit Trades)
    tiefenanalyse_at: str = ""
    tiefenanalyse_model: str = ""
    llm_fehler: str = ""
    fehler: str = ""
    quelle: str = ""                # Herkunfts-Kürzel der Datenquelle (doc/20)
    source_kind: str = "live"  # Demo-Ergebnisse nie in den Live-Katalog übernehmen.
    persisted_this_run: bool = False  # Mindestens ein Versuch dieses analyze_candidate-Aufrufs gespeichert.
    ampel_wechsel: dict | None = None  # Protokollierter Wechsel gegen den letzten Chronik-Eintrag (ampel_verlauf).

    @property
    def equity_rekon_gmt_text(self) -> str:
        """Zeitabschnitte offenlegen; ein globaler Wert beschreibt sie nicht."""
        basis = self.equity_rekon_zeitbasis or {}
        if basis.get("modus") == "wochenweise":
            shifts = sorted({p["gmt_h"] for p in basis.get("perioden", [])
                             if isinstance(p.get("gmt_h"), int)
                             and not isinstance(p.get("gmt_h"), bool)})
            werte = ", ".join(f"{h:+d} h" for h in shifts)
            return "GMT abschnittsweise" + (f" ({werte})" if werte else " unbelegt")
        if self.equity_rekon_gmt_h is not None:
            return f"GMT {self.equity_rekon_gmt_h:+d} h"
        return "GMT unbelegt"

    def _equity_messwerte(self) -> dict[str, float]:
        """Identische gültige Quellen für den Maximalwert und dessen Status.

        Review 04.10. (Paket D/F/G): Der Monitor-Wert (TradeEqDrawdownPct)
        ist bei ALLEN vier JavaFX-Monitoren eine Closing-Kurve (max. plus
        aktueller Floating-Endpunkt), KEINE historisch floating-inklusive
        Equity-Messung — er bleibt Kanal der harten Schranke (B1), darf
        aber Nenner von RetDD/„Max-Drawdown" nicht mehr sein.
        """
        kurse = None if self.forensik_stale else self.equity_dd_rekonstruiert_pct
        quellen = {"Kurse (H1, virtuelle Trading-Equity)": kurse}
        return {quelle: wert for quelle, wert in quellen.items()
                if isinstance(wert, (int, float)) and not isinstance(wert, bool)
                and math.isfinite(wert) and wert >= 0}

    @property
    def max_drawdown_equity_pct(self) -> float | None:
        """Gemessene Equity inklusive Floating; fehlend bleibt unbekannt.

        Einzig gültige Quelle ist die eigene Kurs-Rekonstruktion (H1,
        verlässlich). Plattformangaben, geschlossene Trades und die
        Monitor-Closing-Kurve ersetzen keine Equity-Messung (Regel 03.10.:
        NIEMALS geschlossene Trades, Balance-DD oder Plattform-Selbstauskunft
        als RetDD-Nenner; Monitor seit Review 04.10. ebenso).
        """
        return max(self._equity_messwerte().values(), default=None)

    def refresh_efficiency(self) -> None:
        """Eine RetDD-Formel für Scan, DB, Tabelle, Auswahl und KI.

        Fehlende/veraltete Equity oder Rendite bleibt unbekannt. Gerundet
        wird erst in der Anzeige, damit 0,999 nicht als >=1 durchgeht.
        """
        def endlich(wert):
            return (isinstance(wert, (int, float)) and not isinstance(wert, bool)
                    and math.isfinite(wert))

        if self.forensik_stale or not endlich(self.ertrag_monat_geom_pct):
            self.ertrag_monat_geom_pct = None
        if self.forensik_stale or not endlich(self.cagr_jahr_pct):
            self.cagr_jahr_pct = None
        dd = self.max_drawdown_equity_pct
        self.retdd_monat = (self.ertrag_monat_geom_pct / dd
                            if self.ertrag_monat_geom_pct is not None and dd
                            else None)
        self.retdd_jahr = (self.cagr_jahr_pct / dd
                           if self.cagr_jahr_pct is not None and dd else None)
        for key in ("retdd_monat", "retdd_jahr"):
            if not endlich(getattr(self, key)):
                setattr(self, key, None)
        status = ("veraltet" if self.forensik_stale else
                  "rendite_nicht_berechenbar" if self.ertrag_monat_geom_pct is None else
                  "ohne_equity_dd" if dd is None else
                  "equity_dd_null" if dd == 0 else
                  "retdd_nicht_berechenbar" if self.retdd_monat is None else "ok")
        self.effizienz_befund = {
            **self.effizienz_befund,
            "effizienz_status": status,
            "dd_max_equity_pct": dd,
            "ertrag_monat_geom_pct": self.ertrag_monat_geom_pct,
            "cagr_jahr_pct": self.cagr_jahr_pct,
            "retdd_monat": self.retdd_monat,
            "retdd_jahr": self.retdd_jahr,
            "retdd_basis": "gemessener_max_equity_drawdown_inkl_floating",
            "equity_messung": self.equity_messung_status,
            "formel_monat": "ertrag_monat_geom_pct / dd_max_equity_pct",
            "formel_jahr": "cagr_jahr_pct / dd_max_equity_pct",
            "vergleichbarkeit": (
                "Rendite auf virtueller Trade-Netto-Kurve; Kurs-Equity ebenfalls virtuell. "
                "Monitor-Basis und Zeitraum können abweichen; keine belegte echte "
                "Konto-Effizienz bei abweichenden Kapitalflüssen/Zeiträumen."),
        }

    @property
    def equity_messung_status(self) -> str:
        quellen = self._equity_messwerte()
        if quellen:
            return "Gemessen: " + " / ".join(quellen)
        if self.forensik_stale and (self.equity_rekon_status
                                   or self.equity_dd_rekonstruiert_pct is not None):
            return ("Kurs-Nachmessung veraltet — erneute Prüfung erforderlich"
                    + (" · " + self.equity_rekon_grund if self.equity_rekon_grund else ""))
        if self.equity_rekon_grund:
            return "Keine belastbare Equity-Messung: " + self.equity_rekon_grund
        return "Keine belastbare Equity-Messung vorhanden"

    def to_row(self) -> dict:
        self.refresh_efficiency()
        return {
            "Ampel": self.ampel, "ID": self.id, "Name": self.name,
            "Platform": self.platform, "Quelle": self.quelle or "mql5",
            "Abo $": self.abo_preis_usd,
            "Abos": self.abonnenten, "Wochen": self.wochen,
            "Growth %": self.growth_pct, "Ertrag/Monat %": self.ertrag_monat_pct,
            "PF": self.pf,
            # Max-Drawdown misst Equity inklusive Floating. Die reine
            # Kurve geschlossener Trades wird separat benannt.
            "Drawdown % (Plattform)": self.dd_equity_pct,
            "Balance-DD % (Plattform)": self.dd_balance_pct,
            "Max-Drawdown %": self.max_drawdown_equity_pct,
            "Gewinn %/Monat": self.ertrag_monat_geom_pct,
            "RetDD": self.retdd_monat,
            "Trading-DD % (geschlossen)": self.trading_dd_pct,
            "Equity-Messung": self.equity_messung_status,
            "Winrate %": self.winrate_pct,
            "Verlustserie": self.max_verlustserie,
            "Peak-Pos": self.peak_positionen,
            "Netto-Lots": self.peak_netto_lots,
            "Schock $": self.shock_usd,
            "Martingale": ("JA" if self.martingale_flag else
                           ("nein" if self.martingale_flag is not None else "")),
            "Stop": self.stop_nachweis, "Score": self.score,
            "Kurzfassung": self.kurzfassung, "Urteil": self.urteil,
            "Bericht vom": self.gesamtbericht_at or None,
            "Fehler": self.fehler,
        }


def _equity_rekon_grund(reko: dict) -> str:
    """Diagnose inklusive fehlender Symbole aus dem vorhandenen Snapshot."""
    grund = reko.get("grund") or ""
    fehlend = reko.get("symbole_ohne_kurse") or []
    if fehlend:
        grund += (" · " if grund else "") + "Kurse fehlen: " + ", ".join(fehlend)
    return grund


def results_from_db(settings: dict | None = None) -> list[ScanResult]:
    """Alle in der SQLite-DB gespeicherten Signale als ScanResult-Liste."""
    settings = {**config.load_settings(), **(settings or {})}
    results: list[ScanResult] = []
    for row in db.list_catalog():
        stats = row.get("stats") or {}
        f = row.get("forensik") or {}
        if not isinstance(f, dict):
            f = {}
        peak = f.get("peak_exposure") or {}
        trading = f.get("trading_dd") or {}
        # Flaches Alt-Schema aus analyze_local_files (trading_dd_pct ohne Nesting).
        if not trading and f.get("trading_dd_pct") is not None:
            trading = {"pct": f.get("trading_dd_pct"), "usd": f.get("trading_dd_usd")}
        last_fehler = stats.get("last_fehler")
        signal_updated = row.get("signal_updated") or ""
        forensik_updated = row.get("forensik_updated") or ""
        forensik_ok = stats.get("forensik_ok")
        # Teilergebnis-Payloads (vollstaendig=False): Werte zeigen, aber nicht
        # als vollstaendige Forensik werten — der Grund steht im Fehlerfeld.
        vollstaendig = f.get("vollstaendig", True)
        # Aktuelle Forensik nur, wenn der letzte Scan sie explizit bestanden hat.
        # Legacy (ohne forensik_ok): last_fehler + Zeitstempel (>= wegen Sekundenaufloesung).
        if forensik_ok is False:
            forensik_stale = bool(f) and vollstaendig
        elif forensik_ok is True:
            forensik_stale = False
        else:
            forensik_stale = bool(last_fehler) and (
                not f or not forensik_updated or signal_updated >= forensik_updated
            )
        version_current = (f.get("version") == FORENSICS_VERSION
                           and stats.get("forensik_version") == FORENSICS_VERSION
                           and peak.get("shock_pct_max") is not None)
        # Unvollstaendige Teilergebnisse sind bekannt-begruendet, nicht "veraltet".
        version_stale = bool(f) and not version_current and vollstaendig
        forensik_stale = forensik_stale or version_stale
        res = ScanResult(
            id=int(row["signal_id"]),
            source_kind="demo" if row.get("platform") == "CSV" else "live",
            name=row.get("name") or str(row["signal_id"]),
            platform=row.get("platform") or "",
            url=row.get("url") or "",
            autor=row.get("autor") or "",
            abonnenten=row.get("abonnenten"),
            abo_preis_usd=row.get("abo_preis"),
            wochen=row.get("wochen"),
            quelle=str(row.get("quelle") or "mql5"),
            growth_pct=stats.get("growth_pct"),
            ertrag_monat_pct=stats.get("ertrag_monat_pct"),
            ertrag_monat_pct_forensik=stats.get("ertrag_monat_pct_forensik"),
            pf=stats.get("pf"),
            dd_equity_pct=stats.get("eq_dd_pct"),
            dd_balance_pct=stats.get("bal_dd_pct"),
            forensik_vorhanden=bool(f) and vollstaendig and not forensik_stale,
            forensik_version=f.get("version"),
            forensik_stale=forensik_stale,
            forensik_aktualisiert=forensik_updated,
            trading_dd_pct=trading.get("pct", f.get("trading_dd_pct")),
            trading_dd_usd=trading.get("usd", f.get("trading_dd_usd")),
            winrate_pct=f.get("winrate_pct"),
            identische_tradezeilen=f.get("identische_tradezeilen", 0),
            duplikate_entfernt=f.get("duplikate_entfernt", 0),
            plattform_trades=f.get("plattform_trades"),
            # B24-Fix (02.10.): RetDD-Kennzahlen aus dem Forensik-Snapshot
            # mitlesen — sonst wären sie nach DB-Reload/Neustart weg.
            ertrag_monat_geom_pct=f.get("ertrag_monat_geom_pct"),
            cagr_jahr_pct=f.get("cagr_jahr_pct"),
            retdd_monat=f.get("retdd_monat"),
            retdd_jahr=f.get("retdd_jahr"),
            effizienz_befund=f.get("effizienz_befund") or {},
            max_verlustserie=f.get("max_verlustserie"),
            verlustserie_usd=f.get("verlustserie_usd"),
            peak_positionen=peak.get("positionen", f.get("peak_positionen")),
            peak_netto_lots=peak.get("netto_lots", f.get("peak_netto_lots")),
            shock_usd=peak.get("schock_usd", f.get("shock_usd")),
            shock_pct_max=peak.get("shock_pct_max"),
            shock_pct_peak_time=peak.get("shock_pct_peak_time"),
            shock_pct_peak_account=peak.get("shock_pct_peak_account"),
            shock_pct_peak_usd=peak.get("shock_pct_peak_usd"),
            martingale_flag=f.get("martingale_flag"),
            martingale_evidenz=f.get("martingale_evidenz") or [],
            stop_nachweis=f.get("stop_nachweis") or "",
            stop_evidence=f.get("stop_evidence"),
            stop_befund=f.get("stop_befund") if isinstance(f.get("stop_befund"), dict) else None,
            kapitalbasis_usd=stats.get("initial_deposit_usd"),
            # Monitor-Nachmessung (Datenquellen-Signale; None ohne Quelle)
            monitor_trade_eq_dd_pct=stats.get("monitor_trade_eq_dd_pct"),
            # Tatsächlich verwendete Kapitalbasis aus dem Forensik-Snapshot
            # (führt durch DB-Reload und Prompt-JSON; siehe ScanResult-Felder)
            equity_dd_rekonstruiert_pct=(f.get("equity_rekonstruktion") or {}).get(
                "equity_dd_pct_raw", (f.get("equity_rekonstruktion") or {}).get(
                    "equity_dd_pct")) if (f.get("equity_rekonstruktion") or {}).get(
                "verlaesslich") else None,
            equity_dd_rekonstruiert_usd=(f.get("equity_rekonstruktion") or {}).get(
                "equity_dd_usd") if (f.get("equity_rekonstruktion") or {}).get(
                "verlaesslich") else None,
            equity_rekon_gmt_h=(f.get("equity_rekonstruktion") or {}).get(
                "gmt_offset_h"),
            equity_rekon_status=(f.get("equity_rekonstruktion") or {}).get("status") or "",
            equity_rekon_grund=_equity_rekon_grund(f.get("equity_rekonstruktion") or {}),
            equity_rekon_abdeckung_pct=(f.get("equity_rekonstruktion") or {}).get("abdeckung_pct"),
            equity_rekon_methodik=(f.get("equity_rekonstruktion") or {}).get("methodik") or "",
            equity_rekon_zeitbasis=(f.get("equity_rekonstruktion") or {}).get("zeitbasis") or {},
            equity_rekon_ohne_kurse=(f.get("equity_rekonstruktion") or {}).get(
                "symbole_ohne_kurse") or [],
            equity_rekon_ohne_kontrakt=(f.get("equity_rekonstruktion") or {}).get(
                "symbole_ohne_kontrakt") or [],
            kapitalbasis_verwendet_usd=(f.get("kapitalbasis") or {}).get("usd")
            if isinstance(f.get("kapitalbasis"), dict) else None,
            kapitalbasis_verwendet_quelle=(f.get("kapitalbasis") or {}).get("quelle") or ""
            if isinstance(f.get("kapitalbasis"), dict) else "",
            broker_server=stats.get("broker_server"),
            symbole=f.get("symbole") or "",
            score=None if forensik_stale else f.get("score"),
            trades_path=row.get("trades_path") or "",
            trades_sha256=row.get("trades_sha256") or "",
            trade_analyse=row.get("trade_analyse") or "",
            trade_analyse_at=row.get("trade_at") or "",
            trade_analyse_model=row.get("trade_model") or "",
            risiko_analyse=row.get("risiko_analyse") or "",
            risiko_analyse_at=row.get("risiko_at") or "",
            risiko_analyse_model=row.get("risiko_model") or "",
            gesamtbericht=row.get("gesamtbericht") or "",
            gesamtbericht_at=row.get("gesamt_at") or "",
            gesamtbericht_model=row.get("gesamt_model") or "",
            tiefenanalyse=row.get("tiefenanalyse") or "",
            tiefenanalyse_at=row.get("tiefe_at") or "",
            tiefenanalyse_model=row.get("tiefe_model") or "",
            fehler=last_fehler or "",
        )
        if forensik_stale and f:
            res.urteil = (f"Veraltete Forensik nach fehlgeschlagenem Neu-Lauf ({last_fehler})"
                          if last_fehler else
                          "Forensik-Version veraltet — erneute Prüfung erforderlich.")
        if res.dd_equity_pct is not None or res.trading_dd_pct is not None \
                or res.dd_balance_pct is not None:
            limit = float(settings.get("schranke_eq_dd_pct", 30.0))
            # F-12: EINE Schranken-Definition (scoring.dd_maximum) statt
            # vier duplizierter max()-Aufrufe. B6 (Lauf-Review 02.10.): Auch
            # beim DB-Laden gehört die Monitor-Zweitmessung ins Maximum —
            # sonst verliert eine unvollständige Forensik die rote Sperre
            # (identisch zu refresh_report_verdict, sonst wäre die Anzeige
            # schwächer als der Scan).
            res.schranke_verletzt = scoring.dd_maximum(
                res.dd_equity_pct, res.trading_dd_pct, res.dd_balance_pct,
                res.equity_dd_rekonstruiert_pct,
                res.monitor_trade_eq_dd_pct) > limit
        if res.gesamtbericht:
            res.kurzfassung = _extract_kurzfassung(res.gesamtbericht)
        if any((res.trade_analyse, res.risiko_analyse, res.gesamtbericht,
                res.tiefenanalyse)):
            try:
                from .pdf_reports import materialize_result_pdfs
                materialize_result_pdfs(res)
            except Exception as exc:
                res.pdf_fehler = f"PDF-Speicherung fehlgeschlagen: {type(exc).__name__}: {exc}"
        res.ampel, res.urteil = ampel_for(res, settings)
        if forensik_stale and last_fehler:
            res.urteil = f"Fehler (Forensik veraltet): {last_fehler}"
        elif forensik_stale:
            res.urteil = "Forensik veraltet oder unvollständig — erneute Prüfung erforderlich."
        restore_current_reports(res, settings)
        # Virtuelle Kapitalbasis dauerhaft im Urteil kennzeichnen (auch nach
        # App-Neustart). Zentrale, idempotente Kennzeichnung — restore/refresh
        # baut das Urteil neu, der Hinweis bleibt dadurch erhalten.
        _kennezeichne_virtuelle_kapitalbasis(res)
        # Rekonstruierter Equity-DD aus Kursen — Messwert im Urteil sichtbar
        # halten (auch nach App-Neustart); idempotent per Marker-Suche.
        if (res.equity_dd_rekonstruiert_pct is not None
                and res.forensik_vorhanden and not res.fehler
                and "Max-DD (Kurse)" not in (res.urteil or "")):
            res.urteil = (res.urteil or "") + (
                f" · Max-DD aus Kursen {res.equity_dd_rekonstruiert_pct} % "
                f"({res.equity_rekon_gmt_text})")
        results.append(res)
    return results


def ampel_for(result: ScanResult, settings: dict) -> tuple[str, str]:
    """Risiko VOR Ertrag; Grün erfordert Forensik, Gewinn und Equity-RetDD.

    Bewiesene rote Flags (Martingale-Signatur aus dem Trade-Muster) gelten
    auch bei sonst unvollständiger Forensik — Kapitalbasis braucht dafuer
    niemand. Alles andere bleibt ohne vollstaendige Batterie Vorprüfung.
    """
    result.refresh_efficiency()
    limit = float(settings.get("schranke_eq_dd_pct", 30.0))
    result.schranke_verletzt = scoring.dd_maximum(
            result.dd_equity_pct, result.dd_balance_pct, result.trading_dd_pct,
            result.equity_dd_rekonstruiert_pct, result.monitor_trade_eq_dd_pct) > limit
    known = config.load_known_signals()
    excluded = {e["id"]: e for e in known.get("ausgeschlossen", [])}
    if result.id in excluded:
        return "⛔", f"Ausgeschlossen (Liste): {excluded[result.id].get('grund', '')}"
    if result.martingale_flag:
        return "🔴", "Martingale-Signatur nachgewiesen (Ablehnung)"
    if result.kapitalbasis_usd is not None and result.kapitalbasis_usd <= 0:
        betrag = f"{result.kapitalbasis_usd:+,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return "🔴", (
            f"Kapitalbasis negativ: die Signalseite nennt einen Initial Deposit "
            f"von {betrag} USD (von MQL5 rueckwaerts aus "
            "Kontostand, Profit, Deposits und Withdrawals abgeleitet — entnommenes "
            "Kapital uebertraf den Signalstart). Das Startkapital ist nicht "
            "belegbar, Drawdown- und Schockpruefung sind unmoeglich — harte Ablehnung.")
    # F-3 (Review 29.09.): Eine bewiesene Schrankenverletzung schweigt nicht
    # mehr hinter einem Zusatz-Fehler (45 % DD + Fehler = ROT, nicht Weiss).
    # BEWEISBAR ist sie aber nur, wenn (a) die Plattform-DDs sie SELBST
    # reissen (die brauchen keine Forensik) oder (b) die Forensik komplett
    # ist — sonst ist ein hoher Trading-DD ein Platzhalter (z. B. 100 %
    # bei unbekannter Kapitalbasis) und der Fall bleibt Fehler/Vorpruefung.
    if result.schranke_verletzt:
        limit = float(settings.get("schranke_eq_dd_pct", 30))
        plattform_dd = scoring.dd_maximum(result.dd_equity_pct,
                                          result.dd_balance_pct,
                                          result.monitor_trade_eq_dd_pct)
        if plattform_dd > limit or result.forensik_vorhanden:
            return "🔴", f"Schranke verletzt: Drawdown > {limit:g} % (harte Ablehnung)"
    if result.fehler and not result.forensik_vorhanden:
        return "⚪", f"Fehler: {result.fehler}"
    if result.fehler:
        return "⚪", f"Prüfung mit Fehler: {result.fehler}"
    if result.forensik_vorhanden:
        # Nutzer-Regel 28.09.2026: Fehlender SL-Nachweis ist NEUTRAL — die
        # meisten Broker übertragen keinen SL. Kandidat entscheidet sich über
        # Schranke, Score und Ertrag; die Stop-Evidenz ist nur Kontext, und
        # abwerten darf allein die KI (begründete Verhaltens-Einschätzung).
        stop_kontext = {
            "direct": "Stop bewiesen",
            "cluster": "Stop per Cluster-Signatur belegt",
            "partial": "Stop teilweise belegt",
        }.get(result.stop_evidence or "", "SL nicht übertragen (neutral — KI schätzt ab)")
        # Nutzer-Entscheidung 04.10.: Das versteckte Score-Gate (score < 5,0
        # als Vorbedingung des Grün-Wegs) ist ENTFERNT. Der Risiko-Score
        # enthält zwei Default-Dimensionen mit fest 5,0 (Broker offshore,
        # Transparenz) — für Quellen-Signale fast unerreichbar; das Gate
        # blockierte damit exakt den messbaren Grün-Weg (Ertrag + RetDD,
        # Nutzer-Regeln 01./02.10.) — realer Fall HRC Algo: DD 2,0 %,
        # Ertrag 10,1 %/M, RetDD 5,1, Score 5,8 = Gelb. Der Score bleibt
        # sichtbare Ampel-Matrix-Zelle und Zahl im Urteil, sperrt aber
        # nicht mehr. Grün entscheiden die harten Regeln (Schranke,
        # Martingale, Ausschlussliste) plus Ertrag und RetDD.
        min_return = settings.get("min_ertrag_pct_monat", 5.0)
        # B2 (Intensiv-Review): Grünt das Ertragskriterium, zählt die
        # EIGENE Kurve auf der Forensik-Kapitalbasis — die Plattformzahl
        # (fremde Basis) steht daneben, entscheidet aber nicht mehr.
        ertrag_wert = result.ertrag_monat_geom_pct
        if ertrag_wert is None:
            return "🟡", (f"Forensik ok ({stop_kontext}), aber eigene geometrische "
                          "Monatsrendite unbelegt — ohne Gewinnnachweis kein Kandidat")
        if (ertrag_wert or 0) >= min_return:
            # Nutzer-Regel 02.10. („retdd=1 minimum — RetDD ist wichtig
            # und gehört in die Berechnung"): Grün erfordert die
            # Mindest-Effizienz. Ohne belegbare RetDD-Basis gibt es
            # ebenfalls kein Grün (Risiko VOR Ertrag — eine unbezahlte
            # oder unbelegte Effizienz ist keine Empfehlungsgrundlage).
            if result.retdd_monat is None:
                return "🟡", (f"Forensik + Ertrag ok ({stop_kontext}), "
                              "aber RetDD unbelegt (keine positive gemessene Equity-DD-Basis) — "
                              "ohne Effizienznachweis kein Kandidat "
                              "(Nutzer-Regel 02.10.)")
            if result.retdd_monat < 1.0:
                return "🟡", (f"Forensik + Ertrag ok ({stop_kontext}), aber "
                              f"RetDD {result.retdd_monat:g} < 1,0 — der "
                              "Ertrag trägt das eingegangene Risiko nicht "
                              "ausreichend (Mindest-Effizienz, Nutzer-Regel "
                              "02.10.)")
            retdd_text = (f", RetDD {result.retdd_monat:g}/M"
                          if result.retdd_monat is not None else "")
            geom_text = (f" (geom. {ertrag_wert:g} %/M)"
                         if ertrag_wert is not None else "")
            score_text = (f", Risiko-Score {result.score:g}"
                          if result.score is not None else "")
            return "🟢", (f"Kandidat: Forensik bestanden, Ertrag ok{geom_text}"
                          f"{retdd_text}{score_text} · {stop_kontext}")
        return "🟡", (f"Forensik ok ({stop_kontext}), aber Ertrag < {min_return:g} %/Monat "
                      f"(geom. {ertrag_wert:g})")
    return "⚪", "Vorprüfung (ohne Trade-Export-Forensik)"


def _kriterien_text(settings: dict) -> str:
    return (f"- Harte Schranke: max. {settings.get('schranke_eq_dd_pct', 30)} % Drawdown — "
            "gewertet wird das MAXIMUM aus dem Plattform-Drawdown (By Equity "
            "und By Balance — Selbstauskunft), dem aus den Trades selbst "
            "berechneten Trading-DD (geschlossen), dem Max-Drawdown aus "
            "Kursmessung (Equity inklusive Floating; nur bei belastbarer Abdeckung) UND "
            "der floating-inclusiven Zweitmessung des Datenquellen-Monitors "
            "(dessen Kapitalbasis kann von der Scanner-Basis abweichen — "
            "über 100 % überzeichnet absolut)\n"
            f"- Mindest-Ertrag: {settings.get('min_ertrag_pct_monat', 5)} %/Monat — "
            "maßgeblich ist die eigene geometrische Monatsrendite "
            "(ertrag_monat_geom_pct) auf der tatsächlichen Zeitspanne des Exports; "
            "linearer Startbasis-Ertrag und Plattformwert sind Zusatzinformationen\n"
            "- Mindest-RetDD: 1,0 pro Monat. RetDD = eigene geometrische Gewinn-%/Monat "
            "/ gemessener Max-Equity-Drawdown in %. Niemals geschlossenen Trading-DD, "
            "Balance-DD oder Plattform-DD als Ersatz verwenden. Fehlende positive "
            "Equity-Messung = RetDD unbekannt, kein Grün. Jahreswert = CAGR / "
            "gemessener Equity-DD, nicht Monatswert mal zwölf\n"
            f"- Listen-Vorfilter: mindestens {settings.get('min_wochen', 26)} Wochen "
            f"und {settings.get('min_abonnenten', 0)} Abonnenten; Fix-IDs umgehen diese "
            "Vorfilter, aber keine Bewertungsregel. Abonnenten sind kein Qualitätsbeweis\n"
                        "- Risiko VOR Ertrag. Bewiesener Stop-Loss (Orderbuch oder eindeutige "
            "Cluster-Signatur) entlastet; ein FEHLENDER Nachweis ist neutral - "
            "kein Malus, keine Sperre, kein Abwertungsgrund (bindende Nutzer-Regel "
            "28.09.2026). Abwerten darf nur die Analyse mit begründetem "
            "Befund (z. B. Verhaltens-Signatur ohne Stop-Schutz)\n"
            "- Schockszenario (Peak-Exposure in USD) ist ein Stress-Szenario zur "
            "Gewichtung und Warnung — kein gemessener Verlust und allein KEIN "
            "Ablehnungsgrund\n"
            "- Keine positive Einstufung vor vollstaendiger Forensik-Batterie")


def _kandidat_json(r: ScanResult) -> str:
    """Kandidaten-Kennzahlen als JSON (LLM-Payload, AGENTS.md Design-Regel 1)."""
    r.refresh_efficiency()
    return json.dumps({
        "id": r.id, "name": r.name, "platform": r.platform,
        "autor": r.autor, "url": r.url,
        "wochen": r.wochen, "abonnenten": r.abonnenten,
        "abo_preis_usd": r.abo_preis_usd,
        "growth_pct": r.growth_pct, "ertrag_monat_pct": r.ertrag_monat_pct,
        "ertrag_monat_pct_forensik": r.ertrag_monat_pct_forensik,
        # K1: Plattformwert = Selbstauskunft auf EIGENER Basis; der
        # Forensikwert ist der comparable Maßstab (s. Definition im
        # Forensik-JSON). Kein Widerspruch, sondern zwei Basen.
        "ertrag_hinweis": "ertrag_monat_geom_pct (eigene geometrische Gewinn-%/Monat) "
                          "ist maßgeblich; Plattform- und lineare Startbasis-Rendite "
                          "sind Zusatzinformationen",
        # Nutzer-Regel 03.10.: Gewinn und Effizienz auf gemessenem Equity-DD.
        # Mindestqualität 1,0; Zahlen entstehen ausschließlich im Code.
        "retdd_monat": r.retdd_monat,
        "retdd_jahr": r.retdd_jahr,
        "ertrag_monat_geom_pct": r.ertrag_monat_geom_pct,
        "cagr_jahr_pct": r.cagr_jahr_pct,
        "max_drawdown_equity_pct": r.max_drawdown_equity_pct,
        "equity_messung_status": r.equity_messung_status,
        "effizienz_befund": r.effizienz_befund,
        "pf": r.pf, "dd_equity_pct": r.dd_equity_pct,
        "dd_balance_pct": r.dd_balance_pct,
        "broker_server": r.broker_server,
        "assets": r.symbole,
        "score_engine": r.score, "ampel": r.ampel,
        "urteil": r.urteil,
        "schranke_verletzt": r.schranke_verletzt,
    }, ensure_ascii=False)


def _forensik_json(r: ScanResult) -> str:
    """Engine-Forensik als JSON (LLM-Payload, AGENTS.md Design-Regel 1)."""
    r.refresh_efficiency()
    # getattr-Härtung: Ergebnisobjekte aus einer älteren Klassendefinition
    # (Server-Neustart mitten im Deploy — realer Fall SFE Impulse 03.10.
    # 22:16: 'ScanResult' object has no attribute ...) dürfen den BERICHT
    # nicht crashen; die Listen sind dann einfach leer.
    _ohne_kurse = getattr(r, "equity_rekon_ohne_kurse", None) or []
    _ohne_kontrakt = getattr(r, "equity_rekon_ohne_kontrakt", None) or []
    return json.dumps({
        "trading_dd": {"pct": r.trading_dd_pct, "usd": r.trading_dd_usd},
        "winrate_pct": r.winrate_pct,
        "max_verlustserie": r.max_verlustserie,
        "verlustserie_usd": r.verlustserie_usd,
        "peak_exposure": {
            "positionen": r.peak_positionen,
            "netto_lots": r.peak_netto_lots,
            "schock_usd": r.shock_usd,
            # EINHEITEN (B11, Intensiv-Review 29./30.09.2026 — beide LLM-
            # Stufen lasen das USD-Feld als Prozent): Felder mit Suffix _usd
            # sind USD-BETRAEGE, Felder mit _pct sind PROZENT.
            # shock_pct_max = einziger Prozentwert (Schock in % des Kontos);
            # shock_pct_peak_account ist der historische Kontostand in USD am
            # Peak (Namensaltlast, Wert = USD), shock_pct_peak_usd der
            # Schockbetrag in USD am Peak.
            "shock_pct_max": r.shock_pct_max,
            "shock_pct_peak_time": r.shock_pct_peak_time,
            "shock_pct_peak_account": r.shock_pct_peak_account,
            "shock_pct_peak_account_usd": r.shock_pct_peak_account,
            "shock_pct_peak_usd": r.shock_pct_peak_usd},
        "martingale_flag": r.martingale_flag,
        "martingale_evidenz": r.martingale_evidenz,
        "stop_nachweis": r.stop_nachweis,
        "stop_evidence": r.stop_evidence,
        # Preserve the identity of legacy reports that did not carry these
        # facts; new scans bind their complete stop evidence to report_basis.
        **({"stop_befund": r.stop_befund} if r.stop_befund is not None else {}),
        # K1 (Fremd-Review 01.10.): Die Engine-Vollstaendigkeit EXPLIZIT
        # nennen — 18 von 54 Gesamtberichten erklaerten die Pflichtbatterie
        # aus nullwertigen Payload-Feldern fälschlich für unvollständig,
        # obwohl die Engine vollstaendig=true gespeichert hatte. Und die
        # Kapitalbasis IMMER liefern (auch belegt per CSV): null wurde als
        # "fehlende Basis" missdeutet.
        "forensik_vollstaendig": bool(r.forensik_vorhanden and not r.fehler),
        **({"trade_datenqualitaet": {
            "identische_tradezeilen": r.identische_tradezeilen,
            "behandlung": (
                "bewiesen doppelte Lieferung entfernt — die Plattform-Anzahl "
                "deckt sich nur ohne die Mehrfachzeilen"
                if r.duplikate_entfernt else
                "alle erhalten; ohne Ticket-ID kein Nachweis einer Doppellieferung"),
            **({"duplikate_entfernt": r.duplikate_entfernt}
               if r.duplikate_entfernt else {}),
            **({"plattform_trades": r.plattform_trades}
               if r.plattform_trades is not None else {})}}
           if r.identische_tradezeilen else {}),
        "kapitalbasis_verwendet": (
            {"usd": r.kapitalbasis_verwendet_usd,
             "quelle": r.kapitalbasis_verwendet_quelle or "csv_einzahlungen"}
            if r.kapitalbasis_verwendet_usd is not None else None),
        # K1: Optionale Messungen brauchen einen STATUS statt stiller null —
        # null heißt jetzt ausdrücklich "Messung nicht verfügbar/geskippt",
        # nicht "Pflicht fehlt".
        "status_optionaler_messungen": {
            "reko_eq_dd": ("veraltet — erneute Pruefung erforderlich" if r.forensik_stale
                           else "gemessen" if r.equity_dd_rekonstruiert_pct is not None
                           else r.equity_messung_status + " — OPTIONAL, kein Pflichtteil"),
            "monitor_eq_dd": ("gemessen" if r.monitor_trade_eq_dd_pct is not None
                              else "nicht_verfuegbar (Datenquelle ohne "
                                   "Zweitmessung) — OPTIONAL, kein Pflichtteil"),
        },
        # K1/B2-Präzisierung (Fremd-Review 01.10.): Definition des
        # Forensik-Ertrags offenlegen — linearer Ø seit Start auf der
        # Start-Basis, KEINE zeitgewichtete Rendite; die Plattformzahl kann
        # eine andere Basis nutzen.
        "ertrag_forensik_definition": (
            "linearer Durchschnitt: Summe Trade-Netto / Startkapital / Monate "
            "seit erstem Trade; Zusatzinformation, kein Ertrags-Auswahlkriterium. "
            "Maßgeblich ist die eigene geometrische Monatsrendite: "
            "100 * ((Endkapital_virtuell / Startkapital) ** (1 / Dauer_Monate) - 1); "
            "Dauer vom ersten Open bis letzten Close, Jahr 365,2425 Tage / 12 Monate"),
        # RetDD = geometrische Monatsrendite / gemessener Equity-DD.
        # Jahreswert nutzt CAGR; geschlossene Trades ersetzen nie Equity.
        "retdd_monat": r.retdd_monat,
        "retdd_jahr": r.retdd_jahr,
        "ertrag_monat_geom_pct": r.ertrag_monat_geom_pct,
        "cagr_jahr_pct": r.cagr_jahr_pct,
        "max_drawdown_equity_pct": r.max_drawdown_equity_pct,
        "equity_messung_status": r.equity_messung_status,
        "effizienz_befund": r.effizienz_befund,
        # Nachgemessener Equity-DD aus Kursdaten (floating inklusive) — die KI
        # soll ihn als Messung deuten und gegen den gemeldeten Wert stellen.
        "equity_dd_rekonstruiert_pct": r.equity_dd_rekonstruiert_pct,
        # Nutzer-Wunsch 03.10.: Fehlende Kurs-/Kontraktsbasis IM BERICHT
        # nennen — der Nutzer will wissen, woran er arbeiten kann (Symbol
        # im Referenzterminal verfügbar machen / Kontraktgröße belegen).
        **({"fehlende_kursdaten": {
            "ohne_kurse": _ohne_kurse,
            "ohne_kontrakt": _ohne_kontrakt,
            "folge": "Für diese Symbole lief die Equity-Nachmessung nicht — "
                     "der gemessene Max-Drawdown kann zu NIEDRIG sein.",
            "handlung": "Kurs-Symbol im MT5-Referenzterminal verfügbar machen "
                        "bzw. Kontraktgröße in data/contract_specs.json "
                        "belegen; dann Signal neu scannen."}}
           if (_ohne_kurse or _ohne_kontrakt) else {}),
        "equity_rekonstruktion_methodik": {
            "status": "veraltet" if r.forensik_stale else r.equity_rekon_status or (
                "ok" if r.equity_dd_rekonstruiert_pct is not None else "nicht_verfuegbar"),
            "grund": r.equity_rekon_grund or None,
            "abdeckung_pct": r.equity_rekon_abdeckung_pct,
            "methodik": r.equity_rekon_methodik or "virtuelle_trading_equity_h1_schlusskurse",
            "zeitbasis": r.equity_rekon_zeitbasis or None,
            "kursraster": "H1-Schlusskurse am Bar-Ende; keine Intrabar-Extrema",
            "drawdown_definition": "groesster relativer Rueckgang vom bisherigen Equity-Hoechststand",
            "kapitalfluesse": "Startkapital + realisiertes Netto + Floating; spaetere Ein-/Auszahlungen fehlen",
            "positionsbasis": "geschlossene Exportpositionen; aktuell offene Positionen fehlen",
            "vergleichbarkeit": "nur bei gleicher DD-Definition, Kapitalbasis, Zeitraum und belegter Datenabdeckung",
            "plattform_mql_hinweis": (
                "Die oeffentliche MQL-Drawdown-Grafik berechnet Floating-Verlust / zeitgleiche Balance; "
                "bei den drei am 03.10.2026 geprueften Signalen entsprach deren Maximum exakt By Equity. "
                "Diese Kennzahl ist kein Peak-to-Trough-DD unserer Equity-Kurve. "
                "Listen-/Radar-Maximum ist das groessere von By Balance und By Equity."),
        },
        # Unabhängige Zweitmessung des Datenquellen-Monitors (volle Trade-
        # Kurve, floating inklusive) — geht seit B1 (Intensiv-Review
        # 29./30.09.2026) als fünftes Maximum in die Drawdown-Schranke
        # ein. Basis-Vorbehalt: Der Monitor rechnet gegen seine eigene
        # (ggf. rückgerechnete) Kapitalbasis.
        "monitor_trade_eq_dd_pct": r.monitor_trade_eq_dd_pct,
    }, ensure_ascii=False)


def _stop_evidence_text(stops: dict) -> str:
    if stops.get("evidence_level") == 1:
        if "positions_with_sl" in stops:
            text = f"Orderbuch: {stops['positions_with_sl']}/{stops.get('positions_total')} mit SL"
        else:
            text = (f"Orderbuch: {stops.get('positions_with_sl_tp')}/"
                    f"{stops.get('positions_total')} mit SL/TP")
        if stops.get("exits_sl"):
            text += f"; {stops['exits_sl']} [sl]-Ausführungen"
    else:
        # Missing exported SL is neutral, not evidence of absent protection.
        text = stops.get("verdict",
                         "SL nicht übertragen — neutral (KI schätzt aus dem Verhalten ab)")
    signature = stops.get("schutzsignatur") or {}
    if signature.get("qualifizierte_verlustgruppen"):
        text += (f"; {signature['qualifizierte_verlustgruppen']} koordinierte Verlust-Exits "
                 f"an {signature.get('tage_mit_verlustgruppen', 0)} Tagen "
                 f"(Schutz-{signature.get('status')}, kein zusätzlicher SL-Beweis)")
    return text


def _kapitalbasis_abgleich(drawdown_befund: dict, stats: dict) -> tuple[bool, str]:
    """Kapitalbasis-Abgleich: Eine von der Signalseite injizierte Kapitalbasis
    ("Initial Deposit") muss den rekonstruierten Endkontostand erklaeren
    (Basis + alle CSV-Fluesse + Netto == Webseiten-Balance). Toleranz
    max(5 USD, 2 %) — die Signalseite rundet (M3, Review-Handoff 29.09.:
    "auf den Cent" war eine AGENTS-Floskel, die der Code nie geliefert hat).

    Returns (ok, fehlermeldung). Bei Kapitalbasis aus CSV-Einzahlungen ent-
    faellt der Check — ein aelterer Cache-Export darf real abweichen, ohne
    die Bewertung umzuwerfen. Dasselbe gilt fuer die VIRTUELLE Annahme aus
    einem Quellen-Monitor (kein Plattformwert) und die IMPLIZITE Basis
    (B3, Intensiv-Review): Sie ist per Konstruktion aus der Web-Balance
    abgeleitet — der Abgleich wäre tautologisch.
    """
    quelle = drawdown_befund.get("startkapital_quelle", "csv_einzahlungen")
    if quelle in ("csv_einzahlungen", KAPITALBASIS_QUELLE_VIRTUELL,
                  KAPITALBASIS_QUELLE_IMPLIZIT):
        return True, ""
    web_kontostand = stats.get("balance_usd")
    real = drawdown_befund.get("end_balance_real")
    if web_kontostand is None:
        return False, ("Kapitalbasis aus Signalseite unbestätigt: die "
                       "Kennzahlen-Seite enthielt keinen 'Balance'-Wert — "
                       "Startkapital nicht belastbar, bleibt Vorprüfung.")
    differenz = abs(float(real) - float(web_kontostand))
    if differenz > max(5.0, abs(float(web_kontostand)) * 0.02):
        return False, ("Kapitalbasis unbestätigt: rekonstruierter Endkontostand "
                       f"{real:.2f} USD weicht um {differenz:.2f} USD vom "
                       f"Webseiten-Kontostand {float(web_kontostand):.2f} USD ab "
                       "(Toleranz max(5 USD, 2 %)) — Trade-Export und Signalseite "
                       "passen nicht zusammen (Cache-Export? Historie gekürzt?).")
    return True, ""


def report_basis_for(result: ScanResult, settings: dict) -> str | None:
    """Stable identity of the facts and criteria used for signal reports.

    Timestamps and storage paths are not evidence: identical CSV bytes and
    facts may reuse a report, while changed risk inputs must not do so.
    """
    # F-4 (Review 29.09.): Risiko-relevante Kandidaten-Felder — volatile
    # Meta-Daten (Abonnenten, Abo-Preis, Wochen, Broker, Autor) stehen
    # bewusst NICHT darin.
    _BASIS_FAKTEN_FELDER = frozenset(
        {"id", "growth_pct", "ertrag_monat_pct", "pf",
         "dd_equity_pct", "dd_balance_pct", "assets", "score_engine"})
    csv_hash = result.trades_sha256
    if not csv_hash and result.trades_path:
        try:
            csv_hash = db.file_sha256(result.trades_path)
        except OSError:
            return None
    facts = json.loads(_kandidat_json(result))
    # Derived display fields are reconstructed from the same facts/criteria.
    facts.pop("ampel", None)
    facts.pop("urteil", None)
    facts.pop("schranke_verletzt", None)
    # F-4 (Review 29.09.): Nur RISIKO-relevante Felder identifizieren einen
    # Bericht. Abonnenten/Abo-Preis/Wochen/Broker aendern sich nahezu jedem
    # Scan — als Basis-Felder liessen sie JEDE existing KI-Analyse als
    # "veraltet" aus der Ansicht verschwinden (restore_current_reports),
    # obwohl sich an Risiko/Ertrag nichts geaendert hat. Sie bleiben im
    # LLM-Payload (_kandidat_json), nur nicht in der Berichts-Identitaet.
    facts = {k: v for k, v in facts.items() if k in _BASIS_FAKTEN_FELDER}
    forensics = json.loads(_forensik_json(result))
    forensics["martingale_evidenz"] = result.martingale_evidenz or []
    content = {
        "format": 1, "version": result.forensik_version,
        "implementation_version": FORENSICS_VERSION,
        "forensics_complete": result.forensik_vorhanden,
        "csv_sha256": csv_hash, "facts": facts, "forensics": forensics,
        "exclusion": next((entry for entry in config.load_known_signals().get("ausgeschlossen", [])
                           if entry["id"] == result.id), None),
        "criteria": {key: settings.get(key, config.DEFAULT_SETTINGS[key])
                     for key in ("schranke_eq_dd_pct", "min_ertrag_pct_monat")},
    }

    def canonical(value):
        if isinstance(value, dict):
            return {key: canonical(item) for key, item in value.items()}
        if isinstance(value, list):
            return [canonical(item) for item in value]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value) if value else 0.0  # SQLite REAL vs. parsed integer
        return value

    encoded = json.dumps(canonical(content), sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _kennezeichne_virtuelle_kapitalbasis(result: ScanResult) -> None:
    """Hinweis "Kapitalbasis virtuell" ans Urteil haengen — idempotent.

    Grundlage ist die von der FORENSIK tatsaechlich verwendete Quelle
    (kapitalbasis_verwendet_quelle), nie die Lauf-Absicht: Eine echte
    CSV-Einzahlung schlaegt die virtuelle Annahme. Wird zentral nach
    jedem ampel_for/refresh aufgerufen (auch llm_runner/run_portfolio
    bauen das Urteil neu — ohne diese Zentrierung wuerde der Hinweis
    vor dem Prompt verschwinden).
    """
    hinweis = "Kapitalbasis virtuell (Annahme der Datenquelle)"
    if (result.kapitalbasis_verwendet_quelle == KAPITALBASIS_QUELLE_VIRTUELL
            and result.forensik_vorhanden and not result.fehler
            and hinweis not in (result.urteil or "")):
        result.urteil = (result.urteil or "") + " · " + hinweis
    # B3 (Intensiv-Review): auch die implizite Basis ist eine Ableitung,
    # keine belegte Einzahlung — sie muss im Urteil sichtbar bleiben.
    hinweis_implizit = "Kapitalbasis implizit (Web-Balance − Trade-Netto)"
    if (result.kapitalbasis_verwendet_quelle == KAPITALBASIS_QUELLE_IMPLIZIT
            and result.forensik_vorhanden and not result.fehler
            and hinweis_implizit not in (result.urteil or "")):
        result.urteil = (result.urteil or "") + " · " + hinweis_implizit


def refresh_report_verdict(result: ScanResult, settings: dict) -> None:
    """Recompute settings-dependent flags before using a current report or prompt."""
    if (result.dd_equity_pct is not None or result.trading_dd_pct is not None
            or result.dd_balance_pct is not None):
        limit = float(settings.get("schranke_eq_dd_pct", 30.0))
        # Konservativ: vom Plattform-Drawdown der HOECHSTE By-Equity-/
        # By-Balance-Wert (Gold Spike: By Equity 3,8 % vs. By Balance 8,11 %).
        # Rekonstruierter Equity-DD (aus Kursen, floating inklusive) geht bei
        # verlässlicher Abdeckung als viertes Maximum ein — Risiko vor Ertrag.
        # Die Monitor-Zweitmessung als fünftes (B1, Intensiv-Review
        # 29./30.09.2026): identische Definition zur Scan-Zeit-Berechnung
        # in scoring.evaluate, sonst würde die Neu-Berechnung (DB-Load,
        # Anzeige) die Schranke schwächer sehen als der Scan.
        result.schranke_verletzt = scoring.dd_maximum(  # F-12: eine Definition
            result.dd_equity_pct, result.trading_dd_pct,
            result.dd_balance_pct, result.equity_dd_rekonstruiert_pct,
            result.monitor_trade_eq_dd_pct) > limit
    result.ampel, result.urteil = ampel_for(result, settings)
    # Kennzeichnung ueberlebt das Neubauen des Urteils (KI-Prompts, Portfolio,
    # DB-Neuladen rufen alle refresh_report_verdict).
    _kennezeichne_virtuelle_kapitalbasis(result)


def restore_current_reports(result: ScanResult, settings: dict) -> bool:
    """Load only analyses bound to the current evidence; retain history in SQLite."""
    if result.forensik_vorhanden and not result.fehler:
        refresh_report_verdict(result, settings)
    basis = report_basis_for(result, settings) if result.forensik_vorhanden and not result.fehler else None
    stale = False
    for kind in ("trade_analyse", "risiko_analyse", "gesamtbericht"):
        previous = db.get_latest_analysis(result.id, kind)
        current = db.get_latest_analysis(result.id, kind, basis=basis) if basis else None
        setattr(result, kind, current["text"] if current else "")
        setattr(result, f"{kind}_at", (current["created_at"] or "") if current else "")
        setattr(result, f"{kind}_model", (current["model"] if "model" in current else "") if current else "")
        stale = stale or bool(previous and current is None)
    # B10 (Lauf-Review 02.10.): Tiefenanalysen (manuell, Prompt 5) genauso an
    # die Datenbasis binden — 47 Bestandsfälle zeigten alte Texte neben neuer
    # Basis ohne Kennzeichnung; sie könnten ungeprüft in PDF-Anhänge laufen.
    # Ohne EVERY Forensik (Vorprüfung) gibt es keine vergleichbare Basis:
    # dann bleibt die letzte Tiefenanalyse sichtbar (Bestehendes Verhalten).
    tiefe_previous = db.get_latest_analysis(result.id, "tiefenanalyse")
    tiefe_current = (db.get_latest_analysis(result.id, "tiefenanalyse", basis=basis)
                     if basis else tiefe_previous)
    result.tiefenanalyse = tiefe_current["text"] if tiefe_current else ""
    result.tiefenanalyse_at = (tiefe_current["created_at"] or "") if tiefe_current else ""
    result.tiefenanalyse_model = ((tiefe_current.get("model") or "")
                                  if tiefe_current else "")
    tiefe_stale = bool(tiefe_previous and tiefe_current is None)
    result.kurzfassung = _extract_kurzfassung(result.gesamtbericht)
    result.berichte_basis = basis or ""
    if stale:
        result.bericht_hinweis = (
            "Vorhandene KI-Berichte sind veraltet oder keiner geprüften Datengrundlage zugeordnet. "
            "Sie bleiben im Archiv bzw. in der Datenbank-Historie erhalten; aktuelle Berichte neu erstellen.")
    elif tiefe_stale:
        result.bericht_hinweis = (
            "Die gespeicherte erweiterte KI-Analyse (Tiefenanalyse) stammt "
            "von einer ÄLTEREN Datenbasis — für PDF-Anhänge und Entscheidungen "
            "neu erstellen (die Historie bleibt erhalten).")
    else:
        result.bericht_hinweis = ""
    return bool(result.gesamtbericht)


def _incomplete_forensics_reason(exposure: dict) -> str:
    warnings = exposure.get("warnings") or []
    if warnings:
        return " ".join(warnings)
    # Fallback mit konkreten Flags statt Sammelphrase — die Engine schreibt
    # normalerweise eine Warnung; dieser Zweig deckt Alt-Befunde ab.
    flags = [name for name, key in (
        ("Kapitalhistorie unvollständig", "capital_history_complete"),
        ("Kontraktspec fehlt", "contract_complete"),
        ("USD-Umrechnung fehlt", "conversion_complete"),
        ("kein belastbarer Schockanteil", "temporal_risk_available"),
    ) if exposure.get(key) is False]
    return ("; ".join(flags) + " — Details im Exposure-Befund.") if flags \
        else "Kapitalhistorie oder Pflichtbefunde fehlen."


class ScanPipeline:
    def __init__(self, settings: dict | None = None, quelle: str = "full"):
        self.settings = {**config.load_settings(), **(settings or {})}
        # Laufart für die Ampel-Chronik ("full" | "gelbgruen") — nur Protokoll.
        self.quelle = quelle
        self.llm = llm_client.GlmClient(
            model_stufe1=self.settings.get("model_stufe1", config.MODEL_STUFE1),
            model_stufe2=self.settings.get("model_stufe2", config.MODEL_STUFE2),
            max_total_tokens=int(self.settings.get("llm_max_total_tokens", 200_000)),
            base_url=self.settings.get("glm_base_url") or None,
        )
        # Aufeinanderfolgende systemische MQL5-Fehler (Ban/Drossel/Login).
        self._mql5_hard_fails = 0
        # Kursdaten-Anbieter für die Equity-DD-Rekonstruktion (lazy, einmal
        # pro Pipeline-Instanz; Setting equity_rekonstruktion, Default an).
        self._kursanbieter = None
        self._kursversuch = False
        self.fail_fast_after = max(1, int(self.settings.get("mql5_fail_fast_after", 3)))

    def _register_mql5_outcome(self, *, ok: bool, exc: BaseException | None = None,
                               log: LogCb | None = None) -> None:
        """Zaehlt Hard-Failures; wirft Mql5HardStopError ab Schwellwert."""
        if ok:
            self._mql5_hard_fails = 0
            return
        if exc is None or not is_hard_mql5_failure(exc):
            return
        self._mql5_hard_fails += 1
        msg = (f"MQL5-Hard-Failure {self._mql5_hard_fails}/"
               f"{self.fail_fast_after}: {type(exc).__name__}: {exc}")
        if log:
            log(msg)
        if self._mql5_hard_fails >= self.fail_fast_after:
            raise Mql5HardStopError(
                f"Fail-Fast: {self._mql5_hard_fails} systemische MQL5-Fehler "
                f"in Folge — weitere Exporte gestoppt, um den Account zu schützen. "
                f"Letzter Fehler: {exc}") from exc

    # ------------------------------------------------------ Schritt 1 + 2
    def crawl(self, on_progress: ProgressCb, log: LogCb) -> list[dict]:
        """Signale holen — je `listen_modus` (doc/20 §6):

        mql5 (Default) : MQL5-Listen per Crawler (bisheriges Verhalten)
        quellen        : Kataloge der Datenquellen-REST (kein MQL5-Kontakt)
        beides         : Vereinigung; bei Doppelung gewinnt MQL5-Direkt
        """
        modus = str(self.settings.get("listen_modus") or "mql5").strip().lower()
        if modus == "quellen":
            from . import ingest
            signals = ingest.kandidaten_aus_quellen(log)
            log(f"{len(signals)} Signale aus Datenquellen geladen (Modus quellen).")
            self._ergaenze_fix_ids(signals, log, session=None)
            return signals
        session = Mql5Session(self.settings)
        signals = crawler.crawl_lists(
            session, seiten_pro_liste=int(self.settings.get("listen_seiten", 2)),
            on_progress=on_progress)
        log(f"{len(signals)} Signale geladen (MT4+MT5, "
            f"{self.settings.get('listen_seiten', 2)} Seiten je Liste).")
        if modus == "beides":
            from . import ingest
            quellen_signale = ingest.kandidaten_aus_quellen(log)
            # F7 (Fremd-Review 01.10.): Plattform-Normalisierung — der
            # Crawler liefert 'MT5'/'MT4', der Quellen-Ingest 'mt5'/'mt4';
            # der exakte Vergleich nahm denselben MQL5-Spiegel-Eintrag
            # zweimal auf (Slots/KI doppelt verbraucht).
            gesehen = {(s.get("id"), str(s.get("platform") or "").lower())
                       for s in signals}
            neu = [s for s in quellen_signale
                   if (s.get("id"), str(s.get("platform") or "").lower())
                   not in gesehen]
            signals.extend(neu)
            log(f"Vereinigt: +{len(neu)} Signale nur aus Datenquellen "
                f"(MQL5-Direkt gewinnt bei Doppelung) — gesamt {len(signals)}.")
        self._ergaenze_fix_ids(signals, log, session=session)
        return signals

    def _ergaenze_fix_ids(self, signals: list[dict], log: LogCb,
                          session: Mql5Session | None = None) -> None:
        """Fix-IDs (immer scannen) fehlen in der geladenen Liste? Nachladen.

        Mit Session (Modus mql5/beides) wird die Detailseite des Signals
        abgerufen; ohne Session (Modus quellen) ist ein Einzelabruf nicht
        moeglich — der Fall wird protokolliert, der Lauf laeuft weiter.
        """
        fix = sorted(fix_signale.fix_ids(self.settings))
        if not fix:
            return
        vorhanden = {s.get("id") for s in signals}
        fehlend = [i for i in fix if i not in vorhanden]
        if not fehlend:
            log(f"Fix-IDs {fix}: alle bereits in der Liste enthalten.")
            return
        for sid in fehlend:
            if session is None:
                log(f"Fix-ID {sid}: im Katalog der Datenquellen nicht gefunden — "
                    "ohne MQL5-Session nicht einzeln ladbar, in diesem Lauf übergangen.")
                continue
            try:
                overview = crawler.fetch_signal_overview(session, sid)
            except Exception as exc:
                log(f"Fix-ID {sid}: Signalseite nicht ladbar "
                    f"({type(exc).__name__}: {exc}) — in diesem Lauf übergangen.")
                continue
            signals.append(overview)
            log(f"Fix-ID {sid}: nicht in den Top-Listen — einzeln von der "
                f"Signalseite geladen ({overview.get('name') or overview.get('url')}).")

    def build_candidates(self, signals: list[dict], log: LogCb,
                         begruendung: list[dict] | None = None) -> list[dict]:
        """Vorfilter + Kandidatenliste. Wenn `begruendung` (Liste) übergeben
        wird, erhält JEDES Eingangssignal einen Erklärungs-Datensatz
        (Nutzer-Wunsch 02.10.2026: Auswahl nachvollziehbar — warum drin,
        warum draußen)."""
        min_abo = int(self.settings.get("min_abonnenten", 0))
        min_wochen = float(self.settings.get("min_wochen", 26))
        fix = fix_signale.fix_ids(self.settings)
        candidates = []
        n_fix = 0

        def _eintrag(s: dict, status: str, grund: str) -> dict:
            return fix_signale.begruendungseintrag(s, status, grund)

        for s in signals:
            # Fix-IDs umgehen die Vorfilter (Nutzer-Wunsch: immer scannen) —
            # ein gepinntes Signal darf nicht an Wochen/Abonnenten scheitern.
            if s.get("id") in fix:
                candidates.append(s)
                n_fix += 1
                if begruendung is not None:
                    begruendung.append(_eintrag(
                        s, "FIX",
                        "📌 Fix-ID — immer im Scope, umgeht Vorfilter "
                        "und belegt keinen Quellen-Slot."))
                continue
            weeks = s.get("wochen")
            # B5/B6 (Intensiv-Review 29./30.09.2026): weeks=None heißt seit
            # der PelicanMonitor-Korrektur ehrlich „Handelshistorie unbekannt"
            # (früher fälschlich 0 = „jung"). Für einen Mindestalter-Filter
            # gilt Unbekannt als NICHT belegt — das Verhalten (Rauswurf)
            # bleibt wie bei weeks=0, nur die Datenlage lügt nicht mehr.
            if weeks is None or weeks < min_wochen:
                if begruendung is not None:
                    grund = ("✗ Alter unbekannt (weeks fehlt bei der Quelle) — "
                             "Mindestalter kann nicht belegt werden."
                             if weeks is None else
                             f"✗ Alter: {weeks:g} Wochen < Mindestalter "
                             f"{min_wochen:g} Wochen.")
                    begruendung.append(_eintrag(s, "DRAUSSEN", grund))
                continue
            if (s.get("abonnenten") or 0) < min_abo:
                if begruendung is not None:
                    begruendung.append(_eintrag(
                        s, "DRAUSSEN",
                        f"✗ Abonnenten: {s.get('abonnenten') or 0} < "
                        f"Mindestabo {min_abo}."))
                continue
            candidates.append(s)
            if begruendung is not None:
                begruendung.append(_eintrag(
                    s, "KANDIDAT",
                    f"✓ Vorfilter bestanden ({weeks:g} Wochen, "
                    f"{s.get('abonnenten') or 0} Abonnenten) — über die "
                    "Auswahl (Slots bzw. Teilscan-Scope) wird als Nächstes "
                    "entschieden."))
        log(f"Vorfilter (Wochen >= {min_wochen:g}, Abonnenten >= {min_abo}): "
            f"{len(signals)} -> {len(candidates)} Kandidaten"
            + (f" (davon {n_fix} Fix-ID(s) ohne Vorfilter)." if n_fix else "."))
        known = config.load_known_signals()
        excluded = {e["id"] for e in known.get("ausgeschlossen", [])}
        out_file = config.DATA_DIR / "candidates.json"
        out_file.write_text(json.dumps(candidates, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        log(f"Kandidatenliste gespeichert: {out_file} "
            f"({len(excluded)} Ausschluesse aus known_signals.json werden markiert).")
        return candidates

    # ------------------------------------------------------ Schritt 3
    def analyze_candidate(self, session: Mql5Session, cand: dict,
                          log: LogCb,
                          should_stop: Callable[[], bool] | None = None) -> ScanResult:
        """Einzelprüfung einmal wiederholen; Hard-Stop-Ausnahmen durchreichen."""
        result = self._analyze_candidate_once(session, cand, log)
        if not result.fehler:
            return result
        log(f"Signal {result.id}: Prüfung fehlgeschlagen — einmalige Wiederholung "
            "in 5 Sekunden (Versuch 2/2).")
        for _ in range(10):
            if should_stop and should_stop():
                log(f"Signal {result.id}: Wiederholung wegen Stop-Anforderung ausgelassen.")
                return result
            time.sleep(0.5)
        if should_stop and should_stop():
            log(f"Signal {result.id}: Wiederholung wegen Stop-Anforderung ausgelassen.")
            return result
        persisted_before_retry = result.persisted_this_run
        try:
            result = self._analyze_candidate_once(session, cand, log)
        except Mql5HardStopError as exc:
            if exc.result is not None:
                exc.result.persisted_this_run |= persisted_before_retry
            raise
        result.persisted_this_run |= persisted_before_retry
        log(f"Signal {result.id}: " + (
            "Auch Versuch 2/2 fehlgeschlagen; keine weitere Wiederholung."
            if result.fehler else "Wiederholung erfolgreich."))
        return result

    def _analyze_candidate_once(self, session: Mql5Session, cand: dict,
                          log: LogCb) -> ScanResult:
        stats: dict = {}  # bleibt leer, wenn die Kennzahlen-Seite fehlschlaegt
        # Kapitalbasis-Entscheidung dieses Laufs (Audit/Uurteil-Kennzeichnung);
        # im try wird sie ggf. auf die virtuelle Annahme umgestellt.
        kapitalbasis_quelle = "signalseite_initial_deposit"
        res = ScanResult(id=cand["id"], name=cand.get("name") or str(cand["id"]),
                         platform=cand.get("platform") or "", url=cand.get("url", ""),
                         autor=cand.get("autor") or "",
                         abonnenten=cand.get("abonnenten"),
                         abo_preis_usd=cand.get("abo_preis_usd"),
                         wochen=cand.get("wochen"), growth_pct=cand.get("growth_pct"),
                         quelle=str(cand.get("quelle_kuerzel") or ""))
        try:
            quelle_row = None
            quelle_version = None
            if cand.get("quelle_kuerzel"):
                from . import ingest
                quelle_row = db.get_quelle(int(cand["quelle_id"]))
                if quelle_row is None or not quelle_row["aktiv"]:
                    raise RuntimeError(f"Datenquelle „{cand['quelle_kuerzel']}“ "
                                       "existiert nicht mehr oder ist inaktiv.")
                quelle_version = str(cand.get("quelle_version") or "mql5")
                log(f"Kennzahlen aus Datenquelle {quelle_row['kuerzel']} "
                    f"({quelle_version}) …")
                stats = ingest.metrics_zu_stats(
                    ingest.hole_metrics(quelle_row, res.id, quelle_version))
            else:
                log("Kennzahlen-Seite laden (mql5) …")
                stats = signal_stats.fetch_signal_stats(session, res.id)
            res.dd_equity_pct = stats.get("dd_equity_pct")
            res.dd_balance_pct = stats.get("dd_balance_pct")
            res.ertrag_monat_pct = stats.get("monthly_growth_pct")
            res.pf = stats.get("profit_factor")
            # Monitor-Nachmessung (nur Datenquellen-Signale; None sonst)
            res.monitor_trade_eq_dd_pct = stats.get("monitor_trade_eq_dd_pct")
            if res.wochen is None:
                res.wochen = stats.get("weeks")
            res.broker_server = stats.get("broker_server")
            # Webseiten-Kapitalbasis (kann negativ sein — eigene rote Regel).
            # Quellen-Signale: erst mit Downloader-Lieferung von InitialDeposit
            # (doc/20 §4) — bis dahin ehrlich None.
            res.kapitalbasis_usd = stats.get("initial_deposit_usd")
            log(f"✓ Kennzahlen: EQ-DD {res.dd_equity_pct} % · PF {res.pf} · "
                f"Ertrag {res.ertrag_monat_pct} %/Monat")

            # Eine öffentliche Kennzahlen-Seite belegt keinen funktionierenden
            # authentifizierten Export. Dessen Fehlerkette hier nicht zurücksetzen.

            log("Trade-Export laden (CSV) …")
            report = None
            try:
                try:
                    if quelle_row is not None:
                        from . import ingest
                        # Rueckgabe ist (pfad, geaendert) — Cache-Meldung
                        # entsprechend drehen (Fremd-Review 01.10.: Log
                        # vertauschte Cache/neu geladen).
                        path, geaendert = ingest.hole_trades(
                            quelle_row, res.id, quelle_version)
                        from_cache = not geaendert
                    else:
                        path, from_cache = exporter.export_positions(
                            session, res.id,
                            extra_pause_s=float(self.settings.get(
                                "rate_pause_zwischen_signalen_s", 5.0)),
                            platform=res.platform or cand.get("platform"))
                except (Mql5HardStopError, Mql5CredentialsMissingError):
                    raise
                except downloader_client.DownloaderError:
                    raise  # Quellen-Fehler haben keinen Browser-Fallback
                except (RuntimeError, requests.HTTPError):
                    # MQL5 drosselt / falscher Export-Pfad — Chrome-Fallback
                    # (History-Link auf der Signal-Seite, MT4+MT5).
                    log("Direkter Abruf fehlgeschlagen — Download über Chrome "
                        "(MqlDownloader-Muster) …")
                    from .mql5.browser_session import export_positions_via_browser
                    path = export_positions_via_browser(res.id, log=log)
                    from_cache = False
                res.trades_path = path
                with open(path, encoding="utf-8") as fh:
                    n_lines = sum(1 for _ in fh)
                log(f"✓ Trade-Export: {n_lines} Zeilen "
                    f"({'Cache' if from_cache else 'neu geladen'})")
                log("Forensik-Batterie (4 Tests) läuft …")
                # EZB-Kurse vorwaermen (Download beim ersten Bedarf) und den
                # Stand ins Protokoll nehmen — FX-Kreuze brauchen sie zur
                # USD-Umrechnung; offline bleibt die Umrechnung ehrlich gesperrt.
                ezb = fx_rates.status()
                log("EZB-Referenzkurse: " + (
                    f"geladen bis {ezb.get('letzte_kursdatum')}" if ezb.get("geladen")
                    else "nicht verfuegbar (offline?) — FX-Kreuze bleiben ohne USD-Schock"))
                # Broker mitgeben: cross_broker=false-Kontraktspecs (z. B. Oel)
                # gelten nur fuer den gelisteten Broker des Signals.
                # Kapitalbasis: 1) Signalseite "Initial Deposit" (belegt,
                # Cent-Abgleich), 2) implizite Basis Web-Balance − Σ Trade-
                # Netto (B3, Intensiv-Review), 3) virtuelle Annahme aus dem
                # Quellen-Monitor ("InitialDepositVirtual") — greift nur, wenn
                # der Export keine Einzahlung vor dem ersten Trade enthaelt
                # (Quellen-CSVs haben keine Kontobewegungszeilen).
                kapitalbasis = stats.get("initial_deposit_usd")
                kapitalbasis_quelle = "signalseite_initial_deposit"
                if kapitalbasis is None:
                    implizit = _implizite_kapitalbasis(
                        stats.get("balance_usd"), path, log,
                        plattform_positions=stats.get("trades"))
                    if implizit is not None:
                        kapitalbasis = implizit
                        kapitalbasis_quelle = KAPITALBASIS_QUELLE_IMPLIZIT
                if kapitalbasis is None:
                    virtuell = _virtuelle_kapitalbasis(stats.get("kapitalbasis_virtual_usd"), log)
                    if virtuell is not None:
                        kapitalbasis = virtuell
                        kapitalbasis_quelle = KAPITALBASIS_QUELLE_VIRTUELL
                if res.monitor_trade_eq_dd_pct is not None:
                    # Review 04.10. (Paket D): TradeEqDrawdownPct ist eine
                    # Closing-Kurve (plus höchstens HEUTIGEM Floating-Endpunkt),
                    # keine historisch floating-inklusive Equity-Messung. Die
                    # Kursdaten-Rekonstruktion läuft deshalb auch bei Quellen-
                    # Signalen — sie ist der EINZIGE valide RetDD-Nenner; der
                    # Monitor-Wert bleibt zusätzlicher Kanal der harten Schranke.
                    log(f"Datenquellen-Monitor liefert Trade-EQ-DD "
                        f"{res.monitor_trade_eq_dd_pct} % (Closing-Kurve — "
                        "nur Schranken-Kanal, kein RetDD-Nenner); "
                        "Kurs-Rekonstruktion läuft zusätzlich.")
                    kursanbieter = self._kursanbieter_fuer(log)
                else:
                    kursanbieter = self._kursanbieter_fuer(log)
                # Beweiswert für doppelte Lieferungen: Signalseiten-Angabe
                # "Trades:" (MQL5-Direkt). Quellen-metrics liefern keine
                # Positionszahl → dort gilt der Beweis als nicht erbracht
                # und identische Zeilen bleiben erhalten (nur Zähler).
                res.plattform_trades = stats.get("trades")
                report = analyze_export(
                    path, broker=res.broker_server,
                    kapitalbasis_usd=kapitalbasis,
                    kapitalbasis_quelle=kapitalbasis_quelle,
                    kursanbieter=kursanbieter,
                    plattform_positions=res.plattform_trades)
            except Mql5CredentialsMissingError:
                log("Trade-Export übersprungen (kein MQL5-Login) — "
                    "Vorprüfung ohne Forensik. Login im Admin-Bereich ergänzen.")
            if report is not None:
                st, fx = report["stats"], report["forensics"]
                if not st.get("trades"):
                    raise ValueError("Forensik unvollständig: keine abgeschlossenen Trades im Export.")
                # Deckung auf den Cent (AGENTS.md): Wurde die Kapitalbasis von
                # der Signalseite injiziert, muss der rekonstruierte Endkon-
                # tostand die Webseiten-Balance erklaeren. Bei CSV-Einzahlungen
                # entfaellt der Check (aelterer Cache-Export darf real abwei-
                # chen, ohne die Bewertung umzuwerfen).
                ok, meldung = _kapitalbasis_abgleich(fx["drawdown"], stats)
                if not ok:
                    raise ValueError(meldung)
                res.forensik_vorhanden = True
                res.symbole = ", ".join(sorted(st.get("symbols", {})))
                # Tatsaechlich verwendete Kapitalbasis laut Engine-Befund: Eine
                # echte CSV-Einzahlung schlaegt jede Injektion — nur diese Quelle
                # darf die "virtuell"-Kennzeichnung steuern (Live-Urteil, DB,
                # Prompt-JSON; siehe _kennezeichne_virtuelle_kapitalbasis).
                res.kapitalbasis_verwendet_usd = fx["drawdown"].get("startkapital")
                res.kapitalbasis_verwendet_quelle = fx["drawdown"].get("startkapital_quelle") or ""
                td = fx["drawdown"]["trading_dd"]
                # Risiko-/Ampel-% = max. relativer DD; USD-Anker bleibt dd_usd.
                res.trading_dd_pct = td.get("dd_pct_max_rel", td.get("dd_pct"))
                res.trading_dd_usd = td["dd_usd"]
                res.winrate_pct = st.get("winrate_pct")
                res.max_verlustserie = st.get("max_consecutive_losses")
                res.verlustserie_usd = st.get("max_consecutive_losses_sum")
                expo = fx["exposure"]
                res.peak_positionen = expo.get("peak_open_positions")
                res.peak_netto_lots = expo.get("peak_net_lots")
                res.shock_usd = expo.get("shock_usd")
                res.shock_pct_max = expo.get("shock_pct_max")
                res.shock_pct_peak_time = expo.get("shock_pct_peak_time")
                res.shock_pct_peak_account = expo.get("shock_pct_peak_account")
                res.shock_pct_peak_usd = expo.get("shock_pct_peak_usd")
                reko = fx.get("equity_rekonstruktion") or {}
                res.equity_rekon_status = reko.get("status") or ""
                res.equity_rekon_grund = _equity_rekon_grund(reko)
                res.equity_rekon_abdeckung_pct = reko.get("abdeckung_pct")
                res.equity_rekon_methodik = reko.get("methodik") or ""
                res.equity_rekon_zeitbasis = reko.get("zeitbasis") or {}
                res.equity_rekon_ohne_kurse = reko.get("symbole_ohne_kurse") or []
                res.equity_rekon_ohne_kontrakt = reko.get("symbole_ohne_kontrakt") or []
                res.equity_rekon_gmt_h = reko.get("gmt_offset_h")
                res.identische_tradezeilen = st.get("identische_tradezeilen", 0)
                res.duplikate_entfernt = st.get("duplikate_entfernt", 0)
                if st.get("duplikate_entfernt"):
                    # Beweisbasiertes Dedup (03.10.): Entfernt wurde nur, weil
                    # die Plattform-Anzahl die Doppellieferung belegt.
                    log(f"✓ {st['duplikate_entfernt']} exakte Duplikat-Zeilen "
                        "aus der Lieferung entfernt — Plattform-Anzahl "
                        f"({res.plattform_trades:g} Trades) belegt die "
                        "Doppellieferung.")
                elif res.identische_tradezeilen:
                    log(f"Trade-Daten: {res.identische_tradezeilen} identische Zeilen erhalten "
                        "(keine Ticket-ID; können verschiedene echte Positionen sein).")
                if reko.get("status") == "ok" and reko.get("verlaesslich"):
                    res.equity_dd_rekonstruiert_pct = reko.get(
                        "equity_dd_pct_raw", reko.get("equity_dd_pct"))
                    res.equity_dd_rekonstruiert_usd = reko.get("equity_dd_usd")
                    log(f"✓ Equity-Rekonstruktion: Reko-EQ-DD {res.equity_dd_rekonstruiert_pct} % "
                        f"({res.equity_rekon_gmt_text}, Abdeckung "
                        f"{reko.get('abdeckung_pct')} %, floating inklusive)")
                elif reko.get("status") == "skipped":
                    log(f"Equity-Rekonstruktion übersprungen: {reko.get('grund')}")
                elif reko:
                    log("Equity-Rekonstruktion nicht belastbar: "
                        + res.equity_rekon_grund)
                res.martingale_flag = fx["martingale"].get("flag")
                res.martingale_evidenz = fx["martingale"].get("evidence") or []
                stops = fx["stops"]
                res.stop_nachweis = _stop_evidence_text(stops)
                res.stop_evidence = stops.get("stop_evidence")
                res.stop_befund = stops
                log(f"✓ Forensik: Winrate {res.winrate_pct} % · Trading-DD "
                    f"{res.trading_dd_pct} % · Serie {res.max_verlustserie} · "
                    f"Peak {res.peak_positionen} Pos · Martingale "
                    f"{'JA' if res.martingale_flag else 'nein'} · Stop: "
                    f"{res.stop_nachweis[:40]}")

                log("Risiko-Score berechnen …")
                platform = {
                    "eq_dd_pct": res.dd_equity_pct or 0,
                    "bal_dd_pct": res.dd_balance_pct or 0,
                    "reko_eq_dd_pct": res.equity_dd_rekonstruiert_pct or 0,
                    # B1 (Intensiv-Review 29./30.09.2026): Die Monitor-
                    # Zweitmessung gehört in Schranke und Score-Dimension —
                    # vorher war sie nur KI-Deutungsauftrag und 🟢 bei 46 %
                    # bzw. 241 % Zweitmessung war möglich.
                    "monitor_trade_eq_dd_pct": res.monitor_trade_eq_dd_pct or 0,
                    "weeks": res.wochen,
                    "broker_risk": 5.0,      # Default offshore; Detailpruefung manuell
                    "transparency_risk": 5.0,
                }
                # B2 (Intensiv-Review): Ertrag/Monat auf der GLEICHEN Basis
                # wie DD und Schock (eigene Kurve), statt nur der Plattform-
                # Selbstauskunft mit fremder Kapitalbasis.
                dd_befund = fx["drawdown"]
                netto_gesamt = dd_befund.get("net_total")
                startkapital = dd_befund.get("startkapital")
                span_wochen = float(st.get("span_weeks") or 0)
                if (netto_gesamt is not None and startkapital
                        and startkapital > 0 and span_wochen > 0):
                    # Gleiche Monatsdefinition wie effizienz_kennzahlen
                    # (365,2425/12 statt gerundet 30,44 — Review 04.10. A3).
                    monate = span_wochen * 7.0 / portfolio_statistik.MONAT_TAGE
                    res.ertrag_monat_pct_forensik = round(
                        100.0 * float(netto_gesamt) / float(startkapital)
                        / monate, 2)
                # B24-Fix (Lauf-Review 02.10.): RetDD-Effizienz WIRKLICH
                # berechnen — Deklaration/Verbraucher existierten seit dem
                # 01.10., die Zuweisung nie (0/97 Signale hatten Werte).
                # RetDD bekommt ausschließlich den gemessenen Equity-DD.
                # Die konservative harte Schranke bleibt davon unabhängig.
                dd_max = res.max_drawdown_equity_pct
                eff = portfolio_statistik.effizienz_kennzahlen(
                    res.trades_path, startkapital, dd_max,
                    plattform_positions=res.plattform_trades)
                if eff:
                    res.effizienz_befund = eff
                    res.ertrag_monat_geom_pct = eff["ertrag_monat_geom_pct"]
                    res.cagr_jahr_pct = eff["cagr_jahr_pct"]
                    res.retdd_monat = eff["retdd_monat"]
                    res.retdd_jahr = eff["retdd_jahr"]
                ev = scoring.evaluate(
                    report, platform=platform,
                    schranke_eq_dd_pct=self.settings.get("schranke_eq_dd_pct", 30.0))
                res.score = ev["score"]
                res.schranke_verletzt = bool(ev["schranke_eq_dd_verletzt"])
                res.forensik_vorhanden = bool(ev["forensics_complete"])
                if not res.forensik_vorhanden:
                    raise ValueError(f"Forensik unvollständig: {_incomplete_forensics_reason(expo)}")
                res.forensik_version = FORENSICS_VERSION
                self._register_mql5_outcome(ok=True)
        except Exception as exc:  # Ein weicher Fehler soll den Lauf nicht abbrechen
            res.fehler = f"{type(exc).__name__}: {exc}"
            res.forensik_vorhanden = False
            log(f"  FEHLER bei {res.id}: {res.fehler}")
            log(traceback.format_exc(limit=3))
            if isinstance(exc, Mql5HardStopError):
                # Stop further network work immediately, but preserve the current
                # failed scan just like a stop raised by the failure counter.
                hard_stop = exc
            else:
                try:
                    self._register_mql5_outcome(ok=False, exc=exc, log=log)
                    hard_stop = None
                except Mql5HardStopError as stop:
                    hard_stop = stop
        else:
            hard_stop = None
        # Alles in die Datenbank (Nutzer-Prinzip: CSV + MQL5-Infos + Befunde)
        try:
            # A public drawdown breach already rules out a signal, even when
            # the authenticated export was skipped and no score was computed.
            refresh_report_verdict(res, self.settings)
            db.init_db()
            stats_payload = {
                "eq_dd_pct": res.dd_equity_pct,
                "bal_dd_pct": res.dd_balance_pct,
                "ertrag_monat_pct": res.ertrag_monat_pct,
                # B2 (Intensiv-Review): Ertrag auf der Forensik-Kapitalbasis —
                # dieselbe Basis wie DD/Schock (Persistenz + REST/Anzeige).
                "ertrag_monat_pct_forensik": res.ertrag_monat_pct_forensik,
                # B24-Fix (02.10.): RetDD-Effizienz persistieren — geometrischer
                # Monatsertrag, echter Calmar, RetDD je Monat/Jahr.
                "ertrag_monat_geom_pct": res.ertrag_monat_geom_pct,
                "cagr_jahr_pct": res.cagr_jahr_pct,
                "retdd_monat": res.retdd_monat,
                "retdd_jahr": res.retdd_jahr,
                "effizienz_befund": res.effizienz_befund,
                "pf": res.pf, "growth_pct": res.growth_pct,
                "broker_server": res.broker_server,
                # Expliziter Vollstaendigkeitsstatus (verhindert Gruen aus alter Forensik).
                "forensik_ok": bool(res.forensik_vorhanden),
                "forensik_version": res.forensik_version,
                # Webseiten-Kontobasis (Audit: woher die Kapitalbasis kommt)
                "initial_deposit_usd": stats.get("initial_deposit_usd"),
                "balance_usd": stats.get("balance_usd"),
                # Virtuelle Annahme aus dem Quellen-Monitor (Audit-Snapshot)
                "kapitalbasis_virtual_usd": stats.get("kapitalbasis_virtual_usd"),
                # Monitor-Nachmessung Trade-EQ-DD (Audit-Snapshot, KI-Kontext)
                "monitor_trade_eq_dd_pct": stats.get("monitor_trade_eq_dd_pct"),
            }
            if res.fehler and not res.forensik_vorhanden:
                stats_payload["last_fehler"] = res.fehler
            else:
                stats_payload["last_fehler"] = None
            if not res.forensik_vorhanden and not res.fehler:
                stats_payload["export_skipped"] = "no_credentials_or_no_export"
            ampel, grund = ampel_for(res, self.settings)
            res.ampel = ampel
            detail = (f" | Score {res.score}, Trading-DD (geschlossen) {res.trading_dd_pct} %, "
                      f"Serie {res.max_verlustserie}, Peak {res.peak_positionen} Pos"
                      if res.forensik_vorhanden and res.trading_dd_pct is not None else "")
            if res.equity_dd_rekonstruiert_pct is not None:
                detail += (f" · Max-DD aus Kursen {res.equity_dd_rekonstruiert_pct} % "
                           f"({res.equity_rekon_gmt_text})")
            res.urteil = grund + detail
            # Kennzeichnung aus der TATSÄCHLICH verwendeten Quelle (Engine-
            # Befund), nicht aus der Lauf-Absicht — echte CSV-Einzahlung
            # schlägt die virtuelle Annahme.
            _kennezeichne_virtuelle_kapitalbasis(res)
            forensik_payload = None
            # Auch unvollstaendige Laeufe speichern ihre Teilergebnisse
            # (vollstaendig=False): Winrate/DD/Martingale/Stop bleiben sichtbar
            # und laden nach App-Neustart aus der DB; bewerten darf sie nur
            # als Vorprüfung bzw. rote Flag — nie als Kandidat.
            if res.forensik_vorhanden or res.winrate_pct is not None:
                forensik_payload = {
                    "version": FORENSICS_VERSION,
                    "vollstaendig": bool(res.forensik_vorhanden),
                    "trading_dd": {"pct": res.trading_dd_pct, "usd": res.trading_dd_usd},
                    "winrate_pct": res.winrate_pct,
                    # B26 (02.10.): Bezugsgrößen für Winrate/DD — ohne n ist
                    # „95,5 % bei wie vielen Trades?“ nicht auflösbar.
                    "trades_anzahl": st.get("trades_anzahl"),
                    # Beweisbasiertes Dedup (03.10.): entfernte exakte Duplikat-
                    # Zeilen NUR mit Plattform-Beweis (Signalseiten-"Trades:"
                    # deckt sich erst ohne die Mehrfachzeilen; THG-Fall).
                    "duplikate_entfernt": st.get("duplikate_entfernt", 0),
                    "identische_tradezeilen": res.identische_tradezeilen,
                    # Plattform-Beweiswert für DB-Reload/Studie (None = kein
                    # Beweis verfügbar, z. B. Datenquellen ohne Positionszahl).
                    "plattform_trades": res.plattform_trades,
                    # B24-Fix (02.10.): RetDD-Effizienz — geometrischer Monats-
                    # ertrag, echter Calmar, RetDD je Monat/Jahr (produziert
                    # in analyze_candidate, hier persistiert für DB-Reload).
                    "ertrag_monat_geom_pct": res.ertrag_monat_geom_pct,
                    "cagr_jahr_pct": res.cagr_jahr_pct,
                    "retdd_monat": res.retdd_monat,
                    "retdd_jahr": res.retdd_jahr,
                    "effizienz_befund": res.effizienz_befund,
                    "max_verlustserie": res.max_verlustserie,
                    "verlustserie_usd": res.verlustserie_usd,
                    "peak_exposure": {"positionen": res.peak_positionen,
                                      "netto_lots": res.peak_netto_lots,
                                      "schock_usd": res.shock_usd,
                                      "shock_pct_max": res.shock_pct_max,
                                      "shock_pct_peak_time": res.shock_pct_peak_time,
                                      "shock_pct_peak_account": res.shock_pct_peak_account,
                                      "shock_pct_peak_usd": res.shock_pct_peak_usd},
                    "martingale_flag": res.martingale_flag,
                    "martingale_evidenz": res.martingale_evidenz,
                    "stop_nachweis": res.stop_nachweis,
                    "stop_evidence": res.stop_evidence,
                    "stop_befund": res.stop_befund,
                    "symbole": res.symbole,
                    # Kapitalbasis samt Herkunft (Audit-Snapshot)
                    "kapitalbasis": {
                        "usd": fx["drawdown"].get("startkapital"),
                        "quelle": fx["drawdown"].get("startkapital_quelle"),
                        "end_balance_real": fx["drawdown"].get("end_balance_real"),
                        "webseite_balance_usd": stats.get("balance_usd"),
                    },
                    # Equity-DD-Rekonstruktion aus Kursen (Audit-Snapshot)
                    "equity_rekonstruktion": fx.get("equity_rekonstruktion"),
                    "fx_kursquelle": expo.get("fx_conversion", {}).get("quelle"),
                    # Score nur bei vollstaendiger Forensik — Design-Regel:
                    # kein Score vor bestandener Batterie.
                    "score": res.score if res.forensik_vorhanden else None,
                    # Ampel-Matrix als Audit-Snapshot: je Testkriterium die
                    # Zellen-Ampel samt exakter Berechnung (Nachvollzieh-
                    # barkeit; Anzeige rechnet aus den Werten aktuell neu).
                    "kriterien_matrix": matrix_payload(res, self.settings),
                    "ampel": res.ampel}
            signal_payload = {
                "name": res.name, "platform": res.platform, "url": res.url,
                "autor": res.autor, "abo_preis": res.abo_preis_usd,
                "abonnenten": res.abonnenten, "wochen": res.wochen,
                "stats": stats_payload,
            }
            # B4 (Lauf-Review 02.10.): Die Quelle IMMER explizit übergeben —
            # vorher nur bei REST-Kandidaten, womit ein MQL5-Direkt-Lauf
            # unter einer bereits als Quellen-Signal dokumentierten ID den
            # Kollisionsschutz (R1/F3 in db.upsert_signal) umging und den
            # Inhalt still unter falschem Quellenlabel ersetzte.
            signal_payload["quelle"] = str(cand.get("quelle_kuerzel") or "mql5")
            saved_trades_path = db.store_scan_result(
                res.id, signal_payload,
                trades_path=res.trades_path, forensik=forensik_payload)
            res.persisted_this_run = True
            if saved_trades_path:
                res.trades_path = saved_trades_path
                res.trades_sha256 = db.file_sha256(saved_trades_path)
            # Farb-Chronik fortschreiben und Wechsel gegen den Vorgänger prüfen
            # (Nutzer-Anforderung: Farben immer aufzeichnen, Wechsel speziell
            # protokollieren). Fehlgeschlagene Läufe schreiben keinen Eintrag.
            if not res.fehler:
                try:
                    res.ampel_wechsel = ampel_verlauf.erfasse_bewertung(
                        res, self.settings, quelle=self.quelle)
                    if res.ampel_wechsel:
                        log("⚡ AMPEL-WECHSEL " + ampel_verlauf.wechsel_kurztext(res.ampel_wechsel))
                except Exception as exc:  # Chronik darf den Lauf nie brechen
                    log(f"  Ampel-Verlauf nicht aufgezeichnet: {type(exc).__name__}: {exc}")
        except Exception as exc:  # DB-Fehler darf den Lauf nicht abbrechen
            storage_error = f"Speichern fehlgeschlagen: {type(exc).__name__}: {exc}"
            res.fehler = f"{res.fehler} | {storage_error}" if res.fehler else storage_error
            log(f"  DB-Fehler bei {res.id}: {exc}")
            ampel, grund = ampel_for(res, self.settings)
            res.ampel = ampel
            detail = (f" | Score {res.score}, Trading-DD (geschlossen) {res.trading_dd_pct} %, "
                      f"Serie {res.max_verlustserie}, Peak {res.peak_positionen} Pos"
                      if res.forensik_vorhanden and res.trading_dd_pct is not None else "")
            res.urteil = grund + detail
            _kennezeichne_virtuelle_kapitalbasis(res)
        if hard_stop is not None:
            hard_stop.result = res
            raise hard_stop
        return res

    def _kursanbieter_fuer(self, log: LogCb):
        """KursDaten lazy je Pipeline (ein Terminal-Start pro Lauf).

        Ohne Terminal/ohne Freigabe: ein Versuch, danach still None —
        die Rekonstruktion entfällt für den Rest des Laufs (kein Malus).
        """
        if self._kursversuch:
            return self._kursanbieter
        self._kursversuch = True
        if not bool(self.settings.get("equity_rekonstruktion", True)):
            return None
        from . import kursdaten
        anbieter = kursdaten.KursDaten(self.settings)
        ok, grund = anbieter.starten()
        if ok:
            self._kursanbieter = anbieter
            log("Kursdaten: Terminal verbunden — Equity-DD-Rekonstruktion aktiv.")
        else:
            log(f"Kursdaten nicht verfügbar: {grund} — Equity-Rekonstruktion entfällt.")
            anbieter.beenden()
        return self._kursanbieter

    def kursdaten_beenden(self) -> None:
        """Terminal des Kursdaten-Anbieters sauber beenden (Lauf-Ende)."""
        if self._kursanbieter is not None:
            self._kursanbieter.beenden()
            self._kursanbieter = None

    # ------------------------------------------------------ Schritt 4
    def run_llm(self, results: list[ScanResult], log: LogCb,
                on_progress: ProgressCb | None = None,
                should_stop: Callable[[], bool] | None = None) -> dict:
        """Drei-Stufen-Auswertung (Nutzer-Prinzip):

        Prompt 1  Trade-Analyse   — Strategie ANHAND DER TRADES ermitteln
                                    (starkes Modell, glm-5.3)
        Prompt 2  Risiko-Analyse  — Risikoprofil aus Forensik-Kennzahlen (Flash)
        Prompt 3  Gesamtbericht   — wertet ALLE Teilergebnisse aus, ausfuehrlich
                                    (starkes Modell, glm-5.3)

        Prompt 1 und 2 laufen parallel; Prompt 3 erst danach.
        Jedes Teilergebnis landet in der Datenbank (Tabelle analyses).
        Fortschritt zählt ausschließlich fertig gespeicherte Prompts. Start-
        und Fehlermeldungen verändern den Zähler nicht. Der Rückgabewert trennt
        erfolgreiche, fehlgeschlagene und nicht ausgeführte Prompts.
        should_stop: kooperativer Stopp (Stop-Button) — wird zwischen Kandidaten
        und vor dem Gesamtbericht geprüft; laufende Modellaufrufe laufen zu Ende.
        """
        from .llm_runner import run_llm
        return run_llm(self, results, log, on_progress, should_stop)

    # ------------------------------------------------------ Schritt 5
    PORTFOLIO_ANALYSIS_ID = None  # Globaler Bericht ohne Fremdschlüssel auf ein Signal.

    def run_portfolio(self, results: list[ScanResult], log: LogCb,
                      on_progress: ProgressCb | None = None,
                      should_stop: Callable[[], bool] | None = None) -> dict:
        """Portfolio-Vorschlag ueber ALLE Ergebnisse (Station 5 der GUI).

        Das LLM sieht je Signal: Kennzahlen, Forensik, Assets, Kurzfassung
        und den vollstaendigen Gesamtbericht — und schlaegt eine
        diversifizierte Depot-Kombination vor (Risiko vor Ertrag). Der
        Bericht landet in der DB unter signal_id=NULL, kind='portfolio'.
        """
        total = 1
        # F-8 (Review 29.09.): Nur 🟢/🟡 in den Portfolio-Prompt — der Prompt
        # verbietet ⛔/🔴-Empfehlungen sowieso, aber sie wurden vorher mit
        # vollem Gesamtbericht BEZAHLT und sprengten bei ~30 Signalen das
        # Budget durch die Reservierung je Job.
        jobs = [r for r in results
                if r.source_kind == "live" and r.forensik_vorhanden
                and not r.fehler and r.ampel in ("🟢", "🟡")]
        if not self.llm.has_key:
            log("Portfolio übersprungen: kein GLM-Key gesetzt (Admin-Bereich).")
            if on_progress:
                on_progress(0, total, "Übersprungen: kein GLM-Key konfiguriert")
            return {"text": "", "reason": "Kein GLM-Key konfiguriert"}
        if not jobs:
            if on_progress:
                on_progress(0, total, "Übersprungen: keine geeigneten Forensik-Ergebnisse")
            return {"text": "", "reason": "Keine geeigneten Forensik-Ergebnisse"}
        kriterien = _kriterien_text(self.settings)
        eintraege = []
        for r in jobs:
            refresh_report_verdict(r, self.settings)
            if r.berichte_basis != report_basis_for(r, self.settings):
                restore_current_reports(r, self.settings)
            eintraege.append({
                "kandidat": json.loads(_kandidat_json(r)),
                "forensik": json.loads(_forensik_json(r)),
                "assets": r.symbole,
                "kurzfassung": r.kurzfassung,
                "gesamtbericht": r.gesamtbericht or "(nicht erstellt)",
            })
        # B20/B21 (Intensiv-Review-Nachtrag): Portfolio-Statistik als
        # Code-Befund — Verlustmonat-Cluster (gemeinsame Schocks),
        # Historie-Tiefe/gemeinsames Fenster und Instrument-Overlap.
        # Code rechnet, KI deutet (Design-Regel 1).
        pstat = portfolio_statistik.statistik(jobs)
        n_cluster = len(pstat["verlustmonate_cluster"])
        n_klumpen = len(pstat["instrument_overlap"])
        log(f"Portfolio-Statistik (Code-Befund): {n_cluster} Verlustmonat-"
            f"Cluster, {n_klumpen} Instrument-Klumpen, gemeinsames Fenster "
            f"{pstat['gemeinsames_fenster']['monate']} Monate.")
        prompt = prompt_fill.build_portfolio_prompt(
            json.dumps(eintraege, ensure_ascii=False), kriterien,
            statistik_json=json.dumps(pstat, ensure_ascii=False))
        model_strong = self.settings.get("model_stufe2", config.MODEL_STUFE2)
        log(f"→ Portfolio: {len(eintraege)} Signal-Berichte "
            f"({len(prompt):,} Zeichen) an {model_strong} …")
        if on_progress:
            on_progress(0, total,
                        f"Portfolio-Analyse über {len(eintraege)} Signale · "
                        "warte auf Modellantwort")
        if should_stop and should_stop():
            log("Stop angefordert — Portfolio-Analyse abgebrochen.")
            if on_progress:
                on_progress(0, total, "Abgebrochen: Stop-Anforderung")
            return {"text": "", "reason": "Abbruch per Stop-Button"}
        meta: dict = {}
        try:
            text = self.llm.chat(prompt, stufe=2, max_tokens=24576, meta_out=meta)
        except llm_client.LlmNoBalanceError as exc:
            log(f"Portfolio abgebrochen: {exc}")
            if on_progress:
                on_progress(0, total, f"Abgebrochen: {exc}")
            return {"text": "", "reason": str(exc)}
        except llm_client.LlmError as exc:
            log(f"  Portfolio-Fehler: {exc}")
            if on_progress:
                on_progress(0, total, f"Fehler: {exc}")
            return {"text": "", "reason": str(exc)}
        storage_error = ""
        try:
            db.store_analysis(self.PORTFOLIO_ANALYSIS_ID, "portfolio", model_strong,
                              meta.get("total_tokens", self.llm.usage.total_tokens) or 0,
                              text)
        except Exception as exc:  # DB-Fehler darf den Bericht nicht verlieren
            storage_error = f"Portfolio nicht in Datenbank gespeichert: {type(exc).__name__}: {exc}"
            log(f"  {storage_error}")
        log(f"  ✓ Portfolio-Vorschlag fertig: {meta.get('zeichen', '?')} Zeichen "
            f"in {meta.get('dauer_s', '?')}s — gesamt bisher: "
            f"{self.llm.usage.total_tokens:,} Tokens")
        if on_progress:
            on_progress(1, total, storage_error or "Portfolio-Vorschlag fertig")
        summary = {"text": text, "zeichen": meta.get("zeichen", len(text)),
                "tokens": meta.get("total_tokens", self.llm.usage.total_tokens) or 0,
                "model": model_strong,
                "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
                "reason": storage_error, "storage_error": storage_error}
        try:
            from .pdf_reports import materialize_portfolio_pdf
            # Anhang „Empfohlene Strategien im Detail" (Nutzer-Wunsch
            # 30.09.2026, erweitert 02.10. auf ALLE Berichte je Strategie):
            # Kennzahlen + Kurzfassung + Risiko-/Trade-Analyse +
            # Gesamtbericht (+ Tiefenanalyse) je empfohlener Strategie.
            materialize_portfolio_pdf(summary, ergebnisse=jobs)
        except Exception as exc:
            pdf_error = f"Portfolio-PDF nicht gespeichert: {type(exc).__name__}: {exc}"
            summary["storage_error"] = "; ".join(filter(None, (storage_error, pdf_error)))
            summary["reason"] = summary["storage_error"]
            log(f"  {pdf_error}")
        return summary

    # ------------------------------------------------------ Hilfen
    @staticmethod
    def analyze_local_files(files: list[str], settings: dict | None = None) -> list[ScanResult]:
        """Verifikations-/Demo-Modus: lokale CSVs (data/raw) durch die Engine."""
        settings = settings or {}
        results: list[ScanResult] = []
        known = config.load_known_signals()
        meta = {s["id"]: s for s in (known.get("empfehlung", []) + known.get("watchlist", []))}
        for path in files:
            try:
                report = analyze_export(path)
                if not report["stats"].get("trades"):
                    raise ValueError("Forensik unvollständig: keine abgeschlossenen Trades im Export.")
            except Exception as exc:
                r = ScanResult(id=0, source_kind="demo", name=path,
                               fehler=f"{type(exc).__name__}: {exc}")
                r.ampel, r.urteil = ampel_for(r, settings)
                results.append(r)
                continue
            st, fx = report["stats"], report["forensics"]
            sid = 0
            for sid_cand in (_extract_id(path),):
                if sid_cand and sid_cand in meta:
                    sid = sid_cand
            r = ScanResult(
                id=sid or (_extract_id(path) or 0),
                source_kind="demo",
                name=path.split("/")[-1].split("\\")[-1].replace("_", " "),
                platform="CSV",
                trades_path=path,
                wochen=st.get("span_weeks"),
                pf=st.get("profit_factor_csv"),
                forensik_vorhanden=True,
                trading_dd_pct=(fx["drawdown"]["trading_dd"].get("dd_pct_max_rel")
                                or fx["drawdown"]["trading_dd"]["dd_pct"]),
                trading_dd_usd=fx["drawdown"]["trading_dd"]["dd_usd"],
                winrate_pct=st.get("winrate_pct"),
                identische_tradezeilen=st.get("identische_tradezeilen", 0),
                max_verlustserie=st.get("max_consecutive_losses"),
                verlustserie_usd=st.get("max_consecutive_losses_sum"),
                peak_positionen=fx["exposure"].get("peak_open_positions"),
                peak_netto_lots=fx["exposure"].get("peak_net_lots"),
                shock_usd=fx["exposure"].get("shock_usd"),
                shock_pct_max=fx["exposure"].get("shock_pct_max"),
                shock_pct_peak_time=fx["exposure"].get("shock_pct_peak_time"),
                shock_pct_peak_account=fx["exposure"].get("shock_pct_peak_account"),
                shock_pct_peak_usd=fx["exposure"].get("shock_pct_peak_usd"),
                martingale_flag=fx["martingale"].get("flag"),
                martingale_evidenz=fx["martingale"].get("evidence") or [],
                symbole=", ".join(sorted(st.get("symbols", {}))),
            )
            stops = fx["stops"]
            r.stop_nachweis = _stop_evidence_text(stops)
            r.stop_evidence = stops.get("stop_evidence")
            r.stop_befund = stops
            r.kapitalbasis_verwendet_usd = fx["drawdown"].get("startkapital")
            r.kapitalbasis_verwendet_quelle = fx["drawdown"].get("startkapital_quelle") or ""
            eff = portfolio_statistik.effizienz_kennzahlen(
                path, r.kapitalbasis_verwendet_usd, r.max_drawdown_equity_pct,
                plattform_positions=st.get("trades"))
            if eff:
                r.ertrag_monat_geom_pct = eff["ertrag_monat_geom_pct"]
                r.cagr_jahr_pct = eff["cagr_jahr_pct"]
                r.effizienz_befund = eff
            ev = scoring.evaluate(
                report, schranke_eq_dd_pct=settings.get("schranke_eq_dd_pct", 30.0))
            r.score = ev["score"]
            r.schranke_verletzt = ev["schranke_eq_dd_verletzt"]
            r.forensik_vorhanden = bool(ev["forensics_complete"])
            r.forensik_version = FORENSICS_VERSION if r.forensik_vorhanden else None
            if not r.forensik_vorhanden:
                r.fehler = f"Forensik unvollständig: {_incomplete_forensics_reason(fx['exposure'])}"
            if sid in meta:
                r.name = meta[sid].get("name", r.name)
                # Demo/Verifikation: kuratierte Referenzscores aus known_signals
                # ueberschreiben den Engine-Ist-Score (Kalibrierungsanker, nicht Live).
                curated = meta[sid].get("score")
                if curated is not None:
                    r.score = curated
                    r.urteil = ""  # ampel_for setzt neu; Kennzeichnung unten
                r.abo_preis_usd = meta[sid].get("abo_preis_usd")
                r.ertrag_monat_pct = meta[sid].get("monat_pct")
            r.ampel, grund = ampel_for(r, settings)
            if sid in meta and meta[sid].get("score") is not None:
                grund = f"{grund} | Score kuratiert ({r.score}, Engine {ev['score']})"
            r.urteil = grund + (f" | Trading-DD {r.trading_dd_pct} %"
                                if r.trading_dd_pct is not None else "")
            # Demo bleibt im Arbeitsspeicher bzw. separat im Laufarchiv.
            # Keine Live-Daten oder alten KI-Texte über dieselbe Signal-ID mischen.
            results.append(r)
        return results

    @staticmethod
    def save_run(results: list[ScanResult], logs: dict[str, list[str]],
                 portfolio: dict | None = None) -> str:
        from .pdf_reports import materialize_portfolio_pdf, materialize_result_pdfs
        portfolio = dict(portfolio) if portfolio is not None else None
        for result in results:
            try:
                materialize_result_pdfs(result)
                result.pdf_fehler = ""
            except Exception as exc:
                result.pdf_fehler = (
                    f"PDF-Speicherung fehlgeschlagen: {type(exc).__name__}: {exc}")
                logs.setdefault("pdf", []).append(
                    f"Signal #{result.id}: {result.pdf_fehler}")
        if portfolio and portfolio.get("text"):
            try:
                # Anhang je empfohlener Strategie (Nutzer-Wunsch 30.09.,
                # erweitert 02.10. auf ALLE Berichte je Strategie):
                # 🟢-Ergebnisse dieses Laufs liefern die Detail-Berichte —
                # auch ohne Gesamtbericht (der Anhang nennt Fehlendes ehrlich).
                materialize_portfolio_pdf(portfolio, ergebnisse=[
                    r for r in results
                    if getattr(r, "ampel", "") == "🟢"])
            except Exception as exc:
                error = f"Portfolio-PDF nicht gespeichert: {type(exc).__name__}: {exc}"
                portfolio["storage_error"] = "; ".join(
                    filter(None, (portfolio.get("storage_error"), error)))
                logs.setdefault("pdf", []).append(error)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f") + "_" + uuid4().hex[:8]
        run_dir = config.RUNS_DIR / stamp
        run_dir.mkdir(parents=True, exist_ok=False)
        payload = {
            "zeitstempel": stamp,
            "ergebnisse": [vars(r) for r in results],
            "logs": logs,
            "portfolio": portfolio,
        }
        out = run_dir / "results.json"
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        # Archivleser sehen erst eine vollständige Datei, auch bei laufender UI.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=run_dir,
                                             suffix=".tmp", delete=False) as fh:
                temporary = fh.name
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(temporary, out)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
        return str(out)


def _extract_id(path: str) -> int | None:
    import re
    m = re.search(r"(\d{6,7})", path)
    return int(m.group(1)) if m else None


def _extract_kurzfassung(bericht: str) -> str:
    """Zieht die Kurzzeile aus dem Gesamtbericht (fuer die Tabellenspalte)."""
    import re
    m = re.search(r"Kurzfassung\s*[:：]\s*(.+)", bericht)
    if m:
        return m.group(1).strip().strip("*").strip()
    return bericht.strip().splitlines()[0][:160] if bericht.strip() else ""
