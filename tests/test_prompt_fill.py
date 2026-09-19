# -*- coding: utf-8 -*-
"""Unit-Tests fuer den sicheren Prompt-Fueller und die vier Builder.

Diese Tests laufen IMMER (keine Netzwerk-/Token-Kosten): Sie sichern den
Mechanismus, der die Prompts zusammenbaut — inkl. Schutz vor Platzhalter-
Injection und Guard gegen unersetzt gebliebene Platzhalter. Die echten
Modellaufrufe liegen in test_llm_prompt_regression.py (Marker `llm`,
opt-in).
"""
from __future__ import annotations

import json

import pytest

from mqlkiscanner import pipeline
from mqlkiscanner.llm import prompt_fill
from mqlkiscanner.llm.client import LlmError


# ---------------------------------------------------------------- fill_prompt

def test_fill_prompt_ersetzt_alle_platzhalter():
    template = "A {kriterien} B {kandidat_json} C"
    out = prompt_fill.fill_prompt(
        template, {"{kriterien}": "KRITERIEN", "{kandidat_json}": "JSON"})
    assert out == "A KRITERIEN B JSON C"


def test_fill_prompt_injection_in_inhalt_wird_nicht_ersetzt():
    """Inhalt mit Platzhalter-Text darf spaetere replace nicht vergiften."""
    template = "Erster: {trade_analyse} Zweiter: {kriterien}"
    boeser_inhalt = "Vorsicht {kriterien} im Berichtstext"
    out = prompt_fill.fill_prompt(
        template, {"{trade_analyse}": boeser_inhalt, "{kriterien}": "ECHTE-KRITERIEN"})
    assert out == ("Erster: Vorsicht {kriterien} im Berichtstext "
                   "Zweiter: ECHTE-KRITERIEN")


def test_fill_prompt_fehlender_platzhalter_in_vorlage_ist_erlaubt():
    """Admin darf Platzhalter aus der Vorlage entfernen — kein Fehler."""
    out = prompt_fill.fill_prompt("Nur Text ohne Slot.", {"{kriterien}": "X"})
    assert out == "Nur Text ohne Slot."


def test_assert_template_covered_erkennt_tippfehler():
    with pytest.raises(LlmError, match="forensik-jason"):
        prompt_fill.assert_template_covered(
            "Daten: {forensik-jason}", ("{forensik_json}",), "gesamtbericht")


def test_assert_template_covered_erkennt_wiring_bug():
    """Vorlage will {kriterien}, Builder beliefert ihn nicht -> Fehler."""
    with pytest.raises(LlmError, match="kriterien"):
        prompt_fill.assert_template_covered(
            "A {kriterien}", ("{kandidat_json}",), "risiko_analyse")


def test_assert_template_covered_laesst_entfernte_platzhalter_durch():
    template = "Nur Text, Slot bewusst entfernt."
    assert prompt_fill.assert_template_covered(
        template, ("{kriterien}",), "portfolio") == template


# -------------------------------------------------------------------- Builder

def _result(**kwargs) -> pipeline.ScanResult:
    base = dict(id=987654, name="Testsignal", platform="MT5",
                forensik_vorhanden=True, trading_dd_pct=12.5,
                trading_dd_usd=500.0, martingale_flag=False,
                stop_evidence="direct", score=3.2, ertrag_monat_pct=15.0)
    base.update(kwargs)
    result = pipeline.ScanResult(**base)
    pipeline.refresh_report_verdict(result, {})
    return result


def test_builder_fuellen_alle_vier_prompts_ohne_restplatzhalter():
    result = _result()
    kriterien = pipeline._kriterien_text({})
    prompts = {
        "trade": prompt_fill.build_trade_prompt(result, '{"meta": {"trades": 3}}'),
        "risiko": prompt_fill.build_risk_prompt(result, kriterien),
        "gesamt": prompt_fill.build_gesamtbericht_prompt(
            result, kriterien, "Trade-Analyse-Text", "Risiko-Analyse-Text"),
        "portfolio": prompt_fill.build_portfolio_prompt("[]", kriterien),
    }
    for name, prompt in prompts.items():
        for placeholder in prompt_fill.KNOWN_PLACEHOLDERS:
            assert placeholder not in prompt, f"{name}: {placeholder} blieb unersetzt"
        assert "\x00PROMPT_SLOT_" not in prompt, f"{name}: Steuer-Token im Prompt"


def test_builder_prompts_enthalten_ampel_und_urteil():
    """Design-Regel: Engine-Ampel/-Urteil muessen im LLM-Payload sein."""
    result = _result()
    kriterien = pipeline._kriterien_text({})
    prompt = prompt_fill.build_risk_prompt(result, kriterien)
    assert '"ampel"' in prompt and '"urteil"' in prompt
    assert json.dumps(result.ampel, ensure_ascii=False) in prompt


def test_builder_uebernimmt_injektionssicher_teilanalysen():
    result = _result()
    kriterien = pipeline._kriterien_text({})
    boese_analyse = "Analyse mit {kriterien} und {forensik_json} im Text"
    prompt = prompt_fill.build_gesamtbericht_prompt(
        result, kriterien, boese_analyse, "Risiko-Text")
    assert boese_analyse in prompt          # Inhalt bleibt unangetastet
    assert "max. 30" in prompt              # echte Kriterien wurden ersetzt
    # Der Literal-Platzhalter darf NUR aus dem boesen Inhalt stammen:
    assert prompt.count("{kriterien}") == 1
    assert prompt.count("{forensik_json}") == 1


def test_kriterien_text_nennt_beide_drawdown_arten_und_schockregel():
    text = pipeline._kriterien_text({})
    assert "MAXIMUM" in text and "Trading-DD" in text
    assert "kein gemessener Verlust" in text


# --------------------------------------------- Bericht-Parser (bericht_parse)

def test_bericht_parse_aufnahmen_liest_listenzeilen():
    from bericht_parse import aufnahmen, hat_aufnahme
    bericht = """## 3. Portfolio-Vorschlag

- Gruen Muster — 70 % — Ertragstraeger
- *Zweites Signal* — 30 % — Risikotraeger

Aussortiert je ein Satz: Rot Muster — EQ-DD 34,22 % ueber Schranke.
"""
    ergebnis = aufnahmen(bericht)
    assert ergebnis == {"Gruen Muster": 70, "Zweites Signal": 30}
    assert hat_aufnahme(ergebnis, "Gruen Muster")
    assert not hat_aufnahme(ergebnis, "Rot Muster")  # Prosa mit % zaehlt nicht


def test_bericht_parse_urteil_und_abschnitt():
    from bericht_parse import abschnitt, urteil
    bericht = ("Kurzfassung: Test.\n\n## 5. Urteil\n\n"
               "**Urteil: ABLEHNUNG.**\n\n## 6. Bedingungen\nText.")
    assert urteil(bericht) == "ABLEHNUNG"
    assert "ABLEHNUNG" in abschnitt(bericht, "Urteil")
    assert "Bedingungen" not in abschnitt(bericht, "Urteil")
    # Toleranz: gemischte Grossschreibung und Abschnitts- statt Zeilenform.
    gemischt = "## 5. Urteil\n\nUrteil: Ablehnung — Risiko vor Ertrag."
    assert urteil(gemischt) == "ABLEHNUNG"
    ohne_header = "Vorstufe: keine Empfehlung.\nUrteil: Watchlist. Grund X."
    assert urteil(ohne_header) == "WATCHLIST"
