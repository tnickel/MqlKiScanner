"""Independent verification of external review claims and confirmed fixes."""
from datetime import datetime, timedelta

import pytest

from mqlkiscanner import parser, scoring
from mqlkiscanner.forensics import exposure, martingale, stops
from mqlkiscanner.models import BalanceRow, ParsedExport, Trade


BASE = datetime(2026, 1, 1)
HEADER = "Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;Profit;Comment"


def trade(o=0, c=1, symbol="XAUUSD", volume=1, profit=-1):
    return Trade(BASE + timedelta(hours=o), BASE + timedelta(hours=c), "Buy",
                 volume, symbol, 2000, 1990, profit)


def parsed(trades):
    return ParsedExport("in-memory", "positions", trades=trades,
                        balances=[BalanceRow(BASE - timedelta(days=1), 10000)])


@pytest.mark.parametrize("symbol", ["JP225", "JP225.cash", "GER40", "UK100", "CHINA50.cash"])
def test_non_us_index_does_not_invent_contract_or_native_currency(symbol):
    result = exposure.run(parsed([trade(symbol=symbol)]))
    assert result["symbol_class"] == "INDEX"
    assert result["contract_complete"] is False
    assert result["missing_contract_symbols"]
    assert result["missing_conversion_symbols"] == []  # even the currency is unproven
    assert result["shock_usd"] is None
    assert result["shock_pct_max"] is None
    assert result["usd_per_unit_per_lot"] is None
    assert result["temporal_risk_available"] is False
    assert "Brokerspezifikation" in result["warnings"][0]
    scenario = next(iter(result["per_symbol_scenarios"].values()))
    assert scenario["quote_currency"] is None
    assert scenario["contract_factor_in_quote"] is None
    assert scenario["stress_quote_per_lot"] is None
    assert scenario["stress_move"] == 50  # a point movement is still well-defined
    assert exposure.shock_usd(1, 50, symbol) is None


@pytest.mark.parametrize("symbol", ["US30", "US100", "NAS100", "NDX", "US500", "SPX500"])
def test_existing_us_index_convention_remains_explicit(symbol):
    result = exposure.run(parsed([trade(symbol=symbol)]))
    assert result["contract_complete"] is True
    assert result["shock_usd"] == 50
    assert result["missing_contract_symbols"] == []


def test_mixed_unknown_index_prevents_a_complete_dollar_total():
    result = exposure.run(parsed([trade(c=5), trade(o=1, c=5, symbol="GER40")]))
    assert result["peak_open_positions"] == 2
    assert result["shock_usd"] is None
    assert result["conversion_complete"] is False
    report = {"forensics": {"exposure": result, "stops": {"stop_evidence": "none"},
                              "drawdown": {"test": "drawdown"}, "martingale": {"flag": False}}}
    assert scoring.evaluate(report)["forensics_complete"] is False


def test_fx_quote_restriction_is_deliberate_and_preserves_native_units():
    result = exposure.run(parsed([trade(symbol="USDJPY")]))
    assert result["contract_complete"] is True
    assert result["missing_contract_symbols"] == []
    assert result["missing_conversion_symbols"] == ["USDJPY"]
    assert result["shock_usd"] is None
    assert result["per_symbol_scenarios"]["USDJPY"]["quote_currency"] == "JPY"
    assert result["per_symbol_scenarios"]["USDJPY"]["stress_pips"] == 500


def test_martingale_follows_specified_adjacent_pair_semantics():
    result = martingale.run(parsed([trade(0, 5, volume=1, profit=-1),
                                   trade(1, 2, volume=.1, profit=1),
                                   trade(6, 7, volume=2, profit=-1)]))
    # A/B overlap; B/C succeeds a winner. Pairing A/C would be a new detector.
    assert result["n_after_loss"] == 0
    assert result["flag"] is False


@pytest.mark.parametrize("comment,sl_count,tp_count", [
    ("[SL]", 1, 0), ("[sl] #123", 1, 0), ("[Sl] Ticket #456", 1, 0),
    ("[TP]", 0, 1), ("[tp] 123", 0, 1), ("[tP] ticket 456", 0, 1),
])
def test_explicit_exit_markers_survive_real_csv_parser(tmp_path, comment, sl_count, tp_count):
    path = tmp_path / "markers.csv"
    path.write_text(HEADER + "\n"
                    "2026.01.01 00:00:00;Buy;.01;XAUUSD;2000;2005;2020;"
                    f"2026.01.01 01:00:00;2010;;;10;{comment}\n", encoding="utf-8")
    result = stops.run(parser.load_export(str(path)))
    assert result["exits_sl"] == sl_count
    assert result["exits_tp"] == tp_count
    assert result["exits_manual"] == 0
    assert result["trailing_proof"] == bool(sl_count)


@pytest.mark.parametrize("comment", ["manual exit near [sl]", "slippage", "[slippage]", "[sl] [tp]"])
def test_prose_or_ambiguous_marker_is_not_an_execution_proof(comment):
    t = trade()
    t.comment = comment
    result = stops.run(ParsedExport("memory", "mt4_orderbook", trades=[t]))
    assert result["exits_manual"] == 1


def test_claimed_missing_entry_price_crash_is_blocked_by_parser(tmp_path):
    path = tmp_path / "missing-price.csv"
    path.write_text(HEADER + "\n"
                    "2026.01.01 00:00:00;Buy;.01;XAUUSD;;1990;2020;"
                    "2026.01.01 01:00:00;1990;;;0;[sl]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Pflichtfeld fehlt"):
        parser.load_export(str(path))
