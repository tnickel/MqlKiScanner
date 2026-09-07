"""Offline regressions for signed metrics, price distances and twin matching."""
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mqlkiscanner import compare, parser
from mqlkiscanner.models import ParsedExport, Trade
from mqlkiscanner.mql5 import crawler
from mqlkiscanner.symbols import fx_pip_size, normalize_symbol, symbol_class
from mqlkiscanner.trade_data import build_trade_payload


def trade(symbol="EURUSD", price=1.1, distance=0.001, seconds=0):
    start = datetime(2026, 1, 1) + timedelta(seconds=seconds)
    return Trade(start, start + timedelta(hours=1), "Buy", 0.1,
                 symbol, price, price - distance, -1)


def parsed(*trades):
    return ParsedExport("memory", "positions", trades=list(trades))


@pytest.mark.parametrize("value,expected", [
    ("-29.8%", -29.8), ("\u221229.8%", -29.8), ("-1,403.03%", -1403.03),
    ("+1,403", 1403), ("1 403.03", 1403.03), ("0%", 0),
])
def test_card_numbers_keep_sign_and_thousands(value, expected):
    assert crawler._num(value) == pytest.approx(expected)


def test_negative_growth_survives_card_parsing():
    html = '''<div class="signal-card">
      <a class="signal-card__wrapper" href="/en/signals/123"></a>
      <span class="signal-card__growth-value">-29.8%</span></div>'''
    assert crawler.parse_list_html(html)[0]["growth_pct"] == pytest.approx(-29.8)


@pytest.mark.parametrize("raw,canonical,kind", [
    ("EURUSD.a", "EURUSD", "FX"), ("EURUSDm", "EURUSD", "FX"),
    ("USDJPY-pro", "USDJPY", "FX"), ("XAUUSD+", "XAUUSD", "METAL"),
    ("NAS100.cash", "US100", "INDEX"), ("SPX500", "US500", "INDEX"),
    ("CHINA50", "CHINA50", "INDEX"), ("EURUSDT", "EURUSDT", "UNKNOWN"),
    ("NOTUS30", "NOTUS30", "UNKNOWN"), ("XAGUSD", "XAGUSD", "UNKNOWN"),
])
def test_instruments_normalize_only_known_suffixes(raw, canonical, kind):
    assert normalize_symbol(raw) == canonical
    assert symbol_class(raw) == kind


def test_fx_quote_currency_determines_pips():
    assert fx_pip_size("USDJPY.r") == 0.01
    assert fx_pip_size("EURUSD+") == 0.0001
    assert fx_pip_size("UNKNOWN") is None


def test_fx_distance_payload_does_not_fabricate_zero_cluster():
    distances = [.0001, .0002, .0005, .001, .002, .003, .005, .008, .013, .0199]
    loss = build_trade_payload(parsed(*(trade(distance=d) for d in distances)))["verluste"]
    assert loss["distanz_median"] == pytest.approx(.0025)
    assert loss["distanz_max"] == pytest.approx(.0199)
    assert all(level["punkte"] > 0 and level["anzahl"] == 1
               for level in loss["distanz_top_level"])
    assert loss["distanz_pro_symbol"][0]["median_pips"] == pytest.approx(25)


def test_distance_payload_keeps_instruments_separate():
    loss = build_trade_payload(parsed(
        trade("EURUSD.a", distance=.001), trade("EURUSDm", distance=.002),
        trade("XAUUSD+", price=2000, distance=10),
        trade("USDJPY", price=150, distance=.05),
    ))["verluste"]
    assert loss["distanz_median"] is None
    assert loss["distanz_max"] is None
    assert loss["distanz_top_level"] == []
    by_symbol = {item["symbol"]: item for item in loss["distanz_pro_symbol"]}
    assert by_symbol["EURUSD"]["anzahl"] == 2
    assert by_symbol["USDJPY"]["median_pips"] == pytest.approx(5)
    assert by_symbol["XAUUSD"]["distanz_median"] == 10


@pytest.mark.parametrize("delay", [0, 2])
def test_twin_rejects_different_instruments_in_both_phases(delay):
    result = compare.run(parsed(trade("EURUSD")),
                         parsed(trade("GBPUSD", price=1.3, seconds=delay)))
    assert result["matched"] == 0
    assert result["verdict"] == "kein eindeutiger Zwilling"


@pytest.mark.parametrize("delay", [0, 2])
def test_twin_accepts_broker_suffixes_and_small_fx_slippage(delay):
    result = compare.run(parsed(trade("EURUSD.a")),
                         parsed(trade("EURUSDm", price=1.1002, seconds=delay)))
    assert result["matched"] == 1
    assert result["entry_diff_median"] == pytest.approx(.0002)


@pytest.mark.parametrize("symbol,price,near,far", [
    ("EURUSD", 1.1, .0003, .001), ("USDJPY", 150, .03, .10),
    ("XAUUSD", 2000, 3, 4), ("US100", 20000, 3, 4),
])
def test_default_matching_tolerance_follows_instrument(symbol, price, near, far):
    a = parsed(trade(symbol, price=price))
    assert compare.run(a, parsed(trade(symbol, price=price + near)))["matched"] == 1
    assert compare.run(a, parsed(trade(symbol, price=price + far)))["matched"] == 0


def test_unknown_instrument_requires_explicit_price_tolerance():
    a, b = parsed(trade("CUSTOM")), parsed(trade("CUSTOM", price=1.2))
    assert compare.run(a, b)["matched"] == 0
    assert compare.run(a, b, max_price_diff=.2)["matched"] == 1


def test_gold_reference_matching_remains_unchanged():
    root = Path(__file__).resolve().parents[1] / "data" / "raw"
    mt4 = parser.load_export(str(root / "gold_spike_mt4_2349227_ORDERBOOK.csv"))
    mt5 = parser.load_export(str(root / "gold_spike_mt5_2375480_positions.csv"))
    result = compare.run(mt4, mt5, since=datetime(2026, 5, 24))
    assert result["matched"] == 98
    assert result["only_mt4"] == 15
    assert result["only_mt5"] == 10
