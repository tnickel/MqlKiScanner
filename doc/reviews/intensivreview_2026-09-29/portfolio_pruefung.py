# -*- coding: utf-8 -*-
"""
Portfolio-/Diversifikationsprüfung des Intensiv-Reviews 2026-09-29/30.

Unabhängige Prüfung der Behauptung „drei getrennte Märkte / wenig
gemeinsame Risiken" aus dem Portfolio-Bericht des Ziellaufs
(2026-09-30_025355_970680_c65bf5cd): Renditekorrelationen auf gemeinsamen
Zeiträumen aus den Trade-Rohdaten (virtuelle Kurve, Monats- und
Wochenraster), gemeinsame Verlustfenster, Überlappung offener Positionen
der drei empfohlenen Signale sowie chronologische Stabilität.

Keine Zukunftsprognose; Grenzen werden in portfolio_pruefung.md benannt.
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
from nachrechnung_pruefung import parse_csv, RESULTS, DB_COPY  # noqa: E402

EMPF = [("mql5", 2349227, "Gold Spike"), ("pelik", 2000028, "Lexo"),
        ("pelik", 2014076, "PentagonForex")]


def pearson(a: list[float], b: list[float]) -> float | None:
    n = len(a)
    if n < 3:
        return None
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    sa = sum((x - ma) ** 2 for x in a)
    sb = sum((y - mb) ** 2 for y in b)
    if sa <= 0 or sb <= 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) ** 0.5


def monatspunkte(trades, bewegungen, fallback):
    """Virtuelle Kurve -> monatliche Renditen (PnL / Balance am Monatsanfang)
    und Wochen-PnL (US-summiert, normalisiert auf Monatsanfangsbalance)."""
    from nachrechnung_pruefung import virtual_dd
    start, quelle, *_ = virtual_dd(trades, bewegungen, fallback)
    erste = min(t.op or t.cl for t in trades)
    monat_pnl, woche_pnl = defaultdict(float), defaultdict(float)
    for t in trades:
        z = t.cl or t.op
        monat_pnl[z.strftime("%Y-%m")] += t.netto
        # ISO-Woche
        wo = z.isocalendar()
        woche_pnl[(wo.year, wo.week)] += t.netto
    renditen, cum = {}, float(start)
    for m in sorted(monat_pnl):
        renditen[m] = monat_pnl[m] / cum if cum > 0 else None
        cum += monat_pnl[m]
    # Wochenrenditen auf gleitender Basis (kumulative Balance am Wochenstart)
    wr, cum2 = {}, float(start)
    # einfache Reihenfolge nach Kalenderwoche reicht fuer Korrelationszwecke
    saldo = defaultdict(float)
    for (yj, wj), pnl in woche_pnl.items():
        saldo[(yj, wj)] = pnl
    cum2 = float(start)
    for w in sorted(saldo):
        wr[w] = saldo[w] / cum2 if cum2 > 0 else None
        cum2 += saldo[w]
    return renditen, wr, quelle


def main():
    d = json.loads(RESULTS.read_text(encoding="utf-8"))
    prod = {x["id"]: x for x in d["ergebnisse"]}
    con = sqlite3.connect(DB_COPY)
    pfade = {}
    for sid, pfad in con.execute(
            "SELECT signal_id, path FROM trade_files "
            "ORDER BY fetched_at DESC"):
        if sid not in pfade:
            pfade[sid] = pfad
    greens = [e for e in d["ergebnisse"] if e["ampel"] == "🟢"]
    yellows = [e for e in d["ergebnisse"] if e["ampel"] == "🟡"]

    series_m, series_w, meta = {}, {}, {}
    for e in greens + yellows:
        sid = e["id"]
        pfad = pfade.get(sid)
        if not pfad or not Path(pfad).exists():
            continue
        trades, beweg, _, _ = parse_csv(Path(pfad))
        if not trades:
            continue
        rm, rw, q = monatspunkte(trades, beweg,
                                 e.get("kapitalbasis_verwendet_usd"))
        series_m[sid], series_w[sid] = rm, rw
        symbole = sorted({t.sym for t in trades})
        meta[sid] = (e["name"], e["quelle"] or "mql5", symbole, len(trades))

    print(f"Signale mit Monatsreihen: {len(series_m)}")
    # Gemeinsamer Zeitraum
    alle_monate = sorted({m for s in series_m.values() for m in s})
    print("Monate insgesamt:", alle_monate[0], "…", alle_monate[-1],
          f"({len(alle_monate)})")

    # --- Korrelationen: Empfehlungs-Trio (Monate, gemeinsamer Raum) ---
    def corr_matrix(sids, serie):
        gemeinsame = None
        for s in sids:
            menge = {m for m, v in serie[s].items() if v is not None}
            gemeinsame = menge if gemeinsame is None else gemeinsame & menge
        monate = sorted(gemeinsame or set())
        rows = {s: [serie[s][m] for m in monate] for s in sids}
        out = {}
        for i, a in enumerate(sids):
            for b in sids[i + 1:]:
                c = pearson(rows[a], rows[b])
                out[(a, b)] = (c, len(monate))
        return out, monate

    trio = [sid for _q, sid, _n in EMPF if sid in series_m]
    out_m, monate_m = corr_matrix(trio, series_m)
    print(f"\n=== Empfehlungs-Trio, Monatsrenditen (gemeinsam {len(monate_m)} "
          f"Monate {monate_m[0]}–{monate_m[-1]}) ===")
    for (a, b), (c, n) in out_m.items():
        print(f"  {meta[a][0][:22]:<22} × {meta[b][0][:22]:<22}: r = "
              f"{c if c is None else round(c, 3)}  (n={n})")

    out_w, wochen = corr_matrix(trio, series_w)
    print(f"\n=== Trio, Wochenrenditen (n={len(wochen)}) ===")
    for (a, b), (c, n) in out_w.items():
        print(f"  {meta[a][0][:22]:<22} × {meta[b][0][:22]:<22}: r = "
              f"{c if c is None else round(c, 3)}  (n={n})")

    # --- chronologische Stabilität (Monate, erste vs. zweite Hälfte) ---
    if len(monate_m) >= 6:
        halbe = len(monate_m) // 2
        teile = [monate_m[:halbe], monate_m[halbe:]]
        print("\n=== Stabilität: Monatshälften ===")
        for (a, b) in out_m:
            for ti, teils in enumerate(teile):
                ra = [series_m[a][m] for m in teils if series_m[a].get(m) is not None]
                rb = [series_m[b][m] for m in teils if series_m[b].get(m) is not None]
                if len(ra) >= 3 and len(rb) >= 3 and len(ra) == len(rb):
                    c = pearson(ra, rb)
                    if c is not None:
                        print(f"  {meta[a][0][:18]:<18} × {meta[b][0][:18]:<18}"
                              f" Hälfte {ti + 1}: r = {round(c, 3)} (n={len(ra)})")

    # --- Gemeinsame Verlustmonate (alle 23) ---
    print("\n=== Verlustmonate je Signal (Monatsrendite < 0) ===")
    for sid in sorted(series_m, key=lambda s: meta[s][0]):
        vm = [m for m, v in series_m[sid].items() if v is not None and v < 0]
        if vm:
            print(f"  {meta[sid][0][:30]:<30} {vm}")

    # --- Grün-grün Korrelationen (alle 7 Grünen, paarweise) ---
    print("\n=== Alle Paare der 7 Grünen (Monate, Schnittmenge ≥ 5) ===")
    gids = [s for s in series_m if prod[s]["ampel"] == "🟢"]
    for i, a in enumerate(gids):
        for b in gids[i + 1:]:
            ma = {m for m, v in series_m[a].items() if v is not None}
            mb = {m for m, v in series_m[b].items() if v is not None}
            gemeinsame = sorted(ma & mb)
            if len(gemeinsame) < 5:
                continue
            ra = [series_m[a][m] for m in gemeinsame]
            rb = [series_m[b][m] for m in gemeinsame]
            c = pearson(ra, rb)
            if c is not None:
                print(f"  {meta[a][0][:20]:<20} × {meta[b][0][:20]:<20}: "
                      f"r = {round(c, 3)} (n={len(gemeinsame)})")

    # --- Überlappung offener Positionen im Trio (Stundenraster) ---
    print("\n=== Gemeinsame offene Exposure des Trios (Stundenraster) ===")
    kurven = {}
    for sid in trio:
        pfad = pfade[sid]
        trades, _, _, _ = parse_csv(Path(pfad))
        ereignisse = []
        for t in trades:
            if t.op and t.cl:
                vorz = 1 if t.typ == "buy" else -1
                ereignisse.append((t.op, vorz, t.vol, t.sym))
                ereignisse.append((t.cl, -vorz, -t.vol, t.sym))
        kurven[sid] = sorted(ereignisse)
    # gemeinsames Fenster
    start = max(min(e[0] for e in v) for v in kurven.values())
    ende = min(max(e[0] for e in v) for v in kurven.values())
    # stundenweiser Zustand je Signal (nur Richtung, Lots je Symbol grob)
    if ende > start:
        stunden = []
        z = start
        from datetime import timedelta
        while z <= ende:
            stunden.append(z)
            z += timedelta(hours=1)
        # Zustand je Stunde: Summe offener richtungszeichen
        def zustand(sid, zeit):
            offen = 0
            lots = 0.0
            for tz, dz, vz, _sym in kurven[sid]:
                if tz <= zeit:
                    offen += dz
                    lots += dz * vz
            return offen, lots
        # effizienter: Sweep
        gemeinsam_drei = 0
        total = 0
        idx = {s: 0 for s in kurven}
        zustaende = {s: (0, 0.0) for s in kurven}
        for zeit in stunden:
            alle_offen = True
            for s in kurven:
                while idx[s] < len(kurven[s]) and kurven[s][idx[s]][0] <= zeit:
                    _, dz, vz, _ = kurven[s][idx[s]]
                    o, l = zustaende[s]
                    zustaende[s] = (o + dz, l + dz * vz)
                    idx[s] += 1
                if zustaende[s][0] == 0:
                    alle_offen = False
            total += 1
            if alle_offen:
                gemeinsam_drei += 1
        print(f"  Fenster {start:%Y-%m-%d} – {ende:%Y-%m-%d}: "
              f"{total} Stunden, davon alle drei gleichzeitig offen: "
              f"{gemeinsam_drei} "
              f"({100 * gemeinsam_drei / max(total, 1):.1f} %)")

    # Vollmatrix als CSV
    aus = HIER / "portfolio_korrelation.csv"
    with aus.open("w", encoding="utf-8-sig") as fh:
        fh.write("Signal A;Signal B;r_Monat;n_Monate;r_Woche;n_Wochen\n")
        sids = list(series_m)
        for i, a in enumerate(sids):
            for b in sids[i + 1:]:
                ma = {m for m, v in series_m[a].items() if v is not None}
                mb = {m for m, v in series_m[b].items() if v is not None}
                gm = sorted(ma & mb)
                cm = pearson([series_m[a][m] for m in gm],
                             [series_m[b][m] for m in gm]) if len(gm) >= 3 else None
                wa = {w for w, v in series_w[a].items() if v is not None}
                wb = {w for w, v in series_w[b].items() if v is not None}
                gw = sorted(wa & wb)
                cw = pearson([series_w[a][w] for w in gw],
                             [series_w[b][w] for w in gw]) if len(gw) >= 3 else None
                fh.write(f"{meta[a][0]};{meta[b][0]};"
                         f"{'' if cm is None else round(cm, 3)};{len(gm)};"
                         f"{'' if cw is None else round(cw, 3)};{len(gw)}\n")
    print(f"\nVollmatrix: {aus}")


if __name__ == "__main__":
    main()
