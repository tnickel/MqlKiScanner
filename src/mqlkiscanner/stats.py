# -*- coding: utf-8 -*-
"""Grundkennzahlen aus Trade-Exporten (Winrate, PF, Serien, Monate, ...).

Konsolidiert aus scripts/reference/analyze_*.py — die Zahlen, die die
Analyse-Reihe in doc/01_analysen-verlauf.md zitiert.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import timedelta

from .models import ParsedExport


def compute(parsed: ParsedExport) -> dict:
    trades = parsed.trades
    if not trades:
        return {"trades": 0}

    seq_close = sorted(trades, key=lambda t: t.close_time)
    wins = [t for t in trades if t.profit > 0]
    losses = [t for t in trades if t.profit <= 0]
    gross_profit = sum(t.profit for t in wins)
    gross_loss = sum(t.profit for t in losses)
    net = sum(t.net for t in trades)

    span_days = (max(t.close_time for t in trades) - min(t.open_time for t in trades)).days

    streak_len = streak_sum = 0
    max_streak = max_streak_sum = 0
    streak_start = streak_end = None
    best_streak_window: list = []
    cur_window: list = []
    for t in seq_close:
        if t.profit <= 0:
            streak_len += 1
            streak_sum += t.profit
            cur_window.append(t)
            if streak_len > max_streak:
                max_streak = streak_len
                max_streak_sum = streak_sum
                streak_start, streak_end = t.open_time, t.close_time
                best_streak_window = list(cur_window)
        else:
            streak_len, streak_sum, cur_window = 0, 0.0, []

    by_day_pnl: dict[str, float] = defaultdict(float)
    by_day_cnt: Counter = Counter()
    for t in trades:
        key = t.open_time.date().isoformat()
        by_day_pnl[key] += t.profit
        by_day_cnt[key] += 1

    monthly_close: dict[str, float] = defaultdict(float)
    for t in trades:
        monthly_close[t.close_time.strftime("%Y-%m")] += t.net
    negative_months = sorted(m for m, v in monthly_close.items() if v < 0)

    hours = Counter(t.open_time.hour for t in trades)

    per_symbol: dict[str, dict] = {}
    for sym in sorted({t.symbol for t in trades}):
        sub = [t for t in trades if t.symbol == sym]
        sub_wins = [t for t in sub if t.profit > 0]
        per_symbol[sym] = {
            "trades": len(sub),
            "net": round(sum(t.net for t in sub), 2),
            "winrate_pct": round(len(sub_wins) / len(sub) * 100, 1),
            "lots_min": min(t.volume for t in sub),
            "lots_max": max(t.volume for t in sub),
            "median_holding_hours": round(statistics.median(t.holding_hours for t in sub), 2),
        }

    def median_or_none(values: list) -> float | None:
        return statistics.median(values) if values else None

    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "winrate_pct": round(len(wins) / len(trades) * 100, 1),
        "net": round(net, 2),
        "commission": round(sum(t.commission for t in trades), 2),
        "swap": round(sum(t.swap for t in trades), 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor_csv": round(gross_profit / abs(gross_loss), 2) if gross_loss else None,
        "avg_win": round(statistics.mean(t.profit for t in wins), 2) if wins else None,
        "avg_loss": round(statistics.mean(t.profit for t in losses), 2) if losses else None,
        "median_win": median_or_none([t.profit for t in wins]),
        "median_loss": median_or_none([t.profit for t in losses]),
        "best_trade": round(max(t.profit for t in trades), 2),
        "worst_trade": round(min(t.profit for t in trades), 2),
        "median_holding_hours": round(statistics.median(t.holding_hours for t in trades), 2),
        "max_holding_hours": round(max(t.holding_hours for t in trades), 1),
        "first_open": min(t.open_time for t in trades).isoformat(sep=" "),
        "last_close": max(t.close_time for t in trades).isoformat(sep=" "),
        "span_days": span_days,
        "span_weeks": round(span_days / 7, 1),
        "symbols": dict(Counter(t.symbol for t in trades)),
        "per_symbol": per_symbol,
        "lots": {f"{v:.2f}": c for v, c in sorted(Counter(t.volume for t in trades).items())},
        "max_consecutive_losses": max_streak,
        "max_consecutive_losses_sum": round(max_streak_sum, 2),
        "max_loss_streak_from": streak_start.isoformat(sep=" ") if streak_start else None,
        "max_loss_streak_to": streak_end.isoformat(sep=" ") if streak_end else None,
        "worst_day": min(by_day_pnl.items(), key=lambda kv: kv[1], default=None),
        "best_day": max(by_day_pnl.items(), key=lambda kv: kv[1], default=None),
        "max_trades_per_day": max(by_day_cnt.values(), default=0),
        "monthly_net_by_close": {m: round(v, 2) for m, v in sorted(monthly_close.items())},
        "negative_months_close": negative_months,
        "entry_hours_top": dict(sorted(hours.items(), key=lambda kv: -kv[1])[:8]),
    }


def month_table_by_open(parsed: ParsedExport) -> dict[str, float]:
    """Monatsnetto nach Open-Zeit (Alternative in den Referenzskripten genutzt)."""
    monthly: dict[str, float] = defaultdict(float)
    for t in parsed.trades:
        monthly[t.open_time.strftime("%Y-%m")] += t.net
    return {m: round(v, 2) for m, v in sorted(monthly.items())}


def weeks_between(first_open, last_close) -> float:
    return round((last_close - first_open).total_seconds() / (7 * 86400), 1)


def full_month_keys(first_open, last_close) -> set[str]:
    """Monate, die der Datenzeitraum voll abdeckt (Randmonate sind Partiale)."""
    import calendar

    full: set[str] = set()
    cursor = first_open.replace(day=1)
    last = last_close.replace(day=1)
    while cursor <= last:
        key = cursor.strftime("%Y-%m")
        days_in_month = calendar.monthrange(cursor.year, cursor.month)[1]
        first_is_full = first_open.strftime("%Y-%m") != key or first_open.day == 1
        last_is_full = last_close.strftime("%Y-%m") != key or last_close.day == days_in_month
        if first_is_full and last_is_full:
            full.add(key)
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    return full


def negative_months_full(parsed: ParsedExport) -> list[str]:
    """Negative Monate, nur voll abgedeckte Monate gezaehlt (Plattform-Tabelle)."""
    monthly: dict[str, float] = defaultdict(float)
    for t in parsed.trades:
        monthly[t.close_time.strftime("%Y-%m")] += t.net
    full = full_month_keys(min(t.open_time for t in parsed.trades),
                           max(t.close_time for t in parsed.trades))
    return sorted(m for m, v in monthly.items() if v < 0 and m in full)
