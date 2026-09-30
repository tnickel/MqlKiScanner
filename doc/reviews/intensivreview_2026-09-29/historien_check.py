"""Prueft, ob der Trade-Export je Pelikan-Signal die VOLLE Provider-Historie
abdeckt. Denn die implizite Kapitalbasis = web_balance - Summe(NettoPnL) setzt
voraus, dass die Summe aller Trades dem gesamten Lifetime-Gewinn entspricht.
Deckungsluecke -> implizite Basis ZU GROSS (zu konservativ).
"""
import csv
import glob
import json
import os
import sqlite3
from datetime import datetime

ROOT = r"D:\AntiGravitySoftware\GitWorkspace\SIGNALDOWNLOADER\SignalKiScanner"

CAT = {}
for p in glob.glob(os.path.join(ROOT, "data", "quellen", "pelik", "*_katalog.json")):
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    items = d.get("items", d) if isinstance(d, dict) else d
    if isinstance(items, list):
        for it in items:
            if isinstance(it, dict) and it.get("id"):
                CAT[int(it["id"])] = it


def read_times(path):
    first = last = None
    n = 0
    netto = 0.0
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        head = None
        for row in csv.reader(fh, delimiter=";"):
            if not row:
                continue
            if head is None:
                head = [c.strip().lower() for c in row]
                continue
            n += 1
            t = None
            for i, c in enumerate(head):
                if c in ("time", "zeit", "date", "datum", "datetime"):
                    t = row[i]
                    break
            if not t:
                continue
            d = None
            for fmt in ("%Y.%m.%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S",
                        "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M"):
                try:
                    d = datetime.strptime(t.strip()[:19], fmt)
                    break
                except ValueError:
                    d = None
            if d is None:
                continue
            if first is None or d < first:
                first = d
            if last is None or d > last:
                last = d
            for i, c in enumerate(head):
                if c in ("profit", "pnl", "gewinn"):
                    try:
                        netto += float(row[i].replace(" ", "").replace("\u00a0", ""))
                    except ValueError:
                        pass
                    break
    return first, last, n, round(netto, 2)


def main():
    c = sqlite3.connect(os.path.join(ROOT, "data", "mqlkiscanner.db"))
    c.row_factory = sqlite3.Row
    ids = [r["signal_id"] for r in c.execute(
        "select signal_id from signals where quelle='pelik' order by signal_id")]
    print("id\tname\tweeks\tfirst\tlast\tspan_mon\tn_trades\tnetto_csv\tnetto_db\tnetto_fx")
    for sid in ids:
        r2 = c.execute(
            "select path from quellen_artefakte where signal_id=? and art='trades' "
            "order by fetched_at desc limit 1", (sid,)).fetchone()
        if not r2 or not r2["path"] or not os.path.exists(r2["path"]):
            continue
        first, last, n, netto = read_times(r2["path"])
        if first is None:
            continue
        cat = CAT.get(sid, {})
        r = c.execute("select json from forensik where signal_id=?", (sid,)).fetchone()
        netto_db = netto_fx = None
        if r and r["json"]:
            try:
                fj = json.loads(r["json"])
                tests = fj.get("tests", fj) if isinstance(fj, dict) else {}
                if isinstance(tests, dict):
                    netto_db = tests.get("drawdown", {}).get("netto_pnl") if isinstance(tests.get("drawdown"), dict) else None
                if netto_db is None and isinstance(fj, dict):
                    netto_db = fj.get("netto_pnl")
                fx = fj.get("fx") if isinstance(fj, dict) else None
                if isinstance(fx, dict):
                    netto_fx = fx.get("sum_profit_usd") or fx.get("netto_usd")
            except Exception:
                pass
        print(f"{sid}\t{(cat.get('name') or '')[:20]}\t{cat.get('weeks')}\t"
              f"{first.date()}\t{last.date()}\t{(last-first).days/30.44:.1f}\t{n}\t"
              f"{netto}\t{netto_db}\t{netto_fx}")


if __name__ == "__main__":
    main()
