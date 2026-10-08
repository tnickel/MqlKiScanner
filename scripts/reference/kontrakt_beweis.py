# -*- coding: utf-8 -*-
"""Beweis-Rechner fuer Kontraktgroessen (Muster: Axi-Fall 05.10.):
size = Median(PnL / (Richtung x DeltaPreis x Lots)) je Symbol.
Rundungs-Kandidaten gegenueberstellen (1/10/25/50/100) und Streuung zeigen."""
import sys
from collections import defaultdict
from statistics import median

sys.path.insert(0, "src")
from mqlkiscanner.parser import load_export

DATEIEN = {
    1096166: ("data/trade_snapshots/4ca63341384d12b37af0674355ab94548f227a0a468dc3c168e70b566ac134da.csv", "the best one (vant)"),
    26170186: ("data/trade_snapshots/8bf18ec0c18da0180cac70f64dc85b42f71491d222339bda3c7024af66851a87.csv", "WallstreetInvest (robo)"),
    73009362: ("data/trade_snapshots/18addcce3a90d93f359dce6041207f519c7890686b5c1e30e6bc736ddc861681.csv", "Sonrch (robo)"),
    429464: ("data/trade_snapshots/5f9815ad4f6d0ab4ae91954af5ebba99d71a1f35cb490eae84c960398f8084cd.csv", "Spruce waveband (zulu)"),
    2358336: ("data/trade_snapshots/14e5f450f2862286083d1a34011e7d28b9ed4aeeb10eeed96fa84c60dbab85b4.csv", "SCR EURAUD (mql5)"),
    2368681: ("data/trade_snapshots/76d0902a30f54f177e880e76e11bc3a603a2fb1d4f2a828ac0b4a6a36abadb1a.csv", "BTC One Shot (mql5)"),
    2332746: ("data/trade_snapshots/ba87df332050ad0822af5888dd52ac46a35decea0fc3ceaf26c923fb11f10f35.csv", "Lunar Express (mql5)"),
    21411352: ("data/trade_snapshots/a2fccbf3b460477aa856f1d37d3d05219ed2c2bc800841ca0f49907a9c82472d.csv", "FinancialFreedomFX (robo)"),
}

for sid, (pfad, name) in DATEIEN.items():
    print(f"\n=== #{sid} {name} ===")
    try:
        parsed = load_export(pfad)
    except Exception as e:
        print("  Parser-Fehler:", str(e)[:160])
        continue
    je_symbol = defaultdict(list)
    for t in parsed.trades:
        delta = t.exit_price - t.entry_price
        if t.entry_price and delta and t.volume:
            richtung = 1.0 if t.direction.lower() == "buy" else -1.0
            je_symbol[t.symbol.strip().upper()].append(
                t.net / (richtung * delta * t.volume))
    for symbol, werte in sorted(je_symbol.items()):
        werte.sort()
        med = median(werte)
        n = len(werte)
        # Streuung: 25./75.-Perzentil relativ
        p25, p75 = werte[n // 4], werte[(3 * n) // 4]
        streu = f"{p25:.3f}…{p75:.3f}" if n >= 4 else f"n={n}"
        kandidat = min((1, 10, 25, 50, 100, 1000),
                       key=lambda k: abs(med - k))
        print(f"  {symbol:<14} n={n:4d} Median={med:9.3f} ({streu}) ~ {kandidat}")
