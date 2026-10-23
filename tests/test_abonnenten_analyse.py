"""One-click coordinator, ranking and durable recovery with synthetic boundaries."""
import copy
import json

import pytest

from mqlkiscanner import abonnenten_analyse as analyse, config, db
from mqlkiscanner.abonnenten_analyse_store import Store
from mqlkiscanner.llm.client import LlmBudgetError, LlmError


def row(ref, retdd=2, popularity=50, **changes):
    return {"signal_ref": ref, "id": ref, "quelle": "mql5", "quellen_uid": "uid",
            "name": f"Test {ref}", "eligible": True, "retdd_jahr": retdd,
            "abo_perzentil": popularity, "dauer_monate": 2.1, **changes}


def test_midrank_ties_singleton_nonfinite_and_unknown():
    assert analyse.percentile({1: 1, 2: 1, 3: 3}) == {1: pytest.approx(100/3), 2: pytest.approx(100/3), 3: pytest.approx(250/3)}
    assert analyse.percentile({1: 500}) == {1: 50}
    assert analyse.percentile({1: float("nan"), 2: None, 3: True}) == {}


def test_weighting_is_common_and_high_dd_does_not_exclude():
    entries = [row(1, 4, 5, equity_dd_pct=80), row(2, 3, 95, equity_dd_pct=60)]
    assert [e["id"] for e in analyse.rank_entries(entries, 70)] == [1, 2]
    assert [e["id"] for e in analyse.rank_entries(entries, 50)] == [2, 1]
    assert entries[0]["retdd_jahr"] == 4
    invalid = row(3, 200, None)
    assert invalid not in analyse.rank_entries([*entries, invalid])
    assert invalid["rang"] is None


def test_sidecar_read_does_not_create_or_modify_main_database(tmp_path):
    store = Store()
    assert store.read() is None and store.runs() == []
    assert not store.path.exists()
    assert not db.DB_PATH.exists()
    store.create({"id": "test", "status": "geplant"})
    store.save_task("test", row(1))
    assert Store().tasks("test")[0]["signal_ref"] == 1
    assert not db.DB_PATH.exists()


def test_durable_cost_bound_and_unknown_attempts():
    store = Store()
    store.create({"id": "test"})
    store.reserve("test", "one", 100, 150)
    with pytest.raises(LlmBudgetError):
        store.reserve("test", "two", 60, 150)
    store.finish_call("test", "one", response="paid", tokens=40, meta={})
    store.reserve("test", "two", 100, 150)
    assert Store().spent("test") == 140


@pytest.fixture
def synthetic_run(monkeypatch, tmp_path):
    import mqlkiscanner.abonnenten_analyse_daten as data_module
    store = Store()
    store.create({"id": "job", "status": "geplant", "created_at": "test", "quellen": ["mql5"],
                  "retdd_gewicht": 70.0, "dd_grenze": None, "snapshot_quellen": {}, "logs": []})
    calls = {"data": [], "short": [], "deep": []}
    failures = {"short": None, "data": None, "remove": None}

    def snapshot(store, run, settings, log, stopped):
        if not store.tasks(run["id"]):
            for ref in range(1, 8):
                store.save_task(run["id"], row(ref, retdd=10-ref, popularity=100-ref, data_done=False))
        store.update(run["id"], snapshot_quellen={"mql5": {"status": "fertig"}})

    class Data:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def berechne(self, entry, should_stop):
            calls["data"].append(entry["id"])
            if failures["data"] == entry["id"]:
                return {"data_complete": False, "eligible": False, "grund": "Login fehlt"}
            return {"data_complete": True, "eligible": True, "retdd_jahr": 10-entry["id"],
                    "trades": 50, "dauer_monate": 2.1, "equity_dd_pct": 65,
                    "trades_path": str(tmp_path / "synthetic.csv"), "trades_sha256": "sha",
                    "forensik": {"forensics": {"martingale": {"flag": False}}}, "equity": {"ok": True}}

    class AI:
        def __init__(self, *args, **kwargs):
            self.client = type("Client", (), {"has_key": True})()
        def analyse(self, entry, *, deep=False, comparison=None):
            calls["deep" if deep else "short"].append(entry["id"])
            if not deep and failures["short"] == entry["id"]:
                raise LlmBudgetError("Testbudget")
            if deep:
                if failures["remove"] == entry["id"]:
                    entry["forensik"]["forensics"]["martingale"]["flag"] = True
                    return {"bericht_markdown": "Widerspruch", "neue_pruefhinweise": [{"text": "Beleg"}]}
                return {"bericht_markdown": "# Ausführliche Analyse\n\nBelegte Risiken.", "neue_pruefhinweise": []}
            return {"strategietyp": "Trendfolge", "kurzurteil": "Kurztest", "pruefhinweise": []}

    monkeypatch.setattr(analyse, "_snapshot", snapshot)
    monkeypatch.setattr(data_module, "AnalyseDaten", Data)
    monkeypatch.setattr(analyse, "AnalyseKI", AI)
    monkeypatch.setattr(analyse, "report_pdf", lambda e, rid: str(tmp_path / f"{e['id']}.pdf"))
    monkeypatch.setattr(db, "verify_trade_file", lambda *args: None)
    return store, calls, failures


def test_full_chain_all_short_and_exactly_top_five_deep(synthetic_run):
    store, calls, failures = synthetic_run
    analyse._execute(store, "job", config.load_settings())
    assert store.read("job")["status"] == "abgeschlossen"
    assert calls["short"] == list(range(1, 8))
    assert calls["deep"] == list(range(1, 6))
    assert all(e.get("kurztest") for e in store.tasks("job"))
    assert sum(bool(e.get("bericht_markdown")) for e in store.tasks("job")) == 5


def test_budget_resume_reuses_data_and_completed_short_parts(synthetic_run):
    store, calls, failures = synthetic_run
    failures["short"] = 3
    analyse._execute(store, "job", config.load_settings())
    assert store.read("job")["status"] == "wartet_budget"
    failures["short"] = None
    analyse._execute(Store(), "job", config.load_settings())
    assert store.read("job")["status"] == "abgeschlossen"
    assert calls["data"] == list(range(1, 8))
    assert calls["short"].count(1) == calls["short"].count(2) == 1
    assert calls["short"].count(3) == 2


def test_data_failure_remains_retryable_not_finished(synthetic_run):
    store, calls, failures = synthetic_run
    failures["data"] = 2
    analyse._execute(store, "job", config.load_settings())
    assert store.read("job")["status"] == "teilweise"
    assert not next(e for e in store.tasks("job") if e["id"] == 2)["data_done"]
    failures["data"] = None
    analyse._execute(store, "job", config.load_settings())
    assert calls["data"].count(2) == 2
    assert calls["data"].count(1) == 1
    assert store.read("job")["status"] == "abgeschlossen"


def test_confirmed_new_hard_fact_promotes_next_candidate_automatically(synthetic_run):
    store, calls, failures = synthetic_run
    failures["remove"] = 1
    analyse._execute(store, "job", config.load_settings())
    assert store.read("job")["status"] == "teilweise", "A hard exclusion does not settle an additional model hint"
    entries = store.tasks("job")
    assert next(e for e in entries if e["id"] == 1)["rang"] is None
    assert 6 in calls["deep"]
    assert all(e.get("bericht_markdown") for e in entries if e.get("rang") and e["rang"] <= 5)


def test_open_short_hint_defers_candidate_and_prevents_false_completion(synthetic_run, monkeypatch):
    store, calls, _ = synthetic_run
    original = analyse.AnalyseKI

    class AI(original):
        def analyse(self, entry, *, deep=False, comparison=None):
            result = super().analyse(entry, deep=deep, comparison=comparison)
            if not deep and entry["id"] == 1:
                result["pruefhinweise"] = [{"text": "New unresolved contradiction", "beleg_refs": ["equity"]}]
            return result

    monkeypatch.setattr(analyse, "AnalyseKI", AI)
    analyse._execute(store, "job", config.load_settings())
    entry = next(e for e in store.tasks("job") if e["id"] == 1)
    assert entry["review_pending"] and entry["rang"] is None
    assert entry["eligible"] and not entry.get("hard_excluded")
    assert entry["retdd_jahr"] == 9 and entry["equity_dd_pct"] == 65
    assert calls["deep"] == [2, 3, 4, 5, 6]
    assert store.read("job")["status"] == "teilweise"
    assert "1 offene KI-Prüfungen" in store.read("job")["detail"]


def test_open_deep_hint_promotes_next_candidate_and_survives_empty_short_on_resume(synthetic_run, monkeypatch):
    store, calls, _ = synthetic_run
    original = analyse.AnalyseKI

    class AI(original):
        def analyse(self, entry, *, deep=False, comparison=None):
            result = super().analyse(entry, deep=deep, comparison=comparison)
            if deep and entry["id"] == 1:
                result["neue_pruefhinweise"] = [{"text": "Unresolved deep finding", "beleg_refs": ["equity"]}]
            return result

    monkeypatch.setattr(analyse, "AnalyseKI", AI)
    for _ in range(2):
        analyse._execute(store, "job", config.load_settings())
        entry = next(e for e in store.tasks("job") if e["id"] == 1)
        assert entry["review_pending"] and entry["rang"] is None
        assert entry["eligible"] and not entry.get("hard_excluded")
        assert len(entry["ki_pruefhinweise"]) == 1
        assert store.read("job")["status"] == "teilweise"
    assert 6 in calls["deep"] and calls["deep"].count(1) == 1
    assert calls["data"] == calls["short"] == list(range(1, 8))
    assert all(e.get("bericht_markdown") for e in store.tasks("job") if e.get("rang") and e["rang"] <= 5)


def test_cached_short_hint_is_rechecked_instead_of_trusting_old_resolved_marker(synthetic_run):
    store, calls, _ = synthetic_run
    analyse._execute(store, "job", config.load_settings())
    entry = next(e for e in store.tasks("job") if e["id"] == 1)
    entry["kurztest"]["pruefhinweise"] = [{"text": "Cached unresolved hint", "beleg_refs": ["equity"]}]
    entry["review_pending"] = False
    store.save_task("job", entry)
    analyse._execute(store, "job", config.load_settings())
    entry = next(e for e in store.tasks("job") if e["id"] == 1)
    assert entry["review_pending"] and entry["rang"] is None
    assert calls["short"] == list(range(1, 8))
    assert store.read("job")["status"] == "teilweise"


def test_cached_deep_hint_is_rechecked_without_repeating_paid_analysis(synthetic_run):
    store, calls, _ = synthetic_run
    analyse._execute(store, "job", config.load_settings())
    entry = next(e for e in store.tasks("job") if e["id"] == 1)
    entry["top5_befund"]["neue_pruefhinweise"] = [{"text": "Cached deep finding", "beleg_refs": ["equity"]}]
    entry["review_pending"] = False
    store.save_task("job", entry)
    analyse._execute(store, "job", config.load_settings())
    entry = next(e for e in store.tasks("job") if e["id"] == 1)
    assert entry["review_pending"] and entry["rang"] is None
    assert calls["deep"].count(1) == 1 and 6 in calls["deep"]
    assert store.read("job")["status"] == "teilweise"


def test_new_data_attempt_archives_old_hints_before_new_assessment(synthetic_run, monkeypatch):
    store, calls, _ = synthetic_run
    analyse._execute(store, "job", config.load_settings())
    entry = next(e for e in store.tasks("job") if e["id"] == 1)
    hint = {"text": "Old snapshot finding", "beleg_refs": ["equity"]}
    entry.update(ki_pruefhinweise=[hint], review_pending=True, ki_hinweisstatus="Old pending hint")
    store.save_task("job", entry)
    monkeypatch.setattr(analyse, "POLICY_VERSION", "grok-new-data")
    analyse._execute(store, "job", config.load_settings())
    entry = next(e for e in store.tasks("job") if e["id"] == 1)
    assert not entry.get("review_pending") and not entry.get("ki_pruefhinweise")
    assert entry["previous_results"][-1]["ki_pruefhinweise"] == [hint]
    assert entry["previous_results"][-1]["review_pending"] is True
    assert calls["data"].count(1) == 2 and calls["short"].count(1) == 2
    assert store.read("job")["status"] == "abgeschlossen"


def test_facts_payload_version_repeats_reports_without_redownloading_data(synthetic_run, monkeypatch):
    store, calls, _ = synthetic_run
    analyse._execute(store, "job", config.load_settings())
    monkeypatch.setattr(analyse, "FACTS_PAYLOAD_VERSION", analyse.FACTS_PAYLOAD_VERSION + 1)
    analyse._execute(store, "job", config.load_settings())
    assert len(calls["data"]) == 7 and len(calls["short"]) == 14 and len(calls["deep"]) == 10


def test_snapshot_check_does_not_resolve_hint_or_accumulate_duplicate_findings(synthetic_run):
    _, _, _ = synthetic_run
    entry = row(1, trades_path="verified-by-fixture", trades_sha256="sha", forensik={},
                rang=1, auswahlwert=99, retdd_perzentil=99)
    hint = {"text": "Needs a substantive check", "beleg_refs": ["equity"]}
    for hints in ([hint], [], [hint]):
        analyse._check_hints(entry, hints)
        assert entry["review_pending"]
        assert entry["ki_pruefhinweise"] == [hint]
        assert entry["eligible"] and not entry.get("hard_excluded")
        assert all(entry[key] is None for key in ("rang", "auswahlwert", "retdd_perzentil"))


@pytest.mark.parametrize("failure", ["short_error", "budget"])
def test_open_hint_rank_is_removed_before_another_short_test_interrupts(synthetic_run, monkeypatch, failure):
    store, _, _ = synthetic_run
    original = analyse.AnalyseKI

    class AI(original):
        def analyse(self, entry, *, deep=False, comparison=None):
            result = super().analyse(entry, deep=deep, comparison=comparison)
            if not deep and entry["id"] == 1:
                result["pruefhinweise"] = [{"text": "Unresolved finding", "beleg_refs": ["equity"]}]
            if not deep and entry["id"] == 2:
                if failure == "budget":
                    raise LlmBudgetError("Synthetic budget exhaustion")
                raise LlmError("Synthetic short-test failure")
            return result

    monkeypatch.setattr(analyse, "AnalyseKI", AI)
    analyse._execute(store, "job", config.load_settings())
    entry = next(e for e in store.tasks("job") if e["id"] == 1)
    assert entry["review_pending"]
    assert all(entry[key] is None for key in ("rang", "auswahlwert", "retdd_perzentil"))
    assert entry["retdd_jahr"] == 9 and entry["eligible"]
    assert store.read("job")["status"] == ("wartet_budget" if failure == "budget" else "teilweise")


def test_old_hint_keeps_original_register_when_replacement_short_report_reuses_alias(synthetic_run, monkeypatch):
    store, _, _ = synthetic_run
    analyse._execute(store, "job", config.load_settings())
    entry = next(e for e in store.tasks("job") if e["id"] == 1)
    hint = {"text": "Needs old evidence", "beleg_refs": ["F001"]}
    entry["kurztest"].update(pruefhinweise=[hint], analysegrundlage={"beleg_register": {"F001": "old.path"}})
    entry.update(kurz_basis="legacy-report-basis", ki_pruefhinweise=[hint], review_pending=True)
    store.save_task("job", entry)
    original = analyse.AnalyseKI

    class AI(original):
        def analyse(self, entry, *, deep=False, comparison=None):
            result = super().analyse(entry, deep=deep, comparison=comparison)
            result["analysegrundlage"] = {"beleg_register": {"F001": "new.path"}}
            return result

    monkeypatch.setattr(analyse, "AnalyseKI", AI)
    for _ in range(2):
        analyse._execute(store, "job", config.load_settings())
        entry = next(e for e in store.tasks("job") if e["id"] == 1)
        assert entry["kurztest"]["analysegrundlage"]["beleg_register"] == {"F001": "new.path"}
        records = entry["ki_pruefhinweis_quellen"]
        assert len(records) == 1 and records[0]["hinweis"] == hint
        assert records[0]["herkunft"]["bericht_basis"] == "legacy-report-basis"
        assert records[0]["herkunft"]["analysegrundlage"]["beleg_register"] == {"F001": "old.path"}
        assert entry["review_pending"] and entry["rang"] is None


def test_unattributable_old_hint_is_not_bound_to_unrelated_current_register(synthetic_run):
    entry = row(1, trades_path="verified-by-fixture", trades_sha256="sha",
                ki_pruefhinweise=[{"text": "Old hint", "beleg_refs": ["F001"]}],
                kurztest={"pruefhinweise": [], "analysegrundlage": {"beleg_register": {"F001": "current.path"}}})
    analyse._check_hints(entry, [], stage="kurztest")
    origin = entry["ki_pruefhinweis_quellen"][0]["herkunft"]
    assert "unbekannt" in origin["status"] and "analysegrundlage" not in origin
    assert entry["review_pending"]


def test_prompt_change_only_repeats_dependent_short_and_deep(synthetic_run):
    from mqlkiscanner.llm import prompts
    store, calls, failures = synthetic_run
    analyse._execute(store, "job", config.load_settings())
    path = prompts.PROMPT_FILES["abonnenten_top5"]
    path.write_text(path.read_text(encoding="utf-8") + "\nZusatzfrage", encoding="utf-8")
    analyse._execute(store, "job", config.load_settings())
    assert len(calls["data"]) == len(calls["short"]) == 7
    assert len(calls["deep"]) == 10


def test_robo_quellenwerte_resume_braucht_keine_trade_snapshots_oder_ki(monkeypatch):
    from types import SimpleNamespace
    from mqlkiscanner import abonnenten_analyse_daten as data_module
    store = Store()
    store.create(dict(id="robo", status="geplant", created_at="test", quellen=["robo"],
                      retdd_gewicht=70, dd_grenze=None, snapshot_quellen={"robo": {"status": "fertig"}}, logs=[]))
    store.save_task("robo", dict(signal_ref=1, id=811, quelle="robo", name="Reported profit",
                                 abo_perzentil=90, data_done=False))
    calls = []
    class Data:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def berechne(self, entry, should_stop):
            calls.append(entry["id"])
            return data_module.robo_quellenwerte({"signalId": "811", "version": "rst", "metrics": {
                "ProfitUsd": 100, "YieldWindowPct": 5, "YieldWindowMonths": 3}}, 811, "rst")
    def forbidden(*a, **k): raise AssertionError("Kein Trade-/KI-Pfad für Quellenprofitabilität")
    monkeypatch.setattr(analyse, "_snapshot", lambda *a: None)
    monkeypatch.setattr(data_module, "AnalyseDaten", Data)
    monkeypatch.setattr(db, "verify_trade_file", forbidden)
    monkeypatch.setattr(analyse, "AnalyseKI", lambda *a, **k: SimpleNamespace(analyse=forbidden))
    for _ in range(2):
        analyse._execute(store, "robo", config.load_settings())
        assert store.read("robo")["status"] == "abgeschlossen"
        entry = store.tasks("robo")[0]
        assert entry["status"] == "quellenwerte" and entry["data_done"]
        assert entry["rang"] is None and entry["retdd_jahr"] is None
        assert analyse.zustand("robo")["done"] == 1
    assert calls == [811]


def test_robo_rst_blockiert_nicht_den_quellensnapshot(monkeypatch):
    from types import SimpleNamespace
    from mqlkiscanner import client_updates
    db.add_quelle("robo", "Robo metadata", "http://synthetic-robo:8198")
    store = Store()
    store.create(dict(id="rst", quellen=["robo"], snapshot_quellen={}, logs=[]))
    raw = [dict(signalId=str(i), version=v, signalName=v, subscribers=10-i)
           for i, v in enumerate(("mql4", "mql5", "rst"), 1)]
    monkeypatch.setattr(client_updates, "starte_alle_updates", lambda *a, **k: {
        "robo": {"status": client_updates.FERTIG, "job_id": "fresh-counters"}})
    monkeypatch.setattr(analyse.ingest, "hole_katalog", lambda *a, **k: raw)
    monkeypatch.setattr(analyse.source_registry, "client_fuer_quelle", lambda q: SimpleNamespace(
        health=lambda: {"providerRefresh": False, "providerRefreshReason": "units unverified"}))
    analyse._snapshot(store, store.read("rst"), {}, lambda message: None, lambda: False)
    assert store.read("rst")["snapshot_quellen"]["robo"]["status"] == "fertig"
    assert {e["quelle_version"] for e in store.tasks("rst")} == {"mql4", "mql5", "rst"}
