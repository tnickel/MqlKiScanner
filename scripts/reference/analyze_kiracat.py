# -*- coding: utf-8 -*-
import csv, statistics
from datetime import datetime
from collections import defaultdict, Counter

def num(x):
    x = x.replace(" ", "").replace("\xa0", "")
    return float(x) if x else None

rows = list(csv.reader(open("data/raw/kiracat_2342895_positions.csv", encoding="utf-8-sig"), delimiter=";"))
trades, bals = [], []
for r in rows[1:]:
    if r[1] in ("Buy", "Sell"):
        o = datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S"); c = datetime.strptime(r[6], "%Y.%m.%d %H:%M:%S")
        trades.append(dict(o=o, c=c, dir=r[1], vol=float(r[2]), sym=r[3], ep=num(r[4]),
                           xp=num(r[7]), comm=float(r[8] or 0), swap=float(r[9] or 0), pnl=float(r[10] or 0)))
    else:
        bals.append((datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S"), float(r[10].replace(" ", ""))))

print(f"Trades: {len(trades)} | Kontobewegungen: {len(bals)}")
net = sum(t["pnl"] + t["comm"] + t["swap"] for t in trades)
print(f"Netto: {net:.2f} | Kommission: {sum(t['comm'] for t in trades):.2f} | Swaps: {sum(t['swap'] for t in trades):.2f}")
wins = [t for t in trades if t["pnl"] > 0]; losses = [t for t in trades if t["pnl"] <= 0]
print(f"Winrate: {len(wins)}/{len(trades)} = {len(wins)/len(trades)*100:.1f}% | AvgWin {statistics.mean(t['pnl'] for t in wins):.2f} | AvgLoss {statistics.mean(t['pnl'] for t in losses):.2f}")

# Verlustverteilung
ls = sorted(t["pnl"] for t in losses)
print(f"\nVerluste: Worst {ls[0]:.2f} | P10 {ls[len(ls)//10]:.2f} | Median {ls[len(ls)//2]:.2f}")
bins = Counter()
for p in ls:
    if p > -10: bins["0..-10"] += 1
    elif p > -50: bins["-10..-50"] += 1
    elif p > -150: bins["-50..-150"] += 1
    elif p > -400: bins["-150..-400"] += 1
    else: bins["< -400"] += 1
print("Verlust-Bins:", dict(bins))
worst8 = sorted(trades, key=lambda t: t["pnl"])[:8]
print("Schlechteste 8:")
for t in worst8:
    print(f"  {t['o']:%d.%m.%Y %H:%M} {t['dir']} {t['vol']:.2f} {t['sym']} @ {t['ep']} -> {t['pnl']:+9.2f} ({(t['c']-t['o']).total_seconds()/3600:.1f}h)")

# Zwei-Strategien-Split: US30 vs NZDCAD
for sym in ("US30", "NZDCAD"):
    sub = [t for t in trades if t["sym"] == sym]
    if not sub: continue
    w = [t for t in sub if t["pnl"] > 0]
    durs = [(t["c"]-t["o"]).total_seconds()/3600 for t in sub]
    print(f"\n{sym}: {len(sub)} Trades | Netto {sum(t['pnl']+t['comm']+t['swap'] for t in sub):+.2f} | Win {len(w)/len(sub)*100:.0f}% | Lots {min(t['vol'] for t in sub):.2f}-{max(t['vol'] for t in sub):.2f} | Haltedauer median {statistics.median(durs):.1f}h")

# Lots: grosse Positionen im Gewinn oder Verlust?
big = [t for t in trades if t["vol"] >= 1.0]
print(f"\nTrades >=1.0 Lot: {len(big)}, Netto {sum(t['pnl'] for t in big):+.2f}, Gewinner {sum(1 for t in big if t['pnl']>0)}")
# Volumen-Eskalation am 03.03.2026
mar3 = sorted([t for t in trades if t["o"].strftime("%Y-%m-%d") in ("2026-03-02","2026-03-03","2026-03-04","2026-03-05")], key=lambda t: t["o"])
print("\nEreignis 02.-05.03.2026:")
for t in mar3:
    print(f"  {t['o']:%d.%m. %H:%M} {t['dir']} {t['vol']:5.2f} {t['sym']} @ {t['ep']:.2f} -> {t['pnl']:+9.2f} ({(t['c']-t['o']).total_seconds()/3600:.1f}h)")

# Feb-27-Cluster
f27 = sorted([t for t in trades if t["o"].strftime("%Y-%m-%d") == "2026-02-27"], key=lambda t: t["o"])
print("\n27.02.2026 (Crash-Tag):")
for t in f27:
    print(f"  {t['o']:%H:%M} {t['dir']} {t['vol']:.2f} {t['sym']} @ {t['ep']:.1f} -> {t['pnl']:+8.2f}")

# Baskets: gleicher Exit-Zeitpunkt
baskets = defaultdict(list)
for t in trades:
    baskets[t["c"].strftime("%Y%m%d%H%M%S")].append(t)
multi = [b for b in baskets.values() if len(b) >= 3]
in_multi = sum(len(b) for b in multi)
print(f"\nBasket-Exits >=3 Pos: {len(multi)} | Trades darin: {in_multi} ({in_multi/len(trades)*100:.0f}%)")
nz_baskets = sorted([b for b in multi if b[0]["sym"] == "NZDCAD"], key=len, reverse=True)
if nz_baskets:
    b = sorted(nz_baskets[0], key=lambda t: t["o"])
    print(f"Groesster NZDCAD-Korb ({len(b)} Pos):")
    for t in b:
        print(f"  {t['o']:%d.%m.%Y %H:%M} {t['dir']} {t['vol']:.2f} @ {t['ep']:.5f} -> {t['pnl']:+8.2f}")
    print(f"  NETTO: {sum(t['pnl'] for t in b):+.2f}")

# Stunden + Wochentage
hours = Counter(t["o"].hour for t in trades)
print("\nEinstiegsstunden Top8:", dict(sorted(hours.items(), key=lambda x: -x[1])[:8]))
wd = Counter(t["o"].weekday() for t in trades)
print("Wochentage:", dict(sorted(wd.items())))

# Monate
monthly = defaultdict(float)
for t in trades:
    monthly[t["c"].strftime("%Y-%m")] += t["pnl"] + t["comm"] + t["swap"]
neg = [m for m, v in sorted(monthly.items()) if v < 0]
print("\nMonate (CSV):", {m: round(v,1) for m, v in sorted(monthly.items())})
print("Negative Monate:", neg)

# DD-Rekonstruktion: virtuelles Konto ohne Ein-/Auszahlungen (Basis = erste Einzahlung 9535.48)
seq = sorted(trades, key=lambda t: t["c"])
bal = peak = 9535.48
maxdd, maxdd_pct, when = 0.0, 0.0, None
for t in seq:
    bal += t["pnl"] + t["comm"] + t["swap"]
    peak = max(peak, bal)
    if peak - bal > maxdd:
        maxdd, maxdd_pct, when = peak - bal, (peak - bal) / peak * 100, t["c"]
print(f"\nMax Trading-DD (virtuell, ohne Zufluesse): {maxdd:.2f} USD = {maxdd_pct:.1f}% bei {when:%Y-%m-%d}")
print(f"Virtuelle Endbalance: 9535.48 + {net:.2f} = {9535.48+net:.2f}")
# reale Balance aus allen Flows
flows = sum(v for _, v in bals)
print(f"Real: 9535.48 + Flows ({flows:.2f}) + Netto = {9535.48 + flows + net:.2f} (Plattform: 1 000.00)")

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
print("Beste Tage:", [(d, round(v[1],1)) for d, v in sorted(byday.items(), key=lambda x: -x[1][1])[:5]])
