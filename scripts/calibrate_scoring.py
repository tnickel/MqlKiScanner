# -*- coding: utf-8 -*-
"""Kalibrierungspruefung des Risiko-Scores gegen die 6 Tiefanalysen (doc/01).

World PEACE #2379208 hat keinen Trade-Export in data/raw/ (abgelehnt, nie
voll forensisiert) und kann hier nur mit Plattform-Fakten纲 geschaetzt werden —
der Lauf deckt die 5 Signale mit Daten ab.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mqlkiscanner import engine, scoring  # noqa: E402

RAW = ROOT / "data" / "raw"

REPORT_FILES = {
    "Gold Spike": RAW / "gold_spike_mt4_2349227_ORDERBOOK.csv",
    "Gold Reaper": RAW / "gold_reaper_2265877_positions.csv",
    "KiraCat": RAW / "kiracat_2342895_positions.csv",
    "MSC Gold": RAW / "msc_gold_2231030_positions.csv",
    "FXtrading": RAW / "fxtrading_2356441_trades.json",
}

reports = {name: engine.analyze(str(path)) for name, path in REPORT_FILES.items()}
rows = scoring.calibrate(reports)

print(f"{'Signal':<14} {'Soll':>5} {'Ist':>5} {'Delta':>6}  Schranke  Dimensionen (dd/str/margin/copy/track/transp/broker)")
print("-" * 110)
for r in rows:
    d = r["dims"]
    dims = "/".join(f"{d[k]:.1f}" for k in ("drawdown", "structure", "margin", "copy", "track", "transparency", "broker"))
    print(f"{r['signal']:<14} {r['soll']:>5.1f} {r['ist']:>5.1f} {r['delta']:>+6.1f}  "
          f"{'JA' if r['schranke'] else 'nein':<8}  {dims}")
missing = set(scoring.CALIBRATION_CASES) - set(REPORT_FILES)
if missing:
    print(f"\n(ohne Trade-Daten nicht kalibrierbar: {', '.join(sorted(missing))})")
