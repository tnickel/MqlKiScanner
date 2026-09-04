# -*- coding: utf-8 -*-
"""Trade-Daten-Payload fuer das LLM (Nutzer-Prinzip: "das LLM soll die
Strategie anhand der Trades ermitteln").

Die Engine berechnet ALLE Kennzahlen (AGENTS.md Design-Regel 1) und
stellt sie hier als kompaktes JSON zusammen — plus kuratierte
Beispiel-Trades (schlechteste, beste, laengste Verlustserie, groeszter
Korb), damit das LLM echtes Trade-Verhalten sieht, ohne dass tausende
Rohzeilen in den Kontext gehen. Zitieren der Zahlen erlaubt, eigene
Berechnungen nicht noetig.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict

from .models import ParsedExport, Trade


def _trade_row(t: Trade) -> dict:
    return {
        "open": t.open_time.strftime("%Y-%m-%d %H:%M"),
        "close": t.close_time.strftime("%Y-%m-%d %H:%M"),
        "dir": "Buy" if t.direction == "Buy" else "Sell",
        "lots": t.volume,
        "symbol": t.symbol,
        "ep": t.entry_price,
        "xp": t.exit_price,
        "pnl": round(t.net, 2),
        "hold_h": round(t.holding_hours, 2),
        **({"exit": t.comment} if t.comment else {}),
    }


def build_trade_payload(parsed: ParsedExport, max_samples: int = 12) -> dict:
    """Engine-berechnetes Trade-Level-JSON fuer die LLM-Analyse."""
    trades = parsed.trades
    if not trades:
        return {"fehler": "keine Trades"}

    by_open = sorted(trades, key=lambda t: t.open_time)
    by_close = sorted(trades, key=lambda t: t.close_time)
    wins = [t for t in trades if t.profit > 0]
    losses = [t for t in trades if t.profit <= 0]
    durs = sorted(t.holding_hours for t in trades)

    # --- Monatskurve (Netto je Close-Monat)
    monthly: dict[str, float] = defaultdict(float)
    for t in trades:
        monthly[t.close_time.strftime("%Y-%m")] += t.net

    # --- Pro Symbol
    per_symbol = []
    for sym in sorted({t.symbol for t in trades}):
        sub = [t for t in trades if t.symbol == sym]
        sw = [t for t in sub if t.profit > 0]
        per_symbol.append({
            "symbol": sym, "trades": len(sub),
            "netto": round(sum(t.net for t in sub), 2),
            "winrate_pct": round(len(sw) / len(sub) * 100, 1),
            "lots": f"{min(t.volume for t in sub):.2f}-{max(t.volume for t in sub):.2f}",
            "median_hold_h": round(statistics.median(t.holding_hours for t in sub), 2),
        })

    # --- Laengste Verlustserie (chronologisch nach Close)
    streak, best_len, best_window = 0, 0, []
    window = []
    for t in by_close:
        if t.profit <= 0:
            streak += 1
            window.append(t)
            if streak > best_len:
                best_len, best_window = streak, list(window)
        else:
            streak, window = 0, []

    # --- Groeszter Korb (identischer Close-Zeitpunkt)
    by_exit: dict[str, list] = defaultdict(list)
    for t in trades:
        by_exit[t.close_time.strftime("%Y%m%d%H%M%S")].append(t)
    biggest = max(by_exit.values(), key=len, default=[])

    # --- Verlustdistanzen (Kurspunkte)
    dists = sorted(d for t in trades if (d := t.loss_distance()) is not None)
    dist_levels = Counter(round(d, 1) for d in dists).most_common(5)

    # --- Beispiel-Trades: schlechteste + beste + Serienfenster + erster Handelstag
    worst = sorted(trades, key=lambda t: t.profit)[:max_samples]
    best = sorted(trades, key=lambda t: -t.profit)[:max(4, max_samples // 2)]
    first_day = [t for t in by_open
                 if t.open_time.date() == by_open[0].open_time.date()][:10]

    return {
        "meta": {
            "trades": len(trades),
            "zeitraum": f"{by_open[0].open_time:%Y-%m-%d} bis {by_close[-1].close_time:%Y-%m-%d}",
            "wins": len(wins), "losses": len(losses),
            "winrate_pct": round(len(wins) / len(trades) * 100, 1),
            "netto_gesamt": round(sum(t.net for t in trades), 2),
            "avg_win": round(statistics.mean(t.profit for t in wins), 2) if wins else None,
            "avg_loss": round(statistics.mean(t.profit for t in losses), 2) if losses else None,
            "halt_h_median": round(statistics.median(durs), 2),
            "halt_h_p90": round(durs[int(len(durs) * 0.9)], 2),
            "halt_h_max": round(durs[-1], 1),
        },
        "monatskurve": [{"monat": m, "netto": round(v, 2)} for m, v in sorted(monthly.items())],
        "pro_symbol": per_symbol,
        "lots_verteilung": {f"{v:.2f}": c for v, c in
                            sorted(Counter(t.volume for t in trades).items())},
        "einstiegsstunden_top": dict(sorted(Counter(t.open_time.hour for t in trades).items(),
                                            key=lambda kv: -kv[1])[:8]),
        "verluste": {
            "worst": round(min(t.profit for t in trades), 2),
            "median": round(statistics.median(t.profit for t in losses), 2) if losses else None,
            "distanz_median": round(statistics.median(dists), 2) if dists else None,
            "distanz_max": round(dists[-1], 2) if dists else None,
            "distanz_top_level": [{"punkte": lvl, "anzahl": c} for lvl, c in dist_levels],
        },
        "verlustserie_max": {
            "laenge": best_len,
            "summe": round(sum(t.profit for t in best_window), 2),
            "zeitraum": (f"{best_window[0].open_time:%Y-%m-%d} bis "
                         f"{best_window[-1].close_time:%Y-%m-%d}") if best_window else None,
            "trades": [_trade_row(t) for t in best_window[:25]],
        },
        "groesster_korb": {
            "positionen": len(biggest),
            "netto": round(sum(t.net for t in biggest), 2),
            "legs": [_trade_row(t) for t in
                     sorted(biggest, key=lambda t: t.open_time)[:20]],
        },
        "beispiel_trades": {
            "schlechteste": [_trade_row(t) for t in worst],
            "beste": [_trade_row(t) for t in best],
            "erster_handelstag": [_trade_row(t) for t in first_day],
        },
    }
