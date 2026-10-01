"""Reproduzierbare Review-Gegenproben ohne Netzwerk, DB oder MT5.

Aufruf aus dem Repository: python doc/reviews/codereview_2026-10-01/equity_probes.py
Die Assertions dokumentieren die Fehler des geprüften Standes a43d728.
Nach einer Korrektur müssen diese Erwartungswerte angepasst werden.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from mqlkiscanner.models import ParsedExport, Trade
from mqlkiscanner.forensics import equity_rekonstruktion as eq
from mqlkiscanner import scoring

START = datetime(2026, 1, 5)


def epoch(hour):
    return int((START + timedelta(hours=hour)).replace(tzinfo=timezone.utc).timestamp())


def trade(a, b, entry, exit_, pnl, symbol="XAUUSD"):
    return Trade(START + timedelta(hours=a), START + timedelta(hours=b),
                 "Buy", 1.0, symbol, entry, exit_, pnl)


def bar(hour, close, low=None, high=None):
    return {"time": epoch(hour), "open": close,
            "high": close + 1 if high is None else high,
            "low": close - 1 if low is None else low, "close": close}


class FakeKurse:
    def __init__(self, bars):
        self.bars = bars

    def hole_h1(self, symbol, *_args):
        return self.bars.get(symbol)


def reko(trades, bars):
    gmt = eq.ermittle_gmt_offset(trades, bars)
    assert gmt["offset_s"] == 0, gmt
    result = eq.rekonstruiere(ParsedExport("", "positions", trades=trades),
                            FakeKurse(bars), startkapital=1000)
    assert result["verlaesslich"] is True, result
    return result


def run():
    trades = [trade(0, 2, 1000, 1010, 1000), trade(3, 5, 2000, 1995, -500)]
    bars = [bar(h, c, low=lo, high=hi) for h, c, lo, hi in [
        (-1, 900, 899, 901), (0, 996, 995, 1001), (1, 1000, 999, 1001),
        (2, 1010, 1009, 1011), (3, 1995, 1994, 2001), (4, 2000, 1999, 2001),
        (5, 1995, 1994, 1996), (6, 1995, 1994, 1996)]]
    first = reko(trades, {"XAUUSD": bars})
    assert first["equity_dd_pct"] == 25.0, first
    # Echte Equity: 1000 -> 600 -> 2000 -> 1500, max relativer DD = 40 %.
    gate = scoring.evaluate({"forensics": {"drawdown": {
        "trading_dd": {"dd_pct_max_rel": 25.0}}}},
        platform={"reko_eq_dd_pct": first["equity_dd_pct"]})
    assert gate["schranke_eq_dd_verletzt"] is False

    trades = [trade(0, 50, 1000, 1005, 500),
              trade(0, 50, 30000, 30000, 0, symbol="US30")]
    gold = [bar(h, 1005, low=999 if h == 0 else 1004, high=1006)
            for h in range(-14, 65) if h != 20]
    index = [bar(h, 30000) for h in range(-14, 65)]
    second = reko(trades, {"XAUUSD": gold, "US30": index})
    assert second["equity_dd_pct"] == 33.33, second
    assert second["abdeckung_pct"] == 98.0, second
    # Equity vor Start 1000, danach konstant 1500. Tatsächlicher DD = 0 %.

    trades = [trade(0, 6, 4000, 4100, 1000), trade(20, 22, 4240, 4260, 2000)]

    def price(h):
        if h == 0:
            return 4000
        return 3000 + 10 * h if h < 0 else 4100 + 10 * (h - 6)

    bars = [bar(h, price(h)) for h in range(-14, 37) if h not in range(1, 6)]
    third = reko(trades, {"XAUUSD": bars})
    assert third["abdeckung_pct"] == 100.0, third
    # Offene H1-Stunden: 0..5 und 20..21. Verfügbar: 0,20,21 -> 3/8 = 37,5 %.
    return {"relative_dd": {"expected_pct": 40.0, "observed": first,
                             "threshold_broken_observed": gate["schranke_eq_dd_verletzt"]},
            "missing_single_bar": {"expected_pct": 0.0, "observed": second},
            "missing_all_bars": {"expected_coverage_pct": 37.5, "observed": third}}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
