# -*- coding: utf-8 -*-
import csv, statistics
from datetime import datetime
from collections import Counter

def num(x):
    x = x.replace(" ", "").replace("\xa0", "")
    return float(x) if x else None

rows = list(csv.reader(open("data/raw/puregold_2362868_positions.csv", encoding="utf-8-sig"), delimiter=";"))
trades = []
for r in rows[1:]:
    if len(r) >= 11 and r[1] in ("Buy", "Sell"):
        o = datetime.strptime(r[0], "%Y.%m.%d %H:%M:%S"); c = datetime.strptime(r[6], "%Y.%m.%d %H:%M:%S")
        trades.append(dict(o=o, c=c, dir=r[1], vol=float(r[2]), ep=num(r[4]), xp=num(r[7]), pnl=float(r[10] or 0)))

seq = sorted(trades, key=lambda t: t["o"])

# === TEST 1: Lot nach Verlust vs Lot nach Gewinn (Martingale-Signatur) ===
after_loss, after_win = [], []
for i in range(len(seq) - 1):
    if seq[i + 1]["o"] > seq[i]["c"]:  # nur wenn nicht parallel offen
        (after_loss if seq[i]["pnl"] <= 0 else after_win).append(seq[i + 1]["vol"] / max(seq[i]["vol"], 1e-9))
print("TEST 1 - Lot(i+1)/Lot(i):")
print(f"  nach Verlust : median {statistics.median(after_loss):.2f}x, mittel {statistics.mean(after_loss):.2f}x (n={len(after_loss)})")
print(f"  nach Gewinn  : median {statistics.median(after_win):.2f}x, mittel {statistics.mean(after_win):.2f}x (n={len(after_win)})")
print(f"  -> Martingale waere: nach Verlust deutlich > 1 (Verdopplung ~2x) und > nach Gewinn")

# === TEST 2: Lot-Verlauf WAEHREND der 19er-Verlustserie (04.-06.05.) ===
streak_start = datetime.strptime("2026.05.04", "%Y.%m.%d")
streak_end = datetime.strptime("2026.05.07", "%Y.%m.%d")
ser = [t for t in seq if streak_start <= t["o"] < streak_end]
print(f"\nTEST 2 - Lots waehrend der Verlustserie 04.-06.05. ({len(ser)} Trades):")
print("  " + " -> ".join(f"{t['vol']:.2f}" for t in ser))
mx = max(range(1, len(ser)), key=lambda i: ser[i]["vol"])
print(f"  Max-Lot der Serie: {max(t['vol'] for t in ser):.2f} (Position {mx+1} von {len(ser)})")
print("  -> Martingale waere: monoton steigende Lots bis zum Serienende")

# === TEST 3: Verlustdistanzen (Gold, USD Preisbewegung) - ballen sie sich (SL-Signatur)? ===
loss_dist = []
for t in trades:
    if t["pnl"] < 0 and t["xp"] and t["ep"]:
        d = (t["ep"] - t["xp"]) * (1 if t["dir"] == "Buy" else -1)
        if d > 0: loss_dist.append(round(d, 1))
loss_dist.sort()
if loss_dist:
    print(f"\nTEST 3 - Verlustdistanz USD-Preisbewegung (n={len(loss_dist)}):")
    print(f"  Median {statistics.median(loss_dist):.1f}, P75 {loss_dist[3*len(loss_dist)//4]:.1f}, P90 {loss_dist[9*len(loss_dist)//10]:.1f}, Max {loss_dist[-1]:.1f}")
    top = Counter(loss_dist).most_common(8)
    print(f"  Haeufigste Distanzen: {top}")
    print("  -> Festes SL waere: Ballung bei einem Niveau (z. B. 5 oder 10 USD)")

# === TEST 4: Gleichzeitig offene Positionen (Basket/Exposure) ===
events = []
for t in trades:
    events.append((t["o"], 1)); events.append((t["c"], -1))
events.sort()
cur = mx = 0
for _, d in events:
    cur += d; mx = max(mx, cur)
print(f"\nTEST 4 - Max gleichzeitig offene Positionen: {mx}")

# === TEST 5: Lot-Median im Zeitverlauf (Balance-Skalierung vs Eskalation) ===
t0 = min(t["o"] for t in trades)
buckets = defaultdict(list)
for t in seq:
    m = int((t["o"] - t0).days / 30)
    buckets[m].append(t["vol"])
print("\nTEST 5 - Lot-Median je Monat (0=Start):")
for m in sorted(buckets):
    print(f"  Monat {m+1}: median {statistics.median(buckets[m]):.2f}, max {max(buckets[m]):.2f}, n={len(buckets[m])}")
