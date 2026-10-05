# -*- coding: utf-8 -*-
"""Unabhängige Signal-Statistik für die Übersicht „Alle Signale“ (Nutzer-Wunsch 05.10.2026).

Reine Code-Vorstufe VOR dem KI-Workflow: alles wird aus dem gecachten
Trade-Export gerechnet — Monatsrenditen, geometrischer Ertrag, Profitfaktor,
Winrate, Trading-DD (geschlossene Trades) und Martingale-Schnellflag.

Bewusst NICHT hier: Ampel, Score und Urteil (bleiben bei der Engine bzw.
dem Workflow) und der „Max-Drawdown“ (floating-inklusive, aus Kursen —
bleibt exklusiv bei der Equity-Studie). Der Drawdown dieser Vorstufe heißt
„Trading-DD“: Kurve aus GESCHLOSSENEN Trades, offenes Floating fehlt
(Benennungsregel 03.10.2026). Das Verhältnis Ertrag/Trading-DD ist eine
gekennzeichnete VORBWERTUNG, kein RetDD (dessen Nenner darf nur die
floating-inklusive Kursmessung sein).

Kapitalbasis-Kaskade identisch zur Pipeline (analyze_candidate): Signalseite
„Initial Deposit“ → implizite Basis (Web-Balance − Σ Trade-Netto, B3) →
virtuelle Annahme aus dem Quellen-Monitor. CSV-Einzahlungen im Export
schlagen jede Injektion — die FINALE Basis legt drawdown.run fest.
"""
from __future__ import annotations

import math
from pathlib import Path

from . import stats as stats_mod
from .forensics import drawdown, martingale
from .parser import load_export
from .pipeline import (
    KAPITALBASIS_QUELLE_IMPLIZIT,
    KAPITALBASIS_QUELLE_VIRTUELL,
    _implizite_kapitalbasis,
    _virtuelle_kapitalbasis,
)
from .portfolio_statistik import _monatsserie, effizienz_kennzahlen


def kapitalbasis_kaskade(trades_pfad: str, stats: dict,
                         plattform_positions: float | None = None
                         ) -> tuple[float | None, str]:
    """Externe Kapitalbasis-Kandidatin wie im Scan — OHNE CSV-Entscheidung.

    Reihenfolge exakt wie pipeline.analyze_candidate: Signalseite
    „Initial Deposit“, dann implizite Basis (Web-Balance − Σ Trade-Netto),
    dann virtuelle Annahme. Rückgabe (basis, quelle); basis kann None
    sein. Ob am Ende CSV-Einzahlungen gewinnen, entscheidet drawdown.run.
    """
    basis = stats.get("initial_deposit_usd")
    quelle = "signalseite_initial_deposit"
    if basis is None:
        implizit = _implizite_kapitalbasis(
            stats.get("balance_usd"), trades_pfad,
            plattform_positions=plattform_positions)
        if implizit is not None:
            return implizit, KAPITALBASIS_QUELLE_IMPLIZIT
    if basis is None:
        virtuell = _virtuelle_kapitalbasis(stats.get("kapitalbasis_virtual_usd"))
        if virtuell is not None:
            return virtuell, KAPITALBASIS_QUELLE_VIRTUELL
    return basis, quelle


def _monats_usd(parsed) -> dict[str, float]:
    """Netto je Kalendermonat (Close-Zeit) — Rohbasis der Balkengrafik."""
    monate: dict[str, float] = {}
    for trade in parsed.trades:
        schluessel = trade.close_time.strftime("%Y-%m")
        monate[schluessel] = monate.get(schluessel, 0.0) + trade.net
    return monate


def _kurve(parsed, startkapital: float) -> list[list]:
    """Virtuelle Trading-Kurve [(ISO-Zeit, Stand USD)] nach Close-Zeit."""
    stand = float(startkapital)
    kurve: list[list] = []
    for trade in sorted(parsed.trades, key=lambda t: t.close_time):
        stand += trade.net
        kurve.append([trade.close_time.isoformat(sep=" "), round(stand, 2)])
    return kurve


def berechne(trades_pfad: str | None, stats: dict | None) -> dict | None:
    """Alle Vorstufen-Kennzahlen eines Signals aus dem Trade-Cache.

    Rückgabe dict (nie None bei lesbarer Datei — Fehler stehen im Feld
    „fehler“); None nur, wenn kein Pfad/keine Datei vorliegt. Alle Werte
    ungerundet außer dort, wo die wiederverwendeten Funktionen runden.
    """
    stats = stats or {}
    if not trades_pfad or not Path(trades_pfad).exists():
        return None
    plattform_positions = stats.get("trades")
    try:
        parsed = load_export(trades_pfad, plattform_positions=plattform_positions)
    except Exception as exc:  # Vorstufe darf nie brechen — Fehler benennen
        return {"fehler": f"Trade-Datei nicht lesbar ({type(exc).__name__}: {exc})",
                "trades": 0, "kapitalbasis_ok": False}
    if not parsed.trades:
        return {"fehler": "keine Trades im Export", "trades": 0,
                "kapitalbasis_ok": False}

    basis, basis_quelle = kapitalbasis_kaskade(
        trades_pfad, stats, plattform_positions=plattform_positions)
    dd = drawdown.run(parsed, kapitalbasis_usd=basis,
                      kapitalbasis_quelle=basis_quelle or None)
    startkapital = dd.get("startkapital")
    basis_ok = (isinstance(startkapital, (int, float))
                and math.isfinite(startkapital) and startkapital > 0)
    trading_dd = dd.get("trading_dd") or {}

    grund = stats_mod.compute(parsed)
    netto = math.fsum(t.net for t in parsed.trades)
    eff = None
    monate_pct: dict[str, float] = {}
    kurve: list[list] = []
    if basis_ok:
        # Kanonische Ertragsrechnung (derselbe Produzent wie RetDD im Scan);
        # dd_max hier absichtlich Trading-DD → retdd_monat wird als
        # VORBWERTUNG „ertrag_je_close_dd“ durchgereicht, nicht als RetDD.
        eff = effizienz_kennzahlen(
            trades_pfad, float(startkapital),
            dd_max_pct=trading_dd.get("dd_pct_max_rel"),
            plattform_positions=plattform_positions)
        monate_pct = _monatsserie(parsed, float(startkapital))
        kurve = _kurve(parsed, float(startkapital))

    marti = martingale.run(parsed)
    return {
        "fehler": None,
        "trades": grund.get("trades", 0),
        "duplikate_entfernt": grund.get("duplikate_entfernt", 0),
        "identische_tradezeilen": grund.get("identische_tradezeilen", 0),
        "kapitalbasis_ok": basis_ok,
        "kapitalbasis_usd": float(startkapital) if basis_ok else None,
        "kapitalbasis_quelle": dd.get("startkapital_quelle") or basis_quelle or "",
        "netto_gesamt_usd": netto,
        "endstand_virtuell_usd": float(startkapital) + netto if basis_ok else None,
        "ertrag_monat_geom_pct": (eff or {}).get("ertrag_monat_geom_pct"),
        "cagr_jahr_pct": (eff or {}).get("cagr_jahr_pct"),
        "dauer_monate": (eff or {}).get("dauer_monate"),
        "kalender_monate": (eff or {}).get("kalender_monate"),
        "zeit_von": (eff or {}).get("zeit_von"),
        "zeit_bis": (eff or {}).get("zeit_bis"),
        "kapitalfluesse_nach_start": (eff or {}).get("kapitalfluesse_nach_start"),
        "ertrag_je_close_dd": (eff or {}).get("retdd_monat"),
        "monate_pct": monate_pct,
        "monate_usd": _monats_usd(parsed),
        "kurve": kurve,
        "profit_faktor": grund.get("profit_factor_csv"),
        "winrate_pct": grund.get("winrate_pct"),
        "wins": grund.get("wins"),
        "losses": grund.get("losses"),
        "avg_win_usd": grund.get("avg_win"),
        "avg_loss_usd": grund.get("avg_loss"),
        "best_trade_usd": grund.get("best_trade"),
        "worst_trade_usd": grund.get("worst_trade"),
        "median_holding_h": grund.get("median_holding_hours"),
        "symbole": grund.get("symbols") or {},
        "per_symbol": grund.get("per_symbol") or {},
        "trading_dd_pct": trading_dd.get("dd_pct_max_rel"),
        "trading_dd_usd": trading_dd.get("dd_usd"),
        "trading_dd_datum": trading_dd.get("dd_date_max_rel"),
        "martingale_flag": marti.get("flag"),
        "martingale_text": marti.get("interpretation"),
    }
