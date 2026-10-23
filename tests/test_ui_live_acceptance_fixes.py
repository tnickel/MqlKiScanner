"""Live UI findings: identity labels, current USD fallback and stale colors."""
import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from conftest import ROOT
from mqlkiscanner import app_ui, db, fix_signale, katalog, pipeline
from mqlkiscanner.alle_signale_ui import tabellen_zeile


def _measured(**changes):
    values = dict(id=42, quelle="mql5", platform="mt4", account_currency="USD",
                  forensik_vorhanden=True, equity_dd_rekonstruiert_pct=10.,
                  equity_dd_rekonstruiert_usd=250.)
    values.update(changes)
    return pipeline.ScanResult(**values)


def test_current_workflow_usd_is_visible_without_a_separate_study():
    result = _measured()
    assert tabellen_zeile(result, None)["True-DD USD"] == 250.
    assert result.true_dd_usd is None  # Display fallback does not rewrite evidence.
    assert tabellen_zeile(_measured(true_dd_usd=100.), None)["True-DD USD"] == 100.


@pytest.mark.parametrize("changes", [
    {"forensik_stale": True}, {"forensik_vorhanden": False}, {"fehler": "failed"},
    {"equity_dd_rekonstruiert_pct": None}, {"equity_dd_rekonstruiert_usd": float("nan")},
    {"equity_dd_rekonstruiert_usd": float("inf")}, {"equity_dd_rekonstruiert_usd": -1},
    {"equity_dd_rekonstruiert_usd": True}, {"account_currency": "EUR"},
])
def test_workflow_usd_fallback_cannot_bypass_measurement_or_currency_guards(changes):
    assert tabellen_zeile(_measured(**changes), None)["True-DD USD"] is None


def test_workflow_usd_fallback_respects_partial_statistics_guard():
    assert tabellen_zeile(_measured(), {"teilstatistik_finanzdaten": True})["True-DD USD"] is None


def test_all_signals_styles_actual_stale_marker_and_serializes_missing_values(monkeypatch):
    rows = [_measured(name="Current"), _measured(id=43, name="Stale", forensik_stale=True,
                                                equity_dd_rekon_roh_pct=13.83)]
    monkeypatch.setattr(pipeline, "results_from_db", lambda **kw: rows)
    monkeypatch.setattr(db, "list_catalog", lambda **kw: [])
    monkeypatch.setattr(katalog, "katalog_resultate", lambda **kw: ([], {}))
    captured = []
    original = st.dataframe

    def capture(styled, **kwargs):
        captured.append(styled)
        return original(styled, **kwargs)

    monkeypatch.setattr(st, "dataframe", capture)
    at = AppTest.from_file(str(ROOT / "app_pages/alle_signale.py"), default_timeout=60).run()
    assert not at.exception
    frame = at.dataframe[0].value
    stale_idx = frame.index[frame.Name == "Stale"][0]
    measured_col = frame.columns.get_loc("True-DD %")
    approx_col = frame.columns.get_loc("True-DD ≈")
    ctx = captured[-1]._compute().ctx
    assert (stale_idx, measured_col) not in ctx
    assert dict(ctx[(stale_idx, approx_col)])["color"] == "#fb923c"
    assert pd.isna(frame.loc[stale_idx, "True-DD %"])
    assert pd.isna(frame.loc[stale_idx, "True-DD USD"])
    assert pd.api.types.is_numeric_dtype(frame["True-DD %"])
    assert pd.api.types.is_numeric_dtype(frame["True-DD USD"])


def test_results_missing_measurement_keeps_numeric_data():
    at = AppTest.from_string(
        'import streamlit as st\n'
        'from mqlkiscanner.app_ui import render_results_table\n'
        'render_results_table(st.session_state.rows)', default_timeout=30)
    at.session_state["rows"] = [_measured(), _measured(id=43, equity_dd_rekonstruiert_pct=None)]
    at.run()
    assert not at.exception
    actual = at.dataframe[0].value
    assert pd.api.types.is_numeric_dtype(actual["Max-Drawdown %"])
    assert pd.isna(actual.loc[1, "Max-Drawdown %"])


def test_scan_fix_caption_uses_source_qualified_labels(monkeypatch):
    monkeypatch.setattr(fix_signale, "fix_keys", lambda *a, **kw: {("second", 42), ("mql5", 42)})
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60).run()
    assert not at.exception
    caption = next(c.value for c in at.caption if "Fix gesetzt:" in c.value)
    assert "mql5:42, second:42" in caption
    assert "('mql5'" not in caption
