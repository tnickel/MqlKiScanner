"""Lots display stays truthful for validated data and incomplete old payloads."""
from copy import deepcopy

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import signal_statistik


def _detail(statistics):
    app = AppTest.from_string('''
import streamlit as st
from mqlkiscanner.pipeline import ScanResult
from mqlkiscanner.alle_signale_ui import render_detail
render_detail(ScanResult(id=123, name="Synthetic lots", source_kind="demo",
                         account_currency="USD"), st.session_state["statistics"],
              key_prefix="synthetic_lots")
''', default_timeout=20)
    app.session_state["statistics"] = deepcopy(statistics)
    app.run()
    assert not app.exception
    return next(e for e in app.dataframe if "Lots min/max" in e.value)


def test_validated_csv_statistics_keep_both_precise_lot_bounds(tmp_path):
    path = tmp_path / "synthetic_positions.csv"
    path.write_text(
        "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
        "2026.01.01 00:00:00;Balance;;;;;;;;;1000\n"
        "2026.01.05 10:00:00;Buy;0.001;EURUSD;1.10;0.001;2026.01.05 12:00:00;1.11;0;0;1\n"
        "2026.02.05 10:00:00;Sell;0.125;EURUSD;1.11;0.125;2026.02.05 12:00:00;1.10;0;0;10\n",
        encoding="utf-8")
    statistics = signal_statistik.berechne(str(path), {"account_currency": "USD"})
    assert not statistics.get("fehler")
    assert statistics["per_symbol"]["EURUSD"]["lots_min"] == 0.001
    assert statistics["per_symbol"]["EURUSD"]["lots_max"] == 0.125
    original = deepcopy(statistics)
    element = _detail(statistics)
    assert element.value.iloc[0]["Lots min/max"] == "0.001–0.125"
    assert statistics == original


@pytest.mark.parametrize("bounds,expected", [
    ({}, None),
    ({"lots_min": None, "lots_max": None}, None),
    ({"lots_min": None, "lots_max": 0.125}, "unbekannt–0.125"),
    ({"lots_min": 0.001}, "0.001–unbekannt"),
    ({"lots_min": float("nan"), "lots_max": None}, None),
    ({"lots_min": 0, "lots_max": 0}, "0–0"),
])
def test_incomplete_historical_lot_bounds_stay_unknown_without_inventing_zero(bounds, expected):
    statistics = {"kapitalbasis_ok": False, "trades": 1, "per_symbol": {
        "EURUSD": {"trades": 1, "net": 0, "winrate_pct": 0, **bounds}}}
    element = _detail(statistics)
    value = element.value.iloc[0]["Lots min/max"]
    if expected is None:
        assert pd.isna(value)
        assert element.proto.HasField("placeholder") and element.proto.placeholder == ""
    else:
        assert value == expected
    assert not any(token in str(value) for token in ("None–", "–None", "nan–"))
