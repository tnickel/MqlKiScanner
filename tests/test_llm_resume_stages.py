"""A resumed report pays only for missing, current-basis report stages."""
from types import SimpleNamespace

import pytest

from mqlkiscanner import db, llm_runner, pipeline
from mqlkiscanner.llm.client import LlmError


KINDS = ("trade_analyse", "risiko_analyse", "gesamtbericht")
REAL_REPORT_BASIS = pipeline.report_basis_for


@pytest.fixture
def resume(monkeypatch):
    db.init_db()
    db.upsert_signal(101)
    monkeypatch.setattr(pipeline, "report_basis_for", lambda result, settings: "current-basis")
    monkeypatch.setattr(llm_runner, "_load_verified_trade_payload", lambda result: {})
    monkeypatch.setattr(llm_runner.prompt_fill, "build_trade_prompt", lambda *args: "trade")
    monkeypatch.setattr(llm_runner.prompt_fill, "build_risk_prompt", lambda *args: "risk")
    summaries = []

    def summary_prompt(result, criteria, trade, risk):
        assert trade.strip() and risk.strip()
        summaries.append((trade, risk))
        return "summary"

    monkeypatch.setattr(llm_runner.prompt_fill, "build_gesamtbericht_prompt", summary_prompt)

    class Model:
        has_key = True

        def __init__(self):
            self.calls = []
            self.fail = {}

        def chat(self, prompt, *, stufe, max_tokens, meta_out):
            kind = {16384: KINDS[0], 8192: KINDS[1], 24576: KINDS[2]}[max_tokens]
            self.calls.append(kind)
            if kind in self.fail:
                raise self.fail[kind]
            meta_out["total_tokens"] = 10
            return "new " + kind

    model = Model()
    result = pipeline.ScanResult(id=101, name="Resume", forensik_vorhanden=True)
    pipe = SimpleNamespace(settings={}, llm=model)

    def seed(kind, basis="current-basis", text=None):
        db.store_analysis(101, kind, "cached-model", 7, text if text is not None else "cached " + kind,
                          basis=basis, quelle="mql5")

    return pipe, result, model, seed, summaries


@pytest.mark.parametrize("cached", [(KINDS[0],), (KINDS[1],), KINDS[:2], KINDS])
def test_only_missing_persisted_stages_are_called_and_counted(resume, cached):
    pipe, result, model, seed, summaries = resume
    for kind in cached:
        seed(kind)
    events = []
    outcome = llm_runner.run_llm(pipe, [result], lambda message: None,
                                 lambda *event: events.append(event))
    missing = set(KINDS) - set(cached)
    assert set(model.calls) == missing and len(model.calls) == len(missing)
    assert outcome["total"] == outcome["completed"] == len(missing)
    assert outcome["failed"] == outcome["skipped"] == 0
    assert outcome["updated_ids"] == ([("mql5", 101)] if missing else [])
    assert all(total == len(missing) and 0 <= done <= total for done, total, message in events)
    if missing:
        assert model.calls[-1] == KINDS[2] and len(summaries) == 1
    for kind in cached:
        assert getattr(result, kind) == "cached " + kind
    with db._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 3


def test_old_basis_parts_cannot_satisfy_current_stages(resume):
    pipe, result, model, seed, summaries = resume
    for kind in KINDS:
        seed(kind, basis="old-basis")
        setattr(result, kind, "old in-memory " + kind)
    result.berichte_basis = "old-basis"
    outcome = llm_runner.run_llm(pipe, [result], lambda message: None)
    assert outcome["completed"] == outcome["total"] == 3
    assert set(model.calls) == set(KINDS) and model.calls[-1] == KINDS[2]
    assert summaries == [("new trade_analyse", "new risiko_analyse")]


def test_unsaved_answers_and_blank_saved_text_are_not_cache_hits(resume):
    pipe, result, model, seed, summaries = resume
    result.berichte_basis = "current-basis"
    result.trade_analyse = result.risiko_analyse = "paid but not stored"
    seed(KINDS[0], text=" \n ")
    outcome = llm_runner.run_llm(pipe, [result], lambda message: None)
    assert outcome["completed"] == outcome["total"] == 3
    assert len(model.calls) == 3
    assert summaries == [("new trade_analyse", "new risiko_analyse")]


def test_failed_missing_stage_keeps_cached_peer_and_skips_summary(resume):
    pipe, result, model, seed, summaries = resume
    seed(KINDS[0])
    model.fail[KINDS[1]] = LlmError("risk unavailable")
    outcome = llm_runner.run_llm(pipe, [result], lambda message: None)
    assert model.calls == [KINDS[1]] and not summaries
    assert result.trade_analyse == "cached trade_analyse"
    assert outcome["total"] == 2 and outcome["completed"] == 0
    assert outcome["failed"] == outcome["skipped"] == 1


@pytest.mark.parametrize("failed_kind", [KINDS[0], KINDS[2]])
def test_storage_failure_is_not_success_and_never_synthesizes_from_unsaved_input(resume, monkeypatch, failed_kind):
    pipe, result, model, seed, summaries = resume
    seed(KINDS[1])
    if failed_kind == KINDS[2]:
        seed(KINDS[0])

    def fail_store(*args, **kwargs):
        assert args[1] == failed_kind
        raise OSError("disk unavailable")

    monkeypatch.setattr(db, "store_analysis", fail_store)
    outcome = llm_runner.run_llm(pipe, [result], lambda message: None)
    assert model.calls == [failed_kind]
    assert outcome["completed"] == 0 and outcome["failed"] == 1
    assert outcome["total"] == (2 if failed_kind == KINDS[0] else 1)
    assert outcome["skipped"] == (1 if failed_kind == KINDS[0] else 0)
    assert bool(summaries) == (failed_kind == KINDS[2])
    assert "disk unavailable" in result.llm_fehler and getattr(result, failed_kind)


@pytest.mark.parametrize("after_risk", [False, True])
def test_stop_counts_only_remaining_missing_stages(resume, after_risk):
    pipe, result, model, seed, summaries = resume
    seed(KINDS[0])
    outcome = llm_runner.run_llm(pipe, [result], lambda message: None,
                                 should_stop=lambda: bool(model.calls) if after_risk else True)
    assert model.calls == ([KINDS[1]] if after_risk else []) and not summaries
    assert outcome["total"] == 2 and outcome["completed"] == int(after_risk)
    assert outcome["skipped"] == 2 - int(after_risk) and outcome["failed"] == 0
    assert "Stop" in outcome["reason"]


def test_retry_after_stop_reuses_both_saved_inputs(resume):
    pipe, result, model, seed, summaries = resume
    seed(KINDS[0])
    first = llm_runner.run_llm(pipe, [result], lambda message: None, should_stop=lambda: bool(model.calls))
    assert first["completed"] == 1 and first["skipped"] == 1
    model.calls.clear()
    second = llm_runner.run_llm(pipe, [result], lambda message: None)
    assert model.calls == [KINDS[2]]
    assert second["total"] == second["completed"] == 1 and second["failed"] == second["skipped"] == 0
    assert summaries == [("cached trade_analyse", "new risiko_analyse")]


def test_raised_token_limits_preserve_the_real_report_basis_and_cached_stage(resume, monkeypatch):
    pipe, result, model, seed, summaries = resume
    monkeypatch.setattr(pipeline, "report_basis_for", REAL_REPORT_BASIS)
    pipeline.refresh_report_verdict(result, pipe.settings)
    before = REAL_REPORT_BASIS(result, pipe.settings)
    seed(KINDS[0], basis=before)
    pipe.settings.update(agenten_tagesbudget_tokens=10_000_000,
                         agenten_monatsbudget_tokens=10_000_000,
                         llm_max_total_tokens=10_000_000)
    assert REAL_REPORT_BASIS(result, pipe.settings) == before
    outcome = llm_runner.run_llm(pipe, [result], lambda message: None)
    assert model.calls == [KINDS[1], KINDS[2]]
    assert outcome["total"] == outcome["completed"] == 2
    assert summaries == [("cached trade_analyse", "new risiko_analyse")]
