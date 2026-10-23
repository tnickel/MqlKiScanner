"""Review fixes: historical DD labels and one factual snapshot for table/CSV."""
import io

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from conftest import ROOT
from mqlkiscanner import app_ui, pipeline
from mqlkiscanner.alle_signale_ui import tabellen_zeile


@pytest.mark.parametrize("stale", [False, True])
def test_raw_dd_explains_whether_workflow_finding_is_stale(stale):
    result = pipeline.ScanResult(
        id=123, quelle="mql5", platform="MT5", account_currency="USD",
        forensik_stale=stale, equity_dd_rekon_roh_pct=13.83,
        equity_rekon_grund="Abdeckung nicht ausreichend")
    row = tabellen_zeile(result, None)
    assert row["True-DD %"] == (None if stale else 13.83)
    assert row["True-DD ≈"] == pytest.approx(13.83)
    assert ("Workflow-Forensik veraltet" in row["Messstatus"]) is stale
    assert ("kein aktueller Messnachweis" in row["Messstatus"]) is stale


def test_independent_current_study_is_not_presented_as_old_raw_dd():
    result = pipeline.ScanResult(
        id=123, quelle="mql5", platform="MT5", account_currency="USD",
        forensik_stale=True, equity_dd_rekon_roh_pct=13.83,
        studie_anzeige_dd_pct=7.0, studie_anzeige_vorbehalt=False)
    row = tabellen_zeile(result, {"dauer_monate": 12, "cagr_jahr_pct": 42,
                                "ertrag_monat_geom_pct": 3})
    assert row["True-DD %"] == 7 and row["True-DD ≈"] is None
    assert row["TrueRetDD"] == 6
    assert "Unabhängige H1-Studie" in row["Messstatus"]
    assert "True-DD ≈ aus altem Workflow-Befund" not in row["Messstatus"]


@pytest.mark.parametrize("filtered", [False, True])
def test_results_csv_uses_same_factual_snapshot_as_table(monkeypatch, filtered):
    downloads, document_reads, history_reads, displayed_options = [], [], [], []
    monkeypatch.setattr(st, "download_button", lambda label, data, *a, **kw: downloads.append(data))

    def documents(ids):
        document_reads.append(list(ids))
        return {signal_id: 2 if len(document_reads) == 1 else 9 for signal_id in ids}

    def history(ids, **kwargs):
        history_reads.append(list(ids))
        return {signal_id: {
            "abonnenten": (17 if len(history_reads) == 1 else 99) if signal_id == ("pelik", 101) else None,
            "tage30": 4 if signal_id == ("pelik", 101) else None,
            "tage7": -2 if signal_id == ("pelik", 101) else None,
        } for signal_id in ids}

    monkeypatch.setattr(app_ui.db, "downloader_report_counts", documents)
    monkeypatch.setattr(app_ui.downloader_sync, "abo_bilanz", history)
    original_dataframe = st.dataframe

    def capture(frame, *args, **kwargs):
        displayed_options.append(kwargs)
        return original_dataframe(frame, *args, **kwargs)

    monkeypatch.setattr(st, "dataframe", capture)
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60).run()
    at.session_state["scan_results"] = [
        pipeline.ScanResult(id=101, name="Alpha", quelle="pelik", platform="pelican",
                            ampel="🟡", persisted_this_run=True),
        pipeline.ScanResult(id=102, name="Beta", quelle="mql5", platform="MT5", ampel="🔴"),
    ]
    at.switch_page(str(ROOT / "app_pages/ergebnisse.py")).run()
    at.selectbox(key="results_run").set_value("Aktuelle Sitzung").run()
    assert not at.exception
    downloads.clear()
    document_reads.clear()
    history_reads.clear()
    displayed_options.clear()
    at.text_input(key="results_search").set_value("Beta" if filtered else "").run()
    assert not at.exception
    assert len(downloads) == len(document_reads) == len(history_reads) == 1
    table = at.dataframe[0].value
    exported = pd.read_csv(io.BytesIO(downloads[0]), sep=";", encoding="utf-8-sig",
                           dtype=str, keep_default_na=False)
    factual = table.drop(columns=["Bericht", "Studie"], errors="ignore")
    assert list(exported.columns) == list(factual.columns)
    assert list(exported["ID"].astype(int)) == list(table["ID"]) == ([102] if filtered else [101, 102])
    for column in factual.columns:
        for expected, actual in zip(factual[column], exported[column]):
            if pd.isna(expected) or expected == "":
                assert actual == ""
            elif isinstance(expected, (int, float)):
                assert float(actual) == pytest.approx(expected)
            elif isinstance(expected, pd.Timestamp):
                assert pd.Timestamp(actual) == expected
            else:
                assert str(actual) == str(expected)
    assert table.loc[table["ID"] == 102, "Abonnenten"].iloc[0] == ""
    if not filtered:
        assert table.loc[table["ID"] == 101, "Abonnenten"].iloc[0] == "17"
    options = displayed_options[0]["column_config"]
    assert options["Link"]["label"] == "Signal-Link"
    assert "Monitor-Closing-DD" in options["Max-Drawdown %"]["help"]
