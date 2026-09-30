"""Unabhaengige Nachrechnung: Kapitalbasis-/DD-/Ertragsvergleich je Signal.

Liest nur CSVs + forensik-JSON aus der DB, keine Produktivfunktionen.
"""
import csv
import io
import json
import os
import sqlite3
import sys
from datetime import datetime

AMPEL_OK = ("\U0001F7E2", "\U0001F7E1")  # gruen, gelb
LAUF = sys.argv[1] if len(sys.argv) > 1 else "data/runs/2026-09-30_025355_970680_c65bf5cd/results.json"
DB = "data/mqlkiscanner.db"


def trades(pfad):
    with open(pfad, encoding="utf-8-sig") as fh:
        rd = list(csv.reader(io.StringIO(fh.read()), delimiter=";"))
    head = [h.strip() for h in rd[0]]
    ix = {h: i for i, h in enumerate(head)}
    ti = [i for i, h in enumerate(head) if h == "Time"]

    def f(s):
        s = (s or "").strip().replace("\u00a0", "").replace(" ", "")
        try:
            return float(s)
        except ValueError:
            return 0.0

    rows, mon = [], set()
    for r in rd[1:]:
        if len(r) < len(head):
            continue
        if r[ix["Type"]].strip().lower() not in ("buy", "sell"):
            continue
        try:
            c = datetime.strptime(r[ti[1]][:19], "%Y.%m.%d %H:%M:%S")
        except ValueError:
            continue
        rows.append((c, f(r[ix["Profit"]]) + f(r[ix["Commission"]]) + f(r[ix["Swap"]])))
        mon.add((c.year, c.month))
    rows.sort()
    eq = peak = dd = 0.0
    for _c, n in rows:
        eq += n
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return sum(n for _c, n in rows), dd, max(len(mon), 1), len(rows)


def main():
    con = sqlite3.connect(DB)
    res = json.load(open(LAUF, encoding="utf-8"))["ergebnisse"]
    hdr = ("id", "name", "quelle", "ampel", "netto", "dd_usd", "mon", "n",
           "kb_prod", "kb_quelle_prod", "webbal", "implizit", "end_bal",
           "mon_dd", "ertrag_10k", "ertrag_impl", "dd%_10k", "dd%_impl", "eq_dd_prod")
    print("\t".join(hdr))
    for x in res:
        if x.get("ampel") not in AMPEL_OK:
            continue
        pfad = x.get("trades_path")
        if not pfad or not os.path.exists(pfad):
            continue
        row = con.execute("select json from forensik where signal_id=?", (x["id"],)).fetchone()
        if not row:
            continue
        fj = json.loads(row[0])
        kb = fj.get("kapitalbasis", {})
        netto, dd, mon, n = trades(pfad)
        web = kb.get("webseite_balance_usd")
        endb = kb.get("end_balance_real")
        impl = (web - netto) if web and netto else None
        impl = impl if (impl and impl > 0) else None
        e_i = 100.0 * netto / impl / mon if impl else None
        d_i = 100.0 * dd / impl if impl else None
        vals = [x["id"], x["name"][:18], x.get("quelle") or "mql5", x["ampel"],
                "%.0f" % netto, "%.0f" % dd, mon, n,
                kb.get("usd"), kb.get("quelle"),
                "%.0f" % web if web else "-",
                "%.0f" % impl if impl else "-",
                "%.0f" % endb if endb else "-",
                x.get("dd_equity_pct"),
                "%.2f" % (100.0 * netto / 10000.0 / mon),
                "%.2f" % e_i if e_i else "-",
                "%.2f" % (100.0 * dd / 10000.0),
                "%.2f" % d_i if d_i else "-",
                x.get("trading_dd_pct")]
        print("\t".join(str(v) for v in vals))


if __name__ == "__main__":
    main()
