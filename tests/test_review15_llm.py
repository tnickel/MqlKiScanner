"""Each parallel prompt retains its answer and owns exactly one outcome."""
import re
from types import SimpleNamespace

import pytest

from mqlkiscanner import db, llm_runner, pipeline
from mqlkiscanner.llm.client import LlmBudgetError, LlmError, LlmNoBalanceError


class FakeLlm:
    has_key = True

    def __init__(self, outcomes=None):
        self.outcomes = outcomes or {}
        self.calls = []
        self.usage = SimpleNamespace(total_tokens=0)

    def chat(self, prompt, *, stufe, max_tokens, meta_out):
        sid = int(re.search(r'"id": (\d+)', prompt).group(1))
        stage = {16384: "trade_analyse", 8192: "risiko_analyse", 24576: "gesamtbericht"}[max_tokens]
        self.calls.append((sid, stage))
        value = self.outcomes.get((sid, stage), f"{stage} {sid}. Kurzfassung: current {sid}")
        if isinstance(value, Exception):
            raise value
        self.usage.total_tokens += 10
        return value


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(pipeline, "report_basis_for", lambda r, cfg: f"basis-{r.id}", raising=False)
    stored = []
    monkeypatch.setattr(db, "store_analysis", lambda *args, **kwargs: stored.append((args, kwargs)))
    pipe = SimpleNamespace(settings={}, llm=FakeLlm())

    def result(sid=101, old_basis=""):
        r = pipeline.ScanResult(id=sid, name=f"Signal {sid}", forensik_vorhanden=True)
        r.berichte_basis = old_basis
        r.bericht_hinweis = ""
        return r

    return pipe, result, stored


def test_trade_storage_failure_preserves_both_answers_and_continues_next_signal(setup, monkeypatch):
    pipe, make_result, stored = setup
    first, second = make_result(), make_result(202)
    calls = []

    def store(*args, **kwargs):
        # Both successful futures must reach the result before the first write.
        assert first.trade_analyse and first.risiko_analyse
        calls.append((args[0], args[1]))
        if args[:2] == (101, "trade_analyse"):
            raise OSError("disk unavailable")
        stored.append((args, kwargs))

    monkeypatch.setattr(db, "store_analysis", store)
    events = []
    outcome = llm_runner.run_llm(pipe, [first, second], lambda _: None,
                                 lambda *args: events.append(args))
    assert outcome["completed"] == 4 and outcome["failed"] == 1 and outcome["skipped"] == 1
    assert outcome["updated_ids"] == [101, 202]
    assert first.trade_analyse and first.risiko_analyse and not first.gesamtbericht
    assert "disk unavailable" in first.llm_fehler
    assert (101, "risiko_analyse") in calls
    assert second.gesamtbericht and not second.llm_fehler
    assert [done for done, _, _ in events] == sorted(done for done, _, _ in events)


@pytest.mark.parametrize("failure_kind", ["models", "storage"])
def test_two_parallel_failures_are_two_failed_prompts_and_one_skipped_summary(setup, monkeypatch, failure_kind):
    pipe, make_result, _ = setup
    r = make_result()
    if failure_kind == "models":
        pipe.llm = FakeLlm({(101, "trade_analyse"): LlmError("trade failed"),
                            (101, "risiko_analyse"): LlmError("risk failed")})
    else:
        def fail(*args, **kwargs):
            raise OSError(args[1] + " failed")
        monkeypatch.setattr(db, "store_analysis", fail)
    outcome = llm_runner.run_llm(pipe, [r], lambda _: None)
    assert outcome["completed"] == 0 and outcome["failed"] == 2 and outcome["skipped"] == 1
    assert outcome["updated_ids"] == []
    assert len(pipe.llm.calls) == 2
    assert "trade" in r.llm_fehler and ("risk" in r.llm_fehler or "Risiko" in r.llm_fehler)
    if failure_kind == "storage":
        assert r.trade_analyse and r.risiko_analyse


@pytest.mark.parametrize("error", [LlmNoBalanceError("no balance"), LlmBudgetError("budget exhausted")])
@pytest.mark.parametrize("failed_stage", ["trade_analyse", "risiko_analyse"])
def test_fatal_parallel_error_keeps_successful_other_response_and_stops(setup, error, failed_stage):
    pipe, make_result, stored = setup
    pipe.llm = FakeLlm({(101, failed_stage): error})
    r = make_result()
    outcome = llm_runner.run_llm(pipe, [r, make_result(202)], lambda _: None)
    assert outcome == {"completed": 1, "total": 6, "failed": 1, "skipped": 4,
                       "reason": str(error), "updated_ids": [101]}
    assert len(pipe.llm.calls) == 2 and len(stored) == 1
    assert r.berichte_basis == "basis-101" and r.llm_fehler == str(error)
    other_stage = "risiko_analyse" if failed_stage == "trade_analyse" else "trade_analyse"
    assert getattr(r, other_stage) and not getattr(r, failed_stage)


def test_stale_unbound_parts_and_summary_never_fill_a_failed_new_prompt(setup):
    pipe, make_result, _ = setup
    pipe.llm = FakeLlm({(101, "risiko_analyse"): LlmError("risk unavailable")})
    r = make_result(old_basis="old-basis")
    r.trade_analyse, r.risiko_analyse, r.gesamtbericht, r.kurzfassung = ("OLD",) * 4
    outcome = llm_runner.run_llm(pipe, [r], lambda _: None)
    assert outcome["completed"] == 1 and outcome["failed"] == 1 and outcome["skipped"] == 1
    assert r.trade_analyse != "OLD" and r.berichte_basis == "basis-101"
    assert not r.risiko_analyse and not r.gesamtbericht and not r.kurzfassung


def test_same_basis_old_part_is_retained_but_not_counted_as_a_new_success(setup):
    pipe, make_result, _ = setup
    pipe.llm = FakeLlm({(101, "risiko_analyse"): LlmError("risk unavailable")})
    r = make_result(old_basis="basis-101")
    r.risiko_analyse = "previous same-basis risk"
    outcome = llm_runner.run_llm(pipe, [r], lambda _: None)
    assert r.risiko_analyse == "previous same-basis risk"
    assert outcome["completed"] == 1 and outcome["failed"] == 1
    assert len(pipe.llm.calls) == 2


def test_missing_basis_detaches_old_reports_and_sends_no_requests(setup, monkeypatch):
    pipe, make_result, _ = setup
    monkeypatch.setattr(pipeline, "report_basis_for", lambda r, cfg: None)
    r = make_result(old_basis="outdated")
    r.trade_analyse = r.risiko_analyse = r.gesamtbericht = r.kurzfassung = "OLD"
    outcome = llm_runner.run_llm(pipe, [r], lambda _: None)
    assert not pipe.llm.calls
    assert outcome["failed"] == 1 and outcome["skipped"] == 2
    assert not r.trade_analyse and not r.risiko_analyse and not r.gesamtbericht and not r.berichte_basis


def test_summary_storage_error_retains_text_and_continues(setup, monkeypatch):
    pipe, make_result, stored = setup

    def store(*args, **kwargs):
        if args[:2] == (101, "gesamtbericht"):
            raise OSError("summary disk error")
        stored.append((args, kwargs))

    monkeypatch.setattr(db, "store_analysis", store)
    r = make_result()
    outcome = llm_runner.run_llm(pipe, [r, make_result(202)], lambda _: None)
    assert outcome["completed"] == 5 and outcome["failed"] == 1 and outcome["skipped"] == 0
    assert outcome["updated_ids"] == [101, 202]
    assert r.gesamtbericht and r.kurzfassung and "summary disk error" in r.llm_fehler


def test_success_writes_one_current_basis_for_all_three_parts(setup):
    pipe, make_result, stored = setup
    r = make_result()
    outcome = llm_runner.run_llm(pipe, [r], lambda _: None)
    assert outcome == {"completed": 3, "total": 3, "failed": 0, "skipped": 0,
                       "reason": "", "updated_ids": [101]}
    assert len(stored) == 3 and all(kwargs == {"basis": "basis-101"} for _, kwargs in stored)
    assert r.berichte_basis == "basis-101"


def test_stop_after_parallel_stage_preserves_two_saved_parts(setup):
    pipe, make_result, stored = setup
    r = make_result()
    outcome = llm_runner.run_llm(pipe, [r], lambda _: None, should_stop=lambda: len(pipe.llm.calls) >= 2)
    assert outcome["completed"] == 2 and outcome["failed"] == 0 and outcome["skipped"] == 1
    assert "Stop" in outcome["reason"] and len(stored) == 2 and not r.gesamtbericht


def test_runner_real_basis_and_database_roundtrip():
    db.init_db()
    db.upsert_signal(101)
    result = pipeline.ScanResult(id=101, name="Signal 101", forensik_vorhanden=True)
    pipe = SimpleNamespace(settings={}, llm=FakeLlm())
    outcome = llm_runner.run_llm(pipe, [result], lambda _: None)
    basis = pipeline.report_basis_for(result, {})
    assert outcome["completed"] == 3
    assert result.berichte_basis == basis
    for kind in ("trade_analyse", "risiko_analyse", "gesamtbericht"):
        saved = db.get_latest_analysis(101, kind, basis=basis)
        assert saved["text"] == getattr(result, kind)
    restored = pipeline.ScanResult(id=101, name="Signal 101", forensik_vorhanden=True)
    assert pipeline.restore_current_reports(restored, {})
    assert restored.berichte_basis == basis and restored.gesamtbericht == result.gesamtbericht


def test_current_drawdown_criteria_are_applied_before_basis_and_prompt(setup, monkeypatch):
    pipe, make_result, _ = setup
    pipe.settings = {"schranke_eq_dd_pct": 10}
    r = make_result()
    r.dd_equity_pct = 20
    r.schranke_verletzt = False  # from an earlier 30% threshold
    observed = []

    def basis(result, settings):
        observed.append(result.schranke_verletzt)
        return "current-criteria"

    monkeypatch.setattr(pipeline, "report_basis_for", basis)
    outcome = llm_runner.run_llm(pipe, [r], lambda _: None)
    assert observed == [True] and r.ampel == "🔴"
    assert outcome["completed"] == 3 and r.berichte_basis == "current-criteria"
