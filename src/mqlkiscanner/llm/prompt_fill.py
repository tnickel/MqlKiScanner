# -*- coding: utf-8 -*-
"""Sicheres Fuellen der Prompt-Vorlagen + zentrale Prompt-Builder.

Warum ein eigener Filler: Die Vorlagen wurden per .replace()-Kaskade
gefuellt. Enthaelt ein einzufuegender Inhalt (Gesamtbericht-Text,
Martingale-Evidenz, ...) wortgemaess einen spaeteren Platzhalter wie
"{kriterien}", wuerde die Kaskade ihn im eingefuegten Inhalt mit-ersetzen
und den Prompt verstuemmeln. fill_prompt ersetzt zunaechst nur die
Vorlagen-Platzhalter durch eindeutige Steuer-Token und tauscht diese
danach gegen die Inhalte — eingefuegte Inhalte werden nie erneut gescannt.

assert_template_covered prueft die VORLAGE vor dem Fuellen: Jeder
platzhalterartige Ausdruck muss von einem bekannten Platzhalter gedeckt
sein. Damit werden zwei Fehler frueh und klar benannt, statt dass sie
stumm an das Modell gehen:
- Tippfehler in der Admin-editierbaren Vorlage ("{forensik-jason}")
- Builder-Verschaltung, die einen Platzhalter nicht beliefert

Eingefuegte Inhalte duerfen Literal-Platzhalter enthalten (ohne Wirkung);
die Zwei-Phasen-Fuellung garantiert, dass Vorlagen-Slots immer ersetzt
werden.

Die Builder sind die EINZIGE Stelle, die Prompts zusammenbaut: Produktions
code (llm_runner, pipeline.run_portfolio) und die Prompt-Regressionstests
nutzen dieselben Funktionen — die Tests pruefen damit exakt den
Produktions-Mechanismus.
"""
from __future__ import annotations

import re

from .client import LlmError
from . import prompts as llm_prompts

KNOWN_PLACEHOLDERS = frozenset((
    "{kandidat_json}", "{kandidaten_json}", "{forensik_json}",
    "{trades_json}", "{trade_analyse}", "{risiko_analyse}", "{kriterien}",
    "{signal_name}", "{signal_url}",
))

_PLACEHOLDER_RE = re.compile(r"\{[a-z_][a-z_0-9-]{1,39}\}")


def fill_prompt(template: str, mapping: dict[str, str]) -> str:
    """Ersetzt Vorlagen-Platzhalter, ohne eingefuegte Inhalte anzutasten."""
    tokens: dict[str, str] = {}
    out = template
    for i, (placeholder, value) in enumerate(mapping.items()):
        if placeholder not in out:
            continue  # Vorlage darf Platzhalter bewusst nicht enthalten
        token = f"\x00PROMPT_SLOT_{i}\x00"
        out = out.replace(placeholder, token)
        tokens[token] = value
    for token, value in tokens.items():
        out = out.replace(token, value)
    return out


def assert_template_covered(template: str, keys, vorlage: str) -> str:
    """Jeder platzhalterartige Ausdruck der Vorlage muss versorgt sein."""
    unversorgt = sorted({slot for slot in _PLACEHOLDER_RE.findall(template)
                         if slot not in keys})
    if unversorgt:
        raise LlmError(
            f"Prompt-Vorlage '{vorlage}' enthaelt unversorgte Platzhalter: "
            f"{', '.join(unversorgt)}. Vorlage im Admin-Bereich pruefen.")
    return template


def build_trade_prompt(result, trades_json: str) -> str:
    """Prompt 1 — Strategie aus den Trades (starkes Modell)."""
    from ..pipeline import _kandidat_json  # spaeter Import: kein Kreisimport
    template = assert_template_covered(
        llm_prompts.load_prompt("trade_analyse"),
        ("{kandidat_json}", "{trades_json}"), "trade_analyse")
    return fill_prompt(template, {"{kandidat_json}": _kandidat_json(result),
                                  "{trades_json}": trades_json})


def build_risk_prompt(result, kriterien: str) -> str:
    """Prompt 2 — Risiko-Profil aus Forensik-Kennzahlen (Flash)."""
    from ..pipeline import _forensik_json, _kandidat_json
    template = assert_template_covered(
        llm_prompts.load_prompt("risiko_analyse"),
        ("{kandidat_json}", "{forensik_json}", "{kriterien}"), "risiko_analyse")
    return fill_prompt(template, {"{kandidat_json}": _kandidat_json(result),
                                  "{forensik_json}": _forensik_json(result),
                                  "{kriterien}": kriterien})


def build_gesamtbericht_prompt(result, kriterien: str,
                               trade_analyse: str, risiko_analyse: str) -> str:
    """Prompt 3 — ausfuehrliche Gesamtauswertung (starkes Modell)."""
    from ..pipeline import _forensik_json, _kandidat_json
    template = assert_template_covered(
        llm_prompts.load_prompt("gesamtbericht"),
        ("{kandidat_json}", "{forensik_json}", "{trade_analyse}",
         "{risiko_analyse}", "{kriterien}"), "gesamtbericht")
    return fill_prompt(template, {"{kandidat_json}": _kandidat_json(result),
                                  "{forensik_json}": _forensik_json(result),
                                  "{trade_analyse}": trade_analyse,
                                  "{risiko_analyse}": risiko_analyse,
                                  "{kriterien}": kriterien})


def build_portfolio_prompt(eintraege_json: str, kriterien: str) -> str:
    """Prompt 4 — Portfolio-Vorschlag ueber ALLE Signale (starkes Modell)."""
    template = assert_template_covered(
        llm_prompts.load_prompt("portfolio"),
        ("{kandidaten_json}", "{kriterien}"), "portfolio")
    return fill_prompt(template, {"{kandidaten_json}": eintraege_json,
                                  "{kriterien}": kriterien})


def build_tiefenanalyse_prompt(result, trades_json: str) -> str:
    """Prompt 5 — Erweiterte KI-Analyse (manuell, starkes Modell, mit Trades).

    {signal_name}/{signal_url} ersetzen den festen Anbieter-Namen bzw. Link;
    die URL kommt vom Ergebnis und faellt auf das Standard-MQL5-Muster
    zurueck (https://www.mql5.com/en/signals/{ID}), plattformunabhaengig.
    """
    from ..pipeline import _forensik_json, _kandidat_json  # kein Kreisimport
    template = assert_template_covered(
        llm_prompts.load_prompt("tiefenanalyse"),
        ("{kandidat_json}", "{forensik_json}", "{trades_json}",
         "{signal_name}", "{signal_url}"), "tiefenanalyse")
    url = getattr(result, "url", "") or (
        f"https://www.mql5.com/en/signals/{result.id}" if getattr(result, "id", None) else "")
    return fill_prompt(template, {
        "{kandidat_json}": _kandidat_json(result),
        "{forensik_json}": _forensik_json(result),
        "{trades_json}": trades_json,
        "{signal_name}": getattr(result, "name", "") or "Unbenanntes Signal",
        "{signal_url}": url,
    })
