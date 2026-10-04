"""Equity-DD darf nicht durch den Drawdown geschlossener Trades ersetzt werden."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import db, pipeline
from mqlkiscanner.analysis_version import FORENSICS_VERSION


# Review 04.10. (Paket D): Der Monitor-Wert (TradeEqDrawdownPct) ist eine
# Closing-Kurve — er bleibt Schranken-Kanal, taucht aber NICHT mehr als
# "Max-Drawdown (gemessen)" auf; ohne Kurs-Messung bleibt die Spalte unbekannt.
@pytest.mark.parametrize("kurse,monitor,erwartet", [
    (None, None, None), (44.34, None, 44.34), (None, 46.65, None),
    (20.0, 35.0, 20.0), (0.0, None, 0.0),
])
def test_equity_spalte_ersetzt_geschlossene_trades_nicht(kurse, monitor, erwartet):
    r = pipeline.ScanResult(
        id=2342895, trading_dd_pct=8.14, dd_equity_pct=34.95,
        equity_dd_rekonstruiert_pct=kurse, monitor_trade_eq_dd_pct=monitor)
    zeile = r.to_row()
    assert zeile["Max-Drawdown %"] == erwartet
    assert zeile["Trading-DD % (geschlossen)"] == 8.14
    assert zeile["Drawdown % (Plattform)"] == 34.95


def test_unvollstaendige_kiracat_reko_zeigt_diagnose_und_plattform_sperre():
    db.init_db()
    db.store_scan_result(2342895, {
        "name": "KiraCat", "platform": "MT5",
        "stats": {"eq_dd_pct": 34.95, "bal_dd_pct": 7.08,
                  "forensik_ok": True, "forensik_version": FORENSICS_VERSION}},
        forensik={
            "version": FORENSICS_VERSION, "vollstaendig": True,
            "trading_dd": {"pct": 8.14, "usd": 2117.7},
            "peak_exposure": {"shock_pct_max": 10.0},
            "equity_rekonstruktion": {
                "status": "unvollstaendig", "verlaesslich": False,
                "equity_dd_pct": 44.34, "abdeckung_pct": 96.7,
                "grund": "Kursdaten fehlen für 4 von 556 Trades",
                "symbole_ohne_kurse": ["US100"],
                "methodik": "virtuelle_trading_equity_h1_schlusskurse"}})
    r = pipeline.results_from_db()[0]
    assert r.max_drawdown_equity_pct is None
    assert r.trading_dd_pct == 8.14
    assert r.schranke_verletzt and r.ampel == "🔴"
    assert r.equity_rekon_status == "unvollstaendig"
    assert r.equity_rekon_abdeckung_pct == 96.7
    assert r.equity_rekon_methodik == "virtuelle_trading_equity_h1_schlusskurse"
    assert "US100" in r.to_row()["Equity-Messung"]


def test_detail_benannt_8_prozent_als_trading_dd_und_fehlende_equity():
    r = pipeline.ScanResult(
        id=2342895, name="KiraCat", platform="MT5", trading_dd_pct=8.14,
        dd_equity_pct=34.95, equity_rekon_status="unvollstaendig",
        equity_rekon_grund="Kurse fehlen: US100")
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from mqlkiscanner.app_ui import render_detail\n"
        "render_detail(st.session_state.result)", default_timeout=30)
    at.session_state["result"] = r
    at.run()
    assert not at.exception, at.exception
    werte = {m.label: m.value for m in at.metric}
    assert werte["Max-Drawdown (Equity, gemessen)"] == "—"
    assert werte["Trading-DD (geschlossen)"] == "8.1 %"
    assert werte["Drawdown (Plattform)"] == "35.0 %"
    assert any("US100" in w.value and "keine zwischenzeitlichen" in w.value
               for w in at.warning)


def test_veraltete_kurs_reko_bleibt_auditwert_ohne_frische_equity_anzeige():
    db.init_db()
    alt = FORENSICS_VERSION - 1
    db.store_scan_result(900002, {
        "name": "Alter Kursbefund", "platform": "MT5",
        "stats": {"eq_dd_pct": 5.0, "forensik_ok": True,
                  "forensik_version": alt}},
        forensik={"version": alt, "vollstaendig": True,
                  "trading_dd": {"pct": 5.0},
                  "peak_exposure": {"shock_pct_max": 5.0},
                  "equity_rekonstruktion": {
                      "status": "ok", "verlaesslich": True,
                      "equity_dd_pct": 6.0, "gmt_offset_h": 2}})
    r = pipeline.results_from_db()[0]
    assert r.forensik_stale
    assert r.equity_dd_rekonstruiert_pct == 6.0  # raw Auditwert bleibt
    assert r.to_row()["Max-Drawdown %"] is None
    assert "veraltet" in r.equity_messung_status
    assert "fehlgeschlagen" not in r.urteil and "None" not in r.urteil


def test_forensik_payload_liefert_methodik_und_unvollstaendigkeit():
    r = pipeline.ScanResult(
        id=2342895, equity_rekon_status="unvollstaendig",
        equity_rekon_grund="Kurse fehlen: US100", equity_rekon_abdeckung_pct=96.7,
        equity_rekon_methodik="virtuelle_trading_equity_h1_schlusskurse")
    payload = json.loads(pipeline._forensik_json(r))
    m = payload["equity_rekonstruktion_methodik"]
    assert m["status"] == "unvollstaendig" and m["abdeckung_pct"] == 96.7
    assert "US100" in m["grund"]
    assert "virtuelle" in m["methodik"]
    assert "Bar-Ende" in m["kursraster"] and "Intrabar" in m["kursraster"]
    assert "Ein-/Auszahlungen fehlen" in m["kapitalfluesse"]
    assert "aktuell offene Positionen fehlen" in m["positionsbasis"]


@pytest.mark.parametrize("kind", ["risiko_analyse", "gesamtbericht", "portfolio"])
def test_drawdown_vergleichsregel_ist_mit_defaults_synchron(kind):
    from mqlkiscanner.llm import prompts
    text = (Path(__file__).resolve().parents[1] / "config" / "prompts"
            / f"{kind}.md").read_text(encoding="utf-8")
    assert text.strip() == prompts.DEFAULTS[kind].strip()
    assert "gleicher Kapitalbasis" in text and "Datenabdeckung" in text
    assert "KEINE Schoenmeldung oder Taeuschung" in text or "KEINE Schoenmeldung oder" in text
    assert "Bar-Ende" in text and "Intrabar-Extrema" in text
    assert "meldet seinen Drawdown schoener" not in text
