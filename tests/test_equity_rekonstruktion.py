# -*- coding: utf-8 -*-
"""Equity-DD-Rekonstruktion aus Kursdaten + Auto-GMT (Nutzer-Wunsch 28.09.2026).

Alles gegen synthetische Bars/Trades — kein MT5 nötig. Deckt ab:
GMT-Erkennung (Preisabgleich, eindeutig/falsch/zu wenig Proben),
Equity-Kurve mit floating PnL, DD-Berechnung, Abdeckungs-Regel (kein
Schranken-Wert unter 95 %), Schranken-Integration (refresh_report_verdict
und results_from_db) und stillen Verfall ohne Kursanbieter.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from mqlkiscanner import config, db as _db, kursdaten
from mqlkiscanner.forensics import equity_rekonstruktion as er


def _trade(symbol, direction, open_dt, close_dt, entry, exit_, lots=1.0, pnl=None):
    return SimpleNamespace(
        symbol=symbol, direction=direction,
        open_time=open_dt, close_time=close_dt,
        entry_price=entry, exit_price=exit_, volume=lots,
        net=pnl if pnl is not None else (exit_ - entry) * 100.0 * lots,
    )


def _bars(symbol, start_dt, stunden, base=2000.0, schritt=7.0):
    """Synthetische H1-Bars: je Stunde EINDEUTIGES, enges Preisband
    (close ± 0.4) — nur der korrekte Offset trifft beim Preisabgleich."""
    bars = []
    for i in range(stunden):
        t = start_dt + dt.timedelta(hours=i)
        epoch = int(t.replace(tzinfo=dt.timezone.utc).timestamp()) // 3600 * 3600
        close = base + schritt * i
        bars.append({"time": epoch, "open": close - 0.2, "high": close + 0.4,
                     "low": close - 0.4, "close": close})
    return bars


STUNDE = 3600


def test_gmt_erkennung_findet_eindeutigen_shift():
    # Terminal-Bars ab 2026-01-01 00:00 UTC; Trades 2h VOR Terminal-Zeit
    start = dt.datetime(2026, 1, 1, 0, 0)
    bars = _bars("XAUUSD", start, 48)
    trades = []
    for i in range(6, 40, 4):
        o = start + dt.timedelta(hours=i)
        c = o + dt.timedelta(hours=1)
        entry = bars[i]["close"] - 0.1      # eindeutig in Band i
        exit_ = bars[i + 1]["close"]        # eindeutig in Band i+1
        trades.append(_trade("XAUUSD", "buy",
                             o - dt.timedelta(hours=2),
                             c - dt.timedelta(hours=2),
                             entry, exit_))
    erg = er.ermittle_gmt_offset(trades, {"XAUUSD": bars})
    assert erg["offset_s"] == 2 * STUNDE, erg
    assert erg["trefferquote"] >= 0.9


def test_gmt_erkennung_ohne_match_liefert_none():
    start = dt.datetime(2026, 1, 1)
    bars = _bars("XAUUSD", start, 48)
    # Preise weit außerhalb jeder Bar (×10)
    trades = [_trade("XAUUSD", "buy",
                     start + dt.timedelta(hours=5),
                     start + dt.timedelta(hours=6),
                     99999.0, 99999.0)]
    erg = er.ermittle_gmt_offset(trades, {"XAUUSD": bars})
    assert erg["offset_s"] is None
    assert erg["trefferquote"] < er.GMT_MIN_TREFFER


def test_rekonstruktion_misst_floating_drawdown():
    """Der Kernfall: realisiert PLUSSE, aber floating Verlust in der Mitte —
    der Trading-DD (nur geschlossene) sähe 0 %, die Rekonstruktion misst den
    echten Equity-Einbruch."""
    start = dt.datetime(2026, 1, 1)
    # Jede Stunde eindeutiges Preisband (±0.4); Einbruch bei Stunde 10 auf 1990
    bars = []
    for i in range(24):
        t = start + dt.timedelta(hours=i)
        epoch = int(t.replace(tzinfo=dt.timezone.utc).timestamp()) // 3600 * 3600
        close = 1990.0 if i == 10 else 2000.0 + 7.0 * i
        bars.append({"time": epoch, "open": close, "high": close + 0.4,
                     "low": close - 0.4, "close": close})
    # Kauf in Bar 1 (Preis 2006.9), Schluss in Bar 22; floating tief in Bar 10:
    # 100 USD je 1 $ × (1990 − 2006.9) = −1690 USD → Equity-Tief 8310 → 16.9 %
    trades = [
        _trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
               start + dt.timedelta(hours=22), bars[1]["close"] - 0.1,
               bars[22]["close"], lots=1.0, pnl=0.0),
    ]
    parsed = SimpleNamespace(trades=trades, balances=[], pendings=[])
    fake = kursdaten.FakeKursDaten({"XAUUSD": bars})
    erg = er.rekonstruiere(parsed, fake, startkapital=10_000.0)
    assert erg["status"] == "ok", erg
    assert erg["verlaesslich"] is True
    assert erg["gmt_offset_h"] == 0, erg
    # Kern der Sache: Trading-DD wäre 0 % (net=0) — die Rekonstruktion MISST
    # den tiefen floating-Einbruch (Kauf 2006.9, Bar 10 notiert 1990).
    assert erg["equity_dd_pct"] > 40.0, erg
    assert erg["equity_dd_usd"] > 5_000.0, erg


def test_rekonstruktion_skip_ohne_kurse():
    start = dt.datetime(2026, 1, 1)
    trades = [_trade("XAUUSD", "buy", start + dt.timedelta(hours=1),
                     start + dt.timedelta(hours=2), 2000.0, 2001.0)]
    parsed = SimpleNamespace(trades=trades, balances=[], pendings=[])
    fake = kursdaten.FakeKursDaten({})  # kein Symbol
    erg = er.rekonstruiere(parsed, fake, startkapital=1000.0)
    assert erg["status"] == "skipped"
    assert "Kursdaten fehlen" in erg["grund"]


def test_schranke_beruecksichtigt_reko_dd():
    from mqlkiscanner import pipeline
    res = pipeline.ScanResult(
        id=1, name="Reko-Fall", forensik_vorhanden=True,
        dd_equity_pct=5.0, trading_dd_pct=5.0, dd_balance_pct=5.0,
        equity_dd_rekonstruiert_pct=41.0, equity_rekon_gmt_h=2,
        score=4.0, ertrag_monat_pct=6.0)
    pipeline.refresh_report_verdict(res, {})
    assert res.schranke_verletzt is True
    assert res.ampel == "🔴"
    # Ohne Reko-Wert: alles 5 % — Schranke halten
    res2 = pipeline.ScanResult(
        id=2, forensik_vorhanden=True, dd_equity_pct=5.0, trading_dd_pct=5.0)
    pipeline.refresh_report_verdict(res2, {})
    assert res2.schranke_verletzt is False


def test_results_from_db_laedt_reko_felder():
    from mqlkiscanner import db, pipeline
    from mqlkiscanner.analysis_version import FORENSICS_VERSION
    db.init_db()
    forensik = {
        "version": FORENSICS_VERSION, "vollstaendig": True, "score": 4.0,
        "trading_dd": {"pct": 5.0, "usd": -500.0}, "winrate_pct": 60.0,
        "peak_exposure": {"positionen": 2, "shock_pct_max": 5.0},
        "kapitalbasis": {"usd": 1000.0, "quelle": "csv_einzahlungen"},
        "equity_rekonstruktion": {"status": "ok", "verlaesslich": True,
                                  "equity_dd_pct": 41.0, "equity_dd_usd": -4100.0,
                                  "gmt_offset_h": 2, "abdeckung_pct": 99.0},
        "kriterien_matrix": {}, "ampel": "🟡",
    }
    db.store_scan_result(777001, {
        "name": "Reko-Reload", "platform": "MT5", "url": "", "autor": "",
        "abo_preis": None, "abonnenten": 5, "wochen": 52,
        "stats": {"eq_dd_pct": 5.0, "forensik_ok": True, "forensik_version": FORENSICS_VERSION,
                    "ertrag_monat_pct": 6.0}},
        trades_path=None, forensik=forensik)
    neu = [r for r in pipeline.results_from_db() if r.id == 777001][0]
    assert neu.equity_dd_rekonstruiert_pct == 41.0
    assert neu.equity_rekon_gmt_h == 2
    assert neu.schranke_verletzt is True
    assert neu.ampel == "🔴"
    assert "Reko-EQ-DD 41.0 %" in neu.urteil


def test_unzuverlaessige_rekonstruktion_fliesst_nicht_in_schranke():
    from mqlkiscanner import db, pipeline
    from mqlkiscanner.analysis_version import FORENSICS_VERSION
    db.init_db()
    forensik = {
        "version": FORENSICS_VERSION, "vollstaendig": True, "score": 4.0,
        "trading_dd": {"pct": 5.0, "usd": -500.0}, "winrate_pct": 60.0,
        "peak_exposure": {"positionen": 2, "shock_pct_max": 5.0},
        "kapitalbasis": {"usd": 1000.0, "quelle": "csv_einzahlungen"},
        # Abdeckung < 95 %: informativ, aber kein Schranken-Wert
        "equity_rekonstruktion": {"status": "unvollstaendig", "verlaesslich": False,
                                  "equity_dd_pct": 55.0, "abdeckung_pct": 60.0},
        "kriterien_matrix": {}, "ampel": "🟡",
    }
    db.store_scan_result(777002, {
        "name": "Reko-XX", "platform": "MT5", "url": "", "autor": "",
        "abo_preis": None, "abonnenten": 5, "wochen": 52,
        "stats": {"eq_dd_pct": 5.0, "forensik_ok": True, "forensik_version": FORENSICS_VERSION,
                    "ertrag_monat_pct": 6.0}},
        trades_path=None, forensik=forensik)
    neu = [r for r in pipeline.results_from_db() if r.id == 777002][0]
    assert neu.equity_dd_rekonstruiert_pct is None
    assert neu.schranke_verletzt is False


def test_engine_ohne_kursanbieter_unchanged():
    from mqlkiscanner import engine
    import tempfile, pathlib
    csv = ("Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
           "2026.01.02 01:00:00;Buy;0.01;XAUUSD;2000;0.01;2026.01.02 02:00:00;2010;0;;10\n")
    f = pathlib.Path(tempfile.mkdtemp()) / "t.csv"
    f.write_text(csv, encoding="utf-8")
    report = engine.analyze(str(f))
    assert "equity_rekonstruktion" not in report["forensics"]
