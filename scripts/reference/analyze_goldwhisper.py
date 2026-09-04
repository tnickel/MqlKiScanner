# -*- coding: utf-8 -*-
import csv, statistics
from datetime import datetime
from collections import defaultdict, Counter

def num(x):
    x = x.replace(" ", "").replace("\xa0", "")
    return float(x) if x else None

rows = list(csv.reader(open("data/raw/goldwhisper_2364821_positions.csv", encoding="utf-8-sig"), delimiter=";"))
trades, bals = [], []
for r in rows[1:]:
    if len(r) < 11: continue
    if r[1] in ("Buy", "Sell"):
        o = datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S"); c = datetime.strptime(r[6], "%Y.%m.%d %H:%M:%S")
        trades.append(dict(o=o, c=c, dir=r[1], vol=float(r[2]), sym=r[3], ep=num(r[4]),
                           xp=num(r[7]), comm=float(r[8] or 0), swap=float(r[9] or 0), pnl=float(r[10] or 0)))
    elif r[1] == "Balance":
        bals.append((datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S"), float(r[10].replace(" ", ""))))

print(f"Trades: {len(trades)} | Symbole: {dict(Counter(t['sym'] for t in trades))}")
print(f"Zeitraum: {min(t['o'] for t in trades):%Y-%m-%d} bis {max(t['c'] for t in trades):%Y-%m-%d}")
print("Kontobewegungen:", [(b[0].strftime('%y-%m-%d'), b[1]) for b in sorted(bals)])
net = sum(t["pnl"] + t["comm"] + t["swap"] for t in trades)
wins = [t for t in trades if t["pnl"] > 0]; losses = [t for t in trades if t["pnl"] <= 0]
print(f"Winrate: {len(wins)}/{len(trades)} = {len(wins)/len(trades)*100:.1f}%")
print(f"AvgWin {statistics.mean(t['pnl'] for t in wins):+.2f} | AvgLoss {statistics.mean(t['pnl'] for t in losses):+.2f} | Netto sichtbar: {net:+.2f}")
durs = [(t["c"]-t["o"]).total_seconds()/60 for t in trades]
print(f"Haltedauer min: median {statistics.median(durs):.0f}, max {max(durs)/60:.0f}h")

lots = Counter(t["vol"] for t in trades)
print("\nLot-Verteilung:", dict(sorted(lots.items())))

ls = sorted(t["pnl"] for t in losses)
print(f"\nVerluste: n={len(ls)}, Worst {ls[0]:.2f}, Median {ls[len(ls)//2]:.2f}")
print(f"Gewinne: Median {statistics.median(t['pnl'] for t in wins):+.2f}, Top5: {[round(x,1) for x in sorted((t['pnl'] for t in wins), reverse=True)[:5]]}")
gw = sum(t["pnl"] for t in wins); top5 = sum(sorted((t["pnl"] for t in wins), reverse=True)[:5])
print(f"Top-5-Gewinner-Anteil am Bruttogewinn: {top5/gw*100:.0f}%")

seq = sorted(trades, key=lambda t: t["c"])
streak = maxstreak = 0; cur = []; worst_streak = []
for t in seq:
    if t["pnl"] <= 0:
        streak += 1; cur.append(t)
        if streak > maxstreak: maxstreak, worst_streak = streak, list(cur)
    else:
        streak = 0; cur = []
print(f"\nLaengste Verlustserie: {maxstreak} Trades, Summe {sum(t['pnl'] for t in worst_streak):+.2f} USD")
if worst_streak:
    print(f"  Zeitraum: {worst_streak[0]['o']:%d.%m.%Y} bis {worst_streak[-1]['c']:%d.%m.%Y}")

monthly = defaultdict(float)
for t in trades:
    monthly[t["c"].strftime("%Y-%m")] += t["pnl"] + t["comm"] + t["swap"]
print("\nMonate:", {m: round(v,1) for m, v in sorted(monthly.items())})
print("Negative Monate:", [m for m, v in sorted(monthly.items()) if v < 0])

byday = Counter(t["o"].date().isoformat() for t in trades)
print("\nAktivste Tage:", byday.most_common(5))
per_day = list(byday.values())
per_day.sort()
print(f"Trades/Tag: median {per_day[len(per_day)//2]}, max {per_day[-1]}, Tage ueber 30 Trades: {sum(1 for x in per_day if x > 30)}")
hours = Counter(t["o"].hour for t in trades)
print("Einstiegsstunden Top6:", dict(sorted(hours.items(), key=lambda x: -x[1])[:6]))

# Baskets
baskets = defaultdict(list)
for t in trades:
    baskets[t["c"].strftime("%Y%m%d%H%M")].append(t)
multi = [b for b in baskets.values() if len(b) >= 3]
print(f"Cluster >=3 Fills pro Minute: {len(multi)}, groesster: {max((len(b) for b in multi), default=0)}")

# DD Rekonstruktion (Basis 100)
bal = peak = 100.0
maxdd, maxdd_pct, when = 0.0, 0.0, None
for t in seq:
    bal += t["pnl"] + t["comm"] + t["swap"]
    peak = max(peak, bal)
    if peak - bal > maxdd:
        maxdd, maxdd_pct, when = peak - bal, (peak - bal) / peak * 100, t["c"]
print(f"\nTrading-DD (Basis 100): -{maxdd:.2f} = {maxdd_pct:.1f}% bei {when:%Y-%m-%d}")
