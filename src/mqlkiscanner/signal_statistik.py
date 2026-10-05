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


# Haltezeit-Buckets (Nutzer-Wunsch 05.10.2026: „Scalper abschätzen, wie
# die Trades verteilt sind"). Die ersten beiden sind GEFAEHRLICH beim
# Kopieren: 0-Sekunden-Fills und Trades unter einer Minute sind mit
# Kopier-Latenz/Slippage möglicherweise gar nicht erreichbar.
DAUER_BUCKETS: list[tuple[str, float, float | None]] = [
    ("0 Sek", 0.0, 0.0),            # genau 0 Sekunden (gleicher Zeitstempel)
    ("<1 Min", 0.0, 60.0),
    ("1–5 Min", 60.0, 300.0),
    ("5–15 Min", 300.0, 900.0),
    ("15–60 Min", 900.0, 3600.0),
    ("1–4 Std", 3600.0, 14400.0),
    ("4–24 Std", 14400.0, 86400.0),
    ("1–3 Tage", 86400.0, 259200.0),
    (">3 Tage", 259200.0, None),
]
GEFAEHRLICHE_BUCKETS = frozenset(("0 Sek", "<1 Min"))


def dauer_text(sekunden: float) -> str:
    """Haltezeit kompakt lesbar (0 s / 42 s / 3 Min 12 s / 2 Std 05 / 3 T 4 Std)."""
    if sekunden < 60.0:
        return f"{sekunden:.0f} s"
    minuten = sekunden / 60.0
    if minuten < 60.0:
        return f"{minuten:.0f} Min" if minuten >= 10 else f"{minuten:.1f} Min"
    stunden = sekunden / 3600.0
    if stunden < 24.0:
        return f"{stunden:.1f} Std"
    tage = sekunden / 86400.0
    return f"{tage:.1f} Tage"


def dauer_statistik(parsed) -> dict:
    """Haltezeit-Verteilung der Trades je Bucket (Anzahl, Anteil, Netto)."""
    buckets = {name: {"anzahl": 0, "netto_usd": 0.0}
               for name, _von, _bis in DAUER_BUCKETS}
    dauer_all: list[float] = []
    for trade in parsed.trades:
        dauer = max((trade.close_time - trade.open_time).total_seconds(), 0.0)
        dauer_all.append(dauer)
        for name, von, bis in DAUER_BUCKETS:
            getroffen = (dauer <= von) if name == "0 Sek" else (
                (dauer >= von and (bis is None or dauer < bis)))
            if getroffen:
                buckets[name]["anzahl"] += 1
                buckets[name]["netto_usd"] += trade.net
                break
    gesamt = len(parsed.trades) or 1
    zeilen = [{
        "bucket": name,
        "anzahl": werte["anzahl"],
        "anteil_pct": werte["anzahl"] / gesamt * 100.0,
        "netto_usd": werte["netto_usd"],
        "gefaehrlich": name in GEFAEHRLICHE_BUCKETS,
    } for name, werte in buckets.items()]
    gefaehrlich = sum(z["anzahl"] for z in zeilen if z["gefaehrlich"])
    null_sek = buckets["0 Sek"]["anzahl"]
    unter_1min = buckets["<1 Min"]["anzahl"]
    return {
        "buckets": zeilen,
        "null_sek": null_sek,
        "unter_1min": unter_1min,
        "gefaehrlich_anzahl": gefaehrlich,
        "gefaehrlich_anteil_pct": gefaehrlich / gesamt * 100.0,
        "dauer_median_s": sorted(dauer_all)[len(dauer_all) // 2] if dauer_all else 0.0,
        "dauer_max_s": max(dauer_all) if dauer_all else 0.0,
    }


def tradeliste(trades_pfad: str, stats: dict | None) -> list[dict]:
    """Alle Trades als Zeilen für die Anzeige (neueste zuerst) — lazily
    über die Seite gecacht, weil die Liste groß sein kann (15k+ Zeilen)."""
    stats = stats or {}
    try:
        parsed = load_export(trades_pfad,
                             plattform_positions=stats.get("trades"))
    except Exception:
        return []
    zeilen: list[dict] = []
    for nr, trade in enumerate(
            sorted(parsed.trades, key=lambda t: t.close_time, reverse=True), 1):
        dauer = max((trade.close_time - trade.open_time).total_seconds(), 0.0)
        zeilen.append({
            "Nr": nr,
            "Eröffnet": trade.open_time.strftime("%Y-%m-%d %H:%M:%S"),
            "Geschlossen": trade.close_time.strftime("%Y-%m-%d %H:%M:%S"),
            "Dauer": dauer_text(dauer),
            "Dauer (s)": round(dauer, 1),
            "Symbol": trade.symbol,
            "Richtung": trade.direction,
            "Lots": trade.volume,
            "Entry": trade.entry_price,
            "Exit": trade.exit_price,
            "Netto USD": round(trade.net, 2),
        })
    return zeilen


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
        "dauer_statistik": dauer_statistik(parsed),
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
