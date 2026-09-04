# -*- coding: utf-8 -*-
import csv
from datetime import datetime, date
from collections import defaultdict

rows = list(csv.reader(open("data/raw/msc_gold_2231030_positions.csv", encoding="utf-8-sig"), delimiter=";"))
trades = []
for r in rows[1:]:
    if r[1] in ("Buy", "Sell"):
        o = datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S")
        trades.append(dict(o=o, pnl=float(r[10])))

# FOMC-Entscheidungstage 2024-2026 (US-Ostzeit; Entscheidung 14:00 ET = 21:00 GMT+2-Server)
fomc = ["2024-05-01","2024-06-12","2024-07-31","2024-09-18","2024-11-07","2024-12-18",
        "2025-01-29","2025-03-19","2025-05-07","2025-06-18","2025-07-30","2025-09-17","2025-10-29","2025-12-10",
        "2026-01-28","2026-03-18","2026-04-29","2026-06-17","2026-07-29"]
# NFP-Erstfreitage (Beispielstichprobe)
import calendar
nfp = []
for y in (2024, 2025, 2026):
    for m in range(1, 13):
        c = calendar.Calendar(firstweekday=0).monthdatescalendar(y, m)
        first_friday = [w[4] for w in c if w[4].month == m][0]
        if date(y, 4, 22) <= first_friday <= date(2026, 8, 28):
            nfp.append(first_friday.isoformat())

by_day = defaultdict(lambda: [0, 0.0])
for t in trades:
    k = t["o"].date().isoformat()
    by_day[k][0] += 1
    by_day[k][1] += t["pnl"]

# Durchschnittlicher Tag
avg_cnt = sum(v[0] for v in by_day.values()) / len(by_day)
print(f"Aktive Tage: {len(by_day)}, durchschn. {avg_cnt:.1f} Trades/Tag")

fomc_days = [(d, tuple(by_day.get(d, (0, 0.0)))) for d in fomc]
print("\nFOMC-Tage (Trades, PnL):")
for d, v in fomc_days:
    if d >= "2024-04-22":
        print(f"  {d}: {v[0]:3d} Trades, {v[1]:+8.2f} USD")

nfp_stats = [(d, tuple(by_day.get(d, (0, 0.0)))) for d in nfp]
nfp_act = [(d, v) for d, v in nfp_stats if v[0] > 0]
print(f"\nNFP-Freitages mit Aktivitaet: {len(nfp_act)}/{len(nfp_stats)}")
top_nfp = sorted(nfp_act, key=lambda x: -abs(x[1][1]))[:5]
for d, v in top_nfp:
    print(f"  {d}: {v[0]:3d} Trades, {v[1]:+8.2f} USD")

# Israel-Iran-Schock Juni 2025
print("\nJuni 2025 (Kriegsbeginn 13.06.):")
for d in sorted(k for k in by_day if k.startswith("2025-06")):
    print(f"  {d}: {by_day[d][0]:3d} Trades, {by_day[d][1]:+8.2f} USD")

#aktivste Tage
top = sorted(by_day.items(), key=lambda x: -x[1][0])[:8]
print("\nAktivste Tage:", [(d, v[0], round(v[1],1)) for d, v in top])
# schlechteste Tage
worst = sorted(by_day.items(), key=lambda x: x[1][1])[:6]
print("Schlechteste Tage:", [(d, v[0], round(v[1],1)) for d, v in worst])
