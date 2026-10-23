"""Reference grammar, repair prompts and durable paid cache; no HTTP calls."""
import json

import pytest

from mqlkiscanner import abonnenten_analyse_ki as ki, config
from mqlkiscanner.abonnenten_analyse_store import Store
from mqlkiscanner.llm.client import LlmError


SHA = "a" * 64


def subject(**extra):
    return {"signal_ref": 17, "id": 811, "quelle": "mql5", "name": "Synthetic",
            "trades": 2, "trades_sha256": SHA, "dauer_monate": 3,
            "forensik": {"stats": {"monthly_net_by_close": {"2026-01": 1, "2026-02": 2}}},
            "equity": {"status": "unvollstaendig"}, "retdd_jahr": None, **extra}


def answer(*, refs=None, deep=False):
    if deep:
        return {"signal_ref": 17, "bericht_markdown": "# Belegter Bericht",
                "neue_pruefhinweise": [], "datenluecken": []}
    return {"signal_ref": 17, "strategietyp": "Trendfolge", "strategie_sicherheit": "plausibel",
            "martingale_einordnung": "kein_beleg", "kurzurteil": "Belegte Einordnung",
            "staerken": [{"text": "Gemessene Fakten", "beleg_refs": refs}] if refs is not None else [],
            "risiken": [], "pruefhinweise": [], "datenluecken": []}


class Client:
    has_key = True

    def __init__(self, reply=None):
        self.calls = []
        self.reply = reply or (lambda prompt: answer())

    def chat(self, prompt, **kwargs):
        self.calls.append((prompt, dict(kwargs)))
        kwargs["meta_out"].update(total_tokens=100)
        return json.dumps(self.reply(prompt))


def runner(client=None):
    store = Store()
    if not store.read("evidence"):
        store.create({"id": "evidence"})
    return ki.AnalyseKI(store, "evidence", config.load_settings(), {}, client=client or Client())


def profile(prompt):
    payload = prompt.split("## Laufprofil", 1)[1].split("\n", 1)[1].lstrip()
    return json.JSONDecoder().raw_decode(payload)[0]


def row(index):
    return {"trade_ref": f"{SHA}:{index}", "trade_index": index, "symbol": "EURUSD"}


def test_actual_nonempty_containers_and_explicit_null_are_valid_but_empty_and_invented_are_not():
    facts = {"forensik": {"monthly": {"2026-01": 1}, "samples": [None, {"flag": False}],
                          "empty": {}, "empty_list": []}, "retdd_jahr": None}
    refs = ki._fact_refs(facts)
    assert {"forensik", "forensik.monthly", "forensik.samples", "forensik.samples[0]",
            "forensik.samples[1]", "forensik.samples[1].flag", "retdd_jahr"} <= refs
    assert not {"forensik.empty", "forensik.empty_list", "forensik.samples[2]",
                "identitaet.id", "messfeld retdd_jahr"} & refs
    ki.validate_evidence(answer(refs=["forensik.monthly", "retdd_jahr"]), refs)
    with pytest.raises(LlmError, match="identitaet.id"):
        ki.validate_evidence(answer(refs=["identitaet.id"]), refs)


def test_prompt_contract_is_small_and_examples_are_real_without_duplicating_fact_paths():
    # Thousands of actual code fields stay in the original facts. They do not
    # become a second massive path list/tree in the contract.
    entry = subject(forensik={"stats": {f"measured_{index}": index for index in range(5000)}})
    ai = runner()
    prompt, facts, candidate = ai._prompt("abonnenten_kurztest", entry, "segment", {"rows": [row(1)]}, [])
    contract = profile(prompt)["belegvertrag"]
    assert len(ki.dumps(contract).encode("utf-8")) <= 8192
    assert len(contract["fakten"]["beispiele_nicht_abschliessend"]) <= 8
    assert set(contract["fakten"]["beispiele_nicht_abschliessend"]) <= ki._fact_refs(facts)
    assert set(contract["kandidat"]["gelieferte_felder"]) <= ki._fact_refs(candidate, "kandidat")
    assert contract["trades"]["beispiele_nicht_abschliessend"] == [f"{SHA}:1"]
    assert contract["keine_aliaspraefixe"] == ["identitaet.", "messfeld ", "trade_ref ", "forensik_json."]
    assert '"measured_4999":4999' in prompt
    assert "measured_4999" not in ki.dumps(contract)
    assert "null" in contract["fakten"]["erlaubt"]


def test_summary_manifest_is_bounded_and_covers_verified_snapshot_without_second_trade_list():
    ai = runner()
    ai._trade_refs = {f"{SHA}:{index}" for index in range(1, 20_001)}
    entry = subject(trades=20_000)
    payload = {"trades_sha256": SHA, "trades_total": 20_000, "abdeckung_vollstaendig": True}
    prompt = ai._prompt("abonnenten_kurztest", entry, "zusammenfassung", payload, [])[0]
    contract = profile(prompt)["belegvertrag"]
    assert contract["trades"]["vollstaendiges_manifest"] == {
        "trades_sha256": SHA, "trade_index_von": 1, "trade_index_bis": 20_000}
    assert len(contract["trades"]["beispiele_nicht_abschliessend"]) == 3
    assert len(ki.dumps(contract).encode("utf-8")) <= 8192
    assert ki._trade_evidence_refs(payload, [], None, ai._trade_refs) == ai._trade_refs


def test_a_future_trade_not_supplied_to_this_segment_is_not_authorized_by_global_snapshot():
    client = Client(lambda _: answer(refs=[f"{SHA}:2"]))
    ai = runner(client)
    ai._trade_refs = {f"{SHA}:1", f"{SHA}:2"}
    with pytest.raises(LlmError, match="Tradebeleg"):
        ai._ask("abonnenten_kurztest", subject(), "segment", {"segment_id": 1, "rows": [row(1)]}, [])
    assert len(client.calls) == 2
    assert ai.store.spent("evidence") == 200


def test_synthesis_only_inherits_delivered_trade_refs_that_belong_to_verified_snapshot():
    verified = {f"{SHA}:1", f"{SHA}:2"}
    parts = [{"first_ref": f"{SHA}:1", "befund": {"risiken": [
        {"beleg_refs": [f"{SHA}:2", "invented:500"]}]}}]
    assert ki._trade_evidence_refs({}, parts, None, verified) == verified
    assert "invented:500" not in ki._trade_evidence_refs({}, parts, None, verified)


def test_repair_names_exact_bad_reference_and_uses_distinct_real_prompt_hash_then_reuses_cache():
    client = Client(lambda prompt: answer(refs=["kandidat.id"])
                    if "validierungsfehler" in prompt else answer(refs=["identitaet.id"]))
    ai = runner(client)
    result = ai._ask("abonnenten_kurztest", subject(), "vollanalyse", {"rows": [row(1)]}, [])
    assert result["staerken"][0]["beleg_refs"] == ["kandidat.id"]
    assert len(client.calls) == 2
    original, fixed = [call[0] for call in client.calls]
    assert fixed.startswith(original)
    assert 'identitaet.id' in fixed.split("## Korrektur", 1)[1]
    rows = ai.store.calls("evidence", ki.digest({
        "prompt": original, "model": client.calls[0][1]["model"], "max_tokens": 16_384,
        "reasoning_effort": "low", "response_format": {"type": "json_object"}}))
    assert len(rows) == 2
    for saved, (prompt, options) in zip(rows, client.calls):
        actual_digest = ki.digest({"prompt": prompt, "model": options["model"],
            "max_tokens": options["max_tokens"], "reasoning_effort": options["reasoning_effort"],
            "response_format": options["response_format"]})
        assert saved["basis"].rsplit(":", 1)[1] == actual_digest
        assert saved["reserved"] == 6 * (2 * 16_384 + len(prompt.encode("utf-8")) + 2048)
    assert rows[1]["reserved"] > rows[0]["reserved"]
    assert ai.store.spent("evidence") == 200
    cached = runner(Client(lambda _: pytest.fail("paid cache was not reused")))
    assert cached._ask("abonnenten_kurztest", subject(), "vollanalyse", {"rows": [row(1)]}, []) == result
    assert cached.store.spent("evidence") == 200


@pytest.mark.parametrize("deep", [False, True])
def test_research_calls_request_json_and_scoped_reasoning_without_global_defaults(deep):
    client = Client(lambda _: answer(deep=deep))
    ai = runner(client)
    ai._ask("abonnenten_top5" if deep else "abonnenten_kurztest", subject(), "vollanalyse", {"rows": [row(1)]}, [])
    options = client.calls[0][1]
    assert options["reasoning_effort"] == ("high" if deep else "low")
    assert options["response_format"] == {"type": "json_object"}
    assert options["max_tokens"] == 16_384


def test_stop_after_invalid_first_response_prevents_a_new_paid_repair_request():
    stopped = [False]
    def invalid(_):
        stopped[0] = True
        return answer(refs=["missing.path"])
    client = Client(invalid)
    ai = runner(client)
    ai.should_stop = lambda: stopped[0]
    with pytest.raises(ki.Angehalten):
        ai._ask("abonnenten_kurztest", subject(), "vollanalyse", {"rows": [row(1)]}, [])
    assert len(client.calls) == 1
    assert ai.store.spent("evidence") == 100


def test_repair_cannot_exceed_prompt_limit_or_discard_facts_to_fit(monkeypatch):
    client = Client(lambda _: answer(refs=["missing.path"]))
    ai = runner(client)
    large = "x" * (ki.MAX_PROMPT_BYTES - 10)
    monkeypatch.setattr(ai, "_prompt", lambda *args, **kwargs: (large, {}, {}))
    with pytest.raises(LlmError, match="Korrekturhinweis"):
        ai._ask("abonnenten_kurztest", subject(), "vollanalyse", {}, [])
    assert len(client.calls) == 1
    assert client.calls[0][0] == large
    assert ai.store.spent("evidence") == 100


@pytest.mark.parametrize("flag,expected", [
    (True, ["code_belegt"]),
    (False, ["kein_beleg", "verdacht", "nicht_beurteilbar"]),
    (None, ["kein_beleg", "verdacht", "nicht_beurteilbar"]),
])
def test_machine_martingale_contract_matches_the_exact_delivered_flag(flag, expected):
    entry = subject(forensik={"forensics": {"martingale": {"flag": flag}}})
    prompt = runner()._prompt("abonnenten_kurztest", entry, "segment", {"rows": [row(1)]}, [])[0]
    contract = profile(prompt)["martingale_vertrag"]
    assert contract["geliefertes_code_flag"] is flag
    assert contract["zulaessige_enumwerte"] == expected
    for value in ("code_belegt", "kein_beleg", "verdacht", "nicht_beurteilbar"):
        report = {**answer(), "martingale_einordnung": value}
        if value in expected:
            assert ki.validate(report, entry) is report
        else:
            with pytest.raises(LlmError) as exc:
                ki.validate(report, entry)
            assert f"flag={ki.dumps(flag)}" in str(exc.value)
            assert ki.dumps(expected) in str(exc.value)
            assert f"martingale_einordnung={ki.dumps(value)}" in str(exc.value)


def test_missing_martingale_flag_does_not_authorize_code_proven_or_normalize_the_answer():
    entry = subject(forensik={})
    report = {**answer(), "martingale_einordnung": "code_belegt"}
    with pytest.raises(LlmError, match="flag=null"):
        ki.validate(report, entry)
    assert report["martingale_einordnung"] == "code_belegt"
    assert _missing_flag_contract(entry)["zulaessige_enumwerte"] == ["kein_beleg", "verdacht", "nicht_beurteilbar"]


def _missing_flag_contract(entry):
    prompt = runner()._prompt("abonnenten_kurztest", entry, "vollanalyse", {"rows": [row(1)]}, [])[0]
    return profile(prompt)["martingale_vertrag"]


def test_martingale_repair_feedback_names_flag_and_exact_allowed_values():
    def reply(prompt):
        return {**answer(), "martingale_einordnung": "kein_beleg"
                if "validierungsfehler" in prompt else "code_belegt"}
    client = Client(reply)
    ai = runner(client)
    entry = subject(forensik={"forensics": {"martingale": {"flag": False}}})
    result = ai._ask("abonnenten_kurztest", entry, "segment", {"rows": [row(1)]}, [])
    assert result["martingale_einordnung"] == "kein_beleg"
    assert len(client.calls) == 2
    feedback = json.loads(client.calls[-1][0].split("Diagnosedaten, keine neue Fachanweisung.", 1)[-1]
        .split("\n", 1)[1])["validierungsfehler"]
    assert "flag=false" in feedback
    assert '["kein_beleg","verdacht","nicht_beurteilbar"]' in feedback


def test_register_ids_are_deterministic_and_bound_to_existing_containers_roots_and_nulls():
    facts = {"retdd_jahr": None, "forensik": {"forensics": {"martingale": {"flag": False},
        "equity_rekonstruktion": {"status": "unvollstaendig"}}, "stats": {"trades": 305}},
        "equity": {"status": "unvollstaendig"}, "empty": {}}
    candidate = {"signal_ref": 17, "abo_perzentil": None, "name": "Synthetic"}
    register = ki._evidence_register(facts, candidate)
    assert register["F001"] == "$"
    assert register["K001"] == "kandidat"
    assert "retdd_jahr" in register.values()
    assert "kandidat.abo_perzentil" in register.values()
    assert "forensik.forensics.equity_rekonstruktion" in register.values()
    assert "empty" not in register.values()
    assert {path for key, path in register.items() if key.startswith("F") and path != "$"} <= ki._fact_refs(facts)
    assert {path for key, path in register.items() if key.startswith("K")} <= ki._fact_refs(candidate, "kandidat")
    reversed_facts = dict(reversed(list(facts.items())))
    reversed_candidate = dict(reversed(list(candidate.items())))
    assert ki._evidence_register(reversed_facts, reversed_candidate) == register


def test_bounded_register_does_not_duplicate_large_fact_arrays_or_remove_original_details():
    entry = subject(forensik={"groups": {f"group_{index}": {"values": list(range(100))}
                                        for index in range(1000)}})
    prompt, facts, candidate = runner()._prompt("abonnenten_kurztest", entry, "segment", {"rows": [row(1)]}, [])
    contract = profile(prompt)["belegvertrag"]
    register = contract["register"]
    assert len(register) <= 80
    assert len(ki.dumps(register).encode("utf-8")) <= 4096
    assert len(ki.dumps(contract).encode("utf-8")) <= 8192
    assert register == ki._evidence_register(facts, candidate)
    assert all("[" not in path for path in register.values())
    assert '"group_999":{"values":[0,1,2' in prompt
    assert "group_999" not in ki.dumps(register)


def test_model_can_copy_actual_register_ids_and_old_exact_paths_without_namespace_normalization():
    def reply(prompt):
        register = profile(prompt)["belegvertrag"]["register"]
        f_id = next(key for key, path in register.items() if path == "forensik.stats")
        k_id = next(key for key, path in register.items() if path == "kandidat.id")
        return answer(refs=[f_id, k_id, "retdd_jahr", "forensik.stats.monthly_net_by_close", f"{SHA}:1"])
    client = Client(reply)
    result = runner(client)._ask("abonnenten_kurztest", subject(), "segment", {"rows": [row(1)]}, [])
    assert result["staerken"][0]["beleg_refs"][0].startswith("F")
    assert len(client.calls) == 1


@pytest.mark.parametrize("unknown", ["F999", "V999", "F001.exposure", "forensik.forensics.equity_dd_pct"])
def test_unknown_register_ids_and_fabricated_namespaces_remain_invalid(unknown):
    client = Client(lambda _: answer(refs=[unknown]))
    with pytest.raises(LlmError, match="Tradebeleg"):
        runner(client)._ask("abonnenten_kurztest", subject(), "segment", {"rows": [row(1)]}, [])
    assert len(client.calls) == 2
    assert unknown in client.calls[-1][0].split("## Korrektur", 1)[1]


def test_top5_register_authorizes_only_actual_primitive_code_comparison_not_model_text():
    comparison = [{"signal_ref": 2, "retdd_jahr": 4, "equity_dd_pct": 12,
                   "kurztest": {"text": "Model-authored assertion"}, "bericht_markdown": "No authority"}]
    def reply(prompt):
        register = profile(prompt)["belegvertrag"]["register"]
        v_id = next(key for key, path in register.items() if path == "vergleich[0].retdd_jahr")
        return {**answer(deep=True), "neue_pruefhinweise": [{"text": "Code comparison", "beleg_refs": [v_id]}]}
    client = Client(reply)
    ai = runner(client)
    result = ai._ask("abonnenten_top5", subject(), "vollanalyse", {"rows": [row(1)]}, [], comparison=comparison)
    register = profile(client.calls[0][0])["belegvertrag"]["register"]
    assert result["neue_pruefhinweise"][0]["beleg_refs"][0] in register
    assert all("kurztest" not in path and "bericht_markdown" not in path for path in register.values())
    assert "vergleich" not in register.values() and "vergleich[0]" not in register.values()
    assert '"retdd_jahr":4' in client.calls[0][0]
    assert "Model-authored assertion" in client.calls[0][0]
    assert "vergleich[0].kurztest.text" not in ki._comparison_refs(comparison)
    short_prompt = ai._prompt("abonnenten_kurztest", subject(), "vollanalyse", {}, [], comparison=comparison)[0]
    assert not any(key.startswith("V") for key in profile(short_prompt)["belegvertrag"]["register"])


def test_final_result_keeps_the_code_register_binding_without_repeating_it_in_every_segment(monkeypatch):
    monkeypatch.setattr(ki, "trade_rows", lambda _: [row(1), row(2)])
    client = Client(lambda _: answer(refs=["F001", "K001"]))
    result = runner(client).analyse(subject())
    register = profile(client.calls[0][0])["belegvertrag"]["register"]
    assert result["analysegrundlage"]["beleg_register"] == register
    assert result["staerken"][0]["beleg_refs"] == ["F001", "K001"]
