# -*- coding: utf-8 -*-
import json, statistics
from datetime import datetime

trades = json.load(open("data/raw/fxtrading_2356441_trades.json", encoding="utf-8"))
print(f"Trades im Datensatz (sichtbarer Ausschnitt): {len(trades)}")

# P/L-Verteilung
pnls = [t["pnl"] for t in trades]
wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p <= 0]
print(f"Winrate (Ausschnitt): {len(wins)}/{len(pnls)} = {len(wins)/len(pnls)*100:.1f}%")
print(f"Avg Win: {statistics.mean(wins):.2f} | Avg Loss: {statistics.mean(losses):.2f} | Ratio: {statistics.mean(wins)/abs(statistics.mean(losses)):.2f}")
print(f"Best: {max(pnls):.2f} | Worst: {min(pnls):.2f}")
print(f"Netto Ausschnitt: {sum(pnls):.2f} USD")

# Haltedauer
durs = []
for t in trades:
    o = datetime.strptime(t["o"], "%Y-%m-%d %H:%M"); c = datetime.strptime(t["c"], "%Y-%m-%d %H:%M")
    durs.append((c-o).total_seconds()/3600)
print(f"Haltedauer h: min {min(durs):.0f}, max {max(durs):.0f}, median {statistics.median(durs):.0f}")

# Grid-Cluster: mehrere Positionen gleiches Symbol+Richtung, Exit zum selben Zeitpunkt
from collections import defaultdict
clusters = defaultdict(list)
for t in trades:
    clusters[(t["sym"], t["dir"], t["c"][:16])].append(t)
grid = {k: v for k, v in clusters.items() if len(v) >= 2}
print(f"\nBasket-Exits (>=2 Positionen gleichzeitig geschlossen): {len(grid)}")
for k, v in sorted(grid.items(), key=lambda x: -len(x[1])):
    lots = " -> ".join(f'{t["vol"]:.2f}' for t in sorted(v, key=lambda t: t["o"]))
    eps = " -> ".join(f'{t["ep"]:.5f}' for t in sorted(v, key=lambda t: t["o"]))
    net = sum(t["pnl"] for t in v)
    print(f"  {k[0]} {k[1]} exit {k[2]}: {len(v)} Pos, Lots {lots}, Netto {net:+.2f}")

# Lot-Verteilung
vols = [t["vol"] for t in trades]
print(f"\nLot-Groessen: min {min(vols)}, max {max(vols)}, haeufigst {statistics.mode(vols)}")

# Verlustanalyse: Pip-Distanzen der Verlierer
print("\nVerlust-Trades mit Pip-Distanz (FX 5. Dezimalstellen als 1 pip):")
for t in trades:
    if t["pnl"] <= 0:
        pip = 0.0001 if t["sym"] not in ("XAUUSD",) and "JPY" not in t["sym"] else (0.01 if "JPY" in t["sym"] else 1.0)
        dist = (t["ep"] - t["xp"]) / pip * (1 if t["dir"]=="S" else -1)
        o = datetime.strptime(t["o"], "%Y-%m-%d %H:%M"); c = datetime.strptime(t["c"], "%Y-%m-%d %H:%M")
        d_h = (c-o).total_seconds()/3600
        print(f"  {t['sym']:7} {t['dir']} pnl {t['pnl']:+7.2f} dist {dist:+8.0f} pips, Haltedauer {d_h:6.0f} h")

# Einstiegs-Uhrzeiten (Serverzeit)
hours = [int(t["o"][11:13]) for t in trades]
print(f"\nEinstiegsstunden (Serverzeit): min {min(hours)}, max {max(hours)}")
import collections
hc = collections.Counter(hours)
print("Verteilung:", dict(sorted(hc.items())))
