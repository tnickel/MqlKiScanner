# -*- coding: utf-8 -*-
"""Forensik-Test 1: Martingale-Signatur (Spec: doc/03_forensik-tests.md).

Zwei Detektionskanaele:
1. Lot-Nachfolger-Test (Spec-Referenz): Lot(i+1)/Lot(i) nur bei nicht-
   ueberlappenden Nachfolgern; Median nach Verlust > 1,3 = Flag.
   (Referenz: scripts/reference/martingale_exposure_test.py, Test 1)
2. Korb-Leiter: Eskalierende Lot-Staffel innerhalb eines Basket-Exits
   (gleiches Symbol + Richtung, zwei aufeinanderfolgende Schritte >= 2x),
   wie sie bei FXtradings EURNZD-Korb 0,01 -> 0,02 -> 0,04 nachgewiesen
   wurde (doc/01). Der Nachfolger-Median verschluckt solche Koerbe.
"""
from __future__ import annotations

import statistics
from collections import defaultdict

from ..models import ParsedExport

MARTINGALE_FLAG_THRESHOLD = 1.3


def _successor_test(seq) -> dict:
    after_loss: list[float] = []
    after_win: list[float] = []
    for a, b in zip(seq, seq[1:]):
        if b.open_time > a.close_time:  # nicht parallel offen
            ratio = b.volume / max(a.volume, 1e-9)
            (after_loss if a.profit <= 0 else after_win).append(ratio)
    if not after_loss:
        return {"n_after_loss": 0}
    med_loss = statistics.median(after_loss)
    return {
        "n_after_loss": len(after_loss),
        "n_after_win": len(after_win),
        "median_ratio_after_loss": round(med_loss, 2),
        "mean_ratio_after_loss": round(statistics.mean(after_loss), 2),
        "median_ratio_after_win": round(statistics.median(after_win), 2) if after_win else None,
        "flag": med_loss > MARTINGALE_FLAG_THRESHOLD,
    }


def _basket_ladder_test(trades) -> dict:
    """Eskalierende Lot-Leitern in Basket-Exits: mindestens zwei UNMITTELBAR
    aufeinanderfolgende Verdopplungsschritte (klassischer 0,01->0,02->0,04-
    Korridor). Ein einziger Sprung oder nur nicht-benachbarte Spruenge
    reichen nicht — sonst feuert die Regel auf gewoehnliche Lot-Streuung
    (False Positive bei Pure Gold, das kein Martingale betreibt)."""
    by_exit: dict[tuple, list] = defaultdict(list)
    for t in trades:
        by_exit[(t.symbol, t.direction, t.close_time)].append(t)
    escalations: list[dict] = []
    for (sym, direction, close_time), basket in by_exit.items():
        if len(basket) < 3:
            continue
        legs = sorted(basket, key=lambda t: t.open_time)
        vols = [t.volume for t in legs]
        # Korridor-Martingale startet beim Minimum und verdoppelt dann zweimal
        # direkt hintereinander. Leiter, die mitten in groszen Lots beginnen
        # (Nachschieben mit gewachsenem Konto, Fall KiraCat), zaehlen nicht.
        if vols[0] > min(vols):
            continue
        for i in range(len(vols) - 2):
            if vols[i + 1] >= 2 * max(vols[i], 1e-9) and vols[i + 2] >= 2 * max(vols[i + 1], 1e-9):
                escalations.append({
                    "symbol": sym, "direction": direction,
                    "close": close_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "ladder": [f"{v:.2f}" for v in vols],
                    "net": round(sum(t.profit for t in legs), 2),
                })
                break
    return {
        "escalating_baskets": len(escalations),
        "examples": escalations[:3],
        "flag": bool(escalations),
    }


def run(parsed: ParsedExport) -> dict:
    seq = sorted(parsed.trades, key=lambda t: t.open_time)
    result: dict = {"test": "martingale", "threshold": MARTINGALE_FLAG_THRESHOLD}
    succ = _successor_test(seq)
    ladder = _basket_ladder_test(parsed.trades)
    result.update(succ)
    result["basket_ladder"] = ladder
    if not result.get("n_after_loss"):
        result.update({"flag": False, "note": "keine nicht-ueberlappenden Nachfolger"})
        return result
    result["flag"] = bool(succ["flag"] or ladder["flag"])
    result["evidence"] = [e for e, on in (
        (f"Nachfolger-Median nach Verlust {succ['median_ratio_after_loss']}x > "
         f"{MARTINGALE_FLAG_THRESHOLD}", succ["flag"]),
        (f"{ladder['escalating_baskets']} eskalierende Korb-Leitern "
         f"(z. B. {' -> '.join(ladder['examples'][0]['ladder'])} @ "
         f"{ladder['examples'][0]['symbol']})" if ladder["examples"] else "", ladder["flag"]),
    ) if on]
    result["interpretation"] = (
        "Martingale-Signatur (Lots eskalieren nach Verlusten)" if result["flag"]
        else "keine Martingale-Eskalation (Median nach Verlust <= 1,3x, keine Korb-Leiter)"
    )
    return result
