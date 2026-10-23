"""Actual prompt byte bounds and lossless larger blocks, without network calls."""
from __future__ import annotations

import copy
import json
import re

import pytest

from mqlkiscanner import abonnenten_analyse_ki as ki, config
from mqlkiscanner.abonnenten_analyse_store import Store
from mqlkiscanner.llm.client import LlmError


def rows(count):
    return [{"trade_ref": f"{'a'*64}:{index}", "trade_index": index,
             "open": f"2026-01-01T{index:05}", "close": f"2026-01-02T{index:05}",
             "symbol": "EURUSD", "direction": "BUY", "volume": .1,
             "entry": 1.1, "exit": 1.2, "profit": 10, "commission": 0,
             "swap": 0, "sl": None, "tp": None, "comment": "gleiches echtes Handelsmuster"}
            for index in range(count)]


def entry(count, **values):
    return {"signal_ref": 1, "id": 8, "quelle": "mql5", "name": "Synthetic",
            "trades": count, "trades_sha256": "a"*64, "forensik": {}, "equity": {}, **values}


def reply(**extra):
    return {"signal_ref": 1, "strategietyp": "Trendfolge", "strategie_sicherheit": "plausibel",
            "martingale_einordnung": "kein_beleg", "kurzurteil": "Belegte Muster",
            "staerken": [], "risiken": [], "pruefhinweise": [], "datenluecken": [], **extra}


class Client:
    has_key = True
    def __init__(self, answer=None):
        self.prompts = []
        self.answer = answer or (lambda _: reply())
    def chat(self, prompt, **kwargs):
        self.prompts.append(prompt)
        kwargs["meta_out"].update(total_tokens=100)
        return json.dumps(self.answer(prompt))


def runner(client=None):
    store = Store()
    if not store.read("performance"):
        store.create({"id": "performance"})
    return ki.AnalyseKI(store, "performance", config.load_settings(), {}, client=client or Client())


def assert_coverage(blocks, all_rows):
    refs = [row["trade_ref"] for row in all_rows]
    assert [ref for block in blocks for ref in block["primary_refs"]] == refs
    start = 0
    for index, block in enumerate(blocks, 1):
        end = start + len(block["primary_refs"])
        assert block["segment_id"] == index
        assert block["rows"] == all_rows[max(0, start-8):end]
        assert block["overlap_refs"] == refs[max(0, start-8):start]
        start = end


def test_larger_blocks_count_manifests_unicode_and_overlap_exactly():
    all_rows = rows(904)
    for row in all_rows:
        row["comment"] += " \u4e2d\u6587 \U0001f600"
    original = copy.deepcopy(all_rows)
    blocks = ki.segments(all_rows)
    assert 1 < len(blocks) <= 6
    assert_coverage(blocks, all_rows)
    assert all(len(ki.dumps(block).encode("utf-8")) <= 80_000 for block in blocks)
    assert all_rows == original
    # Most blocks use the target rather than the old ~22k-row slice.
    assert len(ki.dumps(blocks[0]).encode("utf-8")) > 75_000


@pytest.mark.parametrize("deep", [False, True])
def test_dynamic_split_counts_actual_facts_template_short_comparison_and_utf8(monkeypatch, deep):
    all_rows = rows(600)
    subject = entry(600, forensik={"facts": "\u4e2d"*38_000})
    key = "abonnenten_top5" if deep else "abonnenten_kurztest"
    short = {"kurzurteil": "\U0001f600"*8_000} if deep else None
    comparison = [{"signal_ref": 2, "name": "\u4e2d"*3_000}] if deep else []
    actual_builder = ki.prompt_fill.build_abonnenten_prompt
    # An editable template may repeat a placeholder. Count rendered bytes,
    # not a guessed constant overhead or just the primary row serialization.
    def repeated(key, **values):
        return actual_builder(key, **values) + "\nWiederholte Trades:\n" + values["trades_json"]
    monkeypatch.setattr(ki.prompt_fill, "build_abonnenten_prompt", repeated)
    ai = runner()
    blocks = ai._fit_blocks(key, subject, all_rows, short=short, comparison=comparison)
    assert len(blocks) > len(ki.segments(all_rows))
    assert_coverage(blocks, all_rows)
    for block in blocks:
        prompt = ai._prompt(key, subject, "segment", block, [], short=short, comparison=comparison)[0]
        assert len(prompt.encode("utf-8")) <= ki.MAX_PROMPT_BYTES == 240_000
    assert ai.client.prompts == []


@pytest.mark.parametrize("huge_facts,huge_trade", [(True, False), (False, True)])
def test_indivisible_oversize_fails_before_any_paid_call(monkeypatch, huge_facts, huge_trade):
    all_rows = rows(5)
    subject = entry(5, forensik={"facts": "x"*245_000} if huge_facts else {})
    if huge_trade:
        all_rows[2]["comment"] = "x"*245_000
    monkeypatch.setattr(ki, "trade_rows", lambda _: all_rows)
    ai = runner()
    with pytest.raises(LlmError, match="keine Trades oder Belege wurden gekürzt"):
        ai.analyse(subject)
    assert ai.client.prompts == []
    assert ai.store.spent("performance") == 0


def test_all_trades_are_covered_and_paid_segments_reused_after_restart(monkeypatch):
    all_rows = rows(904)
    monkeypatch.setattr(ki, "trade_rows", lambda _: all_rows)
    subject = entry(904, forensik={"facts": "x"*71_000})
    first = runner()
    result = first.analyse(subject)
    blocks = first._fit_blocks("abonnenten_kurztest", subject, all_rows)
    assert_coverage(blocks, all_rows)
    assert len(first.client.prompts) == len(blocks)+1 <= 7
    assert all(len(prompt.encode("utf-8")) <= 240_000 for prompt in first.client.prompts)
    assert result["analysegrundlage"]["trades_ki_abgedeckt"] == 904
    spent = first.store.spent("performance")
    restarted = runner()
    assert restarted.analyse(subject) == result
    assert restarted.client.prompts == []
    assert restarted.store.spent("performance") == spent


def test_identical_equity_keeps_both_existing_evidence_paths():
    equity = {"equity_dd_pct_raw": 20.1234, "status": "ok"}
    subject = entry(1, equity=copy.deepcopy(equity),
                    forensik={"forensics": {"equity_rekonstruktion": copy.deepcopy(equity)}})
    refs = ["equity.equity_dd_pct_raw", "forensik.forensics.equity_rekonstruktion.equity_dd_pct_raw"]
    client = Client(lambda _: reply(staerken=[{"text": "identische Messung", "beleg_refs": refs}]))
    ai = runner(client)
    result = ai._ask("abonnenten_kurztest", subject, "vollanalyse", {"rows": rows(1)}, [])
    assert result["staerken"][0]["beleg_refs"] == refs
    assert client.prompts[0].count('"equity_dd_pct_raw":20.1234') == 2


def test_deep_calls_include_full_short_and_comparison_in_planned_prompt(monkeypatch):
    all_rows = rows(904)
    monkeypatch.setattr(ki, "trade_rows", lambda _: all_rows)
    subject = entry(904, kurztest={"kurzurteil": "belegter Kurztest"})
    comparison = [{"signal_ref": 1, "retdd_jahr": 4}, {"signal_ref": 2, "retdd_jahr": 3}]
    def answer(prompt):
        if '"verarbeitung":"segment"' in prompt:
            sid = int(re.search(r'"segment_id":(\d+)', prompt)[1])
            return {"signal_ref": 1, "segment_id": sid, "handelsmuster": "Belegtes Muster",
                    "staerken": [], "risiken": [], "widersprueche": [], "datenluecken": [], "beleg_refs": []}
        return {"signal_ref": 1, "bericht_markdown": "# Ausführlicher Befund",
                "neue_pruefhinweise": [], "datenluecken": []}
    ai = runner(Client(answer))
    result = ai.analyse(subject, deep=True, comparison=comparison)
    assert result["bericht_markdown"].startswith("#")
    assert result["analysegrundlage"]["trades_ki_abgedeckt"] == 904
    assert all('belegter Kurztest' in prompt and '"retdd_jahr":3' in prompt for prompt in ai.client.prompts)
    assert all(len(prompt.encode("utf-8")) <= 240_000 for prompt in ai.client.prompts)
