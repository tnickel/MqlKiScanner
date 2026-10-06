# -*- coding: utf-8 -*-
"""Tests für die Validierung von LLM-Urteilen und Portfolio-Gewichten."""
from __future__ import annotations

import pytest

from mqlkiscanner.llm.verdict_check import (
    extract_llm_urteil,
    validate_and_sanitize_verdict,
    parse_and_validate_portfolio,
)


def test_extract_llm_urteil_varianten():
    text1 = "Ein langer Bericht.\n\n## 5. Urteil\nUrteilszeile: EMPFEHLUNG mit Risiko-Score 3."
    assert extract_llm_urteil(text1) == "EMPFEHLUNG"

    text2 = "Abschnitt Fazit.\nUrteil: **WATCHLIST**\nGründe folgen."
    assert extract_llm_urteil(text2) == "WATCHLIST"

    text3 = "Abschlussbewertung.\nUrteil (LLM): ABLEHNUNG."
    assert extract_llm_urteil(text3) == "ABLEHNUNG"

    text4 = "Text ohne explizite Urteilszeile, aber am Ende steht ABLEHNUNG wegen hohem Risiko."
    assert extract_llm_urteil(text4) == "ABLEHNUNG"


def test_sanitize_verdict_rot_verbietet_empfehlung():
    bericht = (
        "## 5. Urteil\n"
        "Urteilszeile: EMPFEHLUNG\n"
        "Score: 2"
    )
    # Signal ist rot (z. B. Martingale oder Drawdown > 30 %)
    bereinigt, urteil, warnungen = validate_and_sanitize_verdict(bericht, "🔴")
    assert urteil == "ABLEHNUNG"
    assert any("Automatisch auf ABLEHNUNG korrigiert" in w for w in warnungen)
    assert "Urteilszeile: ABLEHNUNG" in bereinigt
    assert "Korrektur durch Scanner-Regelwerk" in bereinigt


def test_sanitize_verdict_ausschluss_verbietet_watchlist():
    bericht = "Urteilszeile: WATCHLIST"
    bereinigt, urteil, warnungen = validate_and_sanitize_verdict(bericht, "⛔")
    assert urteil == "ABLEHNUNG"
    assert any("Automatisch auf ABLEHNUNG korrigiert" in w for w in warnungen)
    assert "Urteilszeile: ABLEHNUNG" in bereinigt


def test_sanitize_verdict_gelb_verbietet_empfehlung():
    bericht = "Urteilszeile: EMPFEHLUNG"
    bereinigt, urteil, warnungen = validate_and_sanitize_verdict(bericht, "🟡")
    assert urteil == "WATCHLIST"
    assert any("Automatisch auf WATCHLIST korrigiert" in w for w in warnungen)
    assert "Urteilszeile: WATCHLIST" in bereinigt


def test_sanitize_verdict_gruen_bleibt_unveraendert():
    bericht = "Urteilszeile: EMPFEHLUNG\nAlles in Ordnung."
    bereinigt, urteil, warnungen = validate_and_sanitize_verdict(bericht, "🟢")
    assert urteil == "EMPFEHLUNG"
    assert not warnungen
    assert bereinigt == bericht


def test_portfolio_parsing_und_gewichtungssumme():
    text = """
## 3. Portfolio-Vorschlag
Empfohlene Allokation:
- Gold Spike — 60 % — Risikoträger
- KiraCat – 40% – Ertragsträger
Aussortierte Signale:
- BadSignal: zu hoher Drawdown.
"""
    res = parse_and_validate_portfolio(text, {"Gold Spike": "🟢", "KiraCat": "🟢"})
    assert len(res["allokationen"]) == 2
    assert res["summe_gewicht"] == 100.0
    assert not res["warnungen"]
    assert res["allokationen"][0]["name"] == "Gold Spike"
    assert res["allokationen"][0]["gewicht_pct"] == 60.0


def test_portfolio_warnt_bei_gewichtung_von_nicht_gruen():
    text = """
- KiraCat — 50 % — Ertragsträger
- PureGold — 50 % — Risikoträger
"""
    # PureGold ist gelb oder rot eingestuft
    res = parse_and_validate_portfolio(text, {"KiraCat": "🟢", "PureGold": "🟡"})
    assert res["summe_gewicht"] == 100.0
    assert any("PureGold" in w and "Ampel 🟡" in w for w in res["warnungen"])


def test_portfolio_warnt_bei_abweichender_summe():
    text = """
- Signal A — 30 % — Ertrag
- Signal B — 20 % — Risiko
"""
    res = parse_and_validate_portfolio(text, {"Signal A": "🟢", "Signal B": "🟢"})
    assert res["summe_gewicht"] == 50.0
    assert any("50.0 %" in w and "erwartet: ca. 100 %" in w for w in res["warnungen"])
