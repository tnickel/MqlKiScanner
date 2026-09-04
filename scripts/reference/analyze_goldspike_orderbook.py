# -*- coding: utf-8 -*-
import csv, statistics
from datetime import datetime
from collections import defaultdict, Counter

def num(x):
    x = x.replace(" ", "").replace("\xa0", "")
    return float(x) if x else None

rows = list(csv.reader(open("data/raw/gold_spike_mt4_2349227_ORDERBOOK.csv", encoding="utf-8-sig"), delimiter=";"))
filled, pend, bals = [], [], []
for r in rows[1:]:
    typ = r[1]
    if typ in ("Buy", "Sell"):
        o = datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S")
        c = datetime.strptime(r[7], "%Y.%m.%d %H:%M:%S")
        filled.append(dict(o=o, c=c, dir=typ, vol=float(r[2]), ep=num(r[4]),
                           sl=num(r[5]), tp=num(r[6]), xp=num(r[8]),
                           comm=float(r[9] or 0), swap=float(r[10] or 0), pnl=float(r[11] or 0),
                           comment=(r[12] if len(r) > 12 else "").strip()))
    elif typ in ("Buy Stop", "Sell Stop"):
        pend.append((datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S"), typ, r[12] if len(r) > 12 else ""))
    else:
        bals.append((datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S"), float(r[11].replace(" ", ""))))

print(f"Filled: {len(filled)} | Pendings: {len(pend)} (storniert {sum(1 for p in pend if p[2]=='cancelled')})")
net = sum(t["pnl"] + t["comm"] + t["swap"] for t in filled)
print(f"Netto: {net:.2f} | Komm: {sum(t['comm'] for t in filled):.2f} | Swap: {sum(t['swap'] for t in filled):.2f}")
wins = [t for t in filled if t["pnl"] > 0]
losses = [t for t in filled if t["pnl"] <= 0]
print(f"Winrate: {len(wins)}/{len(filled)} = {len(wins)/len(filled)*100:.1f}% | AvgWin {statistics.mean(t['pnl'] for t in wins):.2f} | AvgLoss {statistics.mean(t['pnl'] for t in losses):.2f}")

sl_init, tp_init, rr = [], [], []
for t in filled:
    if t["sl"] and t["tp"] and t["ep"]:
        sld = (t["ep"] - t["sl"]) * (1 if t["dir"] == "Buy" else -1)
        tpd = (t["tp"] - t["ep"]) * (1 if t["dir"] == "Buy" else -1)
        if sld > 0 and tpd > 0:
            sl_init.append(sld); tp_init.append(tpd); rr.append(tpd / sld)
sl_init.sort(); tp_init.sort(); rr.sort()
print(f"\nInitiale SL-Distanz USD: n={len(sl_init)}, median {statistics.median(sl_init):.2f}, P25 {sl_init[len(sl_init)//4]:.2f}, P75 {sl_init[3*len(sl_init)//4]:.2f}, max {sl_init[-1]:.2f}")
print(f"Initiale TP-Distanz USD: median {statistics.median(tp_init):.2f}, max {tp_init[-1]:.2f}")
print(f"R:R (TP/SL initial): median {statistics.median(rr):.2f}")
sl_exits = [t for t in filled if t["comment"] == "[sl]"]
tp_exits = [t for t in filled if t["comment"] == "[tp]"]
sl_profit = [t for t in sl_exits if t["pnl"] > 0]
print(f"\nExits: [sl] {len(sl_exits)}, [tp] {len(tp_exits)}, manuell/sonstige {len(filled)-len(sl_exits)-len(tp_exits)}")
print(f"Trailing-Beweis: {len(sl_profit)} von {len(sl_exits)} SL-Exits im PLUS (Stop nachgezogen), Summe {sum(t['pnl'] for t in sl_profit):+.2f} USD")
for t in sorted(sl_profit, key=lambda t: -t["pnl"])[:3]:
    print(f"  {t['o']:%d.%m.%Y %H:%M} {t['dir']} @ {t['ep']:.2f} -> SL-Exit {t['xp']:.2f} {t['pnl']:+.2f}")
sl_loss = [t for t in sl_exits if t["pnl"] <= 0]
sl_loss_dist = [(t["ep"] - t["xp"]) * (1 if t["dir"] == "Buy" else -1) for t in sl_loss]
if sl_loss_dist:
    print(f"SL-Verlustdistanzen: median {statistics.median(sl_loss_dist):.2f} USD, max {max(sl_loss_dist):.2f}")

lots = Counter(t["vol"] for t in filled)
print("\nLots:", dict(sorted(lots.items())))
v02 = [t for t in filled if t["vol"] >= 0.02]
print(f"0.02-Lot-Trades: {len(v02)}")
for t in v02[:10]:
    print(f"  {t['o']:%d.%m.%Y} {t['dir']} {t['vol']:.2f} pnl {t['pnl']:+.2f}")

clusters = defaultdict(list)
for t in filled:
    clusters[t["o"].strftime("%Y%m%d%H")].append(t)
multi = sorted([b for b in clusters.values() if len(b) >= 3], key=len, reverse=True)
print(f"\nCluster >=3 Fills in 1h: {len(multi)} | groesstes: {len(multi[0]) if multi else 0}")
if multi:
    for t in sorted(multi[0], key=lambda t: t["o"]):
        print(f"  {t['o']:%d.%m. %H:%M:%S} {t['dir']} {t['vol']:.2f} @ {t['ep']:.2f} -> {t['pnl']:+7.2f} {t['comment']}")

durs = [(t["c"] - t["o"]).total_seconds() / 3600 for t in filled]
print(f"\nHaltedauer h: median {statistics.median(durs):.2f}, avg {statistics.mean(durs):.1f}, max {max(durs):.0f}")
hours = Counter(t["o"].hour for t in filled)
print("Einstiegsstunden Top8:", dict(sorted(hours.items(), key=lambda x: -x[1])[:8]))
ph = Counter(p[0].hour for p in pend)
print("Pending-Platzierung Top6:", dict(sorted(ph.items(), key=lambda x: -x[1])[:6]))

monthly = defaultdict(float)
for t in filled:
    monthly[t["c"].strftime("%Y-%m")] += t["pnl"] + t["comm"] + t["swap"]
print("\nMonate (CSV):", {m: round(v, 1) for m, v in sorted(monthly.items())})
seq = sorted(filled, key=lambda t: t["c"])
bal, peak, maxdd, maxdd_pct, when = 3116.0, 3116.0, 0, 0, None
bi = 0
bs = sorted(bals)
for t in seq:
    while bi < len(bs) and bs[bi][0] <= t["c"]:
        bal += bs[bi][1]
        peak = max(peak, bal)
        bi += 1
    bal += t["pnl"] + t["comm"] + t["swap"]
    peak = max(peak, bal)
    if peak - bal > maxdd:
        maxdd, maxdd_pct, when = peak - bal, (peak - bal) / peak * 100, t["c"]
print(f"Max realisierter DD: {maxdd:.2f} USD = {maxdd_pct:.1f}% bei {when:%Y-%m-%d} | Endbalance {bal:.2f}")

worst8 = sorted(filled, key=lambda t: t["pnl"])[:8]
print("\nSchlechteste 8:")
for t in worst8:
    print(f"  {t['o']:%d.%m.%Y %H:%M} {t['dir']} {t['vol']:.2f} @ {t['ep']:.2f} SL {t['sl']} TP {t['tp']} -> {t['pnl']:+8.2f} {t['comment']}")
best5 = sorted(filled, key=lambda t: -t["pnl"])[:5]
print("Beste 5:")
for t in best5:
    print(f"  {t['o']:%d.%m.%Y %H:%M} {t['dir']} {t['vol']:.2f} @ {t['ep']:.2f} -> {t['pnl']:+8.2f} {t['comment']} ({(t['c']-t['o']).total_seconds()/3600:.1f}h)")

streak = maxstreak = 0
for t in seq:
    streak = streak + 1 if t["pnl"] <= 0 else 0
    maxstreak = max(maxstreak, streak)
print(f"Max konsekutive Verluste: {maxstreak}")
byday = defaultdict(lambda: [0, 0.0])
for t in filled:
    byday[t["o"].date().isoformat()][0] += 1
    byday[t["o"].date().isoformat()][1] += t["pnl"]
print("Schlechteste Tage:", [(d, round(v[1], 1)) for d, v in sorted(byday.items(), key=lambda x: x[1][1])[:5]])
print("Beste Tage:", [(d, round(v[1], 1)) for d, v in sorted(byday.items(), key=lambda x: -x[1][1])[:5]])
