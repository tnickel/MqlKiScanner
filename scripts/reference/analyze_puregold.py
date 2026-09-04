# -*- coding: utf-8 -*-
import csv, statistics
from datetime import datetime
from collections import defaultdict, Counter

def num(x):
    x = x.replace(" ", "").replace("\xa0", "")
    return float(x) if x else None

rows = list(csv.reader(open("data/raw/puregold_2362868_positions.csv", encoding="utf-8-sig"), delimiter=";"))
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
print(f"Winrate: {len(wins)}/{len(trades)} = {len(wins)/len(trades)*100:.1f}% | AvgWin {statistics.mean(t['pnl'] for t in wins):+.2f} | AvgLoss {statistics.mean(t['pnl'] for t in losses):+.2f} | Netto {net:+.2f}")
durs = [(t["c"]-t["o"]).total_seconds()/3600 for t in trades]
print(f"Haltedauer h: median {statistics.median(durs):.2f}, max {max(durs):.0f}")
lots = Counter(t["vol"] for t in trades)
print("Lots:", dict(sorted(lots.items())))

ls = sorted(t["pnl"] for t in losses)
print(f"\nVerluste: n={len(ls)}, Worst {ls[0]:.2f}, Median {ls[len(ls)//2]:.2f}")

seq = sorted(trades, key=lambda t: t["c"])
streak = maxstreak = 0; cur = []; worst_streak = []
for t in seq:
    if t["pnl"] <= 0:
        streak += 1; cur.append(t)
        if streak > maxstreak: maxstreak, worst_streak = streak, list(cur)
    else:
        streak = 0; cur = []
print(f"Laengste Verlustserie: {maxstreak} Trades, {sum(t['pnl'] for t in worst_streak):+.2f} USD, Zeitraum {worst_streak[0]['o']:%d.%m.} bis {worst_streak[-1]['c']:%d.%m.%Y}")

monthly = defaultdict(float)
for t in trades:
    monthly[t["c"].strftime("%Y-%m")] += t["pnl"] + t["comm"] + t["swap"]
print("\nMonate:", {m: round(v,1) for m, v in sorted(monthly.items())})
print("Negative Monate:", [m for m, v in sorted(monthly.items()) if v < 0])

# Groesste Verlusttage + Gaben die Anlaesse?
byday = defaultdict(float)
cnt_day = Counter(t["o"].date().isoformat() for t in trades)
for t in trades: byday[t["o"].date().isoformat()] += t["pnl"]
worst_days = sorted(byday.items(), key=lambda x: x[1])[:5]
print("\nSchlechteste Tage:", [(d, round(v,1)) for d, v in worst_days])

# Lots ueber Zeit: Eskalation?
t0 = min(t["o"] for t in trades)
early = [t["vol"] for t in trades if (t["o"]-t0).days < 45]
late = [t["vol"] for t in trades if (t["o"]-t0).days >= 90]
print(f"\nLot-Median frueh: {statistics.median(early):.2f}, spaet: {statistics.median(late):.2f} (Eskalation?)")

# DD-Rekonstruktion ohne Ein-/Auszahlungen, Start = erste Einzahlungssumme vor erstem Trade
dep = sum(v for _, v in sorted(bals) if v > 0)
bal = peak = max(dep, 100.0)
maxdd, maxdd_pct, when = 0.0, 0.0, None
for t in seq:
    bal += t["pnl"] + t["comm"] + t["swap"]
    peak = max(peak, bal)
    if peak - bal > maxdd:
        maxdd, maxdd_pct, when = peak - bal, (peak - bal) / peak * 100, t["c"]
print(f"\nTrading-DD (Start {max(dep,100):.0f}): -{maxdd:.2f} = {maxdd_pct:.1f}% bei {when:%Y-%m-%d}")

# Was passierte im DD-Zeitraum?
dd_trades = [t for t in seq if abs((t["c"]-when).days) <= 12]
if dd_trades:
    print("Um den DD-Tag:", [(f"{t['o']:%d.%m.}", t['sym'], f"{t['vol']:.2f}", f"{t['pnl']:+.0f}") for t in dd_trades[:14]])
