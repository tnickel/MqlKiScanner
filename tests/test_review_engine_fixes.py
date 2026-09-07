"""Offline regressions for export integrity and historical risk calculations."""
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mqlkiscanner import engine, parser, scoring
from mqlkiscanner.forensics import exposure, stops
from mqlkiscanner.models import BalanceRow, ParsedExport, Trade


BASE = datetime(2026, 1, 1)
POSITION_HEADER = "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit"
ORDER_HEADER = "Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;Profit;Comment"


def trade(open_day=0, close_day=10, lots=1.0, profit=0.0, symbol="XAUUSD"):
    return Trade(BASE + timedelta(days=open_day), BASE + timedelta(days=close_day),
                 "Buy", lots, symbol, 2000.0, 2000.0 + profit, profit)


def parsed(trades, flows=((0, 1000),)):
    return ParsedExport("in-memory", "positions", trades=trades,
                        balances=[BalanceRow(BASE + timedelta(days=day), amount)
                                  for day, amount in flows])


@pytest.mark.parametrize("header,row", [
    (POSITION_HEADER, "2026.01.01 00:00:00;Buy;0.1;XAUUSD;2000;;2026.01.02 00:00:00;1900;;"),
    (ORDER_HEADER, "2026.01.01 00:00:00;Buy;0.1;XAUUSD;2000;1900;2100;2026.01.02 00:00:00;1900;;"),
    (POSITION_HEADER, "2026.01.01 00:00:00;Balance;;;;;;;;"),
])
def test_truncated_economic_row_invalidates_export(tmp_path, header, row):
    path = tmp_path / "truncated.csv"
    path.write_text(header + "\n" + row + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Zeile 2.*Felder"):
        engine.analyze(str(path))


@pytest.mark.parametrize("profit", ["", "NaN", "inf"])
def test_missing_or_nonfinite_profit_is_not_zero(tmp_path, profit):
    path = tmp_path / "profit.csv"
    path.write_text(POSITION_HEADER + "\n"
                    "2026.01.01 00:00:00;Buy;0.1;XAUUSD;2000;;"
                    f"2026.01.02 00:00:00;1900;;;{profit}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        parser.load_export(str(path))


def test_blank_lines_and_empty_fees_are_valid(tmp_path):
    path = tmp_path / "valid.csv"
    path.write_text(POSITION_HEADER + "\n\n"
                    "2026.01.01 00:00:00;Buy;0.1;XAUUSD;2000;;"
                    "2026.01.02 00:00:00;2000;;;0\n\n", encoding="utf-8")
    result = parser.load_export(str(path))
    assert len(result.trades) == 1
    assert result.trades[0].net == 0


def test_later_profit_cannot_reduce_historical_shock_ratio():
    result = exposure.run(parsed([trade(close_day=365, profit=99000)]))
    assert result["shock_usd"] == 5000
    assert result["shock_pct_max"] == 500
    assert result["shock_pct_peak_account"] == 1000
    assert result["account_at_shock_peak"] == 1000
    assert scoring.dimension_inputs({"forensics": {"exposure": result}})["margin"] == 10


def test_withdrawal_updates_risk_during_open_trade():
    result = exposure.run(parsed([trade()], ((-1, 10000), (3, -9000))))
    assert result["shock_pct_max"] == 500
    assert result["shock_pct_peak_time"] == "2026-01-04 00:00:00"
    assert result["shock_pct_peak_account"] == 1000


def test_later_deposit_does_not_fund_earlier_exposure():
    result = exposure.run(parsed([trade()], ((-1, 1000), (3, 99000))))
    assert result["shock_pct_max"] == 500
    assert result["shock_pct_peak_account"] == 1000


def test_realized_net_loss_changes_capital_of_remaining_positions():
    loser = trade(close_day=2, lots=.01, profit=-8000)
    loser.commission = -1000
    result = exposure.run(parsed([trade(), loser], ((-1, 10000),)))
    assert result["shock_pct_max"] == 500
    assert result["shock_pct_peak_account"] == 1000
    assert result["shock_pct_peak_time"] == "2026-01-03 00:00:00"


def test_same_timestamp_withdrawal_open_and_losing_close():
    result = exposure.run(parsed([trade(close_day=2, lots=.1, profit=-1000),
                                  trade(open_day=2, close_day=5)],
                                 ((-1, 10000), (2, -8000))))
    assert result["shock_pct_max"] == 500
    assert result["shock_pct_peak_account"] == 1000
    assert result["shock_pct_peak_usd"] == 5000
    assert result["shock_pct_peak_time"] == "2026-01-03 00:00:00"


def test_relative_peak_is_independent_of_dollar_peak():
    result = exposure.run(parsed([trade(close_day=1, lots=.1),
                                  trade(open_day=3, close_day=5)],
                                 ((-1, 1000), (2, 99000))))
    assert result["shock_usd"] == 5000
    assert result["shock_pct_max"] == 50
    assert result["shock_pct_peak_usd"] == 500
    assert result["shock_pct_peak_account"] == 1000


@pytest.mark.parametrize("flows", [(), ((-1, 0),), ((-1, 1000), (2, -1000))])
def test_unavailable_capital_is_not_reported_as_safe(flows):
    result = exposure.run(parsed([trade()], flows))
    assert result["temporal_risk_available"] is False
    assert result["shock_pct_max"] is None
    report = {"forensics": {"exposure": result, "martingale": {"flag": False},
                              "stops": {"clustered": False}, "drawdown": {"test": "drawdown"}}}
    evaluation = scoring.evaluate(report)
    assert evaluation["dimensions"]["margin"] == 10
    assert evaluation["forensics_complete"] is False
    assert evaluation["urteil_gueltig"] is False


def test_legacy_reports_do_not_reuse_future_peak_capital():
    report = {"forensics": {"exposure": {"shock_usd": 5000},
                              "drawdown": {"trading_dd": {"peak_balance": 100000}}}}
    assert scoring.dimension_inputs(report)["margin"] == 10
    assert scoring.evaluate(report)["forensics_complete"] is False


@pytest.mark.parametrize("distances", [[1, 10, 100], [1, 10, 100, 1000], [20] * 3])
def test_small_samples_never_claim_stop_cluster(distances):
    trades = [trade(profit=-distance) for distance in distances]
    result = stops.run(parsed(trades))
    assert result["clustered"] is False
    assert "Stop-Signatur" not in result["verdict"]


def test_repeated_stop_level_in_adequate_sample_is_preserved():
    trades = [trade(profit=-distance) for distance in [20, 20, 20, 1, 2, 3, 4, 5]]
    assert stops.run(parsed(trades))["clustered"] is True


def test_small_symbol_subset_does_not_clear_whole_account():
    trades = [trade(profit=-20) for _ in range(8)]
    trades += [trade(profit=-distance, symbol="US30") for distance in (1, 10, 100)]
    result = stops.run(parsed(trades))
    assert result["per_symbol"]["XAUUSD"]["clustered"] is True
    assert result["clustered"] is False


def test_real_us100_fixture_uses_index_contract():
    source = Path(__file__).resolve().parents[1] / "data/raw/kiracat_2342895_positions.csv"
    result = parser.load_export(str(source))
    result.trades = [t for t in result.trades if t.symbol == "US100"]
    for t in result.trades:
        assert abs(t.profit / (t.volume * (t.exit_price - t.entry_price))) == pytest.approx(1)
    risk = exposure.run(result)
    assert risk["symbol_class"] == "INDEX"
    assert risk["shock_usd"] == 125


@pytest.mark.parametrize("symbol", ["US30", "SPX500", "US100", "NAS100", "NDX"])
def test_known_index_aliases_keep_index_units(symbol):
    assert exposure.run(parsed([trade(symbol=symbol)]))["shock_usd"] == 50


@pytest.mark.parametrize("symbol", ["BTCUSD", "EURUSDT", "XAGUSD", "FOO", "MYUS30TOKEN"])
def test_unknown_instruments_abort_instead_of_guessing_contract(symbol):
    with pytest.raises(ValueError, match="Unbekannte Instrumente"):
        exposure.run(parsed([trade(symbol=symbol)]))


@pytest.mark.parametrize("path", sorted((Path(__file__).resolve().parents[1] / "data/raw").glob("*.csv")))
def test_existing_complete_csv_fixtures_still_parse(path):
    assert parser.load_export(str(path)).trades
