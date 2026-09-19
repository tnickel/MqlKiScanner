"""Streamlit exposes each stored report as a PDF without losing row identity."""
from __future__ import annotations

from streamlit.testing.v1 import AppTest

from conftest import ROOT
from mqlkiscanner import pipeline
from mqlkiscanner.pdf_reports import snapshot_token


def _downloads(at: AppTest):
    return at.get("download_button")


def test_table_opens_pdf_report_and_detail_offers_all_pdfs_for_repeated_ids(monkeypatch):
    first = pipeline.ScanResult(
        id=900001, name="Snapshot A", trades_path=r"C:\a.csv",
        trade_analyse="Trade A", risiko_analyse="Risiko A", gesamtbericht="Final A")
    second = pipeline.ScanResult(
        id=900001, name="Snapshot B", trades_path=r"C:\b.csv",
        trade_analyse="Trade B", risiko_analyse="Risiko B", gesamtbericht="Final B")
    from types import SimpleNamespace
    from mqlkiscanner import app_ui

    click_pending = True
    captured = {}

    def click_second(*args, **kwargs):
        nonlocal click_pending
        captured["frame"] = args[0]
        if click_pending:
            column = kwargs["column_config"]["Bericht"]
            app_ui.st.session_state[column.key] = SimpleNamespace(row=1)
            column.on_click()
            click_pending = False
        return SimpleNamespace(selection=SimpleNamespace(rows=[]))

    monkeypatch.setattr(app_ui.st, "dataframe", click_second)
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from mqlkiscanner.app_ui import render_results_table, render_report_panel, render_detail\n"
        "render_results_table(st.session_state.rows, key='snapshots')\n"
        "render_report_panel(st.session_state.rows)\n"
        "render_detail(st.session_state.rows[1])",
        default_timeout=30,
    )
    at.session_state["rows"] = [first, second]
    at.run()
    assert not at.exception
    downloads = _downloads(at)
    assert list(captured["frame"]["Bericht"]) == [
        ":material/picture_as_pdf: Öffnen",
        ":material/picture_as_pdf: Öffnen",
    ]
    second_token = snapshot_token(second.source_kind, second.id, second.trades_path,
                                  second.trades_sha256, second.name)
    keys = {item.key for item in downloads}
    assert f"report_panel_final_{second_token}" in keys
    assert f"report_panel_trade_{second_token}" in keys
    assert f"report_panel_risk_{second_token}" in keys
    assert f"detail_trade_{second_token}" in keys
    assert f"detail_risk_{second_token}" in keys
    assert f"detail_final_{second_token}" in keys


def test_report_panel_offers_final_and_intermediate_pdfs_for_exact_snapshot():
    result = pipeline.ScanResult(
        id=0, name="Lokaler Snapshot", trades_path=r"C:\same-id.csv",
        trade_analyse="Trade", risiko_analyse="Risiko", gesamtbericht="Final")
    identity = (result.source_kind, result.id, result.trades_path,
                result.trades_sha256, result.name)
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from mqlkiscanner.app_ui import render_report_panel\n"
        "render_report_panel(st.session_state.rows)",
        default_timeout=30,
    )
    at.session_state["rows"] = [result]
    at.session_state["report_signal_id"] = 0
    at.session_state["report_result_identity"] = identity
    at.run()
    assert not at.exception
    labels = {item.label for item in _downloads(at)}
    assert {"Gesamtbericht als PDF", "Trade-Analyse PDF", "Risiko-Analyse PDF"} <= labels


def test_portfolio_pdf_is_visible_on_scan_and_results_pages():
    result = pipeline.ScanResult(id=1234567, name="Signal", gesamtbericht="Final")
    portfolio = {
        "text": "Portfolio final", "created_at": "2026-09-19 10:15:51", "model": "model-2",
    }
    scan = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    scan.session_state["scan_results"] = [result]
    scan.session_state["portfolio_bericht"] = portfolio["text"]
    scan.session_state["portfolio_result"] = portfolio
    scan.run()
    assert not scan.exception
    assert any(item.key == "scan_portfolio_pdf" for item in _downloads(scan))

    results = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    results.session_state["scan_results"] = [result]
    results.session_state["portfolio_bericht"] = portfolio["text"]
    results.session_state["portfolio_result"] = portfolio
    results.run().switch_page("app_pages/ergebnisse.py").run()
    results.selectbox(key="results_run").set_value("Aktuelle Sitzung").run()
    assert not results.exception
    assert any(item.key == "results_portfolio_pdf_source" for item in _downloads(results))


def test_prompt_tab_explains_engine_inputs_models_and_outputs():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.run().switch_page("app_pages/admin.py").run()
    assert not at.exception
    body = "\n".join(
        element.value
        for kind in ("markdown", "caption", "info")
        for element in getattr(at, kind)
    )
    assert "Die Engine rechnet, die KI interpretiert" in body
    assert "Forensische Fakten" in body
    assert "Trade-Analyse" in body and "Risiko-Analyse" in body
    assert "Gesamtbericht" in body and "Portfolio" in body
    assert "EINGANG" in body and "MODELL" in body and "AUSGANG" in body
    assert at.text_area(key="prompt_trade_analyse")
