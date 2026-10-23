# -*- coding: utf-8 -*-
"""Nutzer-Regel 20.10.2026: Fehlende/leere Berichtsvorlage → sichtbarer
Hinweis (PromptFehlt), NIEMALS stiller Default-Ersatz; der KI-Batch
verweigert den Start mit klarer Meldung."""
from __future__ import annotations

import pytest

from mqlkiscanner.llm import prompts


def test_fehlende_datei_wirft_prompt_fehlt_mit_pfad(monkeypatch):
    # Bewusst in einem LEEREN Unterordner: Der conftest legt die Werk-
    # vorlagen bereits im PROMPTS_DIR an — hier soll die Datei fehlen.
    fehlend = {"tiefenanalyse": prompts.PROMPTS_DIR / "fehlt"
               / "tiefenanalyse.md"}
    monkeypatch.setattr(prompts, "PROMPT_FILES", fehlend)
    with pytest.raises(prompts.PromptFehlt) as excinfo:
        prompts.load_prompt("tiefenanalyse")
    assert "tiefenanalyse.md" in str(excinfo.value)
    assert "Zurücksetzen" in str(excinfo.value)


def test_leere_datei_wirft_prompt_fehlt(monkeypatch, tmp_path):
    leer = tmp_path / "tiefenanalyse.md"
    leer.write_text("   \n", encoding="utf-8")
    monkeypatch.setattr(prompts, "PROMPT_FILES", {"tiefenanalyse": leer})
    with pytest.raises(prompts.PromptFehlt):
        prompts.load_prompt("tiefenanalyse")


def test_fehlende_vorlagen_listet_und_batch_verweigert(monkeypatch):
    monkeypatch.setattr(prompts, "PROMPT_FILES", {
        "tiefenanalyse": prompts.PROMPTS_DIR / "fehlt.md",
    })
    assert prompts.fehlende_vorlagen() == ["tiefenanalyse"]
