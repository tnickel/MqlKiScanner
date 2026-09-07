# -*- coding: utf-8 -*-
"""MT4/MT5-Zwillingsvergleich (Referenz: scripts/reference/compare_mt4_mt5.py).

Frage: Ist ein MT4- und ein MT5-Signal derselbe EA? Stufe 1 paart Trades
exakt sekundengenau nach (Instrument, Open-Zeit, Richtung) mit kleinstem
Preisabstand; Default-Toleranz: 3 FX-Pips bzw. 3 Gold-/Index-Kurseinheiten.
Stufe 2 faengt Unpaarierte fuzzy innerhalb +-max_dt_sec.
Ergebnis: Match-Quote, einseitige Trades, Ausfuehrungsvarianz.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime

from .models import ParsedExport, Trade
from .symbols import fx_pip_size, normalize_symbol, symbol_class


def _price_tolerance(symbol: str, override: float | None) -> float | None:
    """Default: three FX pips or three gold/index price units.

    Unknown instruments require an explicit tolerance in their price units.
    """
    if override is not None:
        if override < 0:
            raise ValueError("max_price_diff muss nichtnegativ sein")
        return override
    pip = fx_pip_size(symbol)
    if pip is not None:
        return 3 * pip
    return 3.0 if symbol_class(symbol) in ("METAL", "INDEX") else None


def _match(mt4: list[Trade], mt5: list[Trade], max_price_diff: float | None,
           max_dt_sec: int):
    used5: set[int] = set()
    pairs: list[tuple[Trade, Trade | None]] = []

    by_exact: dict[tuple, list[tuple[int, Trade]]] = defaultdict(list)
    for i, t in enumerate(mt5):
        by_exact[(normalize_symbol(t.symbol), t.open_time, t.direction)].append((i, t))

    def nearest(t4: Trade, candidates: list[tuple[int, Trade]]):
        best = None
        for i, t5 in candidates:
            if i in used5 or t4.entry_price is None or t5.entry_price is None:
                continue
            d = abs(t4.entry_price - t5.entry_price)
            if best is None or d < best[0]:
                best = (d, i, t5)
        return best

    for t4 in mt4:
        symbol = normalize_symbol(t4.symbol)
        tolerance = _price_tolerance(symbol, max_price_diff)
        best = nearest(t4, by_exact.get((symbol, t4.open_time, t4.direction), []))
        if best and tolerance is not None and best[0] <= tolerance + 1e-12:
            used5.add(best[1])
            pairs.append((t4, best[2]))
        else:
            pairs.append((t4, None))

    # Stufe 2: fuzzy +-max_dt_sec Sekunden
    remaining = sorted(((i, t) for i, t in enumerate(mt5) if i not in used5),
                       key=lambda x: x[1].open_time)

    def fuzzy(t4: Trade):
        symbol = normalize_symbol(t4.symbol)
        tolerance = _price_tolerance(symbol, max_price_diff)
        if tolerance is None or t4.entry_price is None:
            return None
        for i, t5 in remaining:
            if (i in used5 or t5.direction != t4.direction
                    or normalize_symbol(t5.symbol) != symbol or t5.entry_price is None):
                continue
            dt = abs((t5.open_time - t4.open_time).total_seconds())
            if dt <= max_dt_sec and abs(t5.entry_price - t4.entry_price) <= tolerance + 1e-12:
                used5.add(i)
                return t5
        return None

    return [(t4, (t5 if t5 is not None else fuzzy(t4))) for t4, t5 in pairs]


def run(parsed_mt4: ParsedExport, parsed_mt5: ParsedExport,
        since: datetime | None = None, max_price_diff: float | None = None,
        max_dt_sec: int = 3) -> dict:
    mt4 = [t for t in parsed_mt4.trades
           if since is None or t.open_time >= since]
    mt5 = list(parsed_mt5.trades)
    pairs = _match(mt4, mt5, max_price_diff, max_dt_sec)

    matched = [(a, b) for a, b in pairs if b is not None]
    only4 = [a for a, b in pairs if b is None]
    used5 = {id(b) for _, b in matched}
    only5 = [t for t in mt5 if id(t) not in used5]

    entry_diffs = [abs((a.entry_price or 0) - (b.entry_price or 0)) for a, b in matched]
    pnl_diffs = [a.net - b.net for a, b in matched]
    lot_diffs = [(a, b) for a, b in matched if abs(a.volume - b.volume) > 1e-9]

    exact = sum(1 for a, b in matched
                if a.open_time == b.open_time)
    return {
        "mt4_trades_in_window": len(mt4),
        "mt5_trades": len(mt5),
        "matched": len(matched),
        "matched_pct": round(len(matched) / len(mt4) * 100, 0) if mt4 else 0,
        "matched_exact_second": exact,
        "only_mt4": len(only4),
        "only_mt5": len(only5),
        "entry_diff_median": float(f"{statistics.median(entry_diffs):.8g}") if entry_diffs else None,
        "entry_diff_max": float(f"{max(entry_diffs):.8g}") if entry_diffs else None,
        "pnl_diff_sum": round(sum(pnl_diffs), 2),
        "lot_deviation_trades": len(lot_diffs),
        "verdict": (
            "derselbe EA (Ausfuehrungsvarianz)" if mt4 and len(matched) / len(mt4) >= 0.8
            else "kein eindeutiger Zwilling"
        ),
    }
