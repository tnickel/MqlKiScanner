# -*- coding: utf-8 -*-
"""Forensik-Test 3: SL-Clustering / Stop-Nachweis (Spec: doc/03_forensik-tests.md).

Drei Evidenzstufen:
1. Orderbuch-Direktnachweis (History-CSV mit S/L-Spalte und [sl]/[tp]-Kommentaren)
   — der Goldstandard (Referenz: analyze_goldspike_orderbook.py)
2. Verlustdistanz-Clustering aus dem Positions-Export: ballen sich Verlust-
   distanzen an einem Niveau (Stop-Signatur) oder streuen sie frei?
   (Referenz: analyze_goldreaper.py / analyze_kiracat.py / martingale_exposure_test.py Test 3)
3. Ribbon-Statistik: laengste Verlustserie + schlechtester Einzeltrade.

"Kein Nachweis" = NEUTRAL (bindende Nutzer-Regel 28.09.2026): kein
Score-Malus, keine Ampel-Sperre, keine Matrix-Abwertung; abwerten darf
nur die KI-Analyse mit begruendetem Befund. Bewiesener Stop bleibt
die einzige Entlastung.
"""
from __future__ import annotations

import statistics
import re
import math
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import astuple

from ..models import ParsedExport
from ..symbols import normalize_symbol, symbol_class, fx_pip_size

MIN_CLUSTER_LOSSES = 8
MIN_CLUSTER_REPEATS = 3
# Seconds are export resolution, not an inferred order execution delay.
# A wider 5-second window merged extra partial exits in the real controls.
SYNC_CLOSE_SECONDS = 2
MIN_PROTECTIVE_GROUPS = 3
MIN_PROTECTIVE_DAYS = 2


def run(parsed: ParsedExport) -> dict:
    trades = parsed.trades
    if parsed.has_orderbook:
        result = _orderbook_evidence(parsed)
    else:
        result = {"evidence_level": 2, "method": "verlustdistanz-clustering"}
        result.update(_distance_clustering(trades))
        result["stop_evidence"] = "cluster" if result.get("clustered") else "none"
    result["ribbon"] = _ribbon_statistics(trades)
    # A coordinated loss exit is useful behavioural evidence, but neither
    # proves a broker SL nor distinguishes manual exits, stop-out and grid
    # resets. Keep it separate from the existing direct/cluster proof flag.
    result["schutzsignatur"] = _synchronized_loss_exits(trades)
    return result


# ---------------------------------------------------------------- Stufe 1
def _exit_marker(comment: str) -> str | None:
    """Recognize explicit SL/TP markers, with an optional ticket suffix.

    Do not infer an exit reason from arbitrary prose mentioning a stop.
    """
    match = re.fullmatch(r"\[(sl|tp)\](?:\s+(?:ticket\s*)?#?\d+)?",
                         comment.strip(), flags=re.IGNORECASE)
    return match.group(1).lower() if match else None


def _orderbook_evidence(parsed: ParsedExport) -> dict:
    trades = parsed.trades
    with_sl = [t for t in trades if t.sl is not None and t.sl > 0]
    with_sl_tp = [t for t in trades if t.sl and t.tp]
    sl_exits = [t for t in trades if _exit_marker(t.comment) == "sl"]
    tp_exits = [t for t in trades if _exit_marker(t.comment) == "tp"]
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
        "positions_with_sl": len(with_sl),
        "positions_with_sl_pct": round(len(with_sl) / len(trades) * 100, 1) if trades else 0,
        "stop_evidence": ("direct" if trades and len(with_sl) == len(trades)
                          else "partial" if with_sl else "none"),
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
        "verdict": _orderbook_verdict(len(trades), len(with_sl_tp), len(sl_exits), len(with_sl)),
    }


def _orderbook_verdict(total: int, with_sl_tp: int, sl_exits: int,
                       with_sl: int | None = None) -> str:
    with_sl = with_sl_tp if with_sl is None else with_sl
    if total <= 0:
        return "kein SL im Orderbuch"
    if with_sl <= 0:
        return "kein SL im Orderbuch (kein Stop-Nachweis)"
    pct = with_sl / total * 100
    if with_sl == total and sl_exits > 0:
        return ("BEWIESEN: jede Position mit SL im Orderbuch; "
                "Stop-Ausloesungen rekonstruierbar")
    if with_sl == total:
        return (f"Orderbuch: {with_sl}/{total} Positionen mit SL-Feldern "
                "(keine [sl]-Ausfuehrungen im Export)")
    return (f"TEILWEISE: {with_sl}/{total} Positionen ({pct:.0f} %) mit SL "
            "im Orderbuch — kein vollstaendiger Stop-Nachweis")


# ---------------------------------------------------------------- Stufe 2
def _distance_bin(distance: float, symbol: str) -> float:
    """Symbolgerechte Rundung: Gold/Index 0.1, FX 1 Pip (nicht pauschal 0.1)."""
    if symbol_class(symbol) in ("METAL", "INDEX"):
        return round(distance, 1)
    if fx_pip_size(symbol) == 0.01:
        return round(distance, 2)   # 0.01 ≈ 1 Pip
    return round(distance, 4)       # 0.0001 ≈ 1 Pip (Majors)


def _distance_clustering(trades) -> dict:
    """Cluster je Symbol; Teilstichproben entlasten kein ganzes Signal."""
    by_sym: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        d = t.loss_distance()
        if d is not None:
            by_sym[normalize_symbol(t.symbol)].append(d)
    if not by_sym:
        return {"n_losses_with_distance": 0, "clustered": False,
                "verdict": "keine Verluste mit Preisdaten — SL nicht prüfbar (neutral)"}

    best: dict | None = None
    per_symbol: dict[str, dict] = {}
    all_dists: list[float] = []
    for sym in sorted(by_sym):
        dists = by_sym[sym]
        all_dists.extend(dists)
        n = len(dists)
        if n < MIN_CLUSTER_LOSSES:
            per_symbol[sym] = {"n": n, "clustered": False,
                               "reason": "zu wenige Verluste"}
            continue
        rounded = Counter(_distance_bin(d, sym) for d in dists)
        # File order cannot decide stop proof. Among equally frequent modes,
        # prefer the lower level; a tied zero bin must not be bypassed by a
        # positive bin that happened to appear first in the CSV.
        top_level, top_count = min(rounded.items(), key=lambda item: (-item[1], item[0]))
        top_share = top_count / n
        sorted_d = sorted(dists)
        spread = sorted_d[-1] / max(sorted_d[n // 2], 1e-9)
        cand = {
            "symbol": sym,
            "n": n,
            "top_level": top_level,
            "top_share": top_share,
            "spread": spread,
            "clustered": top_count >= MIN_CLUSTER_REPEATS and top_share >= 0.25 and top_level > 0,
            "free_running": top_share < 0.10 and spread >= 10.0,
            "dists": sorted_d,
        }
        per_symbol[sym] = {k: cand[k] for k in ("n", "clustered", "top_level", "top_share")}
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
            "per_symbol": per_symbol,
            "verdict": "zu wenige Verluste je Symbol fuer Cluster-Aussage — neutral",
        }

    n = best["n"]
    dists = best["dists"]
    # BEWUSST konservativ (F3, Review T1/2 29.09.): per_symbol enthaelt nur
    # Symbole mit Verlustbasis — faellt bei einem Symbol ein Verlust weg oder
    # hat es < MIN_CLUSTER_LOSSES Verluste, ist das Signal-Level-Urteil nie
    # "cluster". Das verwehrt nur Entlastung, erzeugt nie falsch-positive
    # Stops; Verhalten bewusst erhalten.
    traded_symbols = {normalize_symbol(t.symbol) for t in trades}
    clustered = (set(per_symbol) == traded_symbols
                 and all(item["clustered"] for item in per_symbol.values()))
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
        "per_symbol": per_symbol,
        "verdict": (
            f"Stop-Signatur ({best['symbol']}): {best['top_share']*100:.0f}% der "
            f"Verlustdistanzen bei {best['top_level']}"
            if clustered
            else ("Stop-Signatur nur in Teilstichproben — fuer das gesamte Signal neutral"
                  if any(item["clustered"] for item in per_symbol.values()) else
                  "Verlustdistanzen ohne Cluster — SL nicht uebertragen (neutral; KI schatzt aus dem Verhalten ab)"
                  if free_running else
                  "kein eindeutiges Stop-Niveau erkennbar — neutral")
        ),
    }


# ------------------------------------------------ Verhaltensbefund
def _synchronized_loss_exits(trades) -> dict:
    """Describe repeated loss exits without promoting them to SL proof.

    Inspect complete symbol windows before looking at PnL. Filtering losses
    first would turn a profitable grid basket with losing legs into apparent
    protection. Windows are anchored at the first close (no chaining). Exact
    duplicate rows cannot manufacture independent positions for this test;
    the actual engine's PnL and other evidence are unaffected here.
    """
    by_symbol: dict[str, list] = defaultdict(list)
    seen = set()
    duplicate_count = 0
    for trade in trades:
        identity = astuple(trade)
        if identity in seen:
            duplicate_count += 1
            continue
        seen.add(identity)
        by_symbol[normalize_symbol(trade.symbol)].append(trade)

    counts = dict(gruppen_gesamt=0, reine_verlustgruppen=0,
                  qualifizierte_verlustgruppen=0, gemischte_gruppen=0,
                  gemischte_netto_positive_gruppen=0,
                  gewinngruppen=0, null_gruppen=0, hedge_gruppen=0,
                  verlustpositionen=0, vollstaendige_symbol_schliessungen=0)
    days = set()
    examples = []
    qualifying_net = []
    for symbol in sorted(by_symbol):
        sequence = sorted(by_symbol[symbol], key=lambda t: (t.close_time, t.open_time,
                                                           t.direction, t.volume, t.profit))
        opens = sorted(t.open_time for t in sequence)
        closes = sorted(t.close_time for t in sequence)
        index = 0
        while index < len(sequence):
            start = sequence[index].close_time
            end = index + 1
            while (end < len(sequence)
                   and (sequence[end].close_time-start).total_seconds() <= SYNC_CLOSE_SECONDS):
                end += 1
            group = sequence[index:end]
            index = end
            if len(group) < 2:
                continue
            counts["gruppen_gesamt"] += 1
            nets = [t.net for t in group]
            if any(net < 0 for net in nets) and any(net > 0 for net in nets) and math.fsum(nets) > 0:
                counts["gemischte_netto_positive_gruppen"] += 1
            directions = {t.direction for t in group}
            if len(directions) > 1:
                counts["hedge_gruppen"] += 1
            if all(net < 0 for net in nets):
                counts["reine_verlustgruppen"] += 1
            elif all(net > 0 for net in nets):
                counts["gewinngruppen"] += 1
                continue
            elif any(net == 0 for net in nets):
                counts["null_gruppen"] += 1
                continue
            else:
                counts["gemischte_gruppen"] += 1
                continue
            # They must have coexisted BEFORE the first close and have the
            # same direction; alternating trades and hedges are not this
            # particular signature. Missing it still has no adverse meaning.
            if len(directions) != 1 or any(t.open_time >= start for t in group):
                continue
            counts["qualifizierte_verlustgruppen"] += 1
            counts["verlustpositionen"] += len(group)
            days.add(start.date().isoformat())
            net = math.fsum(nets)
            qualifying_net.append(net)
            active = bisect_left(opens, start) - bisect_left(closes, start)
            if active == len(group):
                counts["vollstaendige_symbol_schliessungen"] += 1
            distances = [d for t in group for d in [t.loss_distance()] if d is not None]
            examples.append({
                "symbol": symbol, "richtung": group[0].direction,
                "von": start.isoformat(sep=" "),
                "bis": group[-1].close_time.isoformat(sep=" "),
                "anzahl": len(group), "netto_usd": round(net, 2),
                "offene_symbol_positionen_vorher": active,
                "geschlossen_anteil_pct": round(len(group)/active*100, 1) if active else None,
                "lot_min": min(t.volume for t in group),
                "lot_max": max(t.volume for t in group),
                "verlustdistanz_min": min(distances) if distances else None,
                "verlustdistanz_max": max(distances) if distances else None,
            })

    n = counts["qualifizierte_verlustgruppen"]
    plausible = n >= MIN_PROTECTIVE_GROUPS and len(days) >= MIN_PROTECTIVE_DAYS
    status = "plausibel" if plausible else "hinweis" if n else "nicht_beobachtet"
    interpretation = (
        "Wiederholte koordinierte Nettoverlust-Exits: beobachtete "
        "Verlustbegrenzung macht einen internen Schutzmechanismus plausibel."
        if plausible else
        "Koordinierte Nettoverlust-Exits beobachtet; zu wenige unabhängige "
        "Ereignisse/Tage für eine wiederholte Schutzsignatur."
        if n else
        "Keine qualifizierte synchrone Verlustgruppe beobachtet; neutral, "
        "kein Nachweis fehlenden Stop-Schutzes.")
    return {
        "version": 1, "status": status, "plausibel": plausible,
        "fenster_sekunden": SYNC_CLOSE_SECONDS,
        "min_ereignisse": MIN_PROTECTIVE_GROUPS, "min_tage": MIN_PROTECTIVE_DAYS,
        **counts, "tage_mit_verlustgruppen": len(days),
        "exakte_duplikate_ignoriert": duplicate_count,
        "groesster_gruppenverlust_usd": round(min(qualifying_net), 2) if qualifying_net else None,
        # Bound prompt size; order by loss magnitude, then time, not CSV order.
        "beispiele": sorted(examples, key=lambda e: (e["netto_usd"], e["von"], e["symbol"]))[:5],
        "interpretation": interpretation,
        "grenzen": (
            "Heuristik, keine kalibrierte Wahrscheinlichkeit und kein SL-Beweis. "
            "Export enthält nur geschlossene Positionen; offene Restpositionen "
            "und Intratrade-Equity fehlen. Verlustgruppen können auch manuelle "
            "Exits, Grid-Resets oder Margin-Stop-outs sein. Gewinn-/gemischte "
            "Körbe belegen keinen Verluststopp. Ein niedriger historischer "
            "Equity-DD stützt die Risikobegrenzung, beweist weder SL noch "
            "künftige Verlustobergrenze. Stop-Evidenz, Risiko-Score und "
            "Drawdown-Schranke werden durch diese Signatur nicht geändert."),
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
        if t.profit < 0:
            # Verlustserie = konsekutive Verluste; Breakeven (profit == 0)
            # ist kein Verlust und unterbricht die Serie wie ein Gewinn
            # (F4, Review T1/2 29.09. — vorher zaehlte Breakeven als Verlust
            # und vergroesserte die Serie).
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
