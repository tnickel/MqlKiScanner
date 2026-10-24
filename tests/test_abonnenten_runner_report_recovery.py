"""Original comparison recovery and mandatory editorial finish stay independent."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from mqlkiscanner import abonnenten_analyse as runner, abonnenten_analyse_klaerung as clarification
from mqlkiscanner import abonnenten_analyse_redaktion as redaction, config, db
from mqlkiscanner.abonnenten_analyse_store import Store
from mqlkiscanner.llm.client import LlmBudgetError


def row(ref, **extra):
    return {"signal_ref": ref, "id": 100+ref, "quelle": "mql5", "quellen_uid": "mql-source",
            "name": f"Frozen {ref}", "eligible": True, "data_done": True, "data_basis": "frozen-data",
            "trades_path": "mock-verified.csv", "trades_sha256": "mock-sha", "trades": 50,
            "dauer_monate": 8, "retdd_jahr": 10-ref, "equity_dd_pct": 20,
            "abo_perzentil": 100-ref, "abonnenten": 100-ref, "cagr_jahr_pct": 100,
            "account_currency": "USD", "kapitalbasis_usd": 100,
            "quellen_stats": {"account_currency": "USD", "stats_quelle": "datenquelle_metrics"},
            "forensik": {"stats": {"net": 100}, "forensics": {"martingale": {"flag": False}}},
            "equity": {"status": "ok", "verlaesslich": True}, **extra}


@pytest.fixture
def report_env(monkeypatch, tmp_path):
    store = Store()
    run = {"id": "report-recovery", "status": "angehalten", "quellen": ["mql5"],
           "snapshot_quellen": {"mql5": {"status": "fertig"}}, "retdd_gewicht": 30,
           "dd_grenze": None, "kurztest_optional": True, "endpruefung_auto": True,
           "auswahl_modus": "abo_bestand_retdd_v1", "logs": []}
    store.create(run)
    entries = [row(ref) for ref in range(1, 8)]
    for entry in entries:
        store.save_task(run["id"], entry)
    events = []
    controls = {"deep_hint": set(), "clarification_block": set(), "editorial_block": set(),
                "editorial_budget": None}

    class AI:
        def __init__(self, *args, **kwargs):
            self.client = SimpleNamespace(has_key=True)
        def analyse(self, entry, *, deep=False, comparison=None):
            assert deep
            events.append(("deep", entry["signal_ref"]))
            generation = sum(event == ("deep", entry["signal_ref"]) for event in events)
            return {"bericht_markdown": f"# Original {entry['signal_ref']}\nUSD only assumption.\nGeneration {generation}.",
                    "neue_pruefhinweise": ([{"text": "Original comparison requires clarification",
                                               "beleg_refs": ["V001"]}]
                                            if entry["signal_ref"] in controls["deep_hint"] else []),
                    "analysegrundlage": {"beleg_register": {"V001": "vergleich[0].retdd_jahr"}}}

    class Reviewer:
        def __init__(self, *args, **kwargs):
            self.client = SimpleNamespace(has_key=True)
        def klaeren(self, entry):
            events.append(("clarify", entry["signal_ref"]))
            if entry.get("top5_befund"):
                assert entry.get("top5_comparison"), "Original V-context must precede clarification"
                assert entry["top5_comparison_basis"] == entry["top5_basis"]
                origins = entry.get("ki_pruefhinweis_quellen") or []
                assert any(record["herkunft"].get("vergleich") == entry["top5_comparison"]
                           for record in origins if record["herkunft"].get("bericht_stufe") == "top5")
            answer = clarification.blocked_resolution(entry, "Necessary measurement is not available.")
            if entry["signal_ref"] not in controls["clarification_block"]:
                for decision in answer["entscheidungen"]:
                    decision.update(entscheidung="bestaetigt", bewertungsrelevanz="zusatzrisiko",
                                    auswirkung="dokumentierter_risikohinweis",
                                    begruendung="Documented sampling limit; no additional risk threshold.")
            return answer

    class Editor:
        def __init__(self, *args, **kwargs):
            self.client = SimpleNamespace(has_key=True)
        def pruefen(self, entry):
            events.append(("edit", entry["signal_ref"]))
            if controls["editorial_budget"] == entry["signal_ref"]:
                raise LlmBudgetError("Editorial synthetic budget limit")
            original = entry["top5_befund"]["bericht_markdown"]
            return {"schema_version": redaction.REVIEW_VERSION, "signal_ref": entry["signal_ref"],
                    "pruefbasis": redaction.review_basis(entry),
                    "original_bericht_sha256": runner.digest(original),
                    "korrekturen": [{"alt": "USD only assumption.", "neu": "USD verified by source metadata.",
                                     "begruendung": "The source explicitly supplies USD.",
                                     "beleg_refs": ["berichtsfakten.kontowaehrung_quellenbeleg"]}],
                    "offene_pflichtfragen": ([{"text": "Essential account proof remains unknown.",
                                               "begruendung": "The supplied account scope cannot establish it.",
                                               "beleg_refs": ["equity.status"]}]
                                              if entry["signal_ref"] in controls["editorial_block"] else [])}

    def pdf(entry, run_id):
        assert redaction.has_current_review(entry)
        assert entry["bericht_redaktion_status"] == "geprueft"
        events.append(("pdf", entry["signal_ref"]))
        path = tmp_path/f"final-{entry['signal_ref']}.pdf"
        path.write_bytes(b"%PDF-verified synthetic document")
        return str(path)

    monkeypatch.setattr(runner, "AnalyseKI", AI)
    monkeypatch.setattr(clarification, "KlaerungKI", Reviewer)
    monkeypatch.setattr(redaction, "BerichtRedaktionKI", Editor)
    monkeypatch.setattr(runner, "report_pdf", pdf)
    monkeypatch.setattr(db, "verify_trade_file", lambda *args: None)
    return store, run, entries, events, controls


def execute(env):
    store, run, entries, _, _ = env
    runner._execute_optional_finalists(store, run["id"], run, entries, config.load_settings(),
                                      runner._profile(run), lambda text: None, lambda: False)


def test_deep_original_comparison_and_editorial_review_precede_pdf(report_env):
    store, run, entries, events, controls = report_env
    controls["deep_hint"].add(1)
    execute(report_env)
    first = entries[0]
    assert events[:4] == [("deep", 1), ("clarify", 1), ("edit", 1), ("pdf", 1)]
    assert "USD only assumption." in first["top5_befund"]["bericht_markdown"]
    assert "USD only assumption." in first["bericht_markdown_original"]
    assert "USD verified by source metadata." in first["bericht_markdown"]
    assert "USD only assumption." not in first["bericht_markdown"]
    assert first["top5_comparison"][0]["signal_ref"] == 1
    assert store.read(run["id"])["workflow_abgeschlossen"] is True
    assert runner._final_report_complete(first, first["top5_basis"])
    assert redaction.has_current_review(first)


def test_editorial_only_upgrade_reuses_paid_deep_response_and_exact_hash(report_env):
    _, _, entries, events, _ = report_env
    execute(report_env)
    original_deep_count = sum(kind == "deep" for kind, _ in events)
    for field in runner._REDACTION_FIELDS:
        entries[0].pop(field, None)
    entries[0]["bericht_markdown"] = entries[0]["top5_befund"]["bericht_markdown"]
    execute(report_env)
    assert sum(kind == "deep" for kind, _ in events) == original_deep_count
    assert events.count(("edit", 1)) == 2 and events.count(("pdf", 1)) == 2


def test_cached_original_comparison_is_recovered_before_old_hint_clarification(report_env):
    _, run, entries, events, controls = report_env
    controls["deep_hint"].add(1)
    execute(report_env)
    entry = entries[0]
    old_basis = entry["top5_basis"]
    entry.pop("top5_comparison")
    entry.pop("top5_comparison_basis")
    for key in ("ki_pruefentscheidungen", "ki_klaerung_basis", "ki_klaerung_status"):
        entry.pop(key, None)
    entry["review_pending"] = True
    execute(report_env)
    assert entry["top5_basis"] == old_basis
    assert events.count(("deep", 1)) == 1
    assert events.count(("clarify", 1)) == 2
    assert entry["top5_comparison"][0]["signal_ref"] == 1


def test_historical_transport_error_is_cleared_when_final_clarification_blocks(report_env):
    _, _, entries, events, controls = report_env
    entries[0].update(status="ki_fehler", ki_fehler="Old HTTP timeout", endpruefung_fehler="Old timeout")
    controls["deep_hint"].add(1)
    controls["clarification_block"].add(1)
    execute(report_env)
    entry = entries[0]
    assert entry["endpruefung_status"] == "nicht_beurteilbar"
    assert entry["ki_klaerung_gesperrt"] and not entry["review_pending"]
    assert entry["ki_fehler"] == entry["endpruefung_fehler"] == ""
    assert entry["status"] == "fertig"
    assert ("edit", 1) not in events and ("pdf", 1) not in events


def test_current_terminal_editorial_block_survives_resume_without_reanalysis(report_env):
    _, _, entries, events, controls = report_env
    controls["editorial_block"].add(1)
    execute(report_env)
    entry = entries[0]
    assert entry["ki_klaerung_gesperrt"] and entry["endpruefung_status"] == "nicht_beurteilbar"
    assert not redaction.has_current_review(entry)
    assert redaction.has_current_review(entry, allow_blocked=True)
    assert not runner._final_report_complete(entry, entry["top5_basis"])
    execute(report_env)
    assert events.count(("deep", 1)) == events.count(("edit", 1)) == 1
    assert entry["ki_klaerung_gesperrt"] and entry["rang"] is None


def test_positive_clarification_does_not_preserve_stale_negative_editorial_decision(report_env):
    _, _, entries, events, controls = report_env
    controls["deep_hint"].add(1)
    execute(report_env)
    entry = entries[0]
    assert clarification.has_current_resolution(entry)
    assert all(row["auswirkung"] == "dokumentierter_risikohinweis"
               for row in entry["ki_pruefentscheidungen"])
    # Simulate a prior editorial schema veto which the current validator can
    # no longer accept. The positive substantive decision remains unchanged.
    entry["bericht_redaktion_result"]["schema_version"] = -1
    entry.update(bericht_redaktion_status="unbeurteilbar", ki_klaerung_gesperrt=True,
                 endpruefung_status="nicht_beurteilbar")
    assert not redaction.has_current_review(entry, allow_blocked=True)
    assert not runner._sync_final_blocks(entry, redaction=redaction)
    assert entry["ki_klaerung_gesperrt"] is False
    assert entry["endpruefung_status"] == "wartet" and entry["eligible"] is True
    assert not runner._final_report_complete(entry, entry["top5_basis"])
    execute(report_env)
    assert events.count(("deep", 1)) == 1, "A stale editorial veto must not repeat the paid deep report"
    assert events.count(("edit", 1)) == 2
    assert runner._final_report_complete(entry, entry["top5_basis"])


def test_current_negative_clarification_restores_a_stale_false_block_flag(report_env):
    _, _, entries, _, controls = report_env
    controls["deep_hint"].add(1)
    controls["clarification_block"].add(1)
    execute(report_env)
    entry = entries[0]
    assert clarification.has_current_resolution(entry)
    entry.update(ki_klaerung_gesperrt=False, rang=1, auswahlwert=100, retdd_perzentil=100)
    assert runner._sync_final_blocks(entry, redaction=redaction)
    assert entry["ki_klaerung_gesperrt"] is True
    assert entry["rang"] is entry["auswahlwert"] is entry["retdd_perzentil"] is None


def test_editorial_budget_failure_keeps_original_paid_report_resumable(report_env):
    _, _, entries, events, controls = report_env
    controls["editorial_budget"] = 1
    with pytest.raises(LlmBudgetError):
        execute(report_env)
    assert entries[0]["top5_befund"]["bericht_markdown"]
    assert entries[0]["top5_comparison"] and entries[0]["endpruefung_status"] == "wartet"
    assert not entries[0].get("ki_klaerung_gesperrt")
    assert ("pdf", 1) not in events
    controls["editorial_budget"] = None
    execute(report_env)
    assert events.count(("deep", 1)) == 1
    assert entries[0]["endpruefung_status"] == "abgeschlossen"


def test_new_deep_basis_archives_and_resets_previous_editorial_clearance(report_env, monkeypatch):
    _, _, entries, events, _ = report_env
    execute(report_env)
    old_basis = entries[0]["bericht_redaktion_basis"]
    original_fingerprint = runner.prompts.prompt_fingerprint
    monkeypatch.setattr(runner.prompts, "prompt_fingerprint", lambda keys:
                        "updated-deep-template" if keys == ("abonnenten_top5",) else original_fingerprint(keys))
    execute(report_env)
    assert events.count(("deep", 1)) == events.count(("edit", 1)) == 2
    assert entries[0]["bericht_redaktion_basis"] != old_basis
    assert entries[0]["bericht_redaktion_history"][-1]["bericht_redaktion_basis"] == old_basis
    assert "Generation 2." in entries[0]["top5_befund"]["bericht_markdown"]
    assert "Generation 2." in entries[0]["bericht_markdown_original"]
    assert set(runner._REDACTION_FIELDS) <= set(runner._FINAL_REVIEW_FIELDS)


def test_editorial_decisions_are_bound_to_pdf_fingerprint(report_env):
    _, _, entries, _, _ = report_env
    execute(report_env)
    entry = entries[0]
    assert runner._final_report_complete(entry, entry["top5_basis"])
    entry["bericht_redaktion_korrekturen"][0]["begruendung"] += " Tampered decision."
    assert not runner._final_report_complete(entry, entry["top5_basis"])


def test_original_hint_comparison_keeps_old_values_after_new_ranking(report_env):
    _, _, entries, _, _ = report_env
    entry = entries[0]
    hint = {"text": "Original V001 must retain its context", "beleg_refs": ["V001"]}
    original_comparison = [{"signal_ref": 1, "retdd_jahr": 9}]
    entry.update(top5_basis="original-basis", top5_comparison=deepcopy(original_comparison),
                 top5_comparison_basis="original-basis",
                 top5_befund={"neue_pruefhinweise": [hint], "analysegrundlage": {"beleg_register": {
                     "V001": "vergleich[0].retdd_jahr"}}})
    runner._record_hint_origins(entry, [hint], stage="top5")
    entry.update(top5_basis="new-basis", top5_comparison=[{"signal_ref": 2, "retdd_jahr": 777}],
                 top5_comparison_basis="new-basis")
    runner._record_hint_origins(entry, [hint], stage="top5")
    records = entry["ki_pruefhinweis_quellen"]
    assert records[0]["herkunft"]["vergleich"] == original_comparison
    assert records[0]["herkunft"]["bericht_basis"] == "original-basis"
    assert records[1]["herkunft"]["vergleich"][0]["retdd_jahr"] == 777


def test_historical_mask_recovery_requires_exact_v3_hash_and_never_mutates(report_env):
    _, run, entries, _, _ = report_env
    settings, profile = config.load_settings(), runner._profile(run)
    original_rows = deepcopy(entries)
    original_comparison = runner._optional_comparison(runner.rank_entries(
        original_rows, run["retdd_gewicht"], kurztest_optional=True, auswahl_modus=run["auswahl_modus"]))
    target = entries[1]
    target["top5_basis"] = runner.top5_basis(target, profile, settings, original_comparison)
    entries[0]["ki_klaerung_gesperrt"] = True
    before = deepcopy(entries)
    recovered = runner.reconstruct_top5_comparison(target, entries, run, settings,
                                                   block_masks=[{1}, set()])
    assert recovered == original_comparison and entries == before
    with pytest.raises(ValueError, match="nicht eindeutig"):
        runner.reconstruct_top5_comparison(target, entries, run, settings, block_masks=[{1}])


@pytest.mark.parametrize("change", ["sha", "profile", "unknown_mask"])
def test_original_comparison_recovery_rejects_changed_basis_or_foreign_masks(report_env, change):
    _, run, entries, _, _ = report_env
    settings = config.load_settings()
    comparison = runner._optional_comparison(runner.rank_entries(
        deepcopy(entries), run["retdd_gewicht"], kurztest_optional=True))
    target = entries[0]
    target["top5_basis"] = runner.top5_basis(target, runner._profile(run), settings, comparison)
    mask = set()
    if change == "sha":
        target["trades_sha256"] = "different-snapshot"
    elif change == "profile":
        run["retdd_gewicht"] = 99
    else:
        mask = {999999}
    with pytest.raises(ValueError):
        runner.reconstruct_top5_comparison(target, entries, run, settings, block_masks=[mask])
