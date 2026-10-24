"""Optional add-on KI, frozen inflow scaling and verified finalist completion."""
from copy import deepcopy
import hashlib

import pytest

from mqlkiscanner import abonnenten_analyse as analyse, abonnenten_analyse_klaerung as clarification, config, db
from mqlkiscanner import abonnenten_analyse_redaktion as redaction
from mqlkiscanner.abonnenten_analyse_store import Store
from mqlkiscanner.llm.client import LlmBudgetError


def ranked_row(ref, source="mql5", subscribers=50, delta=5, **changes):
    return {"signal_ref": ref, "id": ref, "quelle": source, "quellen_uid": source,
            "name": f"Test {ref}", "eligible": True, "retdd_jahr": 3,
            "abo_perzentil": 50, "abonnenten": subscribers, "dauer_monate": 4,
            "abo_trend": {"verified": True, "delta_7": delta, "coverage": {"7_tage": True}},
            **changes}


def test_equal_relative_source_mean_growth_is_equal_not_large_broker_preference():
    entries = [ranked_row(1, "pelik", 1000, 100), ranked_row(2, "mql5", 50, 5),
               ranked_row(3, "pelik", 1000, 100, eligible=False),
               ranked_row(4, "mql5", 50, 5, eligible=False)]
    ranked = analyse.rank_entries(entries, 30, kurztest_optional=True, auswahl_modus="abo_zufluss_retdd_v1")
    assert len(ranked) == 2
    assert ranked[0]["abo_zufluss_skaliert"] == ranked[1]["abo_zufluss_skaliert"] == .1
    assert ranked[0]["abo_zufluss_perzentil"] == ranked[1]["abo_zufluss_perzentil"] == 50
    assert entries[0]["abo_quellen_referenz_n"] == entries[1]["abo_quellen_referenz_n"] == 2
    assert ranked[0]["auswahlwert"] == ranked[1]["auswahlwert"]


def test_inflow_unknown_is_never_zero_or_stock_fallback_and_negatives_are_real():
    entries = [ranked_row(1, delta=0), ranked_row(2, delta=-5),
               ranked_row(3, delta=None), ranked_row(4, delta=999,
                    abo_trend={"verified": False, "delta_7": 999})]
    ranked = analyse.rank_entries(entries, 30, kurztest_optional=True, auswahl_modus="abo_zufluss_retdd_v1")
    assert [entry["id"] for entry in ranked] == [1, 2]
    assert all(entry["rang"] is None for entry in entries[2:])
    assert all(entry["abo_zufluss_skaliert"] is None for entry in entries[2:])


def test_optional_short_hints_are_addons_but_final_foundation_blocks_still_apply():
    entries = [ranked_row(1, review_pending=True), ranked_row(2, ki_klaerung_gesperrt=True)]
    assert [entry["id"] for entry in analyse.rank_entries(entries, 30, kurztest_optional=True)] == [1]
    assert not analyse.rank_entries(entries, 30)


def test_profit_tiebreak_prefers_capital_normalised_return_before_dollar_profit():
    entries = [ranked_row(1, cagr_jahr_pct=10, forensik={"stats": {"net": 1_000_000}}),
               ranked_row(2, cagr_jahr_pct=20, forensik={"stats": {"net": 100}})]
    ranked = analyse.rank_entries(entries, 30, kurztest_optional=True, auswahl_modus="abo_zufluss_retdd_v1")
    assert [entry["id"] for entry in ranked] == [2, 1]


@pytest.fixture
def optional_run(monkeypatch, tmp_path):
    from mqlkiscanner import abonnenten_analyse_trend as trend
    store = Store()
    run = {"id": "optional", "status": "angehalten", "quellen": ["mql5"], "snapshot_quellen": {
        "mql5": {"status": "fertig", "stand": "2026-10-23T16:11:29+02:00"}},
        "retdd_gewicht": 30, "dd_grenze": None, "kurztest_optional": True, "endpruefung_auto": True,
        "auswahl_modus": "abo_zufluss_retdd_v1", "logs": []}
    store.create(run)
    path = tmp_path / "snapshot.csv"
    path.write_bytes(b"synthetic,not,parsed\n")
    entries = [ranked_row(ref, delta=10-ref, data_done=True, data_basis="data", trades=50,
                          trades_path=str(path), trades_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                          forensik={"stats": {"net": 100-ref}, "forensics": {"martingale": {"flag": False}}},
                          equity={"status": "ok", "verlaesslich": True}) for ref in range(1, 8)]
    for entry in entries:
        store.save_task(run["id"], entry)
    calls = {"deep": [], "short": [], "review": [], "payloads": [], "clients": [], "review_clients": []}
    control = {"unknown": set(), "budget": None, "deep_hint": set(), "stopped": False, "timeout": None}

    class AI:
        def __init__(self, *args, **kwargs):
            self.client = type("Client", (), {"has_key": True})()
            if control["timeout"] is not None:
                self.client.timeout = control["timeout"]
            calls["clients"].append(self.client)
        def analyse(self, entry, *, deep=False, comparison=None):
            assert deep, "Optional add-on shorttests must not precede final review"
            calls["deep"].append(entry["id"])
            calls["payloads"].append(deepcopy(entry))
            if control["budget"] == entry["id"]:
                raise LlmBudgetError("test-budget")
            return {"bericht_markdown": "# Full final trade analysis", "neue_pruefhinweise": (
                [{"text": "Neue belegte Grundlage prüfen", "beleg_refs": ["equity.status"]}]
                if entry["id"] in control["deep_hint"] else [])}

    class Reviewer:
        def __init__(self, *args, **kwargs):
            self.client = type("Client", (), {"has_key": True})()
            calls["review_clients"].append(self.client)
        def klaeren(self, entry):
            calls["review"].append(entry["id"])
            answer = clarification.blocked_resolution(entry, "Fehlende notwendige Brokergrundlage")
            if entry["id"] not in control["unknown"]:
                for row in answer["entscheidungen"]:
                    row.update(entscheidung="bestaetigt", auswirkung="dokumentierter_risikohinweis",
                               bewertungsrelevanz="zusatzrisiko",
                               begruendung="Bestehende Messgrenze dokumentiert; keine zusätzliche Freigabeschranke.")
            return answer

    class Editor:
        def __init__(self, *args, **kwargs): self.client = type("Client", (), {"has_key": True})()
        def pruefen(self, entry):
            # This fixture's report contains no factual numeric claims. Its
            # editorial pass still uses the real validation/application path.
            return {"schema_version": redaction.REVIEW_VERSION, "signal_ref": entry["signal_ref"],
                    "pruefbasis": redaction.review_basis(entry),
                    "original_bericht_sha256": analyse.digest(entry["top5_befund"]["bericht_markdown"]),
                    "korrekturen": [], "offene_pflichtfragen": []}

    def pdf(entry, run_id):
        assert entry.get("rang") is not None, "PDF must retain current code ranking after hint review"
        target = tmp_path / f"{entry['id']}.pdf"
        target.write_bytes(b"%PDF-synthetic final report")
        return str(target)

    monkeypatch.setattr(analyse, "AnalyseKI", AI)
    monkeypatch.setattr(clarification, "KlaerungKI", Reviewer)
    monkeypatch.setattr(redaction, "BerichtRedaktionKI", Editor)
    monkeypatch.setattr(analyse, "report_pdf", pdf)
    monkeypatch.setattr(db, "verify_trade_file", lambda *args: None)
    monkeypatch.setattr(trend, "freeze_trends", lambda *args: None)
    return store, run, entries, calls, control


def execute_optional(fixture):
    store, run, entries, calls, control = fixture
    settings = config.load_settings()
    analyse._execute_optional_finalists(store, run["id"], run, entries, settings, analyse._profile(run),
                                       lambda message: store.log(run["id"], message), lambda: control["stopped"])


def test_missing_short_is_optional_full_top5_and_pdf_finish_then_resume_reuses(optional_run):
    store, run, entries, calls, _ = optional_run
    entries[0].update(kurztest={"pruefhinweise": [], "kurzurteil": "STALE"}, kurz_basis="outdated")
    execute_optional(optional_run)
    assert calls["deep"] == [1, 2, 3, 4, 5]
    assert "kurztest" not in calls["payloads"][0]
    assert store.read(run["id"])["workflow_abgeschlossen"]
    assert all(entry["endpruefung_status"] == "abgeschlossen" for entry in entries[:5])
    assert store.read(run["id"])["abo_quellen_referenz"]["mql5"]["bekannte_positive_n"] == 7
    assert "kein Plattformvollmittel" in entries[0]["abo_quellen_referenz_scope"]
    execute_optional(optional_run)
    assert calls["deep"] == [1, 2, 3, 4, 5]


def test_unanswerable_final_hint_promotes_sixth_and_clears_no_hard_facts(optional_run):
    store, run, entries, calls, control = optional_run
    entries[0]["ki_pruefhinweise"] = [{"text": "Notwendige Messgrundlage fehlt", "beleg_refs": ["equity.status"]}]
    control["unknown"].add(1)
    control["deep_hint"].add(2)
    execute_optional(optional_run)
    assert entries[0]["eligible"] and not entries[0].get("hard_excluded")
    assert entries[0]["ki_klaerung_gesperrt"] and not entries[0]["review_pending"]
    assert entries[0]["rang"] is None and entries[0]["endpruefung_status"] == "nicht_beurteilbar"
    assert calls["deep"] == [2, 3, 4, 5, 6]
    assert 2 in calls["review"]
    assert all(entry["endpruefung_status"] == "abgeschlossen" for entry in entries[1:6])
    assert store.read(run["id"])["workflow_abgeschlossen"]


def test_budget_exception_propagates_without_turning_it_into_unanswerable(optional_run):
    store, run, entries, _, control = optional_run
    control["budget"] = 1
    with pytest.raises(LlmBudgetError):
        execute_optional(optional_run)
    assert entries[0]["endpruefung_status"] == "wartet"
    assert not entries[0].get("ki_klaerung_gesperrt")
    assert not entries[0].get("ki_pruefentscheidungen")


def test_real_data_gaps_do_not_prevent_workflow_end_but_remain_partial(optional_run):
    store, run, entries, _, _ = optional_run
    entries[-1].update(data_done=False, eligible=False)
    execute_optional(optional_run)
    result = store.read(run["id"])
    assert result["workflow_abgeschlossen"] is True
    assert result["status"] == "teilweise" and result["daten_vollstaendig"] is False


def test_empty_or_short_candidate_list_never_claims_five_complete_final_reports(optional_run):
    store, run, entries, calls, _ = optional_run
    for entry in entries:
        entry["abo_trend"] = {"verified": False, "delta_7": None}
    execute_optional(optional_run)
    assert not calls["deep"]
    assert store.read(run["id"])["workflow_abgeschlossen"] is False
    assert store.read(run["id"])["status"] == "teilweise"
    assert "nur 0 belegte Kandidaten" in store.read(run["id"])["detail"]


def test_irrelevant_excluded_source_without_trends_does_not_invalidate_five_finalists(optional_run):
    store, run, entries, _, _ = optional_run
    entries[-1].update(eligible=False, data_done=True, abo_trend={"verified": False, "delta_7": None})
    execute_optional(optional_run)
    assert store.read(run["id"])["workflow_abgeschlossen"] is True
    assert store.read(run["id"])["daten_vollstaendig"] is True


def test_changed_frozen_abonnenten_membership_cannot_silently_replace_source_mean(optional_run):
    execute_optional(optional_run)
    optional_run[2][0]["abonnenten"] = 99999
    with pytest.raises(ValueError, match="ursprünglichen Auswahl"):
        execute_optional(optional_run)


def test_top5_basis_covers_trade_data_profile_trend_and_comparison(optional_run):
    _, run, entries, _, _ = optional_run
    entry = entries[0]
    profile, settings, comparison = analyse._profile(run), config.load_settings(), [{"signal_ref": 1}]
    original = analyse.top5_basis(entry, profile, settings, comparison)
    for field, changed in [("data_basis", "new"), ("trades_sha256", "new"),
                           ("abo_trend", {"verified": True, "delta_7": 999})]:
        candidate = {**entry, field: changed}
        assert analyse.top5_basis(candidate, profile, settings, comparison) != original
    assert analyse.top5_basis(entry, {**profile, "retdd_gewicht": 99}, settings, comparison) != original
    assert analyse.top5_basis(entry, profile, settings, [{"signal_ref": 2}]) != original


def test_state_recomputes_coherent_live_ranks_without_changing_persistence(optional_run):
    store, run, entries, _, _ = optional_run
    # Simulate the worker having saved a newly ranked finalist while remaining
    # task rows still carry the previous stock-based order.
    entries[0]["rang"] = 3
    entries[1]["rang"] = 1
    entries[2]["rang"] = 2
    entries[3].update(ki_klaerung_gesperrt=True, rang=4)
    for entry in entries:
        store.save_task(run["id"], entry)
    before_run, before_tasks = store.read(run["id"]), store.tasks(run["id"])
    before_bytes = store.path.read_bytes()
    state = analyse.zustand(run["id"])
    ranked = [entry for entry in state["entries"] if entry.get("rang")]
    assert [entry["id"] for entry in ranked] == [1, 2, 3, 5, 6, 7]
    assert [entry["rang"] for entry in ranked] == list(range(1, 7))
    assert next(entry for entry in state["entries"] if entry["id"] == 4)["rang"] is None
    assert store.read(run["id"]) == before_run
    assert store.tasks(run["id"]) == before_tasks
    assert store.path.read_bytes() == before_bytes


def test_legacy_state_keeps_persisted_order_unchanged(optional_run):
    store, run, entries, _, _ = optional_run
    store.update(run["id"], auswahl_modus="abo_bestand_retdd_v1", kurztest_optional=False)
    for index, entry in enumerate(reversed(entries), 1):
        entry["rang"] = index
        store.save_task(run["id"], entry)
    state = analyse.zustand(run["id"])
    assert [entry["id"] for entry in state["entries"]] == list(range(7, 0, -1))


@pytest.mark.parametrize("configured,expected", [(None, 900), (300, 900), (1200, 1200)])
def test_only_final_client_gets_minimum_timeout_and_cooperative_single_slot(optional_run, configured, expected):
    _, _, entries, calls, control = optional_run
    entries[0]["ki_pruefhinweise"] = [{"text": "Bestätigtes Risiko", "beleg_refs": ["equity.status"]}]
    control["timeout"] = configured
    execute_optional(optional_run)
    client = calls["clients"][0]
    assert client.timeout == expected
    assert client.request_gate.status()["requested_limit"] == 1
    assert calls["review_clients"][0].request_gate is client.request_gate
    control["stopped"] = True
    with pytest.raises(analyse.Angehalten):
        client.request_gate.check_stop()
    with pytest.raises(analyse.Angehalten):
        with client.request_gate.slot():
            pytest.fail("A stopped final workflow must not admit another HTTP request")


def test_final_basis_explicitly_binds_the_output_contract(optional_run, monkeypatch):
    _, run, entries, _, _ = optional_run
    captured = []
    original_digest = analyse.digest
    monkeypatch.setattr(analyse, "digest", lambda value: (captured.append(value), original_digest(value))[1])
    analyse.top5_basis(entries[0], analyse._profile(run), config.load_settings(), [])
    contract = next(value for value in captured if isinstance(value, dict) and "output_contract" in value)
    assert contract["version"] == 3
    assert contract["output_contract"] == {"max_tokens": 32768, "reasoning_effort": "high"}


def test_legacy_research_client_timeout_and_gate_are_unchanged(monkeypatch):
    from mqlkiscanner import abonnenten_analyse_daten as data_module
    settings = config.load_settings()
    store = Store()
    run = {"id": "legacy-client", "status": "geplant", "quellen": ["robo"], "retdd_gewicht": 70,
           "dd_grenze": None, "snapshot_quellen": {"robo": {"status": "fertig"}}, "logs": []}
    store.create(run)
    entry = {"signal_ref": 1, "id": 1, "quelle": "robo", "quellen_uid": "robo", "name": "Source values",
             "data_done": True, "auswertung_typ": "quellenprofitabilitaet", "eligible": False}
    entry["data_basis"] = analyse.eintrag_basis(entry, analyse.daten_basis(settings), {})
    store.save_task(run["id"], entry)
    clients = []

    class AI:
        def __init__(self, *args, **kwargs):
            self.client = type("Client", (), {"has_key": True, "timeout": 300, "request_gate": None})()
            clients.append(self.client)

    class Data:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def berechne(self, *args, **kwargs): pytest.fail("Stored source values must be reused")

    monkeypatch.setattr(analyse, "AnalyseKI", AI)
    monkeypatch.setattr(analyse, "_snapshot", lambda *args: None)
    monkeypatch.setattr(data_module, "AnalyseDaten", Data)
    analyse._execute(store, run["id"], settings)
    assert clients and all(client.timeout == 300 and client.request_gate is None for client in clients)
    assert store.read(run["id"])["status"] == "abgeschlossen"
