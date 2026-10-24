"""Final prose corrections retain paid originals and require current proof."""
import copy
import json

import pytest

from mqlkiscanner import abonnenten_analyse_ki as ki, abonnenten_analyse_redaktion as edit, config
from mqlkiscanner.abonnenten_analyse_store import Store
from mqlkiscanner.llm.client import LlmBudgetError, LlmError


@pytest.fixture
def entry():
    body = "# Bericht\n\nDie Kontowährung beruht nur auf Projektkonvention.\n\nBelegte übrige Aussage."
    return {"signal_ref": 1, "id": 1, "quelle": "mql5", "name": "Synthetic",
            "account_currency": "USD", "quellen_stats": {"account_currency": "USD", "stats_quelle": "datenquelle_metrics"},
            "forensik": {"stats": {"net": 100}, "forensics": {"martingale": {"flag": False}}},
            "equity": {"equity_dd_usd": 88.65, "equity_dd_pct_am_usd_max": 23.68},
            "equity_dd_pct": 42.36, "data_basis": "data", "trades_sha256": "snapshot",
            "top5_basis": "final", "top5_comparison": [{"signal_ref": 1, "rang": 1, "retdd_jahr": 3}],
            "rang": 1, "auswahlwert": 80, "retdd_perzentil": 90,
            "top5_befund": {"bericht_markdown": body}, "bericht_markdown": body}


def answer(entry, **changes):
    return {"schema_version": 1, "signal_ref": 1, "pruefbasis": edit.review_basis(entry),
            "original_bericht_sha256": ki.digest(entry["top5_befund"]["bericht_markdown"]),
            "korrekturen": [{"alt": "Die Kontowährung beruht nur auf Projektkonvention.",
                             "neu": "USD ist durch die gelieferten Quellenmetrics belegt; die CSV enthält keine Währung.",
                             "begruendung": "Expliziter Quellenbeleg vorhanden.",
                             "beleg_refs": ["berichtsfakten.kontowaehrung_quellenbeleg"]}],
            "offene_pflichtfragen": [], **changes}


def test_correction_is_audited_original_answer_unchanged_and_scope_unverified(entry):
    original = copy.deepcopy(entry["top5_befund"])
    edit.apply_review(entry, answer(entry))
    assert entry["top5_befund"] == original
    assert entry["bericht_markdown_original"] == original["bericht_markdown"]
    assert "Quellenmetrics belegt" in entry["bericht_markdown"]
    assert "globale Top-200-Abdeckung" in entry["bericht_markdown"]
    assert "unbestätigt" in entry["bericht_markdown"]
    assert entry["bericht_redaktion_status"] == "geprueft" and edit.has_current_review(entry)


@pytest.mark.parametrize("change", ["data", "comparison", "body", "source_proof"])
def test_changed_facts_original_comparison_and_edited_body_invalidate_review(entry, change):
    edit.apply_review(entry, answer(entry))
    if change == "data":
        entry["data_basis"] = "new"
    elif change == "comparison":
        entry["top5_comparison"][0]["retdd_jahr"] = 9
    elif change == "body":
        entry["bericht_markdown"] += " Unevidenced added claim."
    else:
        entry["quellen_stats"]["account_currency"] = "EUR"
    assert not edit.has_current_review(entry)


def test_derived_display_rank_does_not_reopen_finished_editorial_check(entry):
    edit.apply_review(entry, answer(entry))
    entry.update(rang=None, auswahlwert=None, retdd_perzentil=None, abo_zufluss_perzentil=None)
    assert edit.has_current_review(entry)


def test_real_essential_question_preserves_terminal_block_across_resume(entry):
    result = answer(entry, offene_pflichtfragen=[{"text": "Kapitalnachweis widersprüchlich",
                    "begruendung": "Nicht durch vorliegende Belege entscheidbar.",
                    "beleg_refs": ["berichtsfakten.kapitalbasis_usd"]}])
    edit.apply_review(entry, result)
    assert entry["ki_klaerung_gesperrt"] and entry["bericht_redaktion_status"] == "unbeurteilbar"
    assert not edit.has_current_review(entry)
    assert edit.has_current_review(entry, allow_blocked=True)


@pytest.mark.parametrize("fault", ["wrong_basis", "missing_reference", "nonunique", "overlap", "boolean_schema"])
def test_unverifiable_or_ambiguous_replacements_rejected(entry, fault):
    result = answer(entry)
    if fault == "wrong_basis":
        result["pruefbasis"] = "foreign"
    elif fault == "missing_reference":
        result["korrekturen"][0]["beleg_refs"] = ["invented.value"]
    elif fault == "nonunique":
        result["korrekturen"][0]["alt"] = "does not exist"
    elif fault == "overlap":
        result["korrekturen"].append(copy.deepcopy(result["korrekturen"][0]))
    else:
        result["schema_version"] = True
    with pytest.raises(LlmError):
        edit.apply_review(entry, result)
    assert not entry.get("bericht_redaktion_basis")


class Client:
    has_key = True
    def __init__(self, result):
        self.result, self.requests = result, []
    def chat(self, prompt, **kwargs):
        self.requests.append((prompt, kwargs))
        if isinstance(self.result, Exception):
            raise self.result
        kwargs["meta_out"].update(total_tokens=100)
        return json.dumps({"signal_ref": 1, "strategietyp": "Redaktion", "strategie_sicherheit": "belegt",
                           "martingale_einordnung": "kein_beleg", "kurzurteil": "Faktenprüfung",
                           "staerken": [], "risiken": [], "pruefhinweise": [], "datenluecken": [],
                           "berichtpruefung": self.result})


def test_fact_editor_uses_low_reasoning_existing_budget_and_durable_response_cache(entry):
    store = Store()
    store.create({"id": "job"})
    client = Client(answer(entry))
    editor = edit.BerichtRedaktionKI(store, "job", config.load_settings(), {}, client=client)
    result = editor.pruefen(entry)
    assert result["korrekturen"]
    prompt, request = client.requests[0]
    assert request["reasoning_effort"] == "low" and request["max_tokens"] == 16384
    assert "originaler_vergleich" in prompt and "kontowaehrung_quellenbeleg" in prompt
    replay = Client(LlmError("must not call model"))
    edit.BerichtRedaktionKI(store, "job", config.load_settings(), {}, client=replay).pruefen(entry)
    assert not replay.requests and store.spent("job") == 100


def test_budget_error_remains_recoverable_without_editorial_clearance(entry):
    store = Store()
    store.create({"id": "job"})
    editor = edit.BerichtRedaktionKI(store, "job", config.load_settings(), {}, client=Client(LlmBudgetError("limit")))
    with pytest.raises(LlmBudgetError):
        editor.pruefen(entry)
    assert not entry.get("bericht_redaktion_status")
