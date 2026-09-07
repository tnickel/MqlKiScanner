"""Reject ambiguous CSV schemas and avoid fictitious intrasecond risk paths."""
from datetime import datetime, timedelta
from itertools import permutations

import pytest

from mqlkiscanner import engine, parser, scoring


BASE = datetime(2024, 1, 1)
POSITION = list(parser.POSITION_HEADER)
ORDERBOOK = list(parser.ORDERBOOK_HEADER)


def trade(open_hour, close_hour, profit, lots=.1, entry=2000, direction="Buy", sl="", tp=""):
    sign = 1 if direction == "Buy" else -1
    return [
        (BASE + timedelta(hours=open_hour)).strftime(parser.TIME_FMT), direction,
        str(lots), "XAUUSD", str(entry), str(sl), str(tp),
        (BASE + timedelta(hours=close_hour)).strftime(parser.TIME_FMT),
        str(entry + sign * profit / (100 * lots)), "0", "0", str(profit), "",
    ]


def write_export(tmp_path, rows, header=None, capital=1000):
    header = ORDERBOOK if header is None else header
    balance = [""] * len(header)
    balance[0:2] = ["2023.12.31 00:00:00", "Balance"]
    balance[11 if len(header) == 13 else 10] = str(capital)
    path = tmp_path / "history.csv"
    path.write_text("\n".join(";".join(row) for row in [header, balance, *rows]) + "\n",
                    encoding="utf-8-sig")
    return str(path)


@pytest.mark.parametrize("header", [POSITION, ORDERBOOK])
def test_both_complete_schemas_accept_bom_and_outer_field_whitespace(tmp_path, header):
    header = [" " + field + " " for field in header]
    result = parser.load_export(write_export(tmp_path, [], header))
    assert len(result.balances) == 1
    assert result.has_orderbook == (len(header) == 13)


@pytest.mark.parametrize("header,index", [(h, i) for h in (POSITION, ORDERBOOK) for i in range(1, len(h))])
def test_every_named_column_is_validated_before_positional_parsing(tmp_path, header, index):
    altered = list(header)
    altered[index] = "Unexpected"
    with pytest.raises(ValueError, match="unbekannter CSV-Header"):
        parser.load_export(write_export(tmp_path, [], altered))


def test_swapped_take_profit_never_turns_into_stop_proof(tmp_path):
    rows = [trade(0, 1, 10, tp=2001)]
    valid = engine.analyze(write_export(tmp_path, rows))
    assert valid["forensics"]["stops"]["stop_evidence"] == "none"
    altered = list(ORDERBOOK)
    altered[5], altered[6] = altered[6], altered[5]
    rows[0][5], rows[0][6] = rows[0][6], rows[0][5]
    with pytest.raises(ValueError, match="unbekannter CSV-Header"):
        engine.analyze(write_export(tmp_path, rows, altered))


def test_complete_valid_orderbook_keeps_direct_stop_evidence(tmp_path):
    report = engine.analyze(write_export(tmp_path, [trade(0, 1, 10, sl=1900)]))
    assert report["forensics"]["stops"]["stop_evidence"] == "direct"


def test_same_second_profit_and_loss_are_a_single_drawdown_booking(tmp_path):
    rows = [trade(0, 24, 400, entry=1960), trade(1, 24, -400, entry=2040)]
    outcomes = []
    for ordered in permutations(rows):
        report = engine.analyze(write_export(tmp_path, ordered))
        drawdown = report["forensics"]["drawdown"]
        assert drawdown["trading_dd"]["dd_usd"] == 0
        assert drawdown["trading_dd"]["dd_pct_max_rel"] == 0
        assert drawdown["trading_dd"]["end_balance"] == 1000
        assert not scoring.evaluate(report)["schranke_eq_dd_verletzt"]
        outcomes.append(drawdown)
    assert outcomes[0] == outcomes[1]


def test_same_second_closes_keep_real_net_loss_and_cannot_hide_later_drawdown(tmp_path):
    rows = [trade(0, 24, 400), trade(1, 24, -700), trade(25, 26, -100)]
    for ordered in permutations(rows):
        report = engine.analyze(write_export(tmp_path, ordered))
        dd = report["forensics"]["drawdown"]["trading_dd"]
        assert dd["dd_usd"] == 400
        assert dd["dd_pct_max_rel"] == 40
        assert scoring.evaluate(report)["schranke_eq_dd_verletzt"]


def test_same_second_closes_cannot_invent_temporary_capital_shortage(tmp_path):
    rows = [trade(0, 24, 800, lots=.01, entry=1200),
            trade(1, 24, -800, lots=.01, entry=2800),
            trade(2, 48, 0)]
    outcomes = []
    for ordered in permutations(rows):
        report = engine.analyze(write_export(tmp_path, ordered))
        exposure = report["forensics"]["exposure"]
        assert exposure["shock_pct_max"] == 60
        assert exposure["shock_pct_peak_account"] == 1000
        assert exposure["temporal_risk_available"]
        outcomes.append(exposure)
    assert all(result == outcomes[0] for result in outcomes)


def test_same_second_hedged_opens_have_no_csv_order_dependent_intermediate_shock(tmp_path):
    rows = [trade(0, 24, 0, lots=1), trade(0, 24, 0, lots=1, direction="Sell"),
            trade(0, 24, 0, lots=.1)]
    outcomes = []
    for ordered in permutations(rows):
        exposure = engine.analyze(write_export(tmp_path, ordered))["forensics"]["exposure"]
        assert exposure["peak_open_positions"] == 3
        assert exposure["shock_usd"] == 500
        assert exposure["shock_pct_max"] == 50
        outcomes.append(exposure)
    assert all(result == outcomes[0] for result in outcomes)


def test_future_close_profit_still_cannot_fund_new_positions_at_same_timestamp(tmp_path):
    rows = [trade(0, 24, 9000, lots=.01), trade(24, 25, 0)]
    report = engine.analyze(write_export(tmp_path, rows))
    exposure = report["forensics"]["exposure"]
    assert exposure["peak_open_positions"] == 2
    assert exposure["shock_pct_max"] == 55
    assert exposure["shock_pct_peak_account"] == 1000


def test_fully_hedged_zero_risk_peak_keeps_actual_positions_not_earlier_deposit(tmp_path):
    rows = [trade(0, 24, 0, lots=1), trade(0, 24, 0, lots=1, direction="Sell")]
    for ordered in permutations(rows):
        exposure = engine.analyze(write_export(tmp_path, ordered))["forensics"]["exposure"]
        assert exposure["shock_usd"] == exposure["shock_pct_max"] == 0
        assert exposure["peak_open_positions"] == 2
        assert exposure["peak_long_lots"] == exposure["peak_short_lots"] == 1
        assert exposure["peak_gross_lots"] == 2
        assert exposure["peak_time"] == "2024-01-01 00:00:00"
