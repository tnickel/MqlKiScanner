# -*- coding: utf-8 -*-
import csv, statistics
from datetime import datetime
from collections import defaultdict, Counter

rows = list(csv.reader(open("data/raw/gold_reaper_2265877_positions.csv", encoding="utf-8-sig"), delimiter=";"))
trades, bals = [], []
for r in rows[1:]:
    if r[1] in ("Buy", "Sell"):
        o = datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S"); c = datetime.strptime(r[6], "%Y.%m.%d %H:%M:%S")
        trades.append(dict(o=o, c=c, dir=r[1], vol=float(r[2]), ep=float(r[4]),
                           xp=float(r[7]), comm=float(r[8] or 0), swap=float(r[9] or 0), pnl=float(r[10])))
    elif r[1] == "Balance":
        bals.append((datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S"), float(r[10])))

print(f"Trades: {len(trades)}, {min(t['o'] for t in trades):%Y-%m-%d} bis {max(t['c'] for t in trades):%Y-%m-%d}")
net = sum(t["pnl"] + t["comm"] + t["swap"] for t in trades)
print(f"Netto: {net:.2f} | Gebuehren {sum(t['comm'] for t in trades):.2f} | Swaps {sum(t['swap'] for t in trades):.2f}")
wins = [t for t in trades if t["pnl"] > 0]; losses = [t for t in trades if t["pnl"] <= 0]
print(f"Winrate {len(wins)}/{len(trades)} = {len(wins)/len(trades)*100:.1f}% | AvgWin {statistics.mean(t['pnl'] for t in wins):.2f} | AvgLoss {statistics.mean(t['pnl'] for t in losses):.2f}")
durs = [(t["c"]-t["o"]).total_seconds()/3600 for t in trades]
print(f"Haltedauer h: median {statistics.median(durs):.2f}, avg {statistics.mean(durs):.1f}, max {max(durs):.0f}")

# SL-Analyse
ls = sorted(t["pnl"] for t in losses)
print(f"\nVerluste: Worst {ls[0]:.2f} | P10 {ls[len(ls)//10]:.2f} | Median {ls[len(ls)//2]:.2f}")
bins = Counter()
for p in ls:
    if p > -5: bins["0..-5"] += 1
    elif p > -15: bins["-5..-15"] += 1
    elif p > -30: bins["-15..-30"] += 1
    elif p > -50: bins["-30..-50"] += 1
    elif p > -75: bins["-50..-75"] += 1
    else: bins["< -75"] += 1
print("Verlust-Bins:", dict(bins))
dist = [(t["ep"]-t["xp"]) * (1 if t["dir"]=="Sell" else -1) for t in losses]
print(f"Verlustdistanz USD: min {min(dist):.2f}, max {max(dist):.2f}, median {statistics.median(dist):.2f}")
distw = [(t["xp"]-t["ep"]) * (1 if t["dir"]=="Buy" else -1) for t in wins]
print(f"Gewinndistanz USD: median {statistics.median(distw):.2f}, max {max(distw):.2f}")
# TP-Naehe: Gewinne auf feste Distanz?
wd = sorted(round(x,1) for x in distw)
print("Gewinn-Distanzen P25/P50/P75:", wd[len(wd)//4], wd[len(wd)//2], wd[3*len(wd)//4])

# Pyramiding vs Averaging: Lot-Korrelation mit Einstiegsposition im Korb
baskets = defaultdict(list)
for t in trades:
    baskets[t["o"].strftime("%Y%m%d%H%M")].append(t)  # Gruppierung nach Einstiegsminute
pyr = avg = 0
big_b = sorted(baskets.values(), key=len, reverse=True)
for b in big_b[:60]:
    b2 = sorted(b, key=lambda t: t["ep"])
    if len(b2) < 3: continue
    # Kursrichtung der Nachschiebe: Buys steigend = Pyramiding, fallend = Averaging
    rising = b2[-1]["ep"] > b2[0]["ep"]
    if b2[0]["dir"] == "Buy":
        pyr += 1 if rising else 0
        avg += 0 if rising else 1
    else:
        pyr += 1 if not rising else 0
        avg += 1 if rising else 0
print(f"\nVon {pyr+avg} Koerben (>=3 Beine): Pyramiding (mit dem Trend nachschieben) {pyr}, Averaging (gegen den Trend) {avg}")

# Lot-Progression: groessere Lots spaeter im Korb?
later_bigger = later_smaller = 0
for b in big_b:
    if len(b) < 3: continue
    b2 = sorted(b, key=lambda t: t["o"])
    if b2[-1]["vol"] > b2[0]["vol"]: later_bigger += 1
    elif b2[-1]["vol"] < b2[0]["vol"]: later_smaller += 1
print(f"Letztes Bein groesser: {later_bigger}, kleiner: {later_smaller}")

# Groeszter Korb
big = sorted(max(big_b, key=len), key=lambda t: t["o"])
print(f"\nGroesster Korb ({len(big)} Pos):")
for t in big:
    print(f"  {t['o']:%d.%m. %H:%M:%S} {t['dir']} {t['vol']:.2f} @ {t['ep']:.2f} -> {t['pnl']:+8.2f}")

# 0.04+ Trades: im Gewinn oder Verlust geoeffnet?
bigv = [t for t in trades if t["vol"] >= 0.04]
print(f"\nTrades mit >=0.04 Lots: {len(bigv)}, davon Gewinn: {sum(1 for t in bigv if t['pnl']>0)}, Ergebnis gesamt {sum(t['pnl'] for t in bigv):+.2f}")

# Stunden
hours = Counter(t["o"].hour for t in trades)
print("\nEinstiegsstunden Top10:", dict(sorted(hours.items(), key=lambda x: -x[1])[:10]))
wdays = Counter(t["o"].weekday() for t in trades)
print("Wochentage:", dict(sorted(wdays.items())))

# Monate + Drawdown-Rekonstruktion
monthly = defaultdict(float)
for t in trades:
    monthly[t["c"].strftime("%Y-%m")] += t["pnl"] + t["comm"] + t["swap"]
neg = [m for m, v in sorted(monthly.items()) if v < 0]
print("\nNegative Monate:", neg)
seq = sorted(trades, key=lambda t: t["c"])
bal, peak, maxdd, maxdd_pct, when = 1602.85, 1602.85, 0, 0, None
for t in seq:
    bal += t["pnl"] + t["comm"] + t["swap"]
    peak = max(peak, bal)
    dd = peak - bal
    if dd > maxdd: maxdd, maxdd_pct, when = dd, dd/peak*100, t["c"]
print(f"Max realisierter DD: {maxdd:.2f} USD = {maxdd_pct:.1f}% bei {when:%Y-%m-%d}")

worst10 = sorted(trades, key=lambda t: t["pnl"])[:8]
print("\nSchlechteste 8:")
for t in worst10:
    print(f"  {t['o']:%d.%m.%Y %H:%M} {t['dir']} {t['vol']:.2f} @ {t['ep']:.2f} -> {t['xp']:.2f} {t['pnl']:+8.2f} ({(t['c']-t['o']).total_seconds()/3600:.1f}h)")
best5 = sorted(trades, key=lambda t: -t["pnl"])[:5]
print("Beste 5:")
for t in best5:
    print(f"  {t['o']:%d.%m.%Y %H:%M} {t['dir']} {t['vol']:.2f} @ {t['ep']:.2f} -> {t['xp']:.2f} {t['pnl']:+8.2f} ({(t['c']-t['o']).total_seconds()/3600:.1f}h)")

# konsekutive Verluste
streak = maxstreak = 0
for t in seq:
    streak = streak + 1 if t["pnl"] <= 0 else 0
    maxstreak = max(maxstreak, streak)
print(f"Max konsekutive Verluste: {maxstreak}")
# schlechteste Tage
byday = defaultdict(lambda: [0, 0.0])
for t in trades:
    byday[t["o"].date().isoformat()][0] += 1
    byday[t["o"].date().isoformat()][1] += t["pnl"]
print("Schlechteste Tage:", [(d, round(v[1],1)) for d, v in sorted(byday.items(), key=lambda x: x[1][1])[:6]])
print("Beste Tage:", [(d, round(v[1],1)) for d, v in sorted(byday.items(), key=lambda x: -x[1][1])[:6]])
