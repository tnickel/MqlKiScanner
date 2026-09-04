# -*- coding: utf-8 -*-
import csv, json, statistics
from datetime import datetime
from collections import defaultdict, Counter

rows = list(csv.reader(open("data/raw/msc_gold_2231030_positions.csv", encoding="utf-8-sig"), delimiter=";"))
data = rows[1:]
trades, bals = [], []
for r in data:
    if r[1] in ("Buy", "Sell"):
        o = datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S")
        c = datetime.strptime(r[6], "%Y.%m.%d %H:%M:%S")
        trades.append(dict(o=o, c=c, dir=r[1], vol=float(r[2]), ep=float(r[4]),
                           xp=float(r[7]), comm=float(r[8] or 0), swap=float(r[9] or 0),
                           pnl=float(r[10])))
    elif r[1] == "Balance":
        bals.append((datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S"), float(r[10])))

print(f"Trades: {len(trades)}, Zeitspanne {min(t['o'] for t in trades):%Y-%m-%d} bis {max(t['c'] for t in trades):%Y-%m-%d}")
net = sum(t["pnl"] + t["comm"] + t["swap"] for t in trades)
print(f"Netto (inkl. Gebuehren): {net:.2f} USD | Gebuehren gesamt: {sum(t['comm'] for t in trades):.2f} | Swaps: {sum(t['swap'] for t in trades):.2f}")
wins = [t for t in trades if t["pnl"] > 0]; losses = [t for t in trades if t["pnl"] <= 0]
print(f"Winrate: {len(wins)}/{len(trades)} = {len(wins)/len(trades)*100:.1f}% | AvgWin {statistics.mean(t['pnl'] for t in wins):.2f} | AvgLoss {statistics.mean(t['pnl'] for t in losses):.2f}")

# Haltedauer
durs_h = [(t["c"]-t["o"]).total_seconds()/3600 for t in trades]
print(f"Haltedauer h: median {statistics.median(durs_h):.3f}, avg {statistics.mean(durs_h):.1f}, max {max(durs_h):.0f}, <60s: {sum(1 for d in durs_h if d*3600<60)} ({sum(1 for d in durs_h if d*3600<60)/len(durs_h)*100:.0f}%)")

# SL-Analyse: Verlustverteilung USD
ls = sorted(t["pnl"] for t in losses)
print(f"\nVerluste: Worst {ls[0]:.2f}, P5 {ls[len(ls)//20]:.2f}, P25 {ls[len(ls)//4]:.2f}, Median {ls[len(ls)//2]:.2f}")
bins = Counter()
for p in ls:
    if p > -1: bins["0 bis -1"] += 1
    elif p > -3: bins["-1 bis -3"] += 1
    elif p > -5: bins["-3 bis -5"] += 1
    elif p > -10: bins["-5 bis -10"] += 1
    elif p > -15: bins["-10 bis -15"] += 1
    else: bins["< -15"] += 1
print("Verlust-Bins:", dict(bins))
# Preis-Distanz der Verlierer
dist = [ (t["ep"]-t["xp"]) * (1 if t["dir"]=="Sell" else -1) for t in losses ]
print(f"Verlustdistanz USD Gold: min {min(dist):.2f}, max {max(dist):.2f}, median {statistics.median(dist):.2f}")

# Basket-Analyse: gleicher Exit-Zeitpunkt
baskets = defaultdict(list)
for t in trades:
    baskets[t["c"]].append(t)
b_list = sorted(baskets.values(), key=len, reverse=True)
multi = [b for b in b_list if len(b) >= 2]
print(f"\nBasket-Exits: {len(multi)} mit >=2 Positionen | davon >=4: {sum(1 for b in multi if len(b)>=4)} | groesstes: {len(b_list[0])} Positionen")
big = b_list[0]
for t in sorted(big, key=lambda t: t["o"]):
    print(f"  {t['o']:%Y.%m.%d %H:%M:%S} {t['dir']} {t['vol']:.2f} @ {t['ep']:.2f} -> {t['pnl']:+7.2f}")
print(f"  NETTO Korb: {sum(t['pnl'] for t in big):+.2f} USD")
# Anteil Trades in Multi-Baskets
in_multi = sum(len(b) for b in multi)
print(f"Trades in Multi-Baskets: {in_multi}/{len(trades)} = {in_multi/len(trades)*100:.0f}%")

# Lots: 0.02-Faelle
v02 = [t for t in trades if t["vol"] >= 0.02]
print(f"\n0.02-Lot-Trades: {len(v02)} ({len(v02)/len(trades)*100:.1f}%)")
for t in v02[:8]:
    print(f"  {t['o']:%Y.%m.%d} {t['dir']} {t['vol']} @ {t['ep']:.2f} pnl {t['pnl']:+.2f}")

# Stunden/Session-Muster
hours = Counter(t["o"].hour for t in trades)
print("\nEinstiegsstunden (Top 12):", dict(sorted(hours.items(), key=lambda x: -x[1])[:12]))
wd = Counter(t["o"].weekday() for t in trades)
print("Wochentage (0=Mo):", dict(sorted(wd.items())))

# Monatliche P/L
monthly = defaultdict(float)
for t in trades:
    monthly[t["o"].strftime("%Y-%m")] += t["pnl"] + t["comm"] + t["swap"]
neg_months = [m for m, v in sorted(monthly.items()) if v < 0]
print(f"\nMonate negativ: {neg_months}")
print("Monatssummen 2026:", {m: round(v,1) for m, v in sorted(monthly.items()) if m >= "2026-01"})

# Drawdown-Rekonstruktion (Balance-Kurve abgeschlossener Trades + Einlage/Abhebungen)
events = [(t["o"], 0, None) for t in trades]
seq = sorted(trades, key=lambda t: t["c"])
bal = 139.0
peak, maxdd, maxdd_pct, dd_when = bal, 0, 0, None
curve = []
for t in seq:
    bal += t["pnl"] + t["comm"] + t["swap"]
    for b in bals:
        if b[0] <= t["c"]:
            pass
    curve.append((t["c"], bal))
    if bal > peak: peak = bal
    dd = peak - bal
    if dd > maxdd: maxdd, maxdd_pct, maxdd_when = dd, dd/peak*100, t["c"]
print(f"\nMax Balance-DD (nur realisiert, ohne Abhebungen): {maxdd:.2f} USD = {maxdd_pct:.1f}% bei {maxdd_when:%Y-%m-%d}")

# Grosse Einzelverluste im Kontext
worst10 = sorted(trades, key=lambda t: t["pnl"])[:10]
print("\nSchlechteste 10 Trades:")
for t in worst10:
    print(f"  {t['o']:%Y.%m.%d %H:%M} {t['dir']} @ {t['ep']:.2f} exit {t['xp']:.2f} pnl {t['pnl']:+.2f} (Haltedauer {(t['c']-t['o']).total_seconds()/3600:.1f}h)")

# Beste Trades
best5 = sorted(trades, key=lambda t: -t["pnl"])[:5]
print("Beste 5:")
for t in best5:
    print(f"  {t['o']:%Y.%m.%d %H:%M} {t['dir']} @ {t['ep']:.2f} -> {t['xp']:.2f} pnl {t['pnl']:+.2f} ({(t['c']-t['o']).total_seconds()/3600:.1f}h)")

# Konsekutive Verluste in chronological Close-Reihenfolge
streak, maxstreak = 0, 0
for t in seq:
    streak = streak + 1 if t["pnl"] <= 0 else 0
    maxstreak = max(maxstreak, streak)
print(f"\nMax konsekutive Verluste (Chronologie): {maxstreak}")

json.dump({"monthly": dict(sorted(monthly.items()))}, open("monthly.json", "w"))
