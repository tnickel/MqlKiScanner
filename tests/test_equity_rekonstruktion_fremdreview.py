# -*- coding: utf-8 -*-
"""Regressionstests für die Fixes aus dem Fremd-Review 01.10.2026
(doc/reviews/codereview_2026-10-01/).

F1: Maximaler RELATIVER Equity-DD darf durch ein späteres USD-Maximum bei
    gewachsenem Konto nicht ersetzt werden (1000->600->2000->1500 = 40 %).
F2: Fehlt der Kurs einer offenen Position, darf der unvollständige Punkt
    keinen erfundenen DD erzeugen (50 h +500 USD Floating, 1 Bar fehlt).
F5: Der Abdeckungs-Nenner zählt volle aktive Stunden laut Trade-Zeiten
    abzüglich erkannter Marktpausen (>=20 h Bar-Lücke); Datenlöcher
    (kürzere Lücken) senken die Abdeckung.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mqlkiscanner import scoring
from mqlkiscanner.forensics import equity_rekonstruktion as eq
from mqlkiscanner.models import ParsedExport, Trade

START = datetime(2026, 1, 5, 0, 0, 0, tzinfo=timezone.utc)


def _trade(a, b, entry, exit_, pnl, symbol="XAUUSD"):
    return Trade(open_time=START + timedelta(hours=a),
                 close_time=START + timedelta(hours=b), direction="Buy",
                 volume=1.0, symbol=symbol, entry_price=entry,
                 exit_price=exit_, profit=pnl, commission=0.0, swap=0.0)


def _bar(stunde, close, low=None, high=None):
    zeit = START + timedelta(hours=stunde)
    return {"time": int(zeit.timestamp()), "open": close, "close": close,
            "low": low if low is not None else close - 1,
            "high": high if high is not None else close + 1}


class _Kurse:
    def __init__(self, bars):
        self.bars = bars

    def hole_h1(self, symbol, *_args, **_kw):
        return self.bars.get(symbol)


def _reko(trades, bars, startkapital=1000.0):
    gmt = eq.ermittle_gmt_offset(trades, bars)
    assert gmt["offset_s"] == 0, gmt
    return eq.rekonstruiere(
        ParsedExport("", "positions", trades=trades), _Kurse(bars),
        startkapital=startkapital)


def test_f1_relatives_maximum_ersetzt_nicht_durch_usd_maximum():
    trades = [_trade(0, 2, 1000, 1010, 1000), _trade(3, 5, 2000, 1995, -500)]
    bars = [_bar(h, c, lo, hi) for h, c, lo, hi in [
        (-1, 900, 899, 901), (0, 996, 995, 1001), (1, 1000, 999, 1001),
        (2, 1010, 1009, 1011), (3, 1995, 1994, 2001), (4, 2000, 1999, 2001),
        (5, 1995, 1994, 1996), (6, 1995, 1994, 1996)]]
    ergebnis = _reko(trades, {"XAUUSD": bars})
    assert ergebnis["verlaesslich"] is True
    # Echte Equity: 1000 -> 600 -> 2000 -> 1500; max. relativer DD = 40 %.
    assert ergebnis["equity_dd_pct"] == pytest.approx(40.0, abs=0.01)
    # Der Wert reißt die Schranke (vorher stand 25 % dort und tat es nicht)
    gate = scoring.evaluate({"forensics": {"drawdown": {
        "trading_dd": {"dd_pct_max_rel": 0.0}}}},
        platform={"reko_eq_dd_pct": ergebnis["equity_dd_pct"]})
    assert gate["schranke_eq_dd_verletzt"] is True


def test_f2_fehlender_kurs_erzeugt_keinen_erdachten_dd():
    trades = [_trade(0, 50, 1000, 1005, 500),
              _trade(0, 50, 30000, 30000, 0, symbol="US30")]
    gold = [_bar(h, 1005, low=999 if h == 0 else 1004, high=1006)
            for h in range(-14, 65) if h != 20]
    index = [_bar(h, 30000) for h in range(-14, 65)]
    ergebnis = _reko(trades, {"XAUUSD": gold, "US30": index})
    # Equity vor Start 1000, danach konstant 1500 -> DD 0 %, nicht 33,33 %.
    assert ergebnis["equity_dd_pct"] == pytest.approx(0.0, abs=0.01)


def test_f5_abdeckung_zaehlt_datenluecken_im_nenner():
    trades = [_trade(0, 6, 4000, 4100, 1000), _trade(20, 22, 4240, 4260, 2000)]

    def preis(h):
        if h == 0:
            return 4000
        return 3000 + 10 * h if h < 0 else 4100 + 10 * (h - 6)

    bars = [_bar(h, preis(h)) for h in range(-14, 37) if h not in range(1, 6)]
    ergebnis = _reko(trades, {"XAUUSD": bars})
    # H1-Close-Messpunkte mit offenem Trade: 1..5 und 21 = 6. Die Punkte
    # 6/22 enthalten bereits realisiertes Netto. Nur Bars 0/20 liefern
    # einen Floating-Punkt; die kurze Datenluecke bleibt im Nenner: 2/6.
    assert ergebnis["abdeckung_pct"] == pytest.approx(33.3, abs=0.1)
    assert ergebnis["verlaesslich"] is False


def test_f5_wochenende_als_marktpause_zaehlt_nicht_als_luecke():
    # Zwei Trade-Cluster mit 45 h Bar-Lücke dazwischen (Wochenende): die
    # Lücke darf den Abdeckungs-Nenner nicht belasten. Preissprünge je
    # Cluster sorgen für ein eindeutiges Auto-GMT (Plateau nur bei 0).
    trades = [_trade(0, 2, 4000, 4100, 1000), _trade(20, 22, 4100, 4200, 500),
              _trade(48, 50, 4200, 4300, 750), _trade(70, 72, 4300, 4400, 250)]
    preise = {0: 4000, 1: 4050, 2: 4100, 20: 4100, 21: 4150, 22: 4200,
              48: 4200, 49: 4250, 50: 4300, 70: 4300, 71: 4350, 72: 4400}
    stunden = [h for h in range(-14, 86)
               if h in preise
               or (-13 <= h <= -1) or (3 <= h <= 19) or (23 <= h <= 47)
               or (51 <= h <= 69) or (73 <= h <= 85)]
    # Aneinandergrenzende Stunden füllen mit klaren Trends, Lücken 3-19,
    # 23-47, 51-69 bleiben BAR-leer; davon ist nur 23-47 (45 h) Pause.
    def preis(h):
        if h in preise:
            return preise[h]
        if 3 <= h <= 19:
            return 4105 + (h - 3)          # leicht ansteigend, kein DD-Killer
        if 51 <= h <= 69:
            return 4305 + (h - 51)
        if 73 <= h <= 85:
            return 4405 + (h - 73)
        return 3990 + (h + 13)             # -13..-1 Vorlauf

    bars = [_bar(h, preis(h)) for h in stunden]
    ergebnis = _reko(trades, {"XAUUSD": bars})
    assert ergebnis["abdeckung_pct"] >= 95.0, ergebnis
