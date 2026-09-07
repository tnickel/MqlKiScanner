# -*- coding: utf-8 -*-
"""Forensik-Test 2: Peak-Exposure (Spec: doc/03_forensik-tests.md).

Maximal gleichzeitig offene Positionen + aggregiertes Volumen, umgerechnet
in Dollar-Risiko. Kontraktgroessen (doc/02 Abschnitt 5):
  XAUUSD: 1 Lot = 100 USD je 1 USD Kursbewegung  (der teure Lernpunkt)
  Indizes: 1 Lot = 1 USD je Punkt
  FX: 1 Lot = 100 000 Einheiten (10 USD je Pip bei 4. Dezimale)

Schockszenario je Symbolklasse:
  Metall 50 USD Kursbewegung | Index 50 Punkte | FX 500 Pips (0.0500)

Zwei Peak-Masse (Spec-Frage: max. aggregierte Marktposition / Schockkosten):
  - peak_open_positions: Maximum der Positions*anzahl*
  - shock_usd / peak_net_*: am Zeitpunkt des maximalen Dollar-Schocks
    (Volumen-Peak je Symbol, kein Cross-Symbol-Lot-Netting als Hedge)

Rote Flagge: Schockszenario > 30 % des Kontos (scoring.margin / flag).
Referenz: scripts/reference/martingale_exposure_test.py (Test 4).
"""
from __future__ import annotations

from collections import defaultdict
import math

from ..models import ParsedExport, Trade
from ..symbols import normalize_symbol, symbol_class

# USD-Risiko je 1.00 Kurseinheit und Lot
CONTRACT_FACTOR_PER_UNIT: dict[str, float] = {
    "METAL": 100.0,   # XAUUSD, XAUUSD+, XAGUSD ...
    "INDEX": 1.0,     # US30, NAS100, SPX500, GER40 ...
    "FX": 100_000.0,  # je 1.00 Bewegung; praktisch ueber Pips berichten
}

# Stressbewegung je Symbolklasse in Preiseinheiten
STRESS_MOVE_BY_CLASS: dict[str, float] = {
    "METAL": 50.0,
    "INDEX": 50.0,
    "FX": 0.05,   # 500 Pips bei 4. Dezimale
}

_UNIT_LABEL = {"METAL": "USD Kursbewegung", "INDEX": "Punkte",
               "FX": "Preiseinheiten (=500 Pips)"}


def shock_usd(net_lots: float, move: float, symbol: str) -> float:
    """Dollar-Risiko einer Gegenbewegung `move` Preiseinheiten bei `net_lots`."""
    sclass = symbol_class(symbol)
    if sclass == "UNKNOWN":
        raise ValueError(f"Unbekanntes Instrument {symbol!r}: Kontraktgroesse nicht belegt")
    return abs(net_lots) * move * CONTRACT_FACTOR_PER_UNIT[sclass]


def _portfolio_shock(net_by_symbol: dict[str, float],
                     stress_move: float | None = None) -> tuple[float, str]:
    """Schock je Symbol mit eigener Klasse, dann summieren (kein Cross-Hedge)."""
    total = 0.0
    dominant = ""
    dominant_abs = 0.0
    for sym, net in net_by_symbol.items():
        if abs(net) < 1e-12:
            continue
        sclass = symbol_class(sym)
        move = stress_move if stress_move is not None else STRESS_MOVE_BY_CLASS[sclass]
        total += shock_usd(net, move, sym)
        if abs(net) >= dominant_abs:
            dominant_abs = abs(net)
            dominant = sym
    return total, dominant


def _snapshot(net_by_symbol: dict[str, float], long_vol: float, short_vol: float,
              time, stress_move: float | None) -> dict:
    by_sym = {s: v for s, v in net_by_symbol.items() if abs(v) > 1e-12}
    shock, peak_symbol = _portfolio_shock(by_sym, stress_move)
    return {
        "time": time,
        "long": long_vol,
        "short": short_vol,
        "by_sym": by_sym,
        "shock": shock,
        "peak_symbol": peak_symbol,
    }


def run(parsed: ParsedExport, stress_move: float | None = None) -> dict:
    trades = parsed.trades
    if not trades:
        return {"test": "exposure", "flag": False, "temporal_risk_available": False}
    unknown = sorted({t.symbol for t in trades if symbol_class(t.symbol) == "UNKNOWN"})
    if unknown:
        raise ValueError("Unbekannte Instrumente ohne belegte Kontraktgroesse: " + ", ".join(unknown))
    if stress_move is not None and (not math.isfinite(stress_move) or stress_move < 0):
        raise ValueError("Schockbewegung muss endlich und nicht negativ sein")

    events: list[tuple] = []
    for t in trades:
        events.append((t.open_time, 1, 1, t))
        events.append((t.close_time, 2, -1, t))
    for flow in parsed.balances:
        events.append((flow.time, 0, 0, flow))
    # Kontobewegungen vor Opens, Opens vor Closes derselben Sekunde.
    # Ein Close verbucht sein Netto erst beim Entfernen der Position; damit
    # kann spaeterer Gewinn die historische Belastung nicht verkleinern.
    events.sort(key=lambda e: (e[0], e[1]))

    open_count = 0
    long_vol = short_vol = 0.0
    net_by_symbol: dict[str, float] = defaultdict(float)
    peak_count = 0
    count_snap: dict | None = None
    risk_snap: dict | None = None
    relative_snap: dict | None = None
    account = 0.0
    first_open = min(t.open_time for t in trades)
    initial_capital = sum(b.amount for b in parsed.balances if b.time <= first_open)
    capital_history_complete = initial_capital > 0
    temporal_risk_available = capital_history_complete

    for time, kind, delta, item in events:
        if kind == 0:
            account += item.amount
        else:
            t = item
            open_count += delta
            signed = delta * t.volume
            sym = normalize_symbol(t.symbol)
            if delta == -1:
                account += t.net
            if t.direction == "Buy":
                long_vol += signed
                net_by_symbol[sym] += signed
            else:
                short_vol += signed
                net_by_symbol[sym] -= signed
        snap = _snapshot(net_by_symbol, long_vol, short_vol, time, stress_move)
        snap["account"] = account
        if snap["shock"] > 0 and account <= 0:
            temporal_risk_available = False
        if open_count > 0 and account > 0:
            snap["shock_pct"] = snap["shock"] / account * 100
            if relative_snap is None or snap["shock_pct"] > relative_snap["shock_pct"]:
                relative_snap = snap
        if open_count > peak_count:
            peak_count = open_count
            count_snap = snap
        if risk_snap is None or snap["shock"] > risk_snap["shock"]:
            risk_snap = snap

    assert count_snap is not None and risk_snap is not None
    peak_net_by_symbol = risk_snap["by_sym"]
    shock = risk_snap["shock"]
    peak_symbol = risk_snap["peak_symbol"]
    peak_long, peak_short = risk_snap["long"], risk_snap["short"]
    peak_time = risk_snap["time"]
    gross = peak_long + peak_short
    signed_peak_net = sum(peak_net_by_symbol.values())
    abs_lots = sum(abs(v) for v in peak_net_by_symbol.values())
    # Cross-Symbol-Lot-Netting als "0 Lots" waere irrefuehrend (Schock bleibt hoch).
    if peak_net_by_symbol and abs(signed_peak_net) + 1e-12 < abs_lots * 0.5:
        headline_net = max(peak_net_by_symbol.values(), key=abs)
    else:
        headline_net = signed_peak_net

    sym = peak_symbol or (trades[0].symbol if trades else "")
    sclass = symbol_class(sym) if sym else "FX"
    move = stress_move if stress_move is not None else STRESS_MOVE_BY_CLASS[sclass]

    temporal_risk_available = temporal_risk_available and relative_snap is not None
    result: dict = {
        "test": "exposure",
        "peak_open_positions": peak_count,
        "peak_count_time": (count_snap["time"].isoformat(sep=" ")
                            if count_snap["time"] else None),
        "peak_count_net_by_symbol": {
            k: round(v, 2) for k, v in sorted(count_snap["by_sym"].items())},
        "peak_count_shock_usd": round(count_snap["shock"], 2),
        "peak_time": peak_time.isoformat(sep=" ") if peak_time else None,
        "peak_long_lots": round(peak_long, 2),
        "peak_short_lots": round(peak_short, 2),
        "peak_net_lots": round(headline_net, 2),
        "peak_net_lots_signed_sum": round(signed_peak_net, 2),
        "peak_gross_lots": round(gross, 2),
        "peak_net_by_symbol": {k: round(v, 2) for k, v in sorted(peak_net_by_symbol.items())},
        "symbol_class": sclass,
        "usd_per_unit_per_lot": CONTRACT_FACTOR_PER_UNIT[sclass],
        "stress_move": move,
        "stress_move_unit": _UNIT_LABEL[sclass],
        "shock_usd": round(shock, 2),
        "account_at_shock_peak": round(risk_snap["account"], 2),
        "capital_history_complete": capital_history_complete,
        "temporal_risk_available": temporal_risk_available,
        "shock_pct_max": round(relative_snap["shock_pct"], 4) if temporal_risk_available else None,
        "shock_pct_peak_time": relative_snap["time"].isoformat(sep=" ") if temporal_risk_available else None,
        "shock_pct_peak_account": round(relative_snap["account"], 2) if temporal_risk_available else None,
        "shock_pct_peak_usd": round(relative_snap["shock"], 2) if temporal_risk_available else None,
        "unknown_symbols": [],
        "shock_formula": (
            f"Summe je Symbol am Volumen-/Schock-Peak = {shock:,.2f} USD"
            if len(peak_net_by_symbol) > 1 else
            f"{abs(headline_net):.2f} Lots x {move:g} {_UNIT_LABEL[sclass]} x "
            f"{CONTRACT_FACTOR_PER_UNIT[sclass]:g} = {shock:,.2f} USD"
        ),
        "flag": not temporal_risk_available or relative_snap["shock_pct"] > 30.0,
    }
    if sclass == "FX" and len(peak_net_by_symbol) <= 1:
        pip_factor = 0.01 if "JPY" in sym.upper() else 0.0001
        pip_usd = shock_usd(headline_net, pip_factor * 10, sym)  # 10 Pips
        result["fx_pips_10_usd"] = round(pip_usd, 2)
    return result
