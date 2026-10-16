"""Separate Kontokosten sind Netto-Ergebnis, weder Trades noch Kapitalflüsse."""
from datetime import datetime as D

import pytest

from mqlkiscanner import signal_statistik, stats
from mqlkiscanner.models import AccountCostRow, BalanceRow, ParsedExport, Trade


def trade(opened, closed, profit, commission=0):
    return Trade(opened, closed, "Buy", 0.1, "EURUSD", 1.1, 1.2, profit, commission)


def test_trade_pf_win_count_stay_trade_based_while_months_and_net_include_costs():
    parsed = ParsedExport("fixture", "positions", trades=[
        trade(D(2026, 1, 1), D(2026, 1, 31), 100, -5),
        trade(D(2026, 2, 1), D(2026, 2, 28), -20)], costs=[
            AccountCostRow(D(2026, 1, 20), -100, "Commission"),
            AccountCostRow(D(2026, 2, 10), 2, "Commission rebate")])
    result = stats.compute(parsed)
    assert result["trades"] == 2 and result["winrate_pct"] == 50
    assert result["profit_factor_csv"] == 5
    assert result["commission"] == -5
    assert result["kontokosten_anzahl"] == 2 and result["kontokosten_usd"] == -98
    assert result["net"] == -23
    assert result["monthly_net_by_close"] == {"2026-01": -5, "2026-02": -18}
    assert stats.negative_months_full(parsed) == ["2026-01", "2026-02"]
    assert signal_statistik._monats_usd(parsed) == {"2026-01": -5, "2026-02": -18}


def test_open_month_alternative_keeps_cost_booking_month():
    parsed = ParsedExport("fixture", "positions", trades=[
        trade(D(2026, 1, 20), D(2026, 2, 1), 100)], costs=[
            AccountCostRow(D(2026, 2, 3), -15, "Commission")])
    assert stats.month_table_by_open(parsed) == {"2026-01": 100, "2026-02": -15}


def test_curve_does_not_neutralize_fees_or_double_preopen_costs():
    parsed = ParsedExport("fixture", "positions", trades=[
        trade(D(2026, 1, 2), D(2026, 1, 4), 50, -5)],
        balances=[BalanceRow(D(2026, 1, 3, 12), 100)], costs=[
            AccountCostRow(D(2026, 1, 1), -10, "Commission"),
            AccountCostRow(D(2026, 1, 3), -2, "Commission")])
    # Drawdown start already accounts for the pre-open -10.
    curve = signal_statistik._kurve(parsed, 90)
    assert curve == [["2026-01-03 00:00:00", 88, 0],
                     ["2026-01-03 12:00:00", 188, 100],
                     ["2026-01-04 00:00:00", 233, 0]]


@pytest.mark.parametrize("before_open", [False, True])
def test_signal_end_amount_and_total_net_include_each_cost_once(tmp_path, monkeypatch, before_open):
    path = tmp_path / "fixture.csv"; path.touch()
    parsed = ParsedExport(str(path), "positions", trades=[
        trade(D(2026, 1, 2), D(2026, 1, 4), 50, -5)], costs=[
            AccountCostRow(D(2026, 1, 1 if before_open else 2), -10, "Commission"),
            AccountCostRow(D(2026, 1, 3), -2, "Commission")])
    monkeypatch.setattr(signal_statistik, "load_export", lambda *a, **k: parsed)
    monkeypatch.setattr(signal_statistik, "effizienz_kennzahlen", lambda *a, **k: None)
    monkeypatch.setattr(signal_statistik, "_monatsserie", lambda *a, **k: {})
    result = signal_statistik.berechne(str(path), {"initial_deposit_usd": 100})
    assert result["kapitalbasis_usd"] == (90 if before_open else 100)
    assert result["netto_gesamt_usd"] == 33
    assert result["endstand_virtuell_usd"] == 133
    assert result["kurve"][-1][1] == 133
    assert result["kontokosten_anzahl"] == 2 and result["kontokosten_usd"] == -12


def test_cost_only_export_keeps_money_sum_without_trade_metrics(tmp_path, monkeypatch):
    path = tmp_path / "fixture.csv"; path.touch()
    parsed = ParsedExport(str(path), "positions", costs=[
        AccountCostRow(D(2026, 1, 1), -10, "Commission")])
    result = stats.compute(parsed)
    assert result["trades"] == 0 and result["net"] == -10
    assert result.get("profit_factor_csv") is None
    assert stats.negative_months_full(parsed) == []
    monkeypatch.setattr(signal_statistik, "load_export", lambda *a, **k: parsed)
    result = signal_statistik.berechne(str(path), {})
    assert result["trades"] == 0 and not result["kapitalbasis_ok"]
    assert result["netto_gesamt_usd"] == -10


def test_financial_partial_statistics_keep_fees_without_time_metrics(tmp_path, monkeypatch):
    path = tmp_path / "fixture.csv"; path.touch()
    parsed = ParsedExport(str(path), "positions", trades=[
        trade(D(2026, 1, 2), D(2026, 1, 1), 50, -5)], costs=[
            AccountCostRow(D(2026, 1, 3), -2, "Commission")])
    def load(*args, **kwargs):
        if not kwargs.get("nur_finanzdaten"):
            raise ValueError("negative duration")
        return parsed
    monkeypatch.setattr(signal_statistik, "load_export", load)
    result = signal_statistik.berechne(str(path), {"initial_deposit_usd": 100})
    assert result["teilstatistik_finanzdaten"]
    assert result["netto_gesamt_usd"] == 43
    assert result["trades"] == 1 and result["kontokosten_usd"] == -2
    assert result.get("kurve") is None and result.get("ertrag_monat_geom_pct") is None
