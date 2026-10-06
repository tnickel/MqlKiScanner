"""Auswahl und KI interpretieren dieselben berechneten Equity-RetDD-Werte."""
from pathlib import Path

import pytest

from mqlkiscanner.ampel_matrix import KRITERIEN
from mqlkiscanner.help_content import HELP_CONTENT
from mqlkiscanner.llm import prompt_fill, prompts


@pytest.mark.parametrize("kind", ["risiko_analyse", "gesamtbericht", "portfolio"])
def test_retdd_prompt_und_default_gleiche_messbasis_und_harte_auswahl(kind):
    text = (Path(__file__).resolve().parents[1] / "config" / "prompts"
            / f"{kind}.md").read_text(encoding="utf-8")
    assert text.strip() == prompts.DEFAULTS[kind].strip()
    text = prompt_fill.expand_bausteine(text)
    assert "{kriterien}" in text
    assert "ertrag_monat_geom_pct" in text and "max_drawdown_equity_pct" in text
    assert "inklusive Floating aus der eigenen Kurs-Rekonstruktion" in text
    assert "Closing-Kurve" in text and "KEIN Nenner" in text
    assert "niemals Plattform-, Balance-" in text
    assert "oder Trading-DD geschlossener Trades" in text
    assert "NICHT retdd_monat mal zwoelf" in text
    assert "KEINE eigene Division" in text
    assert "Nur Engine-Gruen und ALLE" in text
    assert "AKTUELL konfigurierten Ertragsschwelle" in text
    assert "Gelb ist Beobachtung und erlaubt keine Empfehlung" in text
    assert "Historische Rendite und RetDD sind keine Prognose" in text
    assert "0.167" not in text
    assert "virtuelle" in text and "Intrabar-Extrema" in text


def test_retdd_tooltip_benennt_feste_mindestqualitaet_und_ersatzverbot():
    text = next(k.beschreibung for k in KRITERIEN if k.key == "retdd")
    assert "Calmar" in text and "min_calmar_jahr" in text
    assert "verbindliche Empfehlungsvoraussetzung" in text or "Empfehlungsvoraussetzung" in text
    assert "niemals als Ersatznenner" in text
    assert "echter Jahres-CAGR" in text
    assert "nicht risikoneutral" in text
    assert "Allein keine harte Sperre" not in text


def test_hilfe_verlangt_eigene_messung_und_gelbe_signale_bleiben_beobachtung():
    metrics = HELP_CONTENT["risk_metrics"][1]
    portfolio = HELP_CONTENT["portfolio_report"][1]
    assert "geometrische Monatsrendite" in metrics
    assert "niemals als Ersatznenner" in metrics
    assert "min_calmar_jahr" in metrics and "3 Monaten" in metrics
    assert "Gelb bleibt Beobachtung" in portfolio
    assert "Fehlender Stop-Nachweis ist neutral" in portfolio
    assert "Signale ohne Stop-Nachweis" not in portfolio
