# -*- coding: utf-8 -*-
"""Forensik-Test 2: Peak-Exposure (Spec: doc/03_forensik-tests.md).

Maximal gleichzeitig offene Positionen + aggregiertes Volumen, umgerechnet
in Dollar-Risiko. Kontraktgroessen (doc/02 Abschnitt 5):
  XAUUSD: 1 Lot = 100 USD je 1 USD Kursbewegung  (der teure Lernpunkt)
  Indizes: 1 Lot = 1 USD je Punkt
  FX: 1 Lot = 100 000 Einheiten (10 USD je Pip bei 4. Dezimale)

Schockszenario je Symbolklasse:
  Metall 50 USD Kursbewegung | Index 50 Punkte | FX 500 Pips (0.0500)

Rote Flagge: Schockszenario > 30 % des Kontos.
Referenz: scripts/reference/martingale_exposure_test.py (Test 4).
"""
from __future__ import annotations

from ..models import ParsedExport, Trade

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


def symbol_class(symbol: str) -> str:
    s = symbol.upper()
    if s.startswith("XAU") or s.startswith("XAG") or s.startswith("XPT"):
        return "METAL"
    if any(idx in s for idx in ("US30", "US500", "NAS100", "GER40", "UK100", "JP225", "SPX", "NDX")):
        return "INDEX"
    return "FX"


def shock_usd(net_lots: float, move: float, symbol: str) -> float:
    """Dollar-Risiko einer Gegenbewegung `move` Preiseinheiten bei `net_lots`."""
    return abs(net_lots) * move * CONTRACT_FACTOR_PER_UNIT[symbol_class(symbol)]


def run(parsed: ParsedExport, stress_move: float | None = None) -> dict:
    trades = parsed.trades
    if not trades:
        return {"test": "exposure", "flag": False}

    events: list[tuple] = []
    for t in trades:
        events.append((t.open_time, 1, t))
        events.append((t.close_time, -1, t))
    # Opens vor Closes am selben Zeitpunkt zaehlen (Position bleibt eine Sekunde offen)
    events.sort(key=lambda e: (e[0], -e[1]))

    open_count = 0
    long_vol = short_vol = 0.0
    peak_count = 0
    peak_long = peak_short = 0.0
    peak_time = None
    peak_symbol = ""
    for time, delta, t in events:
        open_count += delta
        if t.direction == "Buy":
            long_vol += delta * t.volume
        else:
            short_vol += delta * t.volume
        if open_count > peak_count:
            peak_count = open_count
            peak_long, peak_short, peak_time = long_vol, short_vol, time
            peak_symbol = t.symbol

    net = peak_long - peak_short
    gross = peak_long + peak_short
    sym = peak_symbol or (trades[0].symbol if trades else "")
    sclass = symbol_class(sym)
    move = stress_move if stress_move is not None else STRESS_MOVE_BY_CLASS[sclass]
    shock = shock_usd(net, move, sym)

    result: dict = {
        "test": "exposure",
        "peak_open_positions": peak_count,
        "peak_time": peak_time.isoformat(sep=" ") if peak_time else None,
        "peak_long_lots": round(peak_long, 2),
        "peak_short_lots": round(peak_short, 2),
        "peak_net_lots": round(net, 2),
        "peak_gross_lots": round(gross, 2),
        "symbol_class": sclass,
        "usd_per_unit_per_lot": CONTRACT_FACTOR_PER_UNIT[sclass],
        "stress_move": move,
        "stress_move_unit": _UNIT_LABEL[sclass],
        "shock_usd": round(shock, 2),
        "shock_formula": f"{abs(net):.2f} Lots x {move:g} {_UNIT_LABEL[sclass]} x "
                         f"{CONTRACT_FACTOR_PER_UNIT[sclass]:g} = {shock:,.2f} USD",
    }
    if sclass == "FX":
        pip_factor = 0.01 if "JPY" in sym.upper() else 0.0001
        pip_usd = shock_usd(net, pip_factor * 10, sym)  # 10 Pips
        result["fx_pips_10_usd"] = round(pip_usd, 2)
    return result
