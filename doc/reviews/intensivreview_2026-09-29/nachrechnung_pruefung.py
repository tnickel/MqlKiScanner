# -*- coding: utf-8 -*-
"""
Unabhängige Nachrechnung des Intensiv-Reviews 2026-09-29/30 (Ziellauf
2026-09-30_025355_970680_c65bf5cd).

Bewusst OHNE Import von src/mqlkiscanner: eigener CSV-Parser, eigene
Kennzahlen. Vergleichsseite („Produktivwert") kommt ausschließlich aus
data/runs/.../results.json und der forensik-Tabelle (DB-Kopie).

Ausgabe: nachrechnung.csv + Konsolen-Zusammenfassung.
Nur lesend; Produktivdaten werden nicht verändert.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HIER = Path(__file__).resolve().parent
PROJEKT = HIER.parent.parent.parent          # .../SignalKiScanner
DB_COPY = HIER / "tmp" / "review_copy.db"
RESULTS = (PROJEKT / "data" / "runs" / "2026-09-30_025355_970680_c65bf5cd"
           / "results.json")

# Prüf-Signale: (id, kurzname) — Auswahl siehe review.md Abschnitt Nachrechnung
PRUEF_IDS = [2349227, 2063644, 2084818, 2327790, 2014074, 2012139,
             2308093, 2048285, 2000028]

XAU_KONTRAKT = 100.0   # 1 Lot XAUUSD = 100 USD je 1 USD Bewegung (Projektregel)
SCHOCK_USD = 50.0      # Schockszenario 50 USD Goldbewegung


def _num(s: str | None):
    """MT5/Pelican-Zahlen: Tausendertrennzeichen Leerzeichen."""
    if s is None:
        return None
    s = s.strip().replace("\u00a0", " ").replace(" ", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _t(s: str):
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


class Trade:
    __slots__ = ("op", "cl", "typ", "vol", "sym", "p_open", "p_close",
                 "comm", "swap", "profit", "sl", "kommentar", "netto")

    def __init__(self, op, cl, typ, vol, sym, p_open, p_close, comm, swap,
                 profit, sl, kommentar):
        self.op, self.cl, self.typ, self.vol, self.sym = op, cl, typ, vol, sym
        self.p_open, self.p_close = p_open, p_close
        self.comm, self.swap, self.profit = comm, swap, profit
        self.sl, self.kommentar = sl, kommentar
        self.netto = (profit or 0.0) + (comm or 0.0) + (swap or 0.0)


def parse_csv(pfad: Path):
    """Eigenständiger Parser für beide Formate (MT4-Orderbuch 13 Spalten,
    MT5/Pelican-Positionen 11 Spalten). Gibt (trades, kontobewegungen,
    roh_zeilen, typen) zurück. Kontobewegungen = (zeit, betrag)."""
    text = pfad.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    if not text:
        return [], [], 0, {}
    kopf = text[0].split(";")
    breit = len(kopf)
    trades, bewegungen = [], []
    typen = defaultdict(int)
    roh = 0
    for zeile in text[1:]:
        roh += 1
        f = zeile.split(";")
        if len(f) < 10:
            typen["<kurz>"] += 1
            continue
        f += [""] * (breit - len(f))
        typ = f[1].strip()
        typen[typ] += 1
        # Spalten: MT4-Orderbuch 13 Spalten
        #   0 Time 1 Type 2 Volume 3 Symbol 4 Price 5 S/L 6 T/P 7 Time
        #   8 Price 9 Commission 10 Swap 11 Profit 12 Comment
        # MT5/Pelican 11 Spalten
        #   0 Time 1 Type 2 Volume 3 Symbol 4 Price 5 Volume 6 Time 7 Price
        #   8 Commission 9 Swap 10 Profit
        i_profit = 11 if breit >= 13 else 10
        i_comm = 9 if breit >= 13 else 8
        i_swap = 10 if breit >= 13 else 9
        if typ.lower() == "balance":
            bewegungen.append((_t(f[0]), _num(f[i_profit]) or 0.0))
            continue
        if typ.lower() in ("buy", "sell"):
            sym = f[3].strip()
            if sym.lower() == "profit":       # MT4-Summenzeile
                continue
            kommentar = f[12].strip() if breit >= 13 else ""
            if "cancelled" in kommentar.lower():
                continue                      # nie ausgeführter Pending-Order
            vol = _num(f[2])
            profit = _num(f[i_profit])
            comm = _num(f[i_comm])
            swap = _num(f[i_swap])
            sl = _num(f[5]) if breit >= 13 else None
            p_close = _num(f[8]) if breit >= 13 else _num(f[7])
            cl = _t(f[7]) if breit >= 13 else _t(f[6])
            trades.append(Trade(_t(f[0]), cl, typ.lower(), vol, sym,
                                _num(f[4]), p_close, comm, swap, profit,
                                sl, kommentar))
        else:
            typen[f"<sonst:{typ}>"] += 1
    trades = [t for t in trades if t.netto is not None]
    trades.sort(key=lambda t: (t.cl or t.op or datetime.min, t.op or datetime.min))
    return trades, bewegungen, roh, dict(typen)


def virtual_dd(trades, bewegungen, fallback_basis):
    """Unabhängige Implementierung der „virtuellen Trading-Kurve":
    Start = Netto-Kontobewegungen vor dem ersten Trade (kein positives
    Startereignis -> externe/virtuelle Fallback-Basis), Kurve nur aus
    Trade-Netto je Close-Zeit. Gleich-Sekunden-Ereignisse werden wie im
    Produkt als EIN Batch gebucht (fsum) — das CSV legt keine Reihenfolge
    innerhalb einer Sekunde fest. Zusätzlich wird der unbatched-Wert als
    Unsicherheitsband geführt."""
    first_open = min((t.op or t.cl for t in trades), default=None)
    vor = [b for b in bewegungen if b[0] and first_open and b[0] <= first_open]
    hat_positiv = any(a > 0 for _, a in vor)
    start = sum(a for _, a in vor)
    quelle = "csv"
    if not hat_positiv and fallback_basis:
        start = fallback_basis
        quelle = "fallback"
    elif not hat_positiv:
        start = start if start != 0 else fallback_basis or 0.0
        quelle = "fallback-netto" if start else "keine"

    punkte: dict = defaultdict(list)
    for t in trades:
        punkte[t.cl or t.op].append(t.netto)
    bal = peak = float(start)
    dd_usd = pct_event = max_rel = 0.0
    for z in sorted(punkte):
        bal += math.fsum(punkte[z])
        if bal > peak:
            peak = bal
        d = peak - bal
        rel = (100.0 * d / peak) if peak > 0 else (100.0 if d > 0 else 0.0)
        if d > dd_usd:
            dd_usd, pct_event = d, rel
        if rel > max_rel:
            max_rel = rel
    # unbatched (willkürliche Reihenfolge innerhalb der Sekunde)
    bal2 = peak2 = float(start)
    dd_usd_unbatched = 0.0
    for t in trades:
        bal2 += t.netto
        if bal2 > peak2:
            peak2 = bal2
        if peak2 - bal2 > dd_usd_unbatched:
            dd_usd_unbatched = peak2 - bal2
    dd_pct = pct_event
    return (start, quelle, dd_usd, dd_pct, max_rel, bal, peak,
            dd_usd_unbatched)


def kennzahlen(trades, bewegungen, kapitalbasis_produkt, realbasis_proxy=None):
    k: dict = {}
    k["trades"] = len(trades)
    if not trades:
        return k
    k["netto_pnl"] = sum(t.netto for t in trades)
    gewinne = [t.netto for t in trades if t.netto > 0]
    verluste = [t.netto for t in trades if t.netto <= 0]
    k["gewinne"] = len(gewinne)
    k["verluste"] = len(verluste)
    k["winrate"] = 100.0 * len(gewinne) / len(trades)
    k["pf"] = (sum(gewinne) / abs(sum(verluste))) if verluste and sum(verluste) != 0 else None

    # Duplikate
    sig = defaultdict(int)
    for t in trades:
        sig[(t.op, t.typ, t.sym, t.vol, t.cl, t.p_close, round(t.netto, 2))] += 1
    k["duplikate"] = sum(v - 1 for v in sig.values() if v > 1)

    # Zeitraum
    erste = min(t.op or t.cl for t in trades)
    letzte = max(t.cl or t.op for t in trades)
    k["von"], k["bis"] = erste, letzte
    k["monate"] = max((letzte - erste).days / 30.44, 1e-9)

    # Virtuelle Trading-Kurve (unabhängige Implementierung der Produkt-Def.,
    # inkl. Sekunden-Batching) + unbatched-Unsicherheitsband
    start, q, dd_usd, dd_pct, dd_max_rel, end_bal, peak_bal, dd_unb = virtual_dd(
        trades, bewegungen, kapitalbasis_produkt)
    k["basis"] = start
    k["basis_quelle"] = q
    k["end_balance"] = end_bal
    k["dd_usd"] = dd_usd
    k["dd_pct_peak"] = dd_pct          # entspricht Produkt trading_dd.pct
    k["dd_pct_max_rel"] = dd_max_rel   # Wert, der in die Schranke gehört
    k["dd_usd_unbatched"] = dd_unb

    # Sensitivität: DD % bezogen auf Realbalance-Proxy (pelik: aktuelle
    # echte Balance laut Plattform als Endestand -> Rueckrechnung Startbasis)
    if realbasis_proxy and realbasis_proxy > 0:
        real_start = realbasis_proxy - k["netto_pnl"]
        if real_start > 0:
            k["real_start_proxy"] = real_start
            k["dd_pct_real"] = 100.0 * dd_usd / max(peak_bal - start + real_start, 1e-9)
            k["ertrag_real_pct_monat"] = (100.0 * k["netto_pnl"] / real_start
                                          / k["monate"])

    # Monatsrenditen (PnL / Balance am Monatsanfang, virtuelle Kurve)
    monat_pnl = defaultdict(float)
    for t in trades:
        monat_pnl[(t.cl or t.op).strftime("%Y-%m")] += t.netto
    monatsrenditen = {}
    cum = float(start)
    for monat in sorted(monat_pnl):
        monatsrenditen[monat] = (100.0 * monat_pnl[monat] / cum
                                 if cum > 0 else None)
        cum += monat_pnl[monat]
    k["monatsrenditen"] = monatsrenditen
    k["ertrag_linear_pct_monat"] = (100.0 * k["netto_pnl"] / start / k["monate"]
                                    if start and start > 0 else None)
    werte = [v for v in monatsrenditen.values() if v is not None]
    k["ertrag_median_monat"] = statistics.median(werte) if werte else None

    # Verlustserie
    serie, max_serie, serie_usd, max_serie_usd = 0, 0, 0.0, 0.0
    for t in trades:
        if t.netto <= 0:
            serie += 1
            serie_usd += t.netto
            if serie > max_serie:
                max_serie, max_serie_usd = serie, serie_usd
        else:
            serie, serie_usd = 0, 0.0
    k["max_verlustserie"] = max_serie
    k["verlustserie_usd"] = max_serie_usd

    # Martingale: Volumen des Folge-Trades (gleiches Symbol, Close-Reihenfolge)
    # nach Verlust vs. Verlust-Trade
    ratios = []
    letzter: dict[str, Trade] = {}
    for t in trades:
        vor = letzter.get(t.sym)
        if vor is not None and vor.netto < 0 and t.vol and vor.vol:
            ratios.append(t.vol / vor.vol)
        letzter[t.sym] = t
    k["martingale_median_ratio"] = statistics.median(ratios) if ratios else None
    k["martingale_n"] = len(ratios)

    # Gleichzeitige Positionen + Netto-Lots am Peak (alle Symbole zusammen)
    ereignisse = []
    for t in trades:
        if t.op and t.cl:
            vorz = 1 if t.typ == "buy" else -1
            ereignisse.append((t.op, 1, vorz, t.vol))
            ereignisse.append((t.cl, 0, -vorz, t.vol))
    ereignisse.sort(key=lambda e: (e[0], e[1]))
    offen, lots, peak_pos, peak_lots = 0, 0.0, 0, 0.0
    for _, _, dv, vol in ereignisse:
        offen += dv
        lots += dv * vol
        if offen > peak_pos:
            peak_pos, peak_lots = offen, lots
    k["peak_positionen"] = peak_pos
    k["peak_netto_lots"] = peak_lots
    syms = {t.sym for t in trades}
    if len(syms) == 1 and ("XAU" in next(iter(syms)).upper()):
        k["schock_usd"] = abs(peak_lots) * XAU_KONTRAKT * SCHOCK_USD
    return k


def lade_produktwerte():
    d = json.loads(RESULTS.read_text(encoding="utf-8"))
    e = {x["id"]: x for x in d["ergebnisse"]}
    con = sqlite3.connect(DB_COPY)
    foren = {}
    for sid, j in con.execute("SELECT signal_id, json FROM forensik"):
        try:
            foren[sid] = json.loads(j)
        except Exception:
            pass
    con.close()
    return e, foren


def main():
    ergebnisse, forensik = lade_produktwerte()
    con = sqlite3.connect(DB_COPY)
    pfade = {}
    for sid, pfad, sha in con.execute(
            "SELECT signal_id, path, sha256 FROM trade_files"):
        if sid not in pfade:                      # jüngster Stand je Signal
            pfade[sid] = (Path(pfad), sha)
    con.close()

    zeilen = [["Quelle/Signal", "Kennzahl", "Produktivwert", "Unabhaengiger Wert",
               "Differenz/Toleranz", "Grundlage", "Auswirkung auf Auswahl/Ampel/Bericht"]]

    for sid in PRUEF_IDS:
        prod = ergebnisse.get(sid)
        if prod is None:
            print(f"!! {sid} nicht in results.json")
            continue
        pfad, sha = pfade.get(sid, (None, None))
        if pfad is None or not pfad.exists():
            print(f"!! {sid} Trade-Datei fehlt: {pfad}")
            continue
        ist_sha = hashlib.sha256(pfad.read_bytes()).hexdigest()
        assert ist_sha == sha, f"SHA-Abweichung {sid}!"
        trades, beweg, roh, typen = parse_csv(pfad)
        real_proxy = ((forensik.get(sid, {}).get("kapitalbasis") or {})
                      .get("webseite_balance_usd"))
        k = kennzahlen(trades, beweg, prod.get("kapitalbasis_verwendet_usd")
                       or prod.get("kapitalbasis_usd"), real_proxy)
        name = f"{prod.get('quelle') or 'mql5'}/{sid} {prod['name'][:28]}"
        f = forensik.get(sid, {})
        ref = lambda pf, d=None: (f.get(pf) if pf in f else d)

        def add(kennz, pw, uw, tol, grund, wirkung=""):
            zeilen.append([name, kennz, pw, uw, tol, grund, wirkung])

        add("Trade-Zeilen (CSV roh)", "—", roh, "info",
            f"SHA {sha[:12]}…, {pfad.name}")
        add("Trades geparst (ohne Pending/Summe)",
            ref("peak_exposure.positionen") and "—", k["trades"], "info",
            f"Typen: {typen}")
        add("Netto-PnL USD", "—", round(k["netto_pnl"], 2), "info",
            "Summe Profit+Commission+Swap")
        add("Winrate %", prod.get("winrate_pct"),
            round(k["winrate"], 1), "±0.5",
            "gewonnen/gesamt (Close-Reihenfolge)")
        add("Profit Factor", prod.get("pf"), round(k["pf"], 2) if k["pf"] else None,
            "±0.05", "Bruttogewinn/Bruttoverlust")
        add("Duplikate", "—", k["duplikate"], "=0 erwartet",
            "Schlüssel Open+Close+Vol+PnL")
        add("Trading-DD % (Sekunden-Batch, wie Produkt)", prod.get("trading_dd_pct"),
            round(k["dd_pct_peak"], 2), "±0.05",
            f"USD {round(k['dd_usd'],2)} (Prod {ref('trading_dd.usd')}); "
            f"max-rel {round(k['dd_pct_max_rel'],2)} %")
        add("DD-USD unbatched (Intra-Sekunde-Band)", "—",
            round(k["dd_usd_unbatched"], 2), "info",
            "wahre Reihenfolge gleichzeitiger Closes im CSV unbestimmbar — "
            "obere Schätzung; Grid-Körbe systematisch betroffen")
        add("Startbasis virtuelle Kurve USD",
            ((f.get("kapitalbasis") or {}).get("usd")),
            round(k["basis"], 2), "±1",
            f"Quelle: {k['basis_quelle']} "
            f"(Prod {(f.get('kapitalbasis') or {}).get('quelle')}; "
            f"Realbalance Plattform {real_proxy})")
        if "dd_pct_real" in k:
            add("Sensitivität: DD % auf Realbasis-Proxy", "—",
                round(k["dd_pct_real"], 2), "info",
                f"Startbasis real ≈ {round(k['real_start_proxy'],0)} statt "
                f"{round(k['basis'],0)} — gleiche USD-DD, anderer Nenner")
            add("Sensitivität: Ertrag %/Monat auf Realbasis", "—",
                round(k["ertrag_real_pct_monat"], 1), "info",
                "Prod-Ertrag bezieht sich u. U. auf andere Basis")
        add("End-Balance USD", "—", round(k["end_balance"], 2), "info",
            "Basis + Σ netto")
        add("Ertrag/Monat % (linear, eigene Basis)",
            prod.get("ertrag_monat_pct"),
            round(k["ertrag_linear_pct_monat"], 2) if k["ertrag_linear_pct_monat"] else None,
            "Def. vergleichen", f"{round(k['monate'],1)} Monate "
            f"({k['von']:%Y-%m-%d}–{k['bis']:%Y-%m-%d})")
        add("Ertrag/Monat % (Median Monatsrenditen)", "—",
            round(k["ertrag_median_monat"], 2) if k["ertrag_median_monat"] else None,
            "info", "Monats-PnL / Balance am Monatsanfang")
        add("Max. Verlustserie (Trades)", prod.get("max_verlustserie"),
            k["max_verlustserie"], "±0",
            f"Summe {round(k['verlustserie_usd'],2)} USD "
            f"(Prod {prod.get('verlustserie_usd')})")
        add("Peak gleichzeitige Positionen", prod.get("peak_positionen"),
            k["peak_positionen"], "±0", "Intervall-Überlappung")
        add("Peak Netto-Lots", prod.get("peak_netto_lots"),
            round(k["peak_netto_lots"], 2), "±0.02",
            "signierte Summe am Positions-Peak")
        if "schock_usd" in k:
            add("Schock 50 USD am Peak (USD)",
                (f.get("peak_exposure") or {}).get("schock_usd"),
                round(k["schock_usd"], 0), "±5",
                "XAUUSD 100 USD/Lot/1-$-Move")
        add("Martingale Median-Ratio", ref("martingale_flag"),
            (round(k["martingale_median_ratio"], 3)
             if k["martingale_median_ratio"] is not None else None),
            "Schwelle 1.3", f"n={k['martingale_n']}")
        # S/L-Nachweis nur MT4-Orderbuch (S/L-Spalte vorhanden)
        if (f.get("stop_evidence") or "") and typen and any(
                "Buy" in t or "Sell" in t for t in typen):
            mit_sl = sum(1 for t in trades if t.sl is not None)
            add("Trades mit S/L im Orderbuch", f.get("stop_nachweis"),
                f"{mit_sl}/{len(trades)}", "vergleichen",
                "S/L-Spalte != leer")
        if sid in (2063644, 2084818, 2014074, 2012139, 2048285, 2000028):
            add("Monitor-Trade-EQ-DD %", prod.get("monitor_trade_eq_dd_pct"),
                "s. Sensitivitätszeilen", "info",
                "Monitor wertet volle Trade-Kurve auf echter Basis; hier: "
                f"virtuelle Kurve DD {round(k['dd_pct_peak'],2)} % "
                f"({round(k['dd_usd'],0)} USD)")
        print(f"✓ {sid} {prod['name'][:40]} — netto {k['netto_pnl']:.0f} USD, "
              f"DD {k['dd_pct_peak']:.2f} %, {k['trades']} Trades")

    aus = HIER / "nachrechnung.csv"
    with aus.open("w", newline="", encoding="utf-8-sig") as fh:
        csv.writer(fh, delimiter=";").writerows(zeilen)
    print(f"\nGeschrieben: {aus} ({len(zeilen) - 1} Zeilen)")


if __name__ == "__main__":
    sys.exit(main())
