# -*- coding: utf-8 -*-
"""Forensik-Test 3: SL-Clustering / Stop-Nachweis (Spec: doc/03_forensik-tests.md).

Drei Evidenzstufen:
1. Orderbuch-Direktnachweis (History-CSV mit S/L-Spalte und [sl]/[tp]-Kommentaren)
   — der Goldstandard (Referenz: analyze_goldspike_orderbook.py)
2. Verlustdistanz-Clustering aus dem Positions-Export: ballen sich Verlust-
   distanzen an einem Niveau (Stop-Signatur) oder streuen sie frei?
   (Referenz: analyze_goldreaper.py / analyze_kiracat.py / martingale_exposure_test.py Test 3)
3. Ribbon-Statistik: laengste Verlustserie + schlechtester Einzeltrade.

"Kein Nachweis" = Warnflag, niemals Entlastung (AGENTS.md Regel 2).
"""
from __future__ import annotations

import statistics
from collections import Counter

from ..models import ParsedExport


def run(parsed: ParsedExport) -> dict:
    trades = parsed.trades
    if parsed.has_orderbook:
        result = _orderbook_evidence(parsed)
    else:
        result = {"evidence_level": 2, "method": "verlustdistanz-clustering"}
        result.update(_distance_clustering(trades))
    result["ribbon"] = _ribbon_statistics(trades)
    return result


# ---------------------------------------------------------------- Stufe 1
def _orderbook_evidence(parsed: ParsedExport) -> dict:
    trades = parsed.trades
    with_sl_tp = [t for t in trades if t.sl and t.tp]
    sl_exits = [t for t in trades if t.comment == "[sl]"]
    tp_exits = [t for t in trades if t.comment == "[tp]"]
    manual = len(trades) - len(sl_exits) - len(tp_exits)
    sl_in_plus = [t for t in sl_exits if t.profit > 0]

    sl_dists: list[float] = []
    tp_dists: list[float] = []
    rr: list[float] = []
    for t in with_sl_tp:
        sld = (t.entry_price - t.sl) * t.sign
        tpd = (t.tp - t.entry_price) * t.sign
        if sld > 0 and tpd > 0:
            sl_dists.append(sld)
            tp_dists.append(tpd)
            rr.append(tpd / sld)

    sl_loss_dists = [d for t in sl_exits if t.profit <= 0
                     for d in [t.loss_distance()] if d]

    return {
        "evidence_level": 1,
        "method": "orderbuch-direktnachweis",
        "positions_total": len(trades),
        "positions_with_sl_tp": len(with_sl_tp),
        "positions_with_sl_tp_pct": round(len(with_sl_tp) / len(trades) * 100, 1) if trades else 0,
        "exits_sl": len(sl_exits),
        "exits_tp": len(tp_exits),
        "exits_manual": manual,
        "sl_exits_in_plus": len(sl_in_plus),
        "sl_exits_in_plus_sum": round(sum(t.profit for t in sl_in_plus), 2),
        "trailing_proof": len(sl_exits) > 0 and len(sl_in_plus) / len(sl_exits) > 0.5,
        "initial_sl_dist_median": round(statistics.median(sl_dists), 2) if sl_dists else None,
        "initial_sl_dist_max": round(max(sl_dists), 2) if sl_dists else None,
        "initial_tp_dist_median": round(statistics.median(tp_dists), 2) if tp_dists else None,
        "rr_median": round(statistics.median(rr), 2) if rr else None,
        "sl_loss_dist_median": round(statistics.median(sl_loss_dists), 2) if sl_loss_dists else None,
        "sl_loss_dist_max": round(max(sl_loss_dists), 2) if sl_loss_dists else None,
        "verdict": (
            "BEWIESEN: jede Position mit SL/TP im Orderbuch; Stop-Ausloesungen "
            "rekonstruierbar" if with_sl_tp else "kein SL im Orderbuch"
        ),
    }


# ---------------------------------------------------------------- Stufe 2
def _distance_clustering(trades) -> dict:
    dists = sorted(d for t in trades if (d := t.loss_distance()) is not None)
    if not dists:
        return {"n_losses_with_distance": 0, "verdict": "keine Verluste mit Preisdaten"}
    n = len(dists)
    rounded = Counter(round(d, 1) for d in dists)
    top_level, top_count = rounded.most_common(1)[0]
    top_share = top_count / n
    spread = dists[-1] / max(dists[n // 2], 1e-9)  # max / median
    clustered = top_share >= 0.25
    free_running = top_share < 0.10 and spread >= 10.0
    return {
        "n_losses_with_distance": n,
        "loss_dist_median": round(statistics.median(dists), 2),
        "loss_dist_p75": round(dists[3 * n // 4], 2),
        "loss_dist_p90": round(dists[9 * n // 10], 2),
        "loss_dist_max": round(dists[-1], 2),
        "top_distance_level": top_level,
        "top_distance_share_pct": round(top_share * 100, 1),
        "spread_max_over_median": round(spread, 1),
        "clustered": clustered,
        "verdict": (
            f"Stop-Signatur: {top_share*100:.0f}% der Verlustdistanzen bei {top_level}"
            if clustered
            else ("Verlustdistanzen ungebundelt, laufen frei (kein Stop-Nachweis)"
                  if free_running else
                  "kein eindeutiges Stop-Niveau erkennbar (kein Nachweis)")
        ),
    }


# ---------------------------------------------------------------- Stufe 3
def _ribbon_statistics(trades) -> dict:
    """Laengste Verlustserie (chronologisch nach Close) mit Summe und Zeitraum."""
    seq = sorted(trades, key=lambda t: t.close_time)
    worst = min(trades, key=lambda t: t.profit, default=None)
    base = {"worst_single_trade": round(worst.profit, 2) if worst else None}
    streak_len = best_len = 0
    streak_sum = best_sum = 0.0
    window: list = []
    best_window: list = []
    for t in seq:
        if t.profit <= 0:
            streak_len += 1
            streak_sum += t.profit
            window.append(t)
            if streak_len > best_len:
                best_len, best_sum = streak_len, streak_sum
                best_window = list(window)
        else:
            streak_len, streak_sum, window = 0, 0.0, []
    if best_len:
        base.update({
            "max_loss_streak": best_len,
            "max_loss_streak_sum": round(best_sum, 2),
            "streak_from": best_window[0].open_time.date().isoformat(),
            "streak_to": best_window[-1].close_time.date().isoformat(),
        })
    return base
