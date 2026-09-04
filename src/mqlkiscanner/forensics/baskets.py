# -*- coding: utf-8 -*-
"""Basket-/Cluster-Analysen (Soll-Teil der Forensik, doc/03).

- Basket-Exits: Trades mit identischem Close-Zeitpunkt (>=2 = Basket-Exit).
  Anteil der Trades in Koerben = Grid-Indikator; Koerbe auf Richtung und
  Lot-Staffelung pruefen (Averaging vs. Pyramiding).
- Korb-Laufen: Beine eines Koerbs chronologisch — letzte Beine groesser
  = Eskalation (Martingale-Verdacht), kleiner = Verkleinerung.

Referenz: analyze_kiracat.py, analyze_msc.py, analyze_goldreaper.py,
analyze_fxtrading.py.
"""
from __future__ import annotations

from collections import defaultdict

from ..models import ParsedExport


def run(parsed: ParsedExport, min_basket: int = 2) -> dict:
    trades = parsed.trades
    if not trades:
        return {"test": "baskets"}

    by_close: dict[str, list] = defaultdict(list)
    for t in trades:
        by_close[t.close_time.strftime("%Y%m%d%H%M%S")].append(t)
    baskets = [b for b in by_close.values() if len(b) >= min_basket]
    in_baskets = sum(len(b) for b in baskets)
    biggest = max(baskets, key=len, default=[])

    per_symbol_max: dict[str, int] = {}
    for b in baskets:
        for sym in {t.symbol for t in b}:
            size = sum(1 for t in b if t.symbol == sym)
            per_symbol_max[sym] = max(per_symbol_max.get(sym, 0), size)

    # Lot-Staffelung im groszen Korb (chronologisch)
    ladder = []
    if biggest:
        for t in sorted(biggest, key=lambda t: t.open_time):
            ladder.append(f"{t.volume:.2f}")

    # Eskalation: letztes Bein groezer als erstes, ueber alle Mehrfach-Koerbe
    bigger = smaller = 0
    for b in baskets:
        if len(b) < 3:
            continue
        legs = sorted(b, key=lambda t: t.open_time)
        if legs[-1].volume > legs[0].volume:
            bigger += 1
        elif legs[-1].volume < legs[0].volume:
            smaller += 1

    return {
        "test": "baskets",
        "min_basket": min_basket,
        "basket_exits": len(baskets),
        "trades_in_baskets": in_baskets,
        "trades_in_baskets_pct": round(in_baskets / len(trades) * 100, 1),
        "biggest_basket": len(biggest),
        "biggest_basket_symbol_lots": ladder[:20],
        "max_basket_per_symbol": per_symbol_max,
        "baskets_last_leg_bigger": bigger,
        "baskets_last_leg_smaller": smaller,
        "grid_indicator_pct": round(in_baskets / len(trades) * 100, 1),
    }
