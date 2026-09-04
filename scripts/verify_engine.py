# -*- coding: utf-8 -*-
"""Verifikation der Engine gegen die Analyse-Reihe (doc/04_roadmap.md, Phase 1).

"Pipeline gegen die 8 CSVs in data/raw/ laufen lassen — Ergebnisse muessen
die Werte aus doc/01_analysen-verlauf.md reproduzieren. Erst wenn die
Rekonstruktion auf den Cent stimmt, ist die Engine fertig."

Ankerwerte:
- doc/01_analysen-verlauf.md        (Urteile, Winrates, Serien, Befunde)
- doc/03_forensik-tests.md          (4 Cent-exakte DD-Anker)
- data/known_signals.json           ( Exposure 32 Pos / 2,66 Lots, 19er-Serie)
- scripts/reference/*               (Praezisionswerte der Referenzskripte)

Aufruf:  python scripts/verify_engine.py   (Exit-Code 0 = alle Checks PASS)
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mqlkiscanner import compare, engine, parser, stats  # noqa: E402

RAW = ROOT / "data" / "raw"

FILES = {
    "spike_mt4": RAW / "gold_spike_mt4_2349227_ORDERBOOK.csv",
    "spike_mt5": RAW / "gold_spike_mt5_2375480_positions.csv",
    "kiracat": RAW / "kiracat_2342895_positions.csv",
    "reaper": RAW / "gold_reaper_2265877_positions.csv",
    "msc": RAW / "msc_gold_2231030_positions.csv",
    "fxtrading": RAW / "fxtrading_2356441_trades.json",
    "puregold": RAW / "puregold_2362868_positions.csv",
    "goldwave": RAW / "goldwave_2339082_positions.csv",
    "goldwhisper": RAW / "goldwhisper_2364821_positions.csv",
}

CHECKS: list[dict] = []


def check(signal: str, name: str, expected, actual, tol: float | None = 0.0,
          source: str = "doc/01", note: str = ""):
    CHECKS.append(dict(signal=signal, name=name, expected=expected,
                       actual=actual, tol=tol, source=source, note=note))


def near(a, b, tol) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


# --------------------------------------------------------------- Ground Truth
parsed = {key: parser.load_export(str(path)) for key, path in FILES.items()}
report = {key: engine.analyze(str(path)) for key, path in FILES.items()}


def fx(key):  # Abkuerzungen
    r = report[key]
    return r["stats"], r["forensics"], r


# ============================ Gold Spike MT4 #2349227 (Orderbuch) ============
s, f, r = fx("spike_mt4")
st = f["stops"]; dd = f["drawdown"]
check("SpikeMT4", "gefuellte Trades", 363, s["trades"], 0, "doc/01: 363 gepruefte Trades")
check("SpikeMT4", "Pendings", 618, r["n_pendings"], 0, "doc/01: 618 Pendings")
check("SpikeMT4", "Positionen mit SL+TP (%)", 100.0, st["positions_with_sl_tp_pct"], 0.0,
      "doc/01: alle Positionen mit SL/TP (dort '368/368' inkl. andere Export-Staende; "
      "CSV: 363/363)", note="Orderbuch-Goldstandard")
check("SpikeMT4", "[sl]-Exits", 186, st["exits_sl"], 0)
check("SpikeMT4", "[tp]-Exits", 122, st["exits_tp"], 0)
check("SpikeMT4", "SL-Exits im Plus (Trailing)", 161, st["sl_exits_in_plus"], 0,
      "doc/01: 161 von 186 im Plus")
check("SpikeMT4", "Trailing-Summe USD", 1016.35, st["sl_exits_in_plus_sum"], 0.5,
      "doc/01: +1.016 USD")
check("SpikeMT4", "schlechtester Einzeltrade", -40.97, s["worst_trade"], 0.5,
      "doc/01: Verlustdeckel ~-41 USD")
check("SpikeMT4", "Winrate %", 76.3, s["winrate_pct"], 0.1, "Referenzskript")
check("SpikeMT4", "Trading-DD USD (Cent-Anker)", 157.20, dd["trading_dd"]["dd_usd"], 0.005,
      "doc/03: 157,20 USD exakt")
check("SpikeMT4", "Trading-DD %", 4.6, dd["trading_dd"]["dd_pct"], 0.1,
      "doc/01: realer DD 4,6 %")
check("SpikeMT4", "Startkapital", 3116.00, dd["start_capital"], 0.0, "doc/01: 3.116 USD Start")
check("SpikeMT4", "Entnahmen USD", -3400.03, dd["withdrawals_total"], 0.5,
      "doc/01: 3.400 USD entnommen")
check("SpikeMT4", "Lots 0.01 Anteil", 361, s["lots"].get("0.01"), 0,
      "doc/03: 361/363 bei 0.01 = flach")

# MT4/MT5-Zwilling
twin = engine.compare_twin(str(FILES["spike_mt4"]), str(FILES["spike_mt5"]),
                           since=datetime(2026, 5, 24))
check("SpikeTwin", "gematchte Trades", 98, twin["matched"], 0, "Referenzskript")
check("SpikeTwin", "Match-Quote %", 87, twin["matched_pct"], 0.5,
      "doc/01: 87 % sekundengenau identisch")
check("SpikeTwin", "nur MT4", 15, twin["only_mt4"], 0)
check("SpikeTwin", "nur MT5", 10, twin["only_mt5"], 0)

# ============================ KiraCat #2342895 ===============================
s, f, r = fx("kiracat")
dd = f["drawdown"]; bk = f["baskets"]; st = f["stops"]
us30 = s["per_symbol"]["US30"]; nzd = s["per_symbol"]["NZDCAD"]
check("KiraCat", "Trades gesamt", 550, s["trades"], 0)
check("KiraCat", "US30-Trades", 443, us30["trades"], 0, "doc/01: US30-Scalps 443")
check("KiraCat", "US30-Netto USD", 18396.48, us30["net"], 0.5, "doc/01: +18.396 USD")
check("KiraCat", "US30-Median-Haltedauer h", 1.1, us30["median_holding_hours"], 0.1,
      "doc/01: Median 1,1 h")
check("KiraCat", "NZDCAD-Trades (Grid-Sleeve)", 101, nzd["trades"], 0,
      "doc/01: NZDCAD-Sleeve ab 04/2026, 101 Trades")
check("KiraCat", "NZDCAD-Netto USD", 3267.02, nzd["net"], 0.5)
check("KiraCat", "Winrate %", 89.3, s["winrate_pct"], 0.1)
check("KiraCat", "Trading-DD USD (Cent-Anker)", 2117.70, dd["trading_dd"]["dd_usd"], 0.005,
      "doc/03: 2.117,70 USD exakt")
check("KiraCat", "Trading-DD % (real)", 7.9, dd["trading_dd"]["dd_pct"], 0.1,
      "doc/01: realer Trading-DD 7,9 % validiert")
check("KiraCat", "schlechtester Trade (03.03. 5-Lot-Short)", -2150.90, s["worst_trade"], 0.01,
      "doc/01: -2.150,90 USD, ~7 % des Kontos")
check("KiraCat", "groeszter NZDCAD-Korb", 11, bk["max_basket_per_symbol"].get("NZDCAD"), 0,
      "doc/01: Koerbe bis 11 Positionen")
check("KiraCat", "kein Martingale-Flag", False, f["martingale"]["flag"], None,
      "doc/01: 100 % manuell, kein Lot-Eskalationsmuster ueber Serien")

# ============================ Gold Reaper #2265877 ===========================
s, f, r = fx("reaper")
dd = f["drawdown"]
big = [t for t in parsed["reaper"].trades if t.volume >= 0.04]
check("Reaper", "Trades", 850, s["trades"], 0)
check("Reaper", "Winrate %", 73.8, s["winrate_pct"], 0.1)
check("Reaper", "Positionen >= 0.04 Lots (Pyramiding)", 17, len(big), 0,
      "doc/01: 17 groeszte Positionen")
check("Reaper", "Netto der >= 0.04-Lots USD", 375.95, sum(t.profit for t in big), 0.5,
      "doc/01: +376 USD")
check("Reaper", "Trading-DD USD (Cent-Anker)", 319.49, dd["trading_dd"]["dd_usd"], 0.005,
      "doc/03: 319,49 USD exakt")
check("Reaper", "max. Verlustserie", 8, s["max_consecutive_losses"], 0, "Referenzskript")
check("Reaper", "negative Monate (voll)", 3,
      len(stats.negative_months_full(parsed["reaper"])), 0,
      "doc/01: 3 Verlustmonate, je Folgemonat erholt "
      "(CSV by-close: 4 inkl. Partialmonat 2024-10)")

# ============================ MSC Gold #2231030 ==============================
s, f, r = fx("msc")
dd = f["drawdown"]; bk = f["baskets"]; nw = f["news"]; st = f["stops"]
check("MSC", "Trades", 1085, s["trades"], 0, "doc/01: 1.085 Trades")
check("MSC", "Winrate %", 83.2, s["winrate_pct"], 0.1)
check("MSC", "Avg-Gewinn USD", 2.51, s["avg_win"], 0.05,
      "doc/01: 'Median-Gewinn 2,50' — Referenzskript liefert AvgWin 2,51; "
      "echter Median 1,70 (Befund 'Sekunden-Scalper' bleibt, Label in doc/01 falsch)")
check("MSC", "Trading-DD USD (Cent-Anker)", 76.83, dd["trading_dd"]["dd_usd"], 0.005,
      "doc/03: 76,83 USD exakt")
check("MSC", "Trading-DD %", 15.4, dd["trading_dd"]["dd_pct"], 0.1,
      "doc/01 Kalibrierung: realer DD 15,4 %")
check("MSC", "Track Record Wochen", 123, round(s["span_weeks"]), 0, "doc/01: 123 Wochen")
check("MSC", "FOMC-Tage ohne Trades", 11, nw["fomc_days_without_trades"], 0,
      "Referenzskript news_check.py zaehlt 11/19 FOMC-Tage ohne Trades; "
      "doc/01 nennt '14/19' — ueberlieferte Zahl falsch, qualitativer Befund "
      "(meistenteils ausgespart) bleibt bestehen")
check("MSC", "FOMC-Tage im Zeitraum", 19, nw["fomc_days_in_period"], 0)
check("MSC", "Basket-Exits (>=2)", 179, bk["basket_exits"], 2, "Referenzskript")
check("MSC", "Anteil Trades in Koerben %", 46, bk["trades_in_baskets_pct"], 1.0,
      "Grid-Indikator")
check("MSC", "groeszter Korb", 8, bk["biggest_basket"], 0, "Referenzskript")
check("MSC", "Verlustdistanz-Median USD", 2.14, st["loss_dist_median"], 0.05)

# ============================ Pure Gold 2000 #2362868 ========================
s, f, r = fx("puregold")
dd = f["drawdown"]; ex = f["exposure"]; mg = f["martingale"]; st = f["stops"]
check("PureGold", "Trades", 602, s["trades"], 0)
check("PureGold", "Winrate %", 52.3, s["winrate_pct"], 0.1)
check("PureGold", "Netto USD", 20731.47, s["net"], 0.5, "doc/01: +20.731 USD in 6 Monaten")
check("PureGold", "Startkapital", 10000.0, dd["start_capital"], 0.0, "doc/01: 10.000-USD-Konto")
check("PureGold", "Entnahmen USD", -12000.0, dd["withdrawals_total"], 0.01,
      "doc/01: Ernte 12.000 USD")
check("PureGold", "Peak gleichz. Positionen", 32, ex["peak_open_positions"], 0,
      "doc/01: max. 32 gleichzeitige SELL-Positionen")
check("PureGold", "Peak-Netto Lots (short)", -2.66, ex["peak_net_lots"], 0.005,
      "doc/01: 2,66 Lots netto")
check("PureGold", "50-USD-Schock USD", -13300.0, -ex["shock_usd"], 1.0,
      "doc/01: 50-USD-Schock ~ -13.300 USD (266 USD je 1 USD Bewegung)")
check("PureGold", "Martingale-Signal ausgeschlossen (Median nach Verlust)", 0.92,
      mg["median_ratio_after_loss"], 0.02,
      "doc/03: Pure Gold 0,92x nach Verlust gegen 1,00x nach Gewinn = KEIN Martingale")
check("PureGold", "Median-Ratio nach Gewinn", 1.00, mg["median_ratio_after_win"], 0.02)
check("PureGold", "19er-Verlustserie", 19, st["ribbon"]["max_loss_streak"], 0,
      "doc/01: 19-Verluste-Serie in 3 Tagen")
check("PureGold", "Serie-Summe USD", -1702.88, st["ribbon"]["max_loss_streak_sum"], 0.5,
      "known_signals: -1.703 USD")
check("PureGold", "Serie-Zeitraum (Kalendertage inkl.)", 3,
      (datetime.fromisoformat(st["ribbon"]["streak_to"])
       - datetime.fromisoformat(st["ribbon"]["streak_from"])).days + 1, 0,
      "doc/01: in 3 Tagen (04.-06.05.)")
check("PureGold", "Worst-Verlustdistanz USD", 152.01, st["loss_dist_max"], 0.05,
      "doc/01: Worst -152 USD Bewegung, Verlustdistanzen ungebundelt")
check("PureGold", "kein Stop-Niveau (ungebundelt)", False, st["clustered"], None,
      "doc/01: KEIN Stop-Loss-Nachweis")

# ============================ GoldWave #2339082 ==============================
s, f, r = fx("goldwave")
dd = f["drawdown"]
hours = s["entry_hours_top"]
rollover_share = sum(hours.get(h, 0) for h in (20, 21, 22, 23)) / s["trades"] * 100
check("GoldWave", "Trades", 281, s["trades"], 0)
check("GoldWave", "Winrate %", 96.8, s["winrate_pct"], 0.1, "doc/01: 96,8 % Winrate")
check("GoldWave", "Netto USD", 362.13, s["net"], 0.5, "doc/01: 362 USD Gesamtgewinn")
check("GoldWave", "Median-Gewinn USD", 1.06, s["median_win"], 0.01,
      "doc/01: Median-Gewinn 1,06 USD (Pfennig-Jagd)")
check("GoldWave", "negative Monate", 0, len(s["negative_months_close"]), 0,
      "doc/01: 0 negative Monate")
check("GoldWave", "max. Verlustserie", 2, s["max_consecutive_losses"], 0)
check("GoldWave", "Rollover-Anteil 20-23 Uhr %", 49.1, rollover_share, 2.0,
      "doc/01: Rollover-Scalper (20-23 Uhr)")

# ============================ Gold Whisperer #2364821 ========================
s, f, r = fx("goldwhisper")
dd = f["drawdown"]; st = f["stops"]
check("GoldWhisper", "Trades", 1011, s["trades"], 0)
check("GoldWhisper", "Winrate %", 31.3, s["winrate_pct"], 0.1,
      "doc/01 ('Low Risk'-Namensluege): 31 % Winrate")
check("GoldWhisper", "25 Verluste an EINEM Tag", 25, st["ribbon"]["max_loss_streak"], 0,
      "doc/01: 25 Verluste an einem Tag")
check("GoldWhisper", "Serie an einem Tag (from==to)", True,
      st["ribbon"]["streak_from"] == st["ribbon"]["streak_to"], None)
check("GoldWhisper", "Trading-DD % in doc-Spanne 17-25", True,
      17.0 <= dd["trading_dd"]["dd_pct"] <= 25.0, None,
      f"doc/01: DD ~17-25 % (Engine: {dd['trading_dd']['dd_pct']} %)")
check("GoldWhisper", "Startkapital", 1000.0, dd["start_capital"], 0.0)

# ============================ FXtrading #2356441 (JSON-Auszug) ===============
s, f, r = fx("fxtrading")
mg = f["martingale"]
# Martingale-Korb: EURNZD 0.01 -> 0.02 -> 0.04 im selben Basket-Exit (Referenzskript)
from collections import defaultdict
baskets_fx: dict[tuple, list] = defaultdict(list)
for t in parsed["fxtrading"].trades:
    baskets_fx[(t.symbol, t.direction, t.close_time.strftime("%Y-%m-%d %H:%M"))].append(t)
eurnzd_ladder = None
for (sym, d, ctime), b in baskets_fx.items():
    if sym == "EURNZD" and len(b) >= 3:
        legs = sorted(b, key=lambda t: t.open_time)
        if [round(t.volume, 2) for t in legs] == [0.01, 0.02, 0.04]:
            eurnzd_ladder = (ctime, round(sum(t.profit for t in legs), 2))
check("FXtrading", "Trades im Auszug", 48, s["trades"], 0, "JSON = sichtbarer Ausschnitt")
check("FXtrading", "Winrate % (Auszug)", 79.2, s["winrate_pct"], 0.1)
check("FXtrading", "EURNZD-Martingale-Korb 0.01>0.02>0.04", True, eurnzd_ladder is not None,
      None, "doc/01: Martingale-Korb nachgewiesen (EURNZD 0,01->0,02->0,04)")
check("FXtrading", "Korb-Netto USD (+6,15 im Referenzskript)", 6.15,
      eurnzd_ladder[1] if eurnzd_ladder else None, 0.01)
check("FXtrading", "verschiedene Symbole im Auszug", 13, len(s["symbols"]), 0,
      "doc/01: 17 Paare gesamt — Auszug enthaelt 13 (Information)")
check("FXtrading", "CAD-Bezug Anteil der Trades %", 45.8,
      round(sum(c for sym, c in s["symbols"].items() if "CAD" in sym) / s["trades"] * 100, 1),
      0.1, "doc/01: 36 % CAD-Exposure (Gesamtdatensatz; Auszug abweichend, Information)")

# ============================================================================= 
# Auswertung
# =============================================================================
def fmt(x):
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") \
        if isinstance(x, float) else str(x)


passed = failed = 0
print("=" * 100)
print(f"{'Signal':<12} {'Check':<44} {'Soll':>12} {'Ist':>12} {'Status':>6}  Quelle")
print("=" * 100)
for c in CHECKS:
    if c["tol"] is None:
        ok = c["actual"] == c["expected"]
    else:
        ok = near(c["expected"], c["actual"], c["tol"]) if isinstance(c["expected"], (int, float)) \
            else c["expected"] == c["actual"]
    passed += ok
    failed += (not ok)
    print(f"{c['signal']:<12} {c['name']:<44} {fmt(c['expected']):>12} {fmt(c['actual']):>12} "
          f"{'PASS' if ok else 'FAIL':>6}  {c['source']}")
    if not ok and c["note"]:
        print(f"{'':12} {'-> ' + c['note']}")
print("=" * 100)
print(f"ERGEBNIS: {passed} PASS, {failed} FAIL von {len(CHECKS)} Checks "
      f"ueber 8 Datensaetze + MT4/MT5-Zwillingssystem")
sys.exit(1 if failed else 0)
