"""Isolated final hint decisions: binding, ranking consequences and paid cache."""
from copy import deepcopy
import hashlib
import json

import pytest

from mqlkiscanner import abonnenten_analyse_klaerung as kl
from mqlkiscanner import config
from mqlkiscanner.abonnenten_analyse_store import Store
from mqlkiscanner.llm.client import LlmError


@pytest.fixture
def entry(tmp_path):
    path = tmp_path / "hint_trades.csv"
    path.write_text("Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
                    "2026.01.01 12:00:00;Buy;0.01;EURUSD;1.1;0.01;2026.01.01 13:00:00;1.2;0;0;10\n",
                    encoding="utf-8")
    hint = {"text": "Angeblich wurden zwei identische Trades entfernt.", "beleg_refs": ["F023"]}
    origin = {"bericht_stufe": "kurztest", "bericht_basis": "original-short",
              "data_basis": "frozen-data", "trades_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "analysegrundlage": {"beleg_register": {"F023": "forensik.stats.duplikate_entfernt"}}}
    return {"signal_ref": 1, "id": 1, "quelle": "mql5", "quellen_uid": "source-1", "name": "Synthetic",
            "trades": 1, "trades_path": str(path), "trades_sha256": origin["trades_sha256"],
            "data_basis": "frozen-data", "kurz_basis": "original-short", "eligible": True,
            "forensik": {"stats": {"duplikate_entfernt": 0, "identische_tradezeilen": 2}},
            "equity": {"status": "ok", "verlaesslich": True}, "retdd_jahr": 3.5,
            "ki_pruefhinweise": [hint], "ki_pruefhinweis_quellen": [{"hinweis": deepcopy(hint), "herkunft": origin}],
            "review_pending": True, "rang": 1, "auswahlwert": 90, "retdd_perzentil": 95}


def result(entry, decision="widerlegt", effect="keine_sperre", **extra):
    return {"schema_version": kl.RESOLUTION_VERSION, "signal_ref": entry["signal_ref"],
            "hinweis_basis": kl.resolution_basis(entry), "trades_sha256": entry["trades_sha256"],
            "entscheidungen": [{"hinweis_id": row["hinweis_id"], "entscheidung": decision,
                                "auswirkung": effect,
                                "bewertungsrelevanz": "zusatzrisiko" if effect == "dokumentierter_risikohinweis" else "pflichtgrundlage",
                                "begruendung": "duplikate_entfernt ist ausdrücklich 0.",
                                "beleg_refs": ["forensik.stats.duplikate_entfernt"], **extra}
                               for row in kl.hint_records(entry)]}


def test_original_report_register_preserved_without_alias_rebinding(entry):
    before = deepcopy(entry)
    kl.apply_resolution(entry, result(entry))
    assert entry["ki_pruefhinweise"] == before["ki_pruefhinweise"]
    assert entry["ki_pruefhinweis_quellen"] == before["ki_pruefhinweis_quellen"]
    decision = entry["ki_pruefentscheidungen"][0]
    assert decision["herkunft"][0]["analysegrundlage"]["beleg_register"]["F023"] == "forensik.stats.duplikate_entfernt"
    assert decision["herkunft"][0]["bericht_basis"] == "original-short"
    assert kl.has_current_resolution(entry)


@pytest.mark.parametrize("change", ["trades_sha256", "data_basis", "kurz_basis", "top5_basis", "abonnenten"])
def test_changed_basis_invalidates_final_decisions(entry, change):
    kl.apply_resolution(entry, result(entry))
    entry[change] = "changed"
    assert not kl.resolved_hint_ids(entry)
    assert not kl.has_current_resolution(entry)


def test_changed_original_origin_or_prompt_invalidates_decisions(entry, monkeypatch):
    kl.apply_resolution(entry, result(entry))
    entry["ki_pruefhinweis_quellen"][0]["herkunft"]["bericht_basis"] = "another-report"
    assert not kl.has_current_resolution(entry)
    kl.apply_resolution(entry, result(entry))
    monkeypatch.setattr(kl.prompts, "prompt_fingerprint", lambda keys: "updated-prompt")
    assert not kl.has_current_resolution(entry)


def test_final_unanswerable_is_closed_but_cannot_rank_or_gain_eligibility(entry):
    entry.update(eligible=False, hard_excluded=True)
    facts_before = deepcopy(entry["forensik"])
    answer = result(entry, "nicht_beurteilbar", "bewertungsgrundlage_unzureichend")
    kl.apply_resolution(entry, answer)
    assert not entry["review_pending"] and entry["ki_klaerung_gesperrt"]
    assert entry["ki_klaerung_status"] == "nicht_beurteilbar"
    assert entry["rang"] is entry["auswahlwert"] is entry["retdd_perzentil"] is None
    assert entry["eligible"] is False and entry["hard_excluded"] is True
    assert entry["forensik"] == facts_before
    assert kl.has_current_resolution(entry)


@pytest.mark.parametrize("text", ["Hoher DD von 60 Prozent ohne konfigurierte Grenze.",
                                  "Kein Stop-Loss-Nachweis im Positions-Export."])
def test_confirmed_documented_risks_create_no_new_dd_or_stop_gate(entry, text):
    entry["ki_pruefhinweise"][0]["text"] = text
    answer = result(entry, "bestaetigt", "dokumentierter_risikohinweis")
    kl.apply_resolution(entry, answer)
    assert not entry["ki_klaerung_gesperrt"] and not entry["review_pending"]
    assert entry["eligible"] is True and entry["rang"] == 1


def test_confirmed_missing_essential_facts_remain_blocked(entry):
    answer = result(entry, "bestaetigt", "bewertungsgrundlage_unzureichend")
    kl.apply_resolution(entry, answer)
    assert entry["ki_klaerung_status"] == "geklaert" and entry["ki_klaerung_gesperrt"]
    assert entry["rang"] is None


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong_ref", "wrong_id", "wrong_basis", "no_reason", "bad_effect"])
def test_invalid_or_incomplete_adjudication_never_applies(entry, mutation):
    answer = result(entry)
    row = answer["entscheidungen"][0]
    if mutation == "missing": answer["entscheidungen"] = []
    elif mutation == "duplicate": answer["entscheidungen"].append(deepcopy(row))
    elif mutation == "wrong_ref": row["beleg_refs"] = ["invented.fact"]
    elif mutation == "wrong_id": row["hinweis_id"] = "invented-hint"
    elif mutation == "wrong_basis": answer["hinweis_basis"] = "previous-snapshot"
    elif mutation == "no_reason": row["begruendung"] = "  "
    elif mutation == "bad_effect": row.update(entscheidung="nicht_beurteilbar", auswirkung="keine_sperre")
    before = deepcopy(entry)
    with pytest.raises(LlmError):
        kl.apply_resolution(entry, answer)
    assert entry == before


def test_historical_unknown_origin_is_explicit_never_bound_to_current_register(entry):
    entry.pop("ki_pruefhinweis_quellen")
    assert "unbekannt" in kl.hint_records(entry)[0]["herkunft"][0]["status"]


class FakeClient:
    has_key = True
    def __init__(self, *, invalid_first=False):
        self.prompts = []
        self.invalid_first = invalid_first

    def chat(self, prompt, **kwargs):
        self.prompts.append(prompt)
        payload, _ = json.JSONDecoder().raw_decode(prompt.split("## Klärungsauftrag JSON\n", 1)[1])
        resolution = {key: payload[key] for key in ("schema_version", "signal_ref", "hinweis_basis", "trades_sha256")}
        resolution["entscheidungen"] = [{"hinweis_id": hint["hinweis_id"], "entscheidung": "widerlegt",
                                        "auswirkung": "keine_sperre", "bewertungsrelevanz": "pflichtgrundlage",
                                        "begruendung": "Codezahl entfernt ist 0.",
                                        "beleg_refs": ["forensik.stats.duplikate_entfernt"]}
                                       for hint in payload["urspruengliche_hinweise"]]
        if self.invalid_first and len(self.prompts) == 1:
            resolution["entscheidungen"][0]["beleg_refs"] = ["invented.fact"]
        kwargs["meta_out"].update(total_tokens=100)
        return json.dumps({"schema_version": 1, "signal_ref": 1, "strategietyp": "Trendfolge",
                           "strategie_sicherheit": "plausibel", "martingale_einordnung": "kein_beleg",
                           "kurzurteil": "Gezielte Klärung", "staerken": [], "risiken": [],
                           "pruefhinweise": [], "datenluecken": [], "hinweisklaerung": resolution})


def runner(client):
    store = Store()
    if not store.read("clarification"):
        store.create({"id": "clarification"})
    return kl.KlaerungKI(store, "clarification", config.load_settings(), {}, client=client)


def test_budgeted_response_recovery_and_focused_original_evidence(entry):
    entry["ki_pruefhinweise"][0]["beleg_refs"].append(entry["trades_sha256"] + ":1")
    entry["ki_pruefhinweis_quellen"][0]["hinweis"] = deepcopy(entry["ki_pruefhinweise"][0])
    fake = FakeClient()
    answer = runner(fake).klaeren(entry)
    assert answer["gelieferte_trade_refs"] == [entry["trades_sha256"] + ":1"]
    assert '"bericht_basis":"original-short"' in fake.prompts[0]
    assert '"F023":"forensik.stats.duplikate_entfernt"' in fake.prompts[0]
    assert '"zitierte_tradezeilen":1' in fake.prompts[0]
    again = FakeClient()
    assert runner(again).klaeren(entry) == answer
    assert not again.prompts and Store().spent("clarification") == 100
    kl.apply_resolution(entry, answer, trade_refs=answer["gelieferte_trade_refs"])


def test_additional_schema_failure_gets_bounded_diagnostic_repair_and_cache(entry):
    fake = FakeClient(invalid_first=True)
    answer = runner(fake).klaeren(entry)
    assert len(fake.prompts) == 2
    assert "Korrektur einer ungültigen Antwort" in fake.prompts[1]
    assert Store().spent("clarification") == 200
    again = FakeClient()
    assert runner(again).klaeren(entry) == answer
    assert not again.prompts


def test_corrupt_snapshot_stops_before_any_model_request(entry):
    from pathlib import Path
    Path(entry["trades_path"]).write_text("changed", encoding="utf-8")
    fake = FakeClient()
    with pytest.raises(ValueError):
        runner(fake).klaeren(entry)
    assert not fake.prompts


def test_explicit_inability_to_judge_never_clears_ranking(entry):
    answer = kl.blocked_resolution(entry, "Kein vollständiger Brokerbeleg verfügbar; offene Frage nicht entscheidbar.")
    kl.apply_resolution(entry, answer)
    assert entry["ki_klaerung_status"] == "nicht_beurteilbar"
    assert entry["ki_klaerung_gesperrt"] and entry["rang"] is None


@pytest.mark.parametrize("question", [
    "Unbekannte Betreiberidentität gegenüber namensverwandtem Parallelkonto.",
    "Wie wird die Strategie in zukünftigen Marktphasen performen?",
    "SL-Praxis unbekannt, im Export kein Nachweis.",
    "Korrekt annualisierter Jahres-Calmar aus 2,57 Monaten könnte statistisch überschätzt sein.",
])
def test_unknown_additional_fact_stays_unknown_without_a_new_mandatory_gate(entry, question):
    entry["ki_pruefhinweise"][0]["text"] = question
    answer = result(entry, "nicht_beurteilbar", "dokumentierter_risikohinweis",
                    bewertungsrelevanz="zusatzrisiko",
                    begruendung="Das Zusatzfaktum bleibt unbekannt. Die belegte Kontowährung, Kapitalbasis, "
                                "H1-Messung und das erfüllte Zwei-Monats-Gate bleiben unberührt; "
                                "das Laufprofil verlangt keinen SL-Beleg oder Zukunftsnachweis.")
    kl.apply_resolution(entry, answer)
    assert entry["ki_pruefentscheidungen"][0]["entscheidung"] == "nicht_beurteilbar"
    assert entry["ki_klaerung_status"] == "geklaert"
    assert not entry["ki_klaerung_gesperrt"] and not entry["review_pending"]
    assert entry["eligible"] and entry["rang"] == 1


@pytest.mark.parametrize("missing", ["Kontowährung unbelegt", "Erforderliche H1-Kurse fehlen",
                                    "Echte Kapitalbasis unbelegt"])
def test_unknown_mandatory_foundation_cannot_be_declared_a_documented_risk(entry, missing):
    answer = result(entry, "nicht_beurteilbar", "dokumentierter_risikohinweis",
                    bewertungsrelevanz="pflichtgrundlage", begruendung=missing)
    with pytest.raises(LlmError, match="widersprechen"):
        kl.apply_resolution(entry, answer)
    assert entry["review_pending"] and entry["rang"] == 1
    answer["entscheidungen"][0]["auswirkung"] = "bewertungsgrundlage_unzureichend"
    kl.apply_resolution(entry, answer)
    assert entry["ki_klaerung_gesperrt"] and entry["rang"] is None


def test_missing_explicit_relevance_never_releases_unknown_additional_risk(entry):
    answer = result(entry, "nicht_beurteilbar", "dokumentierter_risikohinweis")
    answer["entscheidungen"][0].pop("bewertungsrelevanz")
    with pytest.raises(LlmError):
        kl.apply_resolution(entry, answer)


def test_original_comparison_values_reach_prompt_and_nested_v_evidence_is_valid(entry):
    entry["top5_comparison"] = [{"signal_ref": 1, "retdd_jahr": 3.5, "dauer_monate": 2.57},
                                {"signal_ref": 2, "retdd_jahr": 8, "dauer_monate": 8.31}]
    fake = FakeClient()
    answer = runner(fake).klaeren(entry)
    payload, _ = json.JSONDecoder().raw_decode(fake.prompts[0].split("## Klärungsauftrag JSON\n", 1)[1])
    assert payload["vergleich"] == entry["top5_comparison"]
    assert payload["aktuelles_vergleich_belegregister"]["V001"] == "vergleich[0].retdd_jahr"
    assert "vergleich[1].dauer_monate" in payload["exakte_vergleich_belegpfade"]
    answer["entscheidungen"][0]["beleg_refs"] = ["V001", "vergleich[1].dauer_monate"]
    kl.apply_resolution(entry, answer)
    assert kl.has_current_resolution(entry)
    entry["top5_comparison"][1]["dauer_monate"] = 99
    assert not kl.has_current_resolution(entry)


def test_explicit_comparison_is_bound_and_mismatching_current_ranking_is_rejected(entry):
    original = [{"signal_ref": 2, "retdd_jahr": 99}]
    entry["top5_comparison"] = deepcopy(original)
    fake = FakeClient()
    runner(fake).klaeren(entry, comparison=original)
    with pytest.raises(LlmError, match="ursprünglichen Top-5-Vergleich"):
        runner(fake).klaeren(entry, comparison=[{"signal_ref": 3, "retdd_jahr": 12}])


def test_old_v_alias_remains_bound_to_its_own_report_comparison(entry):
    entry["top5_comparison"] = [{"signal_ref": 1, "retdd_jahr": 3.5}]
    origin = entry["ki_pruefhinweis_quellen"][0]["herkunft"]
    origin.update(bericht_stufe="top5", bericht_basis="old-deep", vergleich=[{"signal_ref": 2, "retdd_jahr": 99}])
    origin["analysegrundlage"]["beleg_register"]["V001"] = "vergleich[0].retdd_jahr"
    fake = FakeClient()
    answer = runner(fake).klaeren(entry)
    payload, _ = json.JSONDecoder().raw_decode(fake.prompts[0].split("## Klärungsauftrag JSON\n", 1)[1])
    assert payload["vergleich"][0]["retdd_jahr"] == 3.5
    assert payload["urspruengliche_hinweise"][0]["herkunft"][0]["vergleich"][0]["retdd_jahr"] == 99
    old_path = "urspruengliche_hinweise[0].herkunft[0].vergleich[0].retdd_jahr"
    answer["entscheidungen"][0]["beleg_refs"] = [old_path]
    kl.apply_resolution(entry, answer)
    assert entry["ki_pruefentscheidungen"][0]["herkunft"][0]["vergleich"][0]["retdd_jahr"] == 99


def test_v_reference_without_supplied_comparison_and_old_schema_are_rejected(entry):
    answer = result(entry, beleg_refs=["V001"])
    with pytest.raises(LlmError, match="Belegreferenz"):
        kl.apply_resolution(entry, answer)
    answer = result(entry)
    answer["schema_version"] = 1
    with pytest.raises(LlmError, match="Schemaversion"):
        kl.apply_resolution(entry, answer)


def test_clarification_prompt_distinguishes_mandatory_foundations_from_extra_uncertainty(entry):
    fake = FakeClient()
    runner(fake).klaeren(entry)
    assert "bewertungsrelevanz" in fake.prompts[0]
    assert "Unbekannte Betreiberfamilie" in fake.prompts[0]
    assert "erfüllten Zwei-Monats-Gate" in fake.prompts[0]
    assert "Pflichtgrundlagen und Grenzen davon unberührt" in fake.prompts[0]
