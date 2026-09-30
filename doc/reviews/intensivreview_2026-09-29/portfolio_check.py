"""Portfolio-Streuungspruefung: Monatsrenditen-Korrelation + gemeinsame DD-Phasen.

Unabhaengig: nur CSVs + forensik-JSON, keine Produktivfunktionen.
Kapitalbasis je Signal = dieselbe, die die Forensik nennt (implizit/web/einzahlung),
sonst die virtuelle 10k-Annahme.
"""
import csv
import io
import json
import os
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime

LAUF = "data/runs/2026-09-30_025355_970680_c65bf5cd/results.json"
AMPEL_OK = ("\U0001F7E2", "\U0001F7E1")


def monatsserie(pfad):
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

    mon, syms = defaultdict(float), set()
    for r in rd[1:]:
        if len(r) < len(head) or r[ix["Type"]].strip().lower() not in ("buy", "sell"):
            continue
        try:
            c = datetime.strptime(r[ti[1]][:19], "%Y.%m.%d %H:%M:%S")
        except ValueError:
            continue
        mon["%04d-%02d" % (c.year, c.month)] += (
            f(r[ix["Profit"]]) + f(r[ix["Commission"]]) + f(r[ix["Swap"]]))
        syms.add(r[ix["Symbol"]].strip())
    return dict(mon), syms


def korrelation(a, b):
    xs = sorted(set(a) & set(b))
    if len(xs) < 4:
        return None, len(xs)
    ua = [a[k] for k in xs]
    ub = [b[k] for k in xs]
    if statistics.pstdev(ua) == 0 or statistics.pstdev(ub) == 0:
        return None, len(xs)
    ma, mb = statistics.mean(ua), statistics.mean(ub)
    num = sum((x - ma) * (y - mb) for x, y in zip(ua, ub))
    den = (sum((x - ma) ** 2 for x in ua) * sum((y - mb) ** 2 for y in ub)) ** 0.5
    return (num / den if den else None), len(xs)


def main():
    con = sqlite3.connect("data/mqlkiscanner.db")
    res = json.load(open(LAUF, encoding="utf-8"))["ergebnisse"]
    daten = {}
    for x in res:
        if x.get("ampel") not in AMPEL_OK or not x.get("trades_path") \
                or not os.path.exists(x["trades_path"]):
            continue
        row = con.execute("select json from forensik where signal_id=?", (x["id"],)).fetchone()
        if not row:
            continue
        fj = json.loads(row[0])
        kb = fj.get("kapitalbasis", {})
        basis = kb.get("usd") or 10000.0
        mon, syms = monatsserie(x["trades_path"])
        rend = {k: 100.0 * v / basis for k, v in mon.items()}
        # Monate mit Verlust
        neg = sorted(k for k, v in rend.items() if v < 0)
        daten[x["id"]] = {"name": x["name"], "quelle": x.get("quelle") or "mql5",
                          "ampel": x["ampel"], "rend": rend, "syms": syms,
                          "basis": basis, "neg": neg,
                          "schranke": x.get("dd_equity_pct")}

    ids = sorted(daten)
    print("== Monatsrenditen (%% der Forensik-Kapitalbasis), gemeinsame Monate ==")
    alle = sorted({k for d in daten.values() for k in d["rend"]})
    print("Monate gesamt:", len(alle), alle[0], "bis", alle[-1])
    print("\n== Paar-Korrelationen (>= 6 gemeinsame Monate) ==")
    paare = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            r, n = korrelation(daten[a]["rend"], daten[b]["rend"])
            if r is None or n < 6:
                continue
            paare.append((r, a, b, n))
    paare.sort(reverse=True)
    for r, a, b, n in paare:
        print("  %+.2f  n=%2d  %s (%s) <-> %s (%s)" % (r, n, daten[a]["name"][:18],
              daten[a]["quelle"], daten[b]["name"][:18], daten[b]["quelle"]))
    with open("doc/reviews/intensivreview_2026-09-29/korrelationen_alle.csv",
              "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["r", "n_monate", "id_a", "name_a", "quelle_a", "ampel_a",
                     "id_b", "name_b", "quelle_b", "ampel_b"])
        for r, a, b, n in paare:
            wr.writerow(["%.4f" % r, n, a, daten[a]["name"], daten[a]["quelle"],
                         daten[a]["ampel"], b, daten[b]["name"], daten[b]["quelle"],
                         daten[b]["ampel"]])
    print("\n== Instrumentenueberschneidung ==")
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            inter = daten[a]["syms"] & daten[b]["syms"]
            if len(inter) >= max(2, 0.5 * min(len(daten[a]["syms"]), len(daten[b]["syms"]))):
                print("  %s <-> %s : %d gemeinsame Symbole %s" % (
                    daten[a]["name"][:18], daten[b]["name"][:18], len(inter),
                    sorted(inter)[:6]))

    print("\n== Gemeinsame Verlustmonate (>= 3 Signale gleichzeitig im Minus) ==")
    zaehl = defaultdict(list)
    for sid, d in daten.items():
        for m in d["neg"]:
            zaehl[m].append(d["name"][:16])
    for m, lst in sorted(zaehl.items()):
        if len(lst) >= 3:
            print("  %s : %d  %s" % (m, len(lst), lst))

    print("\n== Kennzahlen je Signal ==")
    for sid in ids:
        d = daten[sid]
        pos = [v for v in d["rend"].values() if v > 0]
        print("  %s %-18s %s basis=%8.0f mon=%2d neg=%2d ø=%+6.2f%% sigma=%5.2f min=%+7.2f max=%+7.2f" % (
            sid, d["name"][:18], d["ampel"], d["basis"], len(d["rend"]), len(d["neg"]),
            statistics.mean(d["rend"].values()), statistics.pstdev(d["rend"].values()),
            min(d["rend"].values()), max(d["rend"].values())))


if __name__ == "__main__":
    main()
