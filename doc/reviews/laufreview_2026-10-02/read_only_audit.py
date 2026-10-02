"""Independent decimal CSV audit; production SQLite is opened read-only.

No engine, DB helper, networking, LLM or MT5 calls. Only review JSON is written.
"""
from collections import defaultdict
import csv
from datetime import datetime
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
START = "2026-10-02 11:00:00"

def number(value):
    return D(value.replace(" ", "").replace("\xa0", "") or "0")

def timestamp(value):
    return datetime.strptime(value.strip(), "%Y.%m.%d %H:%M:%S")

def curve(events, start):
    balance = peak = start
    dd_usd = dd_pct = D(0)
    for when, change in sorted(events.items()):
        balance += change
        peak = max(peak, balance)
        dd_usd = max(dd_usd, peak - balance)
        relative = (peak-balance)/peak*100 if peak > 0 else (D(100) if peak > balance else D(0))
        dd_pct = max(dd_pct, relative)
    return round(float(dd_usd), 2), round(float(dd_pct), 2)

def audit(row):
    stored = json.loads(row["json"])
    stats = json.loads(row["stats_json"])
    path = Path(row["path"])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    trades, flows, credits = [], [], []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = csv.reader(handle, delimiter=";")
        header = next(rows)
        orderbook = len(header) == 13
        profit, close, exitprice = (11, 7, 8) if orderbook else (10, 6, 7)
        commission, swap = (9, 10) if orderbook else (8, 9)
        for cells in rows:
            if len(cells) < 2 or not cells[1].strip():
                continue
            kind = cells[1].strip()
            if kind == "Credit":
                credits.append((timestamp(cells[0]), number(cells[profit])))
            elif kind in ("Balance", "Correction"):
                flows.append((timestamp(cells[0]), number(cells[profit])))
            elif kind in ("Buy", "Sell") and cells[3].strip().lower() != "profit":
                trades.append((timestamp(cells[0]), timestamp(cells[close]),
                               number(cells[profit]) + number(cells[commission]) + number(cells[swap]),
                               number(cells[profit])))
    first = min(t[0] for t in trades)
    last = max(t[1] for t in trades)
    csv_start = sum((amount for when, amount in flows if when <= first), D(0))
    # External/implicit/virtual basis cannot be proved solely from this CSV.
    # Its stored value is a declared assumption; CSV-derived basis is checked.
    capital = stored.get("kapitalbasis", {})
    basis = D(str(capital["usd"])) if capital.get("usd") is not None else csv_start
    events = defaultdict(lambda: D(0))
    for opened, closed, net, gross in trades:
        events[closed] += net
    usd, pct = curve(events, basis)
    net = sum((t[2] for t in trades), D(0))
    weeks = round((last-first).days/7, 1)
    monthly = round(float(100*net/basis/D(str(weeks*7/30.44))), 2) if basis > 0 and weeks > 0 else None
    position_events = defaultdict(lambda: [0, 0])
    for opened, closed, _, _ in trades:
        position_events[opened][0] += 1
        position_events[closed][1] += 1
    count = peak = 0
    for opened, closed in (values for _, values in sorted(position_events.items())):
        count += opened
        peak = max(peak, count)
        count -= closed
    checks = {
        "snapshot_sha256": digest == row["sha256"],
        "trading_dd_usd": abs(usd-stored["trading_dd"]["usd"]) <= .01,
        "trading_dd_pct": abs(pct-stored["trading_dd"]["pct"]) <= .01,
        "peak_positions": peak == stored["peak_exposure"]["positionen"],
        "linear_monthly_return": monthly == stats.get("ertrag_monat_pct_forensik"),
    }
    if capital.get("quelle") == "csv_einzahlungen":
        checks["csv_start_capital"] = abs(float(csv_start-basis)) <= .01
    return {"id": row["signal_id"], "name": row["name"], "quelle": row["quelle"],
            "checks": checks, "trades": len(trades), "net_usd": round(float(net), 2),
            "capital_basis_usd": float(basis), "basis_source": capital.get("quelle"),
            "credit_excluded_per_current_parser_usd": float(sum((v for _, v in credits), D(0))),
            "trading_dd_usd": usd, "trading_dd_pct": pct, "peak_positions": peak,
            "linear_monthly_return_pct": monthly,
            "stored_metrics": {key: stats.get(key, stored.get(key)) for key in
                ("retdd_monat", "retdd_jahr", "ertrag_monat_geom_pct", "cagr_jahr_pct")}}

if __name__ == "__main__":
    connection = sqlite3.connect((ROOT/"data/mqlkiscanner.db").as_uri()+"?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("BEGIN")
    rows = connection.execute("""SELECT s.signal_id,s.name,s.quelle,s.stats_json,f.json,f.updated_at,t.path,t.sha256
        FROM signals s JOIN forensik f USING(signal_id) LEFT JOIN trade_files t USING(signal_id)
        WHERE f.updated_at >= ? ORDER BY f.updated_at""", (START,)).fetchall()
    analyses = [dict(row) for row in connection.execute("""SELECT id,signal_id,kind,model,tokens,created_at
        FROM analyses WHERE created_at >= ? ORDER BY id""", (START,))]
    connection.rollback()
    connection.close()
    output = {"snapshot_time": datetime.now().isoformat(timespec="seconds"),
              "run_window_start": START, "signals": [audit(row) for row in rows],
              "new_analysis_metadata": analyses}
    target = Path(__file__).with_name("lauf_audit.json")
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"snapshot_time": output["snapshot_time"], "signals": len(rows),
                      "analyses": len(analyses), "checks": sum(len(s["checks"]) for s in output["signals"]),
                      "failed": [{"id": s["id"], "checks": s["checks"]} for s in output["signals"]
                                  if not all(s["checks"].values())]}, ensure_ascii=True))
