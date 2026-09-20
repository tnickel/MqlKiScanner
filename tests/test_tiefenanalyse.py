# -*- coding: utf-8 -*-
"""Erweiterte KI-Analyse (Prompt 5 „Tiefenanalyse“): Vorlage, Filler,
manueller Lauf, Speicherung und PDF. Alle Modellaufrufe sind gefakt."""
from __future__ import annotations

import types

import pytest

from mqlkiscanner import db, llm_runner, pipeline
from mqlkiscanner.llm import client as llm_client
from mqlkiscanner.llm import prompt_fill, prompts as llm_prompts
from mqlkiscanner.pdf_reports import (render_report_pdf, report_storage_path,
                                      result_pdf_spec)


def test_vorlage_existiert_mit_pflicht_platzhaltern():
    vorlage = llm_prompts.DEFAULTS["tiefenanalyse"]
    for platzhalter in ("{kandidat_json}", "{forensik_json}", "{trades_json}",
                        "{signal_name}", "{signal_url}"):
        assert platzhalter in vorlage
    # Der Beispiel-Anbieter/Link des Nutzers ist durch Variablen ersetzt:
    assert "Macro Overlay FX" not in vorlage
    assert "2385035" not in vorlage
    # Datei wird beim ersten Laden automatisch angelegt:
    assert "{signal_name}" in llm_prompts.load_prompt("tiefenanalyse")


def test_builder_ersetzt_name_und_url_mit_fallback():
    r = pipeline.ScanResult(id=2385035, name="Macro Overlay FX", platform="MT5",
                            url="", trades_path="x.csv")
    prompt = prompt_fill.build_tiefenanalyse_prompt(r, '{"meta": {"trades": 3}}')
    assert "Macro Overlay FX" in prompt
    assert "https://www.mql5.com/en/signals/2385035" in prompt  # Standard-URL-Fallback
    assert '{"meta": {"trades": 3}}' in prompt
    for slot in ("{signal_name}", "{signal_url}", "{trades_json}",
                 "{kandidat_json}", "{forensik_json}"):
        assert slot not in prompt


def test_builder_injektionssicher():
    r = pipeline.ScanResult(id=1, name="X {kriterien} {signal_url}", platform="MT5")
    prompt = prompt_fill.build_tiefenanalyse_prompt(r, "Inhalt mit {kandidat_json} drin")
    # 2-Phasen-Fuellung: der LITERAL-Platzhalter im eingefuegten Inhalt ueberlebt
    # (eine alte .replace()-Kaskade haette ihn mit-ersetzt → 0 Treffer), und alle
    # Vorlagen-Slots sind ersetzt:
    assert prompt.count("{kandidat_json}") == 1
    assert "{signal_name}" not in prompt
    assert "\x00" not in prompt  # keine Steuer-Token im Endergebnis


class _FakeClient:
    has_key = True
    usage = types.SimpleNamespace(total_tokens=1234)

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.last_prompt = ""
        self.last_stufe = None

    def chat(self, prompt, stufe=2, max_tokens=0, meta_out=None):
        self.last_prompt = prompt
        self.last_stufe = stufe
        return "# Tiefenanalyse\nTestbefund mit konkreten Trade-Beispielen."


def test_lauf_ruft_stufe2_mit_trades_und_speichert(monkeypatch):
    db.init_db()
    db.upsert_signal(2385035, name="Macro Overlay FX", platform="MT5")
    erstellt = []

    class _Client(_FakeClient):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            erstellt.append(self)

    monkeypatch.setattr(llm_runner.llm_client, "GlmClient", _Client)
    monkeypatch.setattr(llm_runner, "load_export", lambda path: object())
    monkeypatch.setattr(llm_runner, "build_trade_payload",
                        lambda parsed: {"meta": {"trades": 7}})
    r = pipeline.ScanResult(id=2385035, name="Macro Overlay FX", platform="MT5",
                            trades_path="export.csv")
    ergebnis = llm_runner.run_tiefenanalyse_einzeln(r, settings={}, log=lambda m: None)
    client = erstellt[0]
    assert ergebnis["text"].startswith("# Tiefenanalyse")
    assert client.last_stufe == 2                     # starkes Modell
    assert '"trades": 7' in client.last_prompt        # Tradeliste mitgesendet
    assert "Macro Overlay FX" in client.last_prompt   # Name als Variable ersetzt
    assert r.tiefenanalyse.startswith("# Tiefenanalyse")
    assert r.tiefenanalyse_model == client.kwargs["model_stufe2"]
    gespeichert = db.get_latest_analysis(2385035, "tiefenanalyse")
    assert gespeichert is not None
    assert gespeichert["text"].startswith("# Tiefenanalyse")


def test_lauf_ohne_trades_lehnt_ab():
    db.init_db()
    r = pipeline.ScanResult(id=1, name="X")
    with pytest.raises(llm_client.LlmError):
        llm_runner.run_tiefenanalyse_einzeln(r, settings={}, log=None)


def test_lauf_ohne_key_lehnt_ab(monkeypatch):
    class _OhneKey(_FakeClient):
        has_key = False

    monkeypatch.setattr(llm_runner.llm_client, "GlmClient", _OhneKey)
    r = pipeline.ScanResult(id=1, name="X", trades_path="a.csv")
    with pytest.raises(llm_client.LlmError):
        llm_runner.run_tiefenanalyse_einzeln(r, settings={}, log=None)


def test_pdf_spec_und_speicherpfad():
    r = pipeline.ScanResult(id=2385035, name="Macro Overlay FX",
                            trades_sha256="a" * 64)
    r.tiefenanalyse = "# Tiefenanalyse\nBefund"
    r.tiefenanalyse_at = "2026-09-20 12:00:00"
    r.tiefenanalyse_model = "glm-5.3"
    report, dateiname = result_pdf_spec(r, "tiefenanalyse")
    assert "tiefenanalyse" in dateiname and "2385035" in dateiname
    assert report.body.startswith("# Tiefenanalyse")
    assert report_storage_path(report, snapshot="snap").name == "04-tiefenanalyse.pdf"
    assert render_report_pdf(report).startswith(b"%PDF")


def test_katalog_laedt_tiefenanalyse():
    db.init_db()
    db.upsert_signal(2385035, name="Macro Overlay FX", platform="MT5")
    db.store_analysis(2385035, "tiefenanalyse", "glm-5.3", 100, "# Befund")
    r = next(x for x in pipeline.results_from_db(settings={}) if x.id == 2385035)
    assert r.tiefenanalyse == "# Befund"
    assert r.tiefenanalyse_model == "glm-5.3"
    assert r.tiefenanalyse_at
