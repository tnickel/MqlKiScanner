"""JSON excerpts must not silently fabricate trade direction, volume or PnL."""
import json

import pytest

from mqlkiscanner import engine, parser, scoring


BASE = {"o": "2024-01-01 00:00", "c": "2024-01-02 00:00", "dir": "B",
        "vol": .01, "sym": "XAUUSD", "ep": 2000, "xp": 1990, "pnl": -10}


def write_json(tmp_path, data):
    path = tmp_path / "excerpt.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("key,value", [
    ("dir", "INVALID"), ("dir", "Buy Limit"), ("dir", ""), ("dir", None),
    ("dir", True), ("vol", -.01), ("vol", 0), ("vol", None), ("vol", ""),
    ("vol", float("inf")), ("vol", True), ("pnl", float("nan")),
    ("pnl", float("inf")), ("pnl", "NaN"), ("pnl", True), ("pnl", ""),
    ("ep", float("nan")), ("xp", float("inf")), ("ep", []),
    ("c", "2023-12-31 23:59"), ("o", 123), ("sym", " "), ("sym", []),
])
def test_malformed_excerpt_trade_is_rejected_with_source_and_item_number(tmp_path, key, value):
    path = write_json(tmp_path, [BASE, {**BASE, key: value}])
    with pytest.raises(ValueError, match="Trade 2") as caught:
        engine.analyze(path)
    assert path in str(caught.value)


@pytest.mark.parametrize("key", ["o", "c", "dir", "vol", "sym", "pnl"])
def test_missing_required_json_fields_never_become_default_trades(tmp_path, key):
    item = dict(BASE)
    del item[key]
    with pytest.raises(ValueError, match=f"Pflichtfeld fehlt: {key}"):
        parser.load_export(write_json(tmp_path, [item]))


@pytest.mark.parametrize("data", [{"trades": [BASE]}, None, "not an excerpt", [BASE, 10]])
def test_excerpt_container_and_trade_objects_are_validated(tmp_path, data):
    with pytest.raises(ValueError):
        parser.load_export(write_json(tmp_path, data))


@pytest.mark.parametrize("direction,expected", [
    ("B", "Buy"), ("b", "Buy"), ("Buy", "Buy"), (" BUY ", "Buy"),
    ("S", "Sell"), ("s", "Sell"), ("Sell", "Sell"), (" SELL ", "Sell"),
])
def test_supported_direction_spellings_preserve_economics(tmp_path, direction, expected):
    parsed = parser.load_export(write_json(tmp_path, [{**BASE, "dir": direction}]))
    trade = parsed.trades[0]
    assert trade.direction == expected
    assert trade.volume == .01 and trade.profit == -10


def test_zero_profit_and_optional_missing_prices_remain_valid_incomplete_excerpt(tmp_path):
    item = {k: v for k, v in BASE.items() if k not in ("ep", "xp")}
    item["pnl"] = 0
    path = write_json(tmp_path, [item])
    parsed = parser.load_export(path)
    assert parsed.trades[0].entry_price is None and parsed.trades[0].exit_price is None
    assert parsed.trades[0].profit == 0
    report = engine.analyze(path)
    assert report["stats"]["trades"] == 1
    assert not scoring.evaluate(report)["forensics_complete"]  # excerpt has no capital history


def test_finite_numeric_strings_are_parsed_consistently(tmp_path):
    item = {**BASE, "vol": "0.001", "ep": "2 000.00", "xp": "1 990.00", "pnl": "-1"}
    trade = parser.load_export(write_json(tmp_path, [item])).trades[0]
    assert trade.volume == .001 and trade.entry_price == 2000 and trade.exit_price == 1990
    assert trade.loss_distance() == 10 and trade.net == -1
