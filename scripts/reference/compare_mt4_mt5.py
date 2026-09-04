# -*- coding: utf-8 -*-
import csv, statistics
from datetime import datetime, timedelta
from collections import defaultdict

def num(x):
    x = x.replace(" ", "").replace("\xa0", "")
    return float(x) if x else None

def parse(s): return datetime.strptime(s, "%Y.%m.%d %H:%M:%S")

def load(path, mt4fmt):
    rows = list(csv.reader(open(path, encoding="utf-8-sig"), delimiter=";"))
    fills = []
    for r in rows[1:]:
        if r[1] in ("Buy", "Sell"):
            if mt4fmt:
                fills.append(dict(ot=parse(r[0]), dir=r[1], vol=float(r[2]), ep=num(r[4]),
                                  ct=r[7], xp=num(r[8]), comm=float(r[9] or 0), swap=float(r[10] or 0),
                                  pnl=float(r[11] or 0), comment=(r[12] if len(r) > 12 else "").strip()))
            else:
                fills.append(dict(ot=parse(r[0]), dir=r[1], vol=float(r[2]), ep=num(r[4]),
                                  ct=r[6], xp=num(r[7]), comm=float(r[8] or 0), swap=float(r[9] or 0),
                                  pnl=float(r[10] or 0), comment=""))
    return fills

mt4 = [t for t in load("data/raw/gold_spike_mt4_2349227_ORDERBOOK.csv", True) if t["ot"] >= datetime(2026, 5, 24)]
mt5 = load("data/raw/gold_spike_mt5_2375480_positions.csv", False)
print(f"MT4 im Fenster: {len(mt4)} | MT5: {len(mt5)}")

# Stufe 1: exakte Sekunde + Richtung, paarung nach Einstiegspreis
used5 = set()
pairs = []
q5 = defaultdict(list)
for i, t in enumerate(mt5): q5[(t["ot"], t["dir"])].append((i, t))
for t4 in mt4:
    cand = q5.get((t4["ot"], t4["dir"]), [])
    best = None
    for i, t5 in cand:
        if i in used5: continue
        d = abs(t4["ep"] - t5["ep"])
        if best is None or d < best[0]: best = (d, i, t5)
    if best and best[0] <= 3.0:
        used5.add(best[1]); pairs.append((t4, best[2]))
    else:
        pairs.append((t4, None))

# Stufe 2: fuer unpaarierte MT4 +-3 Sekunden fuzzy
from datetime import timedelta
mt5_sorted = sorted([(i, t) for i, t in enumerate(mt5) if i not in used5], key=lambda x: x[1]["ot"])
def fuzzy(t4):
    for i, t5 in mt5_sorted:
        if i in used5: continue
        if t5["dir"] != t4["dir"]: continue
        dt = abs((t5["ot"] - t4["ot"]).total_seconds())
        if dt <= 3 and abs(t5["ep"] - t4["ep"]) <= 3.0:
            used5.add(i); return t5
    return None

pairs = [(t4, (t5 or fuzzy(t4))) for t4, t5 in pairs]
matched = [(a, b) for a, b in pairs if b]
only4 = [a for a, b in pairs if not b]
only5 = [t for i, t in enumerate(mt5) if i not in used5]

print(f"\nGematcht (inkl. +-3s): {len(matched)} von {len(mt4)} MT4-Trades ({len(matched)/len(mt4)*100:.0f} %)")
print(f"Nur MT4: {len(only4)} | Nur MT5: {len(only5)}")

entryd = [abs(a["ep"] - b["ep"]) for a, b in matched]
pdiff = [a["pnl"] - b["pnl"] for a, b in matched]
print(f"Einstiegs-Differenz: median {statistics.median(entryd):.2f}, max {max(entryd):.2f} USD")
print(f"Ergebnis-Differenz: median {statistics.median(pdiff):+.2f}, Summe {sum(pdiff):+.2f} USD")
big = sorted(matched, key=lambda m: -abs(m[0]['pnl'] - m[1]['pnl']))[:6]
print("Groesste Abweichungen (nach Preis-Paarung):")
for a, b in big:
    print(f"  {a['ot']:%d.%m. %H:%M:%S} {a['dir']} lots {a['vol']:.2f}/{b['vol']:.2f}: MT4 {a['pnl']:+8.2f} vs MT5 {b['pnl']:+8.2f} (Diff {a['pnl']-b['pnl']:+7.2f})")

lotd = [(a, b) for a, b in matched if abs(a["vol"] - b["vol"]) > 1e-9]
print(f"\nLot-Abweichungen: {len(lotd)}")
for a, b in lotd:
    print(f"  {a['ot']:%d.%m. %H:%M:%S} {a['dir']}: MT4 {a['vol']:.2f} vs MT5 {b['vol']:.2f} Lot")

# nur-MT4 / nur-MT5 mit Zeit
print("\nNur in MT4 (MT5 hat den Trade NICHT):")
for t in only4:
    print(f"  {t['ot']:%d.%m.%Y %H:%M:%S} {t['dir']} {t['vol']:.2f} @ {t['ep']:.2f} {t['pnl']:+8.2f}")
print("Nur in MT5:")
for t in only5:
    print(f"  {t['ot']:%d.%m.%Y %H:%M:%S} {t['dir']} {t['vol']:.2f} @ {t['ep']:.2f} {t['pnl']:+8.2f}")
