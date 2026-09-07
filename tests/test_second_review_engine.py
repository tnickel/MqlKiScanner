"""Consequential domain regressions from the second review (offline only)."""
from datetime import datetime, timedelta
from itertools import permutations

import pytest

from mqlkiscanner import scoring, stats
from mqlkiscanner.forensics import baskets, drawdown, exposure, martingale, stops
from mqlkiscanner.models import BalanceRow, ParsedExport, Trade


BASE = datetime(2026, 1, 1)


def trade(day=1, close_day=None, symbol="XAUUSD", lots=.01, profit=-1, sl=None):
    return Trade(BASE + timedelta(days=day),
                 BASE + timedelta(days=day, hours=1) if close_day is None else BASE + timedelta(days=close_day),
                 "Buy", lots, symbol, 2000, 2000 + profit, profit, sl=sl)


def parsed(trades, flows=((0, 1000),), fmt="positions"):
    return ParsedExport("memory", fmt, trades=trades,
                        balances=[BalanceRow(BASE + timedelta(days=day), amount)
                                  for day, amount in flows])


def report(p):
    return {"stats": stats.compute(p), "forensics": {
        mod.__name__.split(".")[-1]: mod.run(p)
        for mod in (exposure, drawdown, stops, martingale, baskets)}}


def test_withdrawal_before_trading_cannot_bypass_drawdown_barrier():
    p = parsed([trade(day=2, close_day=367, profit=-400)], ((0, 10000), (1, -9000)))
    r = report(p)
    assert r["forensics"]["drawdown"]["start_capital"] == 1000
    assert r["forensics"]["drawdown"]["trading_dd"]["dd_usd"] == 400
    assert r["forensics"]["drawdown"]["trading_dd"]["dd_pct_max_rel"] == 40
    assert r["forensics"]["exposure"]["account_at_shock_peak"] == 1000
    assert scoring.evaluate(r)["schranke_eq_dd_verletzt"] is True


def test_later_withdrawals_stay_outside_virtual_trading_drawdown():
    p = parsed([trade(day=1, close_day=4, profit=-400)], ((0, 10000), (2, -9000)))
    r = drawdown.run(p)
    assert r["trading_dd"]["dd_pct_max_rel"] == 4
    assert r["trading_dd"]["dd_usd"] == 400
    assert r["end_balance_estimated"] == 600


@pytest.mark.parametrize("symbol,pip,move,quote", [
    ("EURJPY", .01, 5.0, "JPY"), ("AUDJPY.m", .01, 5.0, "JPY"),
    ("NZDCAD", .0001, .05, "CAD"), ("USDCHF", .0001, .05, "CHF"),
])
def test_non_usd_fx_has_correct_native_units_but_no_invented_dollars(symbol, pip, move, quote):
    p = parsed([trade(symbol=symbol, lots=1)])
    r = exposure.run(p)
    assert r["conversion_complete"] is False
    assert r["shock_usd"] is None
    assert r["fx_pips_10_usd"] is None
    assert r["usd_per_unit_per_lot"] is None
    assert r["shock_pct_max"] is None
    assert r["temporal_risk_available"] is False
    assert r["warnings"] and quote in r["warnings"][0]
    scenario = next(iter(r["per_symbol_scenarios"].values()))
    assert scenario["quote_currency"] == quote
    assert scenario["pip_size"] == pip
    assert scenario["stress_move"] == move
    assert scenario["stress_pips"] == 500
    assert scenario["stress_quote_per_lot"] == move * 100000
    assert scoring.evaluate(report(p))["forensics_complete"] is False


@pytest.mark.parametrize("symbol", ["EURUSD", "GBPUSD.m", "AUDUSD", "NZDUSD"])
def test_usd_quoted_fx_keeps_usd_risk_and_pip_values(symbol):
    r = exposure.run(parsed([trade(symbol=symbol, lots=1)]))
    assert r["conversion_complete"] is True
    assert r["shock_usd"] == 5000
    assert r["fx_pips_10_usd"] == 100
    assert r["shock_pct_max"] == 500


def test_mixed_currency_portfolio_does_not_publish_partial_sum_as_total():
    r = exposure.run(parsed([trade(lots=1, close_day=5),
                             trade(day=2, symbol="NZDCAD", lots=1, close_day=5)]))
    assert r["peak_open_positions"] == 2
    assert r["shock_usd"] is None
    assert r["peak_net_lots"] is None
    assert r["peak_time"] is None
    assert r["missing_conversion_symbols"] == ["NZDCAD"]
    assert set(r["per_symbol_scenarios"]) == {"XAUUSD", "NZDCAD"}


def test_later_trade_profit_never_becomes_an_implied_conversion_rate():
    for pnl in (1.29, 1000000):
        r = exposure.run(parsed([trade(symbol="EURJPY", profit=pnl, close_day=365)]))
        assert r["shock_usd"] is None
        assert r["conversion_complete"] is False


def test_simultaneous_cashflows_have_order_independent_risk():
    results = [exposure.run(parsed([trade(lots=1, close_day=5)],
                                  ((0, 1000), *((2, amount) for amount in order))))
               for order in permutations((-1000, 600, 400))]
    assert all(result == results[0] for result in results)
    assert results[0]["temporal_risk_available"] is True
    assert results[0]["shock_pct_max"] == 500


def test_simultaneous_cashflows_still_capture_real_net_capital_reduction():
    for order in permutations((-900, 400)):
        r = exposure.run(parsed([trade(lots=1, close_day=5)],
                                ((0, 1000), *((2, amount) for amount in order))))
        assert r["shock_pct_max"] == 1000
        assert r["shock_pct_peak_account"] == 500
        assert r["shock_pct_peak_time"] == "2026-01-03 00:00:00"


def test_fixed_sizes_across_instruments_are_not_martingale():
    trades = [trade(day=i * 2, symbol="XAUUSD" if i % 2 == 0 else "US30",
                    lots=.01 if i % 2 == 0 else 1, profit=-1 if i % 2 == 0 else 1)
              for i in range(10)]
    r = martingale.run(parsed(trades))
    assert r["flag"] is False
    assert r["median_ratio_after_loss"] == 1
    assert r["per_symbol"]["XAUUSD"]["median_ratio_after_loss"] == 1


def test_real_same_instrument_martingale_survives_suffixes_and_other_trades():
    trades = [trade(day=i * 2, symbol="XAUUSD" if i == 0 else "XAUUSD+",
                    lots=.01 * 2 ** i, profit=-1) for i in range(3)]
    trades += [trade(day=i, symbol="US30", lots=1, profit=-1) for i in range(1, 20)]
    r = martingale.run(parsed(trades))
    assert r["median_ratio_after_loss"] == 1  # global median must not hide a sleeve
    assert r["flag"] is True
    assert r["per_symbol"]["XAUUSD"]["median_ratio_after_loss"] == 2
    assert "XAUUSD 2.0x" in r["evidence"][0]


def test_empty_orderbook_columns_do_not_reduce_risk():
    trades = [trade(day=i * 2, profit=-d) for i, d in enumerate([1, 2, 3, 4, 5, 6, 7, 100])]
    reports = [report(parsed(trades, fmt=fmt)) for fmt in ("positions", "mt4_orderbook")]
    evaluations = [scoring.evaluate(r) for r in reports]
    assert all(r["forensics"]["stops"]["stop_evidence"] == "none" for r in reports)
    assert evaluations[0]["dimensions"]["structure"] == 5
    assert evaluations[0]["dimensions"] == evaluations[1]["dimensions"]
    assert evaluations[0]["score"] == evaluations[1]["score"] == 5.4


def test_stop_loss_evidence_does_not_require_take_profit():
    r = report(parsed([trade(sl=1990)], fmt="mt4_orderbook"))
    assert r["forensics"]["stops"]["stop_evidence"] == "direct"
    assert r["forensics"]["stops"]["positions_with_sl"] == 1
    assert "1/1 Positionen mit SL-Feldern" in r["forensics"]["stops"]["verdict"]
    assert scoring.evaluate(r)["dimensions"]["structure"] == 2


def test_partial_stop_coverage_never_counts_as_complete_protection():
    p = parsed([trade(day=i, sl=1990 if i else None) for i in range(100)], fmt="mt4_orderbook")
    r = report(p)
    assert r["forensics"]["stops"]["stop_evidence"] == "partial"
    assert scoring.evaluate(r)["dimensions"]["structure"] == 5
