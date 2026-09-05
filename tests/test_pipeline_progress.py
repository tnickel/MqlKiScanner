"""The progress UI must count completed model work and retain failure details.

Trade- und Risiko-Analyse laufen parallel; der Gesamtbericht danach.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from mqlkiscanner import db, pipeline
from mqlkiscanner.llm.client import LlmError, LlmNoBalanceError


class FakeLlm:
    has_key = True

    def __init__(self, failure=None, fail_at=0):
        self.failure = failure
        self.fail_at = fail_at
        self.calls = []
        self.usage = SimpleNamespace(total_tokens=0)
        self.last_call = {"zeichen": 40, "dauer_s": 0.1, "reasoning_tokens": 0,
                          "completion_tokens": 10}

    def chat(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        if self.failure and len(self.calls) == self.fail_at:
            raise self.failure
        self.usage.total_tokens += 10
        return "Testbericht. Kurzfassung: Forensik prüfen."


def _pipe_with_llm(fake):
    pipe = pipeline.ScanPipeline()
    pipe.llm = fake
    db.init_db()
    return pipe


def test_llm_progress_starts_at_zero_and_counts_saved_answers():
    fake = FakeLlm()
    pipe = _pipe_with_llm(fake)
    result = pipeline.ScanResult(id=1234567, name="Test", forensik_vorhanden=True)
    events = []
    summary = pipe.run_llm([result], pipeline.StepLog(), lambda *event: events.append(event))

    assert summary == {"completed": 3, "total": 3, "failed": 0, "skipped": 0, "reason": ""}
    assert events[0][0:2] == (0, 3)
    assert events[-1][0:2] == (3, 3)
    assert [done for done, _, _ in events] == sorted(done for done, _, _ in events)
    starts = [event for event in events if "warte auf Modellantwort" in event[2]]
    assert [done for done, _, _ in starts] == [0, 2]
    assert {call[1]["stufe"] for call in fake.calls[:2]} == {1, 2}
    assert fake.calls[2][1]["stufe"] == 2
    for kind in ("trade_analyse", "risiko_analyse", "gesamtbericht"):
        assert db.get_latest_analysis(result.id, kind)["text"] == getattr(result, kind)


@pytest.mark.parametrize("failure", [LlmError("Model failed"), LlmNoBalanceError("Budget unavailable")])
def test_llm_error_never_reports_full_success(failure):
    fake = FakeLlm(failure, fail_at=2)
    pipe = _pipe_with_llm(fake)
    result = pipeline.ScanResult(id=1234567, name="Test", forensik_vorhanden=True)
    events = []
    summary = pipe.run_llm([result], pipeline.StepLog(), lambda *event: events.append(event))

    assert summary["completed"] == 1
    assert summary["total"] == 3
    assert summary["failed"] == 1
    assert summary["skipped"] == 1
    assert summary["reason"]
    assert result.llm_fehler == str(failure)
    assert (result.trade_analyse or result.risiko_analyse) and not result.gesamtbericht
    assert all(done < total for done, total, _ in events)


def test_missing_key_marks_model_work_as_skipped():
    fake = FakeLlm()
    fake.has_key = False
    pipe = _pipe_with_llm(fake)
    result = pipeline.ScanResult(id=1234567, name="Test", forensik_vorhanden=True)
    events = []
    summary = pipe.run_llm([result], pipeline.StepLog(), lambda *event: events.append(event))

    assert not fake.calls
    assert summary["completed"] == 0 and summary["skipped"] == 3
    assert summary["failed"] == 0 and "Key" in summary["reason"]
    assert events[0][0:2] == (0, 3)


def test_ineligible_results_do_not_generate_model_requests():
    fake = FakeLlm()
    pipe = _pipe_with_llm(fake)
    results = [pipeline.ScanResult(id=1234567, name="Only platform data"),
               pipeline.ScanResult(id=7654321, forensik_vorhanden=True, fehler="Export failed")]
    summary = pipe.run_llm(results, pipeline.StepLog())
    assert not fake.calls
    assert summary["total"] == 0
    assert summary["completed"] == 0
    assert summary["reason"]


def test_run_llm_stops_between_signals_on_stop_request():
    """Stop-Flag: nach dem fertig berichteten Kandidat wird nicht mehr gesendet."""
    fake = FakeLlm()
    pipe = _pipe_with_llm(fake)
    results = [pipeline.ScanResult(id=111, name="A", forensik_vorhanden=True),
               pipeline.ScanResult(id=222, name="B", forensik_vorhanden=True)]
    summary = pipe.run_llm(results, pipeline.StepLog(),
                           should_stop=lambda: len(fake.calls) >= 3)
    assert len(fake.calls) == 3, "Kandidat B darf nach der Stop-Anforderung nicht mehr starten"
    assert summary["completed"] == 3 and summary["total"] == 6
    assert summary["failed"] == 0 and summary["skipped"] == 3
    assert "Stop" in summary["reason"]


def test_run_llm_stop_before_summary_keeps_partial_reports():
    """Stop vor Prompt 3: Teilanalysen bleiben erhalten, Gesamtbericht entfällt."""
    fake = FakeLlm()
    pipe = _pipe_with_llm(fake)
    result = pipeline.ScanResult(id=1234567, name="A", forensik_vorhanden=True)
    # Stop nach den beiden Parallel-Prompts (2 Aufrufe), vor dem Gesamtbericht.
    summary = pipe.run_llm([result], pipeline.StepLog(),
                           should_stop=lambda: len(fake.calls) >= 2)
    assert len(fake.calls) == 2
    assert summary["completed"] == 2 and "Stop" in summary["reason"]
    assert result.trade_analyse and result.risiko_analyse
    assert not result.gesamtbericht
