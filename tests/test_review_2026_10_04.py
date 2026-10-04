# -*- coding: utf-8 -*-
"""Regressionstests des Gesamtbearbeitungs-Reviews vom 04.10.2026
(doc/reviews/codereview_2026-10-04/): Absicherung der Fixes A2a (Dedup-
Beweis durchreichen), A1c/D1 (Monitor-Closing-DD ist kein RetDD-Nenner),
B2a (Scheduler-Versuchsdeckel), B3a (korrupte Lock-ts) und A-P3
(Dezimaltrenner-Parsing).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from mqlkiscanner import pipeline, portfolio_statistik, scoring
from mqlkiscanner.agenten import lock, scan_launcher, scheduler
from mqlkiscanner.scoring import _platform_float

# CSV-Muster wie tests/test_beweis_dedup.py (MQL5-Positions-Export).
HEADER = "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
ZEILEN = [
    "2026.09.01 22:39:54;Sell;0.01;XAUUSD;4324.98;0.01;2026.09.02 04:13:01;4319.66;-0.18;;5.32\n",
    "2026.09.01 16:12:05;Sell;0.01;XAUUSD;4326.38;0.01;2026.09.01 16:31:23;4349.51;-0.18;;-23.13\n",
    "2026.09.02 08:00:00;Buy;0.01;XAUUSD;4330.00;0.01;2026.09.02 09:00:00;4340.00;-0.18;;9.82\n",
    "2026.09.02 10:00:00;Buy;0.01;XAUUSD;4340.00;0.01;2026.09.02 11:00:00;4335.00;-0.18;;-4.18\n",
]
NETTO_BEREINIGT = 5.32 - 23.13 + 9.82 - 4.18 - 4 * 0.18  # 4 eindeutige Trades
NETTO_ROH = NETTO_BEREINIGT + 5.32 - 0.18 + 9.82 - 0.18   # + 2 Doppellieferungen


def _csv_mit_zwillingen(tmp_path: Path) -> Path:
    pfad = tmp_path / "export.csv"
    pfad.write_text(HEADER + "".join(ZEILEN + [ZEILEN[0], ZEILEN[2]]),
                    encoding="utf-8")
    return pfad


# --- A2a: Dedup-Beweis wirkt in RetDD/Portfolio-Kurven -----------------

def test_effizienz_kennzahlen_dedup_wie_forensik(tmp_path):
    pfad = _csv_mit_zwillingen(tmp_path)
    mit_beweis = portfolio_statistik.effizienz_kennzahlen(
        str(pfad), 10000.0, 5.0, plattform_positions=4)
    ohne_beweis = portfolio_statistik.effizienz_kennzahlen(
        str(pfad), 10000.0, 5.0)
    assert mit_beweis["netto_gesamt_usd"] == mit_beweis["netto_gesamt_usd"]
    assert abs(mit_beweis["netto_gesamt_usd"] - NETTO_BEREINIGT) < 1e-6
    assert abs(ohne_beweis["netto_gesamt_usd"] - NETTO_ROH) < 1e-6


def test_monatsrenditen_dedup_wie_forensik(tmp_path):
    pfad = _csv_mit_zwillingen(tmp_path)
    mit = portfolio_statistik.monatsrenditen(str(pfad), 10000.0,
                                             plattform_positions=4)
    ohne = portfolio_statistik.monatsrenditen(str(pfad), 10000.0)
    assert mit and ohne
    assert abs(mit["2026-09"] - NETTO_BEREINIGT / 10000.0 * 100) < 1e-9
    assert ohne["2026-09"] > mit["2026-09"]


def test_statistik_nimmt_plattform_trades_je_ergebnis(tmp_path):
    pfad = _csv_mit_zwillingen(tmp_path)

    class R:
        id = 1
        name = "T"
        source_kind = "live"
        trades_path = str(pfad)
        kapitalbasis_verwendet_usd = 10000.0
        plattform_trades = 4
        symbole = "XAUUSD"
        retdd_monat = None
        retdd_jahr = None
        ertrag_monat_geom_pct = None

        def refresh_efficiency(self):  # no-op statt echter Neuberechnung
            pass

    stat = portfolio_statistik.statistik([R()])
    zeile = stat["signale"][0]
    # Mit Beweis (4 eindeutige): Verlustmonat auf BEREINIGTER Kurve.
    assert zeile["verlustmonate"] == ["2026-09"]
    assert abs(zeile["schlechtester_wert_pct"]
               - NETTO_BEREINIGT / 10000.0 * 100) < 1e-9

    class ROhne(R):
        plattform_trades = None  # kein Beweis → rohe Kurve

    stat2 = portfolio_statistik.statistik([ROhne()])
    zeile2 = stat2["signale"][0]
    # Roh inkl. Doppellieferungen ist der Monat positiv → kein Verlustmonat.
    assert zeile2["verlustmonate"] == []
    assert zeile2["schlechtester_wert_pct"] is None


# --- A1c/D1: Monitor-Closing-DD ist kein RetDD-Nenner -------------------

def _result(**kwargs):
    values = dict(id=900009, name="Muster", forensik_vorhanden=True,
                  score=2.0, martingale_flag=False, stop_evidence="none",
                  ertrag_monat_geom_pct=12.0, cagr_jahr_pct=120.0,
                  equity_dd_rekonstruiert_pct=6.0,
                  trading_dd_pct=0.1, dd_balance_pct=10.0, dd_equity_pct=8.0,
                  retdd_monat=999.0)
    values.update(kwargs)
    return pipeline.ScanResult(**values)


def test_max_drawdown_equity_pct_ignoriert_monitor():
    result = _result(monitor_trade_eq_dd_pct=20.0)
    assert result.max_drawdown_equity_pct == 6.0
    assert "Monitor" not in str(result._equity_messwerte())


def test_monitor_allein_liest_retdd_unbekannt():
    result = _result(equity_dd_rekonstruiert_pct=None,
                     monitor_trade_eq_dd_pct=6.0)
    assert result.max_drawdown_equity_pct is None
    assert result.to_row()["RetDD"] is None
    assert pipeline.ampel_for(result, {})[0] == "🟡"


# --- B2a: Scheduler-Versuchsdeckel --------------------------------------

def test_scan_versuche_zaehlen_und_deckel():
    scan_launcher._scan_versuch_zaehlen("full")
    scan_launcher._scan_versuch_zaehlen("full")
    assert scan_launcher.scan_versuche_heute("full") == 2
    scan_launcher._scan_versuch_zaehlen("full")
    jetzt = datetime.now()
    modi = scheduler.faellige_scans(jetzt, {})
    assert "full" not in modi  # 3 Versuche verbraucht -> heute Schluss
    # Ein neuer Tag (bzw. anderes Datum im Zähler) startet wieder bei 0.
    assert scan_launcher.scan_versuche_heute("full", tag="2020-01-01") == 0


# --- B3a: korrupte Lock-ts wirft nicht mehr -----------------------------

def test_lock_mit_korrupter_ts_ist_ueberholbar(tmp_path):
    lock_datei = tmp_path / "agenten_lauff.lock"
    lock_datei.write_text(json.dumps({"pid": 999999999, "ts": "abc"}),
                          encoding="utf-8")
    with lock.lauf_lock(tmp_path):  # darf KEINEN ValueError werfen
        pass


# --- A-P3: Dezimaltrenner robust ----------------------------------------

def test_platform_float_deutsch_und_en_mischformat():
    assert _platform_float("1.403,03") == 1403.03
    assert _platform_float("1,403.03") == 1403.03
    assert _platform_float("9,10") == 9.10
    assert _platform_float("1 403.03") == 1403.03
    assert _platform_float(True) == 0.0
    assert _platform_float("murks") == 0.0


def test_platform_float_nan_und_infinity_sind_keine_messwerte():
    # Orakel M27 (Review 04.10.): NaN/Infinity — egal ob Zahl oder String —
    # dürfen die DD-Schranke nicht vergiften (max() mit NaN ist in Python
    # positionsabhängig, Infinity sperrt immer).
    for unguelig in (float("nan"), float("inf"), float("-inf"),
                     "nan", "Infinity", "-inf"):
        assert _platform_float(unguelig) == 0.0
    assert scoring.dd_maximum(float("nan"), 12.0) == 12.0
    assert scoring.dd_maximum(float("inf"), 12.0) == 12.0


def test_scoring_dd_maximum_robust_gegen_mischformate():
    assert scoring.dd_maximum("1 403,03") == 1403.03
