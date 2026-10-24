"""Stage one fetches/measures all selected rows with no KI prerequisites."""
from copy import deepcopy
import hashlib

import pytest

from mqlkiscanner import abonnenten_analyse as analyse, config, db
from mqlkiscanner.abonnenten_analyse_store import Store


def forbid_ki(monkeypatch):
    from mqlkiscanner import abonnenten_analyse_klaerung as clarification
    from mqlkiscanner import abonnenten_analyse_redaktion as editorial
    from mqlkiscanner.llm import client, prompts
    def forbidden(*args, **kwargs):
        pytest.fail("Data-only stage must not inspect KI prompts/budgets or instantiate a model client")
    monkeypatch.setattr(analyse, "AnalyseKI", forbidden)
    monkeypatch.setattr(clarification, "KlaerungKI", forbidden)
    monkeypatch.setattr(editorial, "BerichtRedaktionKI", forbidden)
    monkeypatch.setattr(client, "GlmClient", forbidden)
    monkeypatch.setattr(prompts, "fehlende_vorlagen", forbidden)
    monkeypatch.setattr(prompts, "prompt_fingerprint", forbidden)
    monkeypatch.setattr(analyse, "_budget_settings", forbidden)
    monkeypatch.setattr(analyse, "_ki_parallelitaet", forbidden)
    monkeypatch.setattr(analyse, "report_pdf", forbidden)
    monkeypatch.setattr(Store, "reserve", forbidden)


@pytest.fixture
def data_run(monkeypatch, tmp_path):
    from mqlkiscanner import abonnenten_analyse_daten as data_module
    from mqlkiscanner import abonnenten_analyse_trend as trend
    forbid_ki(monkeypatch)
    store = Store()
    run = analyse._data_run(["mql5"], 30, None)
    store.create(run)
    path = tmp_path / "full.csv"
    path.write_bytes(b"immutable,full,source,snapshot\n")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    calls, control = {"data": [], "cleanup": 0, "settings": [], "trends": 0}, {"fail": None, "stop": None}

    def snapshot(store, current, settings, log, stopped):
        if not store.tasks(current["id"]):
            for ref in range(1, 4):
                store.save_task(current["id"], {"signal_ref": ref, "id": ref, "quelle": "mql5", "quellen_uid": "mql5",
                                              "name": f"Synthetic {ref}", "abonnenten": 10 * ref,
                                              "abo_perzentil": 50, "data_done": False})
        store.update(current["id"], snapshot_quellen={"mql5": {"status": "fertig", "stand": "frozen"}})

    class Data:
        def __init__(self, settings, **kwargs): calls["settings"].append(settings)
        def __enter__(self): return self
        def __exit__(self, *args): calls["cleanup"] += 1
        def berechne(self, entry, should_stop):
            calls["data"].append(entry["id"])
            if control["stop"] == entry["id"]:
                store.update(run["id"], stop_requested=True)
            if control["fail"] == entry["id"]:
                return {"data_complete": False, "eligible": False, "grund": "Native export incomplete",
                        "trade_history_complete": False, "trade_history_status": "teilweise"}
            return {"data_complete": True, "eligible": entry["id"] != 3, "hard_excluded": entry["id"] == 3,
                    "forensik": {"stats": {"net": 100 * entry["id"]}, "forensics": {"martingale": {"flag": entry["id"] == 3}}},
                    "equity": {"status": "ok", "verlaesslich": True}, "equity_dd_pct": 25,
                    "retdd_jahr": 4, "cagr_jahr_pct": 100, "dauer_monate": 4,
                    "trades_path": str(path), "trades_sha256": sha, "trades": 500,
                    "trade_history_complete": True, "trade_history_status": "vollstaendig"}

    def freeze(store, run_id, entries, settings, log, stopped, *, include_all=False):
        assert include_all is True, "Data stage must fetch native histories for every positive selected identity"
        calls["trends"] += 1
        for entry in entries:
            entry["abo_trend"] = {"verified": True, "delta_7": entry["id"], "as_of": "unchanged-native-time"}

    monkeypatch.setattr(analyse, "_snapshot", snapshot)
    monkeypatch.setattr(data_module, "AnalyseDaten", Data)
    monkeypatch.setattr(trend, "freeze_trends", freeze)
    return store, run, calls, control


def test_data_only_execution_measures_all_selected_preserves_hard_facts_and_has_no_model_calls(data_run):
    store, run, calls, _ = data_run
    analyse._execute(store, run["id"], config.load_settings())
    result = store.read(run["id"])
    assert calls["data"] == [3, 2, 1] and calls["cleanup"] == 1
    assert all(settings["abonnenten_daten_ohne_ki"] is True for settings in calls["settings"])
    assert result["daten_workflow_abgeschlossen"] and result["daten_vollstaendig"]
    assert result["phase"] == "daten_ergebnis" and result["daten_status"] == "abgeschlossen"
    entries = store.tasks(run["id"])
    assert len(entries) == 3 and all(entry["trades"] == 500 for entry in entries)
    assert entries[2]["hard_excluded"] and entries[2]["rang"] is None
    assert all(not entry.get("kurztest") and not entry.get("bericht_markdown") and not entry.get("pdf_path") for entry in entries)
    assert store.spent(run["id"]) == 0


def test_single_provider_gap_is_explicit_and_resume_reuses_complete_measurements(data_run):
    store, run, calls, control = data_run
    control["fail"] = 2
    analyse._execute(store, run["id"], config.load_settings())
    result = store.read(run["id"])
    assert result["daten_workflow_abgeschlossen"] and not result["daten_vollstaendig"]
    assert result["status"] == "teilweise" and len(store.tasks(run["id"])) == 3
    assert store.tasks(run["id"])[1]["grund"] == "Native export incomplete"
    control["fail"] = None
    analyse._execute(store, run["id"], config.load_settings())
    assert calls["data"].count(1) == calls["data"].count(3) == 1
    assert calls["data"].count(2) == 2
    assert store.read(run["id"])["daten_vollstaendig"]


def test_data_stop_waits_for_provider_cleanup_and_does_not_enter_trends(data_run):
    store, run, calls, control = data_run
    control["stop"] = 2
    analyse._execute(store, run["id"], config.load_settings())
    result = store.read(run["id"])
    assert calls["data"] == [3, 2] and calls["cleanup"] == 1 and calls["trends"] == 0
    assert result["status"] == result["daten_status"] == "angehalten"
    assert not result["daten_workflow_abgeschlossen"]


def test_data_start_has_no_prompt_budget_parallelity_prerequisites_and_uses_scan_lock(monkeypatch):
    forbid_ki(monkeypatch)
    monkeypatch.setattr(db, "list_quellen", lambda **kwargs: [{"kuerzel": "mql5"}])
    launched = []
    def start(callback, **kwargs):
        launched.append((callback, kwargs))
        return object()
    monkeypatch.setattr(analyse.scan_worker, "start", start)
    run_id = analyse.daten_starten(["mql5"], settings={"abonnenten_analyse_parallelitaet": "irrelevant"})
    result = Store().read(run_id)
    assert result["workflow_modus"] == analyse.DATA_WORKFLOW_MODE
    assert result["retdd_gewicht"] == 30
    assert not {"budget_settings", "budget_applied", "ki_parallelitaet"}.intersection(result)
    assert launched[0][1]["lock_basis"] == config.DATA_DIR
    assert launched[0][1]["workflow"]["abonnenten_id"] == run_id


def test_data_resume_refuses_to_repurpose_an_original_ki_job(monkeypatch):
    forbid_ki(monkeypatch)
    store = Store()
    store.create({"id": "original-ki", "status": "angehalten", "budget_settings": {"llm_max_total_tokens": 800_000_000}})
    before = store.read("original-ki")
    with pytest.raises(ValueError, match="ausdrücklich angelegter Datenauftrag"):
        analyse.daten_fortsetzen("original-ki")
    assert store.read("original-ki") == before


def test_copy_to_new_data_job_keeps_original_paid_reports_calls_and_times_unchanged(data_run, monkeypatch):
    store, run, _, _ = data_run
    analyse._execute(store, run["id"], config.load_settings())
    original_id = run["id"]
    entry = store.tasks(original_id)[0]
    entry.update(kurztest={"text": "Paid original"}, bericht_markdown="# Paid original", review_pending=True,
                 ki_klaerung_gesperrt=True, ki_fehler="historic model problem")
    store.save_task(original_id, entry)
    store.update(original_id, workflow_modus="historischer_ki_auftrag", retdd_gewicht=70,
                 budget_settings={"llm_max_total_tokens": 800_000_000})
    with store.connection() as connection:
        connection.execute("INSERT INTO calls(run_id,basis,status,reserved,tokens,response,meta,created_at) "
                           "VALUES(?,?,'response',321,123,'paid-raw-response','{}','historical')",
                           (original_id, "synthetic-paid-original"))
    original_call = store.call(original_id, "synthetic-paid-original")
    before_run, before_tasks = store.read(original_id), store.tasks(original_id)
    def forbidden_launch(*args, **kwargs): pytest.fail("Copy-only data view must not start a worker")
    monkeypatch.setattr(analyse, "_launch", forbidden_launch)
    new_id = analyse.daten_aus_lauf(original_id)
    assert new_id != original_id
    assert store.read(original_id) == before_run and store.tasks(original_id) == before_tasks
    derived, entries = store.read(new_id), store.tasks(new_id)
    assert derived["abgeleitet_von"] == original_id and derived["daten_uebernommen"]
    assert derived["retdd_gewicht"] == 30 and before_run["retdd_gewicht"] == 70
    assert derived["snapshot_quellen"] == before_run["snapshot_quellen"]
    assert entries[0]["abo_trend"]["as_of"] == before_tasks[0]["abo_trend"]["as_of"]
    assert not {"kurztest", "bericht_markdown", "ki_klaerung_gesperrt", "ki_fehler"}.intersection(entries[0])
    assert len(entries) == len(before_tasks) and store.spent(new_id) == 0
    assert store.call(original_id, "synthetic-paid-original") == original_call
    assert store.spent(original_id) == 123


def test_data_ranking_ignores_model_flags_without_erasing_them_or_hard_findings():
    entries = [{"signal_ref": ref, "id": ref, "quelle": "mql5", "quellen_uid": "mql5", "eligible": True,
                "data_done": True, "retdd_jahr": 4, "abonnenten": 10, "dauer_monate": 4,
                "abo_trend": {"verified": True, "delta_7": ref}, "review_pending": True,
                "ki_klaerung_gesperrt": True, "hard_excluded": ref == 2} for ref in (1, 2)]
    assert [entry["id"] for entry in analyse.rank_datamodus(entries)] == [1]
    assert entries[0]["ki_klaerung_gesperrt"] and entries[0]["review_pending"]
    assert entries[1]["hard_excluded"] and entries[1]["rang"] is None


def test_old_completed_research_attempt_without_h1_or_native_history_proof_is_not_complete_data(data_run):
    store, run, _, _ = data_run
    analyse._execute(store, run["id"], config.load_settings())
    entry = store.tasks(run["id"])[0]
    settings = config.load_settings()
    common = analyse.daten_basis(settings)
    assert analyse._data_attempt_reusable(entry, common, {})
    entry.pop("trade_history_complete")
    assert not analyse._data_attempt_reusable(entry, common, {})
    entry["trade_history_complete"] = True
    entry["equity"] = {}
    entry["equity_dd_pct"] = None
    assert not analyse._data_attempt_reusable(entry, common, {})


def test_source_failure_does_not_hide_successful_other_source_rows(data_run, monkeypatch):
    store, run, calls, _ = data_run
    store.update(run["id"], quellen=["mql5", "vant"])
    original_snapshot = analyse._snapshot
    def snapshot(store, current, settings, log, stopped):
        original_snapshot(store, current, settings, log, stopped)
        snapshots = store.read(current["id"])["snapshot_quellen"]
        snapshots["vant"] = {"status": "fehler", "grund": "Native source could not establish provider selection"}
        store.update(current["id"], snapshot_quellen=snapshots)
    monkeypatch.setattr(analyse, "_snapshot", snapshot)
    analyse._execute(store, run["id"], config.load_settings())
    result = store.read(run["id"])
    assert result["daten_workflow_abgeschlossen"] and result["status"] == "teilweise"
    assert not result["daten_vollstaendig"] and len(store.tasks(run["id"])) == 3
    assert result["snapshot_quellen"]["vant"]["status"] == "fehler"
    assert calls["data"] == [3, 2, 1]

    original_mql_reference = deepcopy(result["abo_quellen_referenz"]["mql5"])
    def recovered_snapshot(store, current, settings, log, stopped):
        store.save_task(current["id"], {"signal_ref": 4, "id": 4, "quelle": "vant", "quellen_uid": "vant",
                                      "name": "Recovered source", "abonnenten": 40, "data_done": False})
        store.update(current["id"], snapshot_quellen={"mql5": {"status": "fertig", "stand": "frozen"},
                                                     "vant": {"status": "fertig", "stand": "newly-recovered"}})
    monkeypatch.setattr(analyse, "_snapshot", recovered_snapshot)
    analyse._execute(store, run["id"], config.load_settings())
    recovered = store.read(run["id"])
    assert recovered["status"] == "abgeschlossen" and len(store.tasks(run["id"])) == 4
    assert recovered["abo_quellen_referenz"]["mql5"] == original_mql_reference
    assert recovered["abo_quellen_referenz"]["vant"]["bekannte_positive_n"] == 1
    assert recovered["abo_quellen_referenz_historie"][0]["referenz"]["auswahl_n"] == 0
    assert calls["data"] == [3, 2, 1, 4]


def test_data_runner_requests_history_for_all_800_identities_even_robo_and_measurement_gaps(monkeypatch):
    from mqlkiscanner import abonnenten_analyse_daten as data_module
    from mqlkiscanner import abonnenten_analyse_trend as trend
    forbid_ki(monkeypatch)
    sources = ["mql5", "pelik", "robo", "zulu"]
    run = analyse._data_run(sources, 30, None)
    run["snapshot_quellen"] = {source: {"status": "fertig"} for source in sources}
    rows = {index + 1: {"signal_ref": index + 1, "id": index + 1, "quelle": sources[index // 200],
                       "quellen_uid": sources[index // 200], "quelle_version": "rst" if index // 200 == 2 else "mql5",
                       "name": f"Selected {index}", "abonnenten": 1, "data_done": False, "eligible": False}
            for index in range(800)}
    class MemoryStore:
        def read(self, rid): return deepcopy(run)
        def update(self, rid, **changes): run.update(changes); return deepcopy(run)
        def tasks(self, rid): return deepcopy(list(rows.values()))
        def save_task(self, rid, entry): rows[entry["signal_ref"]] = deepcopy(entry)
        def log(self, *args): pass
    class Data:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def berechne(self, entry, **kwargs):
            return {"data_complete": False, "eligible": False, "grund": "No safe H1/contract basis",
                    "auswertung_typ": "quellenprofitabilitaet" if entry["quelle"] == "robo" else "tradeforensik"}
    received = []
    def histories(store, rid, entries, settings, log, stopped, *, include_all=False):
        assert include_all is True
        received.extend((entry["quelle"], entry["signal_ref"]) for entry in entries)
        assert all(not entry["eligible"] and not entry["data_done"] for entry in entries)
    monkeypatch.setattr(analyse, "_snapshot", lambda *args: None)
    monkeypatch.setattr(data_module, "AnalyseDaten", Data)
    monkeypatch.setattr(trend, "freeze_trends", histories)
    analyse._execute_data_only(MemoryStore(), run["id"], config.load_settings())
    assert len(received) == 800 and len(set(received)) == 800
    assert all(sum(source == selected for selected, ref in received) == 200 for source in sources)
    assert run["daten_workflow_abgeschlossen"] and run["status"] == "teilweise"


@pytest.fixture
def legacy_receipt_entry(tmp_path):
    path = tmp_path / "legacy_full_history.csv"
    path.write_text("Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
                    "2026.01.01 12:00:00;Buy;0.01;EURUSD;1.1;0.01;2026.01.01 13:00:00;1.2;0;0;10\n"
                    "2026.03.03 12:00:00;Sell;0.01;EURUSD;1.2;0.01;2026.03.03 13:00:00;1.1;0;0;10\n",
                    encoding="utf-8")
    entry = {"signal_ref": 10436, "id": 2385128, "quelle": "mql5", "quellen_uid": "source-mql5",
             "quelle_version": "mql5", "platform": "mt5", "name": "Measured legacy provider", "abonnenten": 2,
             "data_done": True, "status": "fertig", "trades_path": str(path),
             "trades_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "trades": 2,
             "equity": {"status": "ok", "verlaesslich": True}, "equity_dd_pct": 42.36, "retdd_jahr": 3,
             "eligible": False, "grund": "Original data reason retained", "account_currency": "USD",
             "refresh": {"providerId": "2385128", "version": "mql5", "platformRefreshed": True,
                         "fullHistory": True, "jobId": "p-native-history-job",
                         "refreshedAt": "2026-10-23T16:21:28.893894Z", "tradelistenFehler": 0,
                         "tradelistenAbgebrochen": False},
             "quellen_stats": {"account_currency": "USD", "quelle_trades_gekappt": None,
                               "quelle_trades_history_complete": None, "quelle_trade_history_complete": None}}
    entry["data_basis"] = analyse.eintrag_basis(entry, analyse.daten_basis(config.load_settings()), {})
    return entry


def test_legacy_native_receipt_is_derived_only_in_new_copy_with_exact_sha_parser_and_original_time(legacy_receipt_entry, monkeypatch):
    forbid_ki(monkeypatch)
    store = Store()
    original = {"id": "original", "status": "angehalten", "quellen": ["mql5"], "dd_grenze": None,
                "retdd_gewicht": 30, "snapshot_quellen": {"mql5": {"status": "fertig", "stand": "old-source-time"}}}
    store.create(original)
    store.save_task("original", legacy_receipt_entry)
    before = store.tasks("original")
    new_id = analyse.daten_aus_lauf("original")
    copied = store.tasks(new_id)[0]
    assert copied["data_done"] and copied["trade_history_complete"]
    assert copied["trade_history_beleg"]["parser_trades"] == 2
    assert copied["trade_history_beleg"]["native_messzeit"] == legacy_receipt_entry["refresh"]["refreshedAt"]
    assert "keine Aussage über globale Plattformhistorie" in copied["trade_history_reason"]
    assert copied["grund"] == "Original data reason retained"
    assert store.tasks("original") == before and "trade_history_complete" not in before[0]


@pytest.mark.parametrize("fault", ["provider", "version", "errors", "aborted", "complete", "truncated",
                                   "count", "sha", "missing_receipt", "missing_job", "explicit_unknown"])
def test_legacy_receipt_gaps_or_conflicts_never_upgrade_export_completeness(legacy_receipt_entry, fault):
    entry = deepcopy(legacy_receipt_entry)
    if fault == "provider": entry["refresh"]["providerId"] = "2385129"
    elif fault == "version": entry["refresh"]["version"] = "mql4"
    elif fault == "errors": entry["refresh"]["tradelistenFehler"] = 1
    elif fault == "aborted": entry["refresh"]["tradelistenAbgebrochen"] = True
    elif fault == "complete": entry["quellen_stats"]["quelle_trade_history_complete"] = False
    elif fault == "truncated": entry["quellen_stats"]["quelle_trades_gekappt"] = True
    elif fault == "count": entry["trades"] = 3
    elif fault == "sha": entry["trades_sha256"] = "wrong-hash"
    elif fault == "missing_receipt": entry.pop("refresh")
    elif fault == "missing_job": entry["refresh"].pop("jobId")
    else: entry["trade_history_complete"] = None
    assert not analyse._derive_legacy_export_receipt(entry, original_run_id="original")
    assert entry.get("trade_history_complete") is not True


def test_native_receipt_does_not_skip_missing_h1_recalculation_or_replace_original_failure_reason(legacy_receipt_entry, monkeypatch):
    forbid_ki(monkeypatch)
    entry = deepcopy(legacy_receipt_entry)
    entry.update(equity={}, equity_dd_pct=None, grund="Actual historical currency/price failure")
    store = Store()
    store.create({"id": "original", "quellen": ["mql5"], "snapshot_quellen": {}, "status": "angehalten"})
    store.save_task("original", entry)
    new_id = analyse.daten_aus_lauf("original")
    copied = store.tasks(new_id)[0]
    assert copied["trade_history_complete"] and not copied["data_done"]
    assert copied["grund"] == "Actual historical currency/price failure"
    assert "Datenfortsetzung erforderlich" in copied["daten_uebernahme_hinweis"]
