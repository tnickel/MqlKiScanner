# -*- coding: utf-8 -*-
"""Quellen-Werte als Strings mit deutschem Dezimalkomma dürfen die
Forensik nie werfen (realer Fall 04.10.: MqlDownloader lieferte
EquityDrawdown '9,10' für GS MT5 — scoring crashte mit ValueError,
DB-Fehler für das Signal, alter Stand blieb)."""
from __future__ import annotations

import pytest

from mqlkiscanner import ingest, scoring


def test_metrics_zu_stats_parsst_komma_strings():
    stats = ingest.metrics_zu_stats({"metrics": {
        "EquityDrawdown": "9,10",
        "Average3MonthProfit": "1 234,5",
        "InitialDeposit": "2.000,00",
        "Balance": 3500.75,
        "TradeEqDrawdownPct": "12,3",
        "InitialDepositVirtual": "10000",
    }})
    assert stats["dd_equity_pct"] == pytest.approx(9.10)
    assert stats["monthly_growth_pct"] == pytest.approx(1234.5)
    assert stats["initial_deposit_usd"] == pytest.approx(2000.0)
    assert stats["balance_usd"] == pytest.approx(3500.75)
    assert stats["monitor_trade_eq_dd_pct"] == pytest.approx(12.3)
    assert stats["kapitalbasis_virtual_usd"] == pytest.approx(10000.0)


def test_metrics_zu_stats_laesst_unparsebares_als_none():
    stats = ingest.metrics_zu_stats({"metrics": {
        "EquityDrawdown": "—", "Balance": None, "InitialDeposit": "n/a"}})
    assert stats["dd_equity_pct"] is None
    assert stats["balance_usd"] is None
    assert stats["initial_deposit_usd"] is None


def test_scoring_ueberlebt_plattform_strings_mit_komma():
    """Der ursprüngliche Crash-Pfad: dimension_inputs/evaluate mit
    eq_dd_pct als '9,10'."""
    report = {"forensics": {"drawdown": {"trading_dd": {"dd_pct": 5.0}}},
              "stats": {}}
    dims = scoring.dimension_inputs(report, {"eq_dd_pct": "9,10"})
    ev = scoring.evaluate(report, platform={"eq_dd_pct": "9,10"},
                          schranke_eq_dd_pct=30.0)
    assert ev["schranke_dd_pct"] == pytest.approx(9.1)
    assert dims  # Dimensionen wurden berechnet, kein ValueError


def test_dd_maximum_parsst_strings_robust():
    assert scoring.dd_maximum(None, "9,10", 4.5) == pytest.approx(9.1)
    assert scoring.dd_maximum("abc", None) == 0.0
