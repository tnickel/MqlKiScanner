# -*- coding: utf-8 -*-
"""Regelwerk der Ausschlussliste: Inhalt, Grenzwerte und Anzeige."""
from __future__ import annotations

from streamlit.testing.v1 import AppTest

from mqlkiscanner import config, db, pipeline, regelwerk
from mqlkiscanner.regelwerk import ausgeschlossen_eintrag, regelwerk_markdown

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def test_regelwerk_listet_alle_ausschluesse_mit_grund(monkeypatch):
    monkeypatch.setattr(config, "load_known_signals", lambda: {
        "ausgeschlossen": [
            {"id": 2306053, "name": "Kenni Trades Gold Breakout (MT4)",
             "grund": "EQ-DD 23.1% UND Bal-DD 27.9%, 18 Verluste in Serie"},
            {"id": 2379208, "name": "World PEACE Multi FX Algo",
             "grund": "Grid+Martingale ohne SL, EQ-DD 30.6%"},
        ],
        "watchlist": []})
    text = regelwerk_markdown({"schranke_eq_dd_pct": 30.0,
                               "min_ertrag_pct_monat": 5.0})
    assert "2306053" in text and "18 Verluste in Serie" in text
    assert "World PEACE Multi FX Algo" in text and "Grid+Martingale" in text
    assert "Aktuelle Ausschlüsse (2)" in text


def test_regelwerk_nennt_kategorien_und_grenzwerte():
    text = regelwerk_markdown({})
    for kategorie, _ in regelwerk.KATEGORIEN:
        assert kategorie in text
    assert "Grenznahe Risikokombination" in text          # Kenni-Kategorie
    assert "Schranke 30 % Drawdown" in text
    assert "Mindest-Ertrag 5 %/Monat" in text
    assert "Wiederaufnahme" in text                        # Entkraeftungs-Pfad


def test_regelwerk_zeigt_grenzwerte_aus_settings():
    text = regelwerk_markdown({"schranke_eq_dd_pct": 25.0,
                               "min_ertrag_pct_monat": 10.0})
    assert "Schranke 25 % Drawdown" in text
    assert "Mindest-Ertrag 10 %/Monat" in text


def test_ausgeschlossen_eintrag_liefert_grund_oder_none(monkeypatch):
    monkeypatch.setattr(config, "load_known_signals", lambda: {
        "ausgeschlossen": [{"id": 111, "name": "X", "grund": "Testgrund"}]})
    eintrag = ausgeschlossen_eintrag(111)
    assert eintrag == {"id": 111, "name": "X", "grund": "Testgrund"}
    assert ausgeschlossen_eintrag(999) is None


def test_markdown_escaped_pipe_in_grund(monkeypatch):
    monkeypatch.setattr(config, "load_known_signals", lambda: {
        "ausgeschlossen": [{"id": 1, "name": "A|B", "grund": "x | y"}]})
    text = regelwerk_markdown({})
    assert "A|B" not in text and "x | y" not in text


def test_ergebnisse_seite_zeigt_regelwerk_abschnitt(monkeypatch):
    db.init_db()
    monkeypatch.setattr(config, "load_known_signals", lambda: {
        "ausgeschlossen": [{"id": 999003, "name": "Listen-Kandidat",
                            "grund": "Test-Schranke verletzt"}],
        "watchlist": []})
    db.store_scan_result(999003, {
        "name": "Listen-Kandidat", "platform": "MT5",
        "stats": {"forensik_ok": True, "eq_dd_pct": 34.0},
    }, forensik={"version": 1, "vollstaendig": True,
                 "trading_dd": {"pct": 34.0, "usd": 900.0},
                 "martingale_flag": False, "stop_evidence": "none",
                 "symbole": "XAUUSD"})
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    at.switch_page("app_pages/ergebnisse.py").run()
    assert not at.exception, at.exception
    # Expander-Inhalt ist in AppTest Bestandteil des Baums:
    inhalt = " ".join(getattr(el, "value", "") or "" for el in at.markdown)
    assert "Harte Regeln" in inhalt                    # Regelwerk-Text
    assert "Drawdown-Schranke verletzt" in inhalt      # Kategorien
    assert "Test-Schranke verletzt" in inhalt          # aktueller Eintrag


def test_detailansicht_zeigt_regelwerk_bei_ausschluss(monkeypatch):
    """⛔-Signal: Detailansicht nennt Grund + Regelwerk (AppTest.from_function)."""
    monkeypatch.setattr(config, "load_known_signals", lambda: {
        "ausgeschlossen": [{"id": 424242, "name": "Kenni-Muster",
                            "grund": "EQ-DD 23.1%, 18 Verluste in Serie"}],
        "watchlist": []})

    def seite():
        import streamlit as st
        from mqlkiscanner import pipeline
        from mqlkiscanner.app_ui import render_detail
        result = pipeline.ScanResult(id=424242, name="Kenni-Muster",
                                     dd_equity_pct=23.1, trading_dd_pct=28.2,
                                     urteil="Ausgeschlossen (Liste): Test")
        result.ampel = "⛔"
        render_detail(result)

    at = AppTest.from_function(seite, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    inhalt = " ".join(getattr(el, "value", "") or "" for el in at.markdown)
    assert "Gemessener Grund:" in inhalt
    assert "18 Verluste in Serie" in inhalt
    assert "Grenznahe Risikokombination" in inhalt  # Regelwerk im Detail
