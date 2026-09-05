# -*- coding: utf-8 -*-
"""Station 5: Portfolio-Vorschlag — Pipeline-Level und UI-Einzelschritt."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import db, pipeline

ROOT = Path(__file__).resolve().parents[1]


class FakeLlm:
    has_key = True

    def __init__(self):
        self.calls = []
        self.usage = SimpleNamespace(total_tokens=42)

    def chat(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return "Kurzfassung: Mischung aus A und B. PORTFOLIO_TEST_BERICHT"


def _pipe_with_llm(fake):
    pipe = pipeline.ScanPipeline()
    pipe.llm = fake
    db.init_db()
    return pipe


def test_run_portfolio_sends_all_reports_and_stores_analysis():
    fake = FakeLlm()
    pipe = _pipe_with_llm(fake)
    results = [
        pipeline.ScanResult(id=111, name="A", forensik_vorhanden=True,
                            gesamtbericht="Bericht A", kurzfassung="Kurz A",
                            symbole="XAUUSD"),
        pipeline.ScanResult(id=222, name="B", forensik_vorhanden=True,
                            gesamtbericht="Bericht B", symbole="US30, NZDCAD"),
        pipeline.ScanResult(id=333, name="Fehlerfall", forensik_vorhanden=True,
                            fehler="export kaputt"),
    ]
    summary = pipe.run_portfolio(results, pipeline.StepLog())
    assert summary["text"].startswith("Kurzfassung:")
    assert "PORTFOLIO_TEST_BERICHT" in summary["text"]
    assert len(fake.calls) == 1
    prompt, kwargs = fake.calls[0]
    assert kwargs["stufe"] == 2  # starkes Modell
    # Nur fehlerfreie Forensik-Ergebnisse landen im Prompt — mit Bericht und Assets.
    assert "Bericht A" in prompt and "Bericht B" in prompt
    assert "Fehlerfall" not in prompt
    assert "XAUUSD" in prompt and "US30" in prompt
    assert "{kandidaten_json}" not in prompt and "{kriterien}" not in prompt
    stored = db.get_latest_analysis(0, "portfolio")
    assert stored and "PORTFOLIO_TEST_BERICHT" in stored["text"]


def test_run_portfolio_without_key_is_skipped():
    fake = FakeLlm()
    fake.has_key = False
    pipe = _pipe_with_llm(fake)
    results = [pipeline.ScanResult(id=111, name="A", forensik_vorhanden=True)]
    summary = pipe.run_portfolio(results, pipeline.StepLog())
    assert summary["text"] == "" and "Key" in summary["reason"]
    assert not fake.calls
    assert db.get_latest_analysis(0, "portfolio") is None


def test_run_portfolio_without_results_is_skipped():
    fake = FakeLlm()
    pipe = _pipe_with_llm(fake)
    summary = pipe.run_portfolio([pipeline.ScanResult(id=1)], pipeline.StepLog())
    assert summary["text"] == "" and summary["reason"]
    assert not fake.calls


def test_run_portfolio_stops_before_model_call():
    fake = FakeLlm()
    pipe = _pipe_with_llm(fake)
    summary = pipe.run_portfolio(
        [pipeline.ScanResult(id=1, name="A", forensik_vorhanden=True)],
        pipeline.StepLog(), should_stop=lambda: True)
    assert summary["text"] == "" and "Stop" in summary["reason"]
    assert not fake.calls


def _scan_page() -> AppTest:
    return AppTest.from_file(str(ROOT / "app_pages" / "scan.py"), default_timeout=30)


def test_step5_portfolio_runs_and_displays(monkeypatch):
    from mqlkiscanner import secrets_store

    monkeypatch.setattr(secrets_store, "get_secret", lambda key: "ui-test-key")

    def fake_run_portfolio(self, results, log, on_progress=None, should_stop=None):
        return {"text": "PORTFOLIO_TEST_BERICHT", "zeichen": 22, "tokens": 42, "reason": ""}

    monkeypatch.setattr(pipeline.ScanPipeline, "run_portfolio", fake_run_portfolio)
    at = _scan_page()
    at.run()
    assert not at.exception, at.exception
    at.session_state["scan_results"] = [
        pipeline.ScanResult(id=1234567, name="A", forensik_vorhanden=True)]
    at.button(key="step_btn_portfolio").click().run()
    assert not at.exception, at.exception
    wf = at.session_state["scan_workflow"]
    assert wf["steps"]["portfolio"]["status"] == "complete"
    assert "PORTFOLIO_TEST_BERICHT" in at.session_state["portfolio_bericht"]


def test_step5_portfolio_without_key_is_skipped():
    at = _scan_page()
    at.run()
    assert not at.exception, at.exception
    at.session_state["scan_results"] = [
        pipeline.ScanResult(id=1234567, name="A", forensik_vorhanden=True)]
    at.button(key="step_btn_portfolio").click().run()
    assert not at.exception, at.exception
    wf = at.session_state["scan_workflow"]
    assert wf["steps"]["portfolio"]["status"] == "skipped"
    assert not at.session_state["portfolio_bericht"]


def test_ergebnisse_page_shows_stored_portfolio_bericht():
    db.init_db()
    db.store_analysis(0, "portfolio", "glm-5.3", 10, "PORTFOLIO_DB_BERICHT")
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60)
    at.run()
    at.switch_page("app_pages/ergebnisse.py").run()
    assert not at.exception, at.exception
    body = "\n".join(m.value for m in at.markdown)
    assert "PORTFOLIO_DB_BERICHT" in body


def test_urteile_farbig_colors_verdict_words():
    """Urteile in KI-Berichten: EMPFEHLUNG gruen, Watchlist gelb, Ablehnung rot."""
    from mqlkiscanner.ui_design import urteile_farbig

    md = (
        "| Signal | Urteil / Rolle | Hauptgrund (Zahlen) |\n"
        "|---|---|---|\n"
        "| Gold Spike (2349227) | EMPFEHLUNG / Ertragsträger | Stop 368/368; DD 4,57 % |\n"
        "| KiraCat (2342895) | Watchlist | kein Stop-Nachweis |\n"
        "| NoPain (2262642) | Ablehnung / überflüssig | 1,64 %/Monat |\n"
        "\n"
        "Urteil: ABLEHNUNG — drei Hauptgründe.\n"
    )
    out = urteile_farbig(md)
    # Ganze Zelle gefaerbt, wenn das Urteil am Zellenanfang steht:
    assert '<span class="mks-urteil-gruen"> EMPFEHLUNG / Ertragsträger </span>' in out
    assert '<span class="mks-urteil-gelb"> Watchlist </span>' in out
    assert '<span class="mks-urteil-rot"> Ablehnung / überflüssig </span>' in out
    # Fliesstext: GROSS geschriebenes Urteil wird gefaerbt ...
    assert '<span class="mks-urteil-rot">ABLEHNUNG</span>' in out
    # ... aber Prosa im Kleinschreibungs-Kontext bleibt unangetastet.
    probe = urteile_farbig("| X | keine Empfehlung ausgesprochen |")
    assert '<span class="mks-urteil-gruen">Empfehlung' not in probe


def test_urteile_farbig_escaped_html_im_bericht():
    from mqlkiscanner.ui_design import urteile_farbig

    out = urteile_farbig("<script>alert(1)</script>\n| A | EMPFEHLUNG / Kern |")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    assert '<span class="mks-urteil-gruen">' in out
