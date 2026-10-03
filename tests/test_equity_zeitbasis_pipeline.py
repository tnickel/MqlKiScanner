"""Wechselnde Kurszeiten bleiben im Reload und im KI-Befund sichtbar."""
from __future__ import annotations

import json

import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import db, pipeline
from mqlkiscanner.analysis_version import FORENSICS_VERSION
from mqlkiscanner.equity_studie_ui import _cache_key


def _zeitbasis(verlaesslich=True):
    return {
        "modus": "wochenweise", "frame": "referenzkurszeit", "global_gmt_h": 0,
        "verlaesslich": verlaesslich,
        "annahme": "Kalenderwochengrenzen sind Modellgrenzen, kein exakter DST-Beleg",
        "perioden": [{"von": "2026-03-02", "bis": "2026-03-09", "gmt_h": 0},
                     {"von": "2026-03-09", "bis": "2026-03-16", "gmt_h": 1}],
        "gruende": [] if verlaesslich else ["abweichender Versatz unbewiesen"],
    }


@pytest.mark.parametrize("verlaesslich", [True, False])
def test_db_reload_und_ki_behalten_abschnittsweise_zeitbasis(verlaesslich):
    db.init_db()
    basis = _zeitbasis(verlaesslich)
    db.store_scan_result(900103, {
        "name": "Zeitbasis Audit", "platform": "MT4",
        "stats": {"forensik_ok": True, "forensik_version": FORENSICS_VERSION}},
        forensik={"version": FORENSICS_VERSION, "vollstaendig": True,
                  "score": 4.0, "trading_dd": {"pct": 1.0},
                  "peak_exposure": {"shock_pct_max": 1.0},
                  "equity_rekonstruktion": {
                      "status": "ok" if verlaesslich else "unvollstaendig",
                      "verlaesslich": verlaesslich, "equity_dd_pct": 7.68,
                      "gmt_offset_h": 0, "zeitbasis": basis}})
    result = pipeline.results_from_db()[0]
    assert result.equity_rekon_zeitbasis == basis
    assert result.equity_rekon_gmt_text == "GMT abschnittsweise (+0 h, +1 h)"
    assert result.max_drawdown_equity_pct == (7.68 if verlaesslich else None)
    payload = json.loads(pipeline._forensik_json(result))
    methodik = payload["equity_rekonstruktion_methodik"]
    assert methodik["zeitbasis"] == basis
    assert "DD-Definition" in methodik["vergleichbarkeit"]
    assert "Floating-Verlust" in methodik["plattform_mql_hinweis"]
    if verlaesslich:
        assert "GMT abschnittsweise" in result.urteil
    else:
        assert payload["max_drawdown_equity_pct"] is None


def test_fehlender_gmt_ist_keine_format_exception():
    result = pipeline.ScanResult(id=1, equity_rekon_gmt_h=None)
    assert result.equity_rekon_gmt_text == "GMT unbelegt"
    assert json.loads(pipeline._forensik_json(result))["equity_rekonstruktion_methodik"]["zeitbasis"] is None


def test_studien_cache_verwendet_neue_methodikversion():
    result = pipeline.ScanResult(id=2349227, trades_sha256="a" * 64)
    assert _cache_key(result) == "eqdd_studie_zeitbasis_v10_2349227_aaaaaaaaaaaa"
    assert not _cache_key(result).startswith("eqdd_studie_h1_ende_v2_")


@pytest.mark.parametrize("profil_ort", ["kurve", "symbol"])
def test_studien_ui_zeigt_unbewiesenen_zeitabschnitt(profil_ort):
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from mqlkiscanner.equity_studie_ui import _symbol_diagnose\n"
        "_symbol_diagnose(st.session_state.daten)", default_timeout=30)
    daten = {
        "symbole": [{"symbol": "XAUUSD", "gmt_h": 0, "status": "erkannt",
                     "trefferquote": .95}]}
    if profil_ort == "kurve":
        daten["zeitbasis"] = _zeitbasis(False)
    else:
        daten["symbole"][0]["zeitbasis"] = _zeitbasis(False)
    at.session_state["daten"] = daten
    at.run()
    assert not at.exception
    assert len(at.dataframe) == 2
    assert any("abweichender Versatz unbewiesen" in w.value for w in at.warning)
    assert any("kein exakter DST-Beleg" in c.value for c in at.caption)
    symboltabelle = next(frame.value for frame in at.dataframe
                         if "Symbol" in frame.value.columns)
    assert symboltabelle.iloc[0]["GMT"] == "abschnittsweise (+0 h, +1 h)"
    assert symboltabelle.iloc[0]["Status"] == "⚠️ Zeitbasis unvollständig"


def test_studien_ui_unangewandtes_modell_verdeckt_symbolversatz_nicht():
    basis = _zeitbasis(False)
    basis["angewandt"] = False
    basis["frame"] = "broker"
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from mqlkiscanner.equity_studie_ui import _symbol_diagnose\n"
        "_symbol_diagnose(st.session_state.daten)", default_timeout=30)
    at.session_state["daten"] = {
        "zeitbasis": basis,
        "symbole": [{"symbol": "XAUUSD", "gmt_h": 2, "status": "erkannt"}]}
    at.run()
    assert not at.exception
    table = next(frame.value for frame in at.dataframe if "Symbol" in frame.value.columns)
    assert table.iloc[0]["GMT"] == "+2 h"
    assert "uneinheitliche" in table.iloc[0]["Status"]
    assert any("nicht auf die Kurve angewandt" in c.value for c in at.caption)


def test_demo_und_ki_behalten_hinweis_auf_identische_tradezeilen(tmp_path):
    from mqlkiscanner.parser import POSITION_HEADER
    path = tmp_path / "identische_positionen.csv"
    balance = ["2026.01.01 09:00:00", "Balance"] + [""] * 8 + ["1000"]
    trade = "2026.01.01 10:00:00;Buy;0.1;XAUUSD;2400;0.1;2026.01.02 10:00:00;2399;0;0;-10"
    path.write_text("\n".join([";".join(POSITION_HEADER), ";".join(balance)]
                              + [trade] * 10), encoding="utf-8")
    result = pipeline.ScanPipeline.analyze_local_files([str(path)])[0]
    assert result.identische_tradezeilen == 9
    assert result.peak_positionen == 10
    assert result.trading_dd_pct == 10.0
    quality = json.loads(pipeline._forensik_json(result))["trade_datenqualitaet"]
    assert quality["identische_tradezeilen"] == 9
    assert "alle erhalten" in quality["behandlung"]
