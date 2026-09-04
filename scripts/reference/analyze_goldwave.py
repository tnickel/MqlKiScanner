# -*- coding: utf-8 -*-
import csv, statistics
from datetime import datetime
from collections import defaultdict, Counter

def num(x):
    x = x.replace(" ", "").replace("\xa0", "")
    return float(x) if x else None

rows = list(csv.reader(open("data/raw/goldwave_2339082_positions.csv", encoding="utf-8-sig"), delimiter=";"))
trades, bals = [], []
for r in rows[1:]:
    if r[1] in ("Buy", "Sell"):
        o = datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S"); c = datetime.strptime(r[6], "%Y.%m.%d %H:%M:%S")
        trades.append(dict(o=o, c=c, dir=r[1], vol=float(r[2]), sym=r[3], ep=num(r[4]),
                           xp=num(r[7]), comm=float(r[8] or 0), swap=float(r[9] or 0), pnl=float(r[10] or 0)))
    elif r[1] == "Balance":
        bals.append((datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S"), float(r[10].replace(" ", ""))))

print(f"Trades: {len(trades)} | Kontobewegungen: {len(bals)}")
for b in sorted(bals): print("  Balance:", b[0].date(), f"{b[1]:+.2f}")
net = sum(t["pnl"] + t["comm"] + t["swap"] for t in trades)
print(f"Netto: {net:.2f} | Komm: {sum(t['comm'] for t in trades):.2f} | Swap: {sum(t['swap'] for t in trades):.2f}")
wins = [t for t in trades if t["pnl"] > 0]; losses = [t for t in trades if t["pnl"] <= 0]
print(f"Winrate: {len(wins)}/{len(trades)} = {len(wins)/len(trades)*100:.1f}% | AvgWin {statistics.mean(t['pnl'] for t in wins):.2f} | AvgLoss {statistics.mean(t['pnl'] for t in losses):.2f}")
durs = [(t["c"]-t["o"]).total_seconds()/3600 for t in trades]
print(f"Haltedauer h: median {statistics.median(durs):.2f}, avg {statistics.mean(durs):.1f}, max {max(durs):.0f}")

# Verlustverteilung
ls = sorted(t["pnl"] for t in losses)
print(f"\nVerluste: n={len(ls)}, Worst {ls[0]:.2f}, P25 {ls[len(ls)//4]:.2f}, Median {ls[len(ls)//2]:.2f}")
bins = Counter()
for p in ls:
    if p > -5: bins["0..-5"] += 1
    elif p > -15: bins["-5..-15"] += 1
    elif p > -30: bins["-15..-30"] += 1
    else: bins["<-30"] += 1
print("Verlust-Bins:", dict(bins))
worst8 = sorted(trades, key=lambda t: t["pnl"])[:8]
print("Schlechteste 8:")
for t in worst8:
    print(f"  {t['o']:%d.%m.%Y %H:%M} {t['dir']} {t['vol']:.2f} @ {t['ep']:.2f} -> {t['xp']:.2f} {t['pnl']:+8.2f} ({(t['c']-t['o']).total_seconds()/3600:.1f}h)")

# Grid-Cluster: gleichzeitige Exits
baskets = defaultdict(list)
for t in trades:
    baskets[t["c"].strftime("%Y%m%d%H%M%S")].append(t)
multi = [b for b in baskets.values() if len(b) >= 2]
in_multi = sum(len(b) for b in multi)
print(f"\nBasket-Exits >=2: {len(multi)} | Trades darin: {in_multi} ({in_multi/len(trades)*100:.0f}%)")
big = sorted(multi, key=len, reverse=True)[:1]
if big:
    for t in sorted(big[0], key=lambda t: t["o"]):
        print(f"  {t['o']:%d.%m. %H:%M:%S} {t['dir']} {t['vol']:.2f} @ {t['ep']:.2f} -> {t['pnl']:+7.2f}")
    print(f"  NETTO: {sum(t['pnl'] for t in big[0]):+.2f}")

# Lots
lots = Counter(t["vol"] for t in trades)
print("\nLots:", dict(sorted(lots.items())))

# 95%-Winrate-Check: Gewinne klein, Verluste groesser?
print(f"Median-Gewinn: {statistics.median(t['pnl'] for t in wins):.2f} | Median-Verlust: {statistics.median(t['pnl'] for t in losses):.2f}")

# Stunden + Monat
hours = Counter(t["o"].hour for t in trades)
print("\nEinstiegsstunden:", dict(sorted(hours.items(), key=lambda x: -x[1])[:8]))
monthly = defaultdict(float)
for t in trades:
    monthly[t["c"].strftime("%Y-%m")] += t["pnl"] + t["comm"] + t["swap"]
print("Monate:", {m: round(v,1) for m, v in sorted(monthly.items())})
neg = [m for m, v in sorted(monthly.items()) if v < 0]
print("Negative Monate:", neg)

# DD-Rekonstruktion (ohne Ein-/Auszahlungen, Start = initiale Einlage laut Plattform)
seq = sorted(trades, key=lambda t: t["c"])
print("\nAlle Kontobewegungen (geordnet):", [(b[0].strftime("%y-%m-%d"), b[1]) for b in sorted(bals)])
start = 95.0  # wird unten ausgegeben; Plattform: Initial Deposit unbekannt hier -> schaetzen wir aus Flows
flows = sum(v for _, v in bals)
print(f"Summe Flows: {flows:.2f}")
# virtueller Start: Endbalance = 138.47? unbekannt; wir nehmen Start=100 Basis und rechnen DD in USD und relativ
bal = peak = 100.0
maxdd, maxdd_pct, when = 0.0, 0.0, None
for t in seq:
    bal += t["pnl"] + t["comm"] + t["swap"]
    peak = max(peak, bal)
    if peak - bal > maxdd:
        maxdd, maxdd_pct, when = peak - bal, (peak - bal) / peak * 100, t["c"]
print(f"Trading-DD (Basis 100): -{maxdd:.2f} = {maxdd_pct:.1f}% bei {when:%Y-%m-%d}")
streak = maxstreak = 0
for t in seq:
    streak = streak + 1 if t["pnl"] <= 0 else 0
    maxstreak = max(maxstreak, streak)
print(f"Max konsekutive Verluste: {maxstreak}")
byday = defaultdict(lambda: [0, 0.0])
for t in trades:
    byday[t["o"].date().isoformat()][0] += 1
    byday[t["o"].date().isoformat()][1] += t["pnl"]
print("Schlechteste Tage:", [(d, round(v[1],1)) for d, v in sorted(byday.items(), key=lambda x: x[1][1])[:5]])
