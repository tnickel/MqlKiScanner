"""Grok F5: omitted chronology is explicit; trade blocks remain separate."""
import json

import pytest

from mqlkiscanner import abonnenten_analyse_ki as ki, config
from mqlkiscanner.abonnenten_analyse_store import Store


@pytest.mark.parametrize("factory", [list, tuple])
@pytest.mark.parametrize("size", [0, 100, 101, 500])
def test_fact_list_preserves_values_or_declares_exact_omitted_range(factory, size):
    raw = factory({"month": index, "profit": index - 40} for index in range(size))
    result = ki.compact({"monthly_results": raw})["monthly_results"]
    if size <= 100:
        assert result == list(raw)
    else:
        assert result["eintraege"] == list(raw[:100])
        assert result["abdeckung"] == {
            "vollstaendig": False, "anzahl_gesamt": size,
            "enthaltene_indizes": [0, 99], "ausgelassene_indizes": [100, size - 1],
            "indexbasis": 0}
    assert len(raw) == size  # Input provenance stays untouched.


def test_nested_fact_lists_carry_their_own_coverage_and_keep_nonfinite_cleanup():
    result = ki.compact({"groups": [{"pairs": list(range(101)), "missing": float("nan")}]})
    assert result["groups"][0]["pairs"]["abdeckung"]["anzahl_gesamt"] == 101
    assert result["groups"][0]["missing"] is None


@pytest.mark.parametrize("factory", [list, tuple])
def test_curves_and_raw_trades_stay_out_of_facts_but_numeric_counts_remain(factory):
    raw = {key: factory(range(101)) for key in
           ("punkte", "equity_curve", "balance_curve", "bars", "rohkurse", "trades")}
    assert ki.compact(raw) == {}
    assert ki.compact({"trades": 101, "curve_count": 101}) == {"trades": 101, "curve_count": 101}


def test_actual_short_and_top5_prompts_disclose_fact_coverage_without_losing_trade_rows():
    store = Store()
    store.create({"id": "grok-facts"})
    ai = ki.AnalyseKI(store, "grok-facts", config.load_settings(), {}, client=object())
    entry = {"signal_ref": 7, "trades": 101, "forensik": {"martingale_pairs": list(range(101))}}
    rows = [{"trade_ref": f"sha:{index}", "trade_index": index} for index in range(101)]
    for key in ("abonnenten_kurztest", "abonnenten_top5"):
        prompt, facts, _ = ai._prompt(key, entry, "vollanalyse", {"rows": rows}, [])
        coverage = facts["forensik"]["martingale_pairs"]["abdeckung"]
        assert coverage["anzahl_gesamt"] == 101 and coverage["vollstaendig"] is False
        assert '"ausgelassene_indizes":[100,100]' in prompt
        assert "Verlauf als vollständig" in prompt
        assert '"trade_ref":"sha:100"' in prompt
        assert len(rows) == 101
        assert json.dumps(facts)  # Normal JSON payload, no nonstandard sentinel.
