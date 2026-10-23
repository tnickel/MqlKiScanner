"""Real prompt filling, lossless segmentation, paid-answer recovery; no HTTP."""
import hashlib
import json
import re

import pytest

from mqlkiscanner import abonnenten_analyse_ki as ki
from mqlkiscanner import config
from mqlkiscanner.abonnenten_analyse_store import Store
from mqlkiscanner.llm.client import LlmBudgetError, LlmError


@pytest.fixture
def entry(tmp_path):
    path = tmp_path / "synthetic.csv"
    # Deliberately descending export; real parser order differs from trading order.
    path.write_text("Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
        "2026.03.03 12:00:00;Buy;0.02;EURUSD;1.1;0.02;2026.03.03 13:00:00;1.2;0;0;10\n"
        "2026.01.01 12:00:00;Buy;0.01;EURUSD;1.1;0.01;2026.01.01 13:00:00;1.0;0;0;-10\n",
        encoding="utf-8")
    return dict(signal_ref=1, id=1, quelle="mql5", name="Synthetic", trades=2,
                trades_path=str(path), trades_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                forensik={}, equity={}, retdd_jahr=2, abo_perzentil=50)


def short(ref=1, **extra):
    return {"schema_version": 1, "signal_ref": ref, "strategietyp": "Trendfolge",
            "strategie_sicherheit": "plausibel", "martingale_einordnung": "kein_beleg",
            "kurzurteil": "Eine belegte kurze Einordnung", "staerken": [], "risiken": [],
            "pruefhinweise": [], "datenluecken": [], **extra}


class FakeClient:
    has_key = True
    def __init__(self, reply=None):
        self.prompts = []
        self.reply = reply or (lambda prompt: short())
    def chat(self, prompt, **kwargs):
        self.prompts.append(prompt)
        result = self.reply(prompt)
        if isinstance(result, Exception):
            raise result
        kwargs["meta_out"].update(total_tokens=100)
        return json.dumps(result)


def runner(client, profile=None):
    store = Store()
    if not store.read("job"):
        store.create({"id": "job"})
    return ki.AnalyseKI(store, "job", config.load_settings(), profile or {}, client=client)


def test_trade_refs_preserve_occurrences_before_chronological_sort(entry):
    rows = ki.trade_rows(entry)
    assert rows[0]["open"].startswith("2026-01-01")
    assert rows[0]["trade_ref"].endswith(":2")
    assert rows[1]["trade_ref"].endswith(":1")
    blocks = ki.segments(rows, max_bytes=1)
    assert [ref for block in blocks for ref in block["primary_refs"]] == [r["trade_ref"] for r in rows]
    assert blocks[1]["overlap_refs"] == [rows[0]["trade_ref"]]


def test_partial_source_coverage_reaches_prompt_and_pdf(entry, monkeypatch):
    from mqlkiscanner import pdf_reports
    entry.update(abo_referenz_vollstaendig=False, abo_ausgelassene_positionen=[1256],
                 abo_katalog_geprueft=5900, bericht_markdown="# Prüfung\n\nAusführlicher Befund.")
    ai = runner(FakeClient())
    prompt, _, candidate = ai._prompt("abonnenten_kurztest", entry, "vollanalyse", {}, [])
    assert candidate["abo_referenz_vollstaendig"] is False
    assert candidate["abo_ausgelassene_positionen"] == [1256]
    assert '"abo_referenz_vollstaendig":false' in prompt
    seen = []
    monkeypatch.setattr(pdf_reports, "render_report_pdf", lambda report: seen.append(report.body) or b"test-pdf")
    path = ki.report_pdf(entry, "job")
    assert "globale Top-200-Auswahl ist nicht bestätigt" in seen[0]
    assert entry["bericht_markdown"] in seen[0]
    from pathlib import Path
    assert Path(path).read_bytes() == b"test-pdf"


def test_complete_paid_answer_reused_across_runner_restart(entry):
    client = FakeClient()
    answer = runner(client).analyse(entry)
    assert answer["analysegrundlage"]["trades_ki_abgedeckt"] == 2
    again = FakeClient()
    runner(again).analyse(entry)
    assert len(client.prompts) == 1 and not again.prompts
    assert Store().spent("job") == 100


def test_preflight_budget_failure_does_not_poison_future_resume(entry):
    with pytest.raises(LlmBudgetError):
        runner(FakeClient(lambda p: LlmBudgetError("temporary"))).analyse(entry)
    success = FakeClient()
    assert runner(success).analyse(entry)["signal_ref"] == 1
    assert len(success.prompts) == 1
    assert Store().spent("job") == 100


def test_wrong_identity_and_invented_evidence_never_become_valid(entry):
    fake = FakeClient(lambda p: short(staerken=[{"text": "invented", "beleg_refs": ["missing.fact"]}]))
    with pytest.raises(LlmError, match="beleg"):
        runner(fake).analyse(entry)
    assert Store().spent("job") == 200
    success = FakeClient()
    assert runner(success).analyse(entry)["signal_ref"] == 1
    assert Store().spent("job") == 300


def test_full_coverage_many_chunks_uses_same_prompt_and_synthesis(entry, monkeypatch):
    original = ki.segments
    rows = []
    for i in range(200):
        rows.append({"trade_ref": f"sha:{i}", "open": str(i), "close": str(i), "trade_index": i})
    monkeypatch.setattr(ki, "trade_rows", lambda e: rows)
    monkeypatch.setattr(ki, "segments", lambda rows: original(rows, max_bytes=300))
    fake = FakeClient(lambda p: short(kurzurteil="Beleg " * 600))
    result = runner(fake).analyse(entry)
    assert result["analysegrundlage"]["trades_ki_abgedeckt"] == 200
    assert result["analysegrundlage"]["segmente"] > 1
    assert any('"aggregation":true' in prompt for prompt in fake.prompts)
    assert '"verarbeitung":"zusammenfassung"' in fake.prompts[-1]


def test_pdf_uses_real_research_report_type(entry):
    entry.update(bericht_markdown="# Analyse\n\nFloating-Equity-DD **20 %**, keine Intrabar-Tiefs.",
                 analyse_at="2026-10-23", analyse_model="synthetic")
    path = ki.report_pdf(entry, "job")
    from pathlib import Path
    payload = Path(path).read_bytes()
    assert payload.startswith(b"%PDF-") and len(payload) > 1000


def test_run_costs_include_unknown_transport_and_successful_retry_receipts():
    from mqlkiscanner.agenten import budget
    settings = {"agenten_tagesbudget_tokens": 10_000, "agenten_monatsbudget_tokens": 10_000}
    unknown = budget.reserve(settings, 500, "synthetic", "first attempt")
    budget.settle(unknown, 500, "transport timeout", "transport_kosten_unbekannt")
    success = budget.reserve(settings, 500, "synthetic", "retry")
    budget.settle(success, 80, "reply", "http_200")
    client = FakeClient()
    client.budget_tickets = [unknown, success]
    assert runner(client)._charged_tokens(0, {"total_tokens": 80}) == 580
    assert runner(client)._charged_tokens(1, {"total_tokens": 80}) == 80
