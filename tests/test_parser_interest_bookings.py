"""Interest is signed performance, with no invented position or capital flow."""
from datetime import datetime

import pytest

from mqlkiscanner import parser, portfolio_statistik
from mqlkiscanner.forensics import drawdown


def export(tmp_path, rows, header=parser.POSITION_HEADER):
    path = tmp_path / "interest.csv"
    path.write_text(";".join(header) + "\n" + "\n".join(";".join(r) for r in rows) + "\n", encoding="utf-8")
    return str(path)


def booking(amount="-5", kind="Deal Interestrate"):
    row = [""] * 11
    row[0], row[1], row[10] = "2026.01.01 02:00:00", kind, amount
    return row


@pytest.mark.parametrize("amount", ["-5", "5", "0"])
def test_interest_changes_performance_and_never_becomes_deposit(tmp_path, amount):
    trade = ["2026.01.01 00:00:00", "Buy", "0.01", "XAUUSD", "2000", "0.01",
             "2026.01.01 04:00:00", "2000", "0", "0", "10"]
    parsed = parser.load_export(export(tmp_path, [trade, booking(amount)]))
    assert len(parsed.trades) == 1 and len(parsed.costs) == 1
    assert parsed.costs[0].kind == "Deal Interestrate"
    assert parsed.costs[0].time == datetime(2026, 1, 1, 2)
    assert parsed.balances == []
    measured = drawdown.run(parsed, 1000)
    assert measured["flows_total"] == 0
    assert measured["net_total"] == pytest.approx(10 + float(amount))
    assert measured["end_balance_real"] == pytest.approx(1010 + float(amount))
    assert portfolio_statistik._monatsserie(parsed, 1000)["2026-01"] == pytest.approx((10 + float(amount)) / 10)


def test_identical_interest_bookings_are_both_real_money(tmp_path):
    parsed = parser.load_export(export(tmp_path, [booking(), booking()]))
    assert len(parsed.costs) == 2 and parsed.net_total == -10
    assert parsed.trades == [] and parsed.balances == []


@pytest.mark.parametrize("column,value", [(0, "bad"), (2, "0.01"), (3, "XAUUSD"),
    (8, "-1"), (9, "-1"), (10, ""), (10, "NaN"), (10, "Infinity")])
def test_malformed_interest_is_not_silently_accepted(tmp_path, column, value):
    row = booking()
    row[column] = value
    with pytest.raises(ValueError):
        parser.load_export(export(tmp_path, [row]))


def test_other_deal_types_remain_blocked(tmp_path):
    with pytest.raises(ValueError, match="unbekannter Datensatztyp"):
        parser.load_export(export(tmp_path, [booking(kind="Deal Unknown")]))


def test_interest_shape_is_not_assumed_for_mt4(tmp_path):
    row = [""] * 13
    row[0], row[1], row[11] = "2026.01.01 02:00:00", "Deal Interestrate", "-5"
    with pytest.raises(ValueError, match="unbekannter Datensatztyp"):
        parser.load_export(export(tmp_path, [row], parser.ORDERBOOK_HEADER))
