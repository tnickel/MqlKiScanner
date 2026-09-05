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
from collections import Counter, defaultdict

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
        "verdict": _orderbook_verdict(len(trades), len(with_sl_tp), len(sl_exits)),
    }


def _orderbook_verdict(total: int, with_sl_tp: int, sl_exits: int) -> str:
    if total <= 0:
        return "kein SL im Orderbuch"
    if with_sl_tp <= 0:
        return "kein SL/TP-Paar im Orderbuch"
    pct = with_sl_tp / total * 100
    if with_sl_tp == total and sl_exits > 0:
        return ("BEWIESEN: jede Position mit SL/TP im Orderbuch; "
                "Stop-Ausloesungen rekonstruierbar")
    if with_sl_tp == total:
        return (f"Orderbuch: {with_sl_tp}/{total} Positionen mit SL/TP-Feldern "
                "(keine [sl]-Ausfuehrungen im Export)")
    return (f"TEILWEISE: {with_sl_tp}/{total} Positionen ({pct:.0f} %) mit SL/TP "
            "im Orderbuch — kein vollstaendiger Stop-Nachweis")


# ---------------------------------------------------------------- Stufe 2
def _distance_bin(distance: float, symbol: str) -> float:
    """Symbolgerechte Rundung: Gold/Index 0.1, FX 1 Pip (nicht pauschal 0.1)."""
    s = (symbol or "").upper()
    if s.startswith(("XAU", "XAG", "XPT")):
        return round(distance, 1)
    if any(idx in s for idx in ("US30", "US500", "NAS100", "GER40", "UK100", "JP225", "SPX", "NDX")):
        return round(distance, 1)
    if "JPY" in s:
        return round(distance, 2)   # 0.01 ≈ 1 Pip
    return round(distance, 4)       # 0.0001 ≈ 1 Pip (Majors)


def _distance_clustering(trades) -> dict:
    """Cluster je Symbol mit angepasster Bin-Weite; staerkstes Symbol gewinnt."""
    by_sym: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        d = t.loss_distance()
        if d is not None:
            by_sym[t.symbol].append(d)
    if not by_sym:
        return {"n_losses_with_distance": 0, "verdict": "keine Verluste mit Preisdaten"}

    best: dict | None = None
    all_dists: list[float] = []
    for sym, dists in by_sym.items():
        all_dists.extend(dists)
        n = len(dists)
        if n < 3:
            continue
        rounded = Counter(_distance_bin(d, sym) for d in dists)
        top_level, top_count = rounded.most_common(1)[0]
        top_share = top_count / n
        sorted_d = sorted(dists)
        spread = sorted_d[-1] / max(sorted_d[n // 2], 1e-9)
        cand = {
            "symbol": sym,
            "n": n,
            "top_level": top_level,
            "top_share": top_share,
            "spread": spread,
            "clustered": top_share >= 0.25,
            "free_running": top_share < 0.10 and spread >= 10.0,
            "dists": sorted_d,
        }
        if best is None or cand["top_share"] > best["top_share"] or (
                cand["top_share"] == best["top_share"] and cand["n"] > best["n"]):
            best = cand

    n_all = len(all_dists)
    if best is None:
        # Zu wenige Verluste je Symbol — Gesamtstatistik ohne Cluster-Claim
        sorted_all = sorted(all_dists)
        return {
            "n_losses_with_distance": n_all,
            "loss_dist_median": round(statistics.median(sorted_all), 5),
            "loss_dist_p75": round(sorted_all[3 * n_all // 4], 5),
            "loss_dist_p90": round(sorted_all[9 * n_all // 10], 5),
            "loss_dist_max": round(sorted_all[-1], 5),
            "top_distance_level": None,
            "top_distance_share_pct": None,
            "spread_max_over_median": None,
            "clustered": False,
            "verdict": "zu wenige Verluste je Symbol fuer Cluster-Aussage (kein Nachweis)",
        }

    n = best["n"]
    dists = best["dists"]
    clustered = best["clustered"]
    free_running = best["free_running"]
    return {
        "n_losses_with_distance": n_all,
        "cluster_symbol": best["symbol"],
        "loss_dist_median": round(statistics.median(dists), 5),
        "loss_dist_p75": round(dists[3 * n // 4], 5),
        "loss_dist_p90": round(dists[9 * n // 10], 5),
        "loss_dist_max": round(dists[-1], 5),
        "top_distance_level": best["top_level"],
        "top_distance_share_pct": round(best["top_share"] * 100, 1),
        "spread_max_over_median": round(best["spread"], 1),
        "clustered": clustered,
        "verdict": (
            f"Stop-Signatur ({best['symbol']}): {best['top_share']*100:.0f}% der "
            f"Verlustdistanzen bei {best['top_level']}"
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
