"""Current reports must describe the same facts as the current forensic result."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mqlkiscanner import db, pipeline


@pytest.fixture
def live_reports(tmp_path, monkeypatch):
    path = tmp_path / "history.csv"
    header = "Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;Profit;Comment"
    rows = [header, "2023.12.31 00:00:00;Balance;;;;;;;;;;1000;"]
    for i in range(26):
        opened = datetime(2024, 1, 1) + timedelta(days=30 * i)
        closed = opened + timedelta(hours=1)
        rows.append(f"{opened:%Y.%m.%d %H:%M:%S};Buy;0.01;XAUUSD;2000;1990;2010;"
                    f"{closed:%Y.%m.%d %H:%M:%S};2010;0;0;10;")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats", Mock(return_value={
        "dd_equity_pct": 5, "monthly_growth_pct": 10, "weeks": 110,
        "profit_factor": 2, "broker_server": "Example",
    }))
    monkeypatch.setattr(pipeline.exporter, "export_positions",
                        Mock(return_value=(str(path), False)))
    monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)
    db.init_db()
    pipe = pipeline.ScanPipeline()
    pipe.llm = SimpleNamespace(has_key=True, usage=SimpleNamespace(total_tokens=0),
                               chat=Mock(return_value="SL nachgewiesen. Kurzfassung: Empfehlung."))
    candidate = {"id": 123, "name": "Example", "platform": "MT4", "abonnenten": 20,
                 "abo_preis_usd": 30, "autor": "Example", "url": "https://example.invalid/123"}

    def scan():
        result = pipe.analyze_candidate(None, candidate, lambda _: None)
        assert not result.fehler and result.forensik_vorhanden
        return result

    return pipe, path, scan


def test_real_scan_report_roundtrip_reuses_identical_facts(live_reports):
    pipe, _, scan = live_reports
    first = scan()
    assert pipe.run_llm([first], lambda _: None)["completed"] == 3
    loaded = pipeline.results_from_db(pipe.settings)[0]
    assert loaded.berichte_basis == first.berichte_basis
    assert loaded.gesamtbericht == first.gesamtbericht
    assert loaded.trade_analyse and loaded.risiko_analyse and not loaded.bericht_hinweis
    second = scan()  # A new timestamp alone must not incur another paid generation.
    assert pipeline.restore_current_reports(second, pipe.settings)
    assert second.gesamtbericht == first.gesamtbericht
    assert pipe.llm.chat.call_count == 3


def test_changed_csv_separates_old_recommendation_from_current_result_and_portfolio(live_reports):
    pipe, path, scan = live_reports
    first = scan()
    assert first.stop_evidence == "direct" and first.ampel == "🟢"
    pipe.run_llm([first], lambda _: None)
    old_text = first.gesamtbericht
    path.write_text(path.read_text(encoding="utf-8").replace(";1990;2010;", ";;2010;"),
                    encoding="utf-8")
    changed = scan()
    assert changed.stop_evidence == "none" and changed.ampel == "🟡"
    assert first.trades_sha256 != changed.trades_sha256
    assert not pipeline.restore_current_reports(changed, pipe.settings)
    assert not changed.gesamtbericht and not changed.kurzfassung
    assert "veraltet" in changed.bericht_hinweis
    loaded = pipeline.results_from_db(pipe.settings)[0]
    assert not loaded.gesamtbericht and not loaded.trade_analyse and not loaded.risiko_analyse
    assert db.get_latest_analysis(123, "gesamtbericht")["text"] == old_text
    # Direct callers can also carry an old in-memory text into a newer result.
    changed.gesamtbericht, changed.kurzfassung = old_text, "Empfehlung"
    changed.berichte_basis = first.berichte_basis
    pipe.llm.chat.reset_mock()
    assert pipe.run_portfolio([changed], lambda _: None)["text"]
    prompt = pipe.llm.chat.call_args.args[0]
    assert old_text not in prompt
    assert '"gesamtbericht": "(nicht erstellt)"' in prompt
    assert '"stop_evidence": "none"' in prompt


@pytest.mark.parametrize("change", ["csv", "facts", "forensics", "version", "criteria"])
def test_changed_evidence_or_criteria_invalidate_reports(live_reports, change):
    pipe, _, scan = live_reports
    result = scan()
    pipe.run_llm([result], lambda _: None)
    settings = dict(pipe.settings)
    if change == "csv":
        result.trades_sha256 = "another-content-hash"
    elif change == "facts":
        result.dd_equity_pct = 35
    elif change == "forensics":
        result.stop_evidence = "none"
    elif change == "version":
        result.forensik_version -= 1
    else:
        settings["min_ertrag_pct_monat"] = 12
    assert not pipeline.restore_current_reports(result, settings)
    assert result.bericht_hinweis and not result.gesamtbericht


def test_old_unbound_reports_stay_in_history_and_are_not_reused(live_reports):
    pipe, _, scan = live_reports
    result = scan()
    db.store_analysis(123, "gesamtbericht", "legacy-model", 15, "Legacy recommendation")
    assert not pipeline.restore_current_reports(result, pipe.settings)
    assert result.bericht_hinweis
    assert db.get_latest_analysis(123, "gesamtbericht")["text"] == "Legacy recommendation"
    assert pipe.run_llm([result], lambda _: None)["completed"] == 3
    assert result.gesamtbericht and not result.bericht_hinweis


def test_new_explicit_exclusion_invalidates_previous_recommendation(live_reports, monkeypatch):
    pipe, _, scan = live_reports
    result = scan()
    pipe.run_llm([result], lambda _: None)
    monkeypatch.setattr(pipeline.config, "load_known_signals", lambda: {
        "ausgeschlossen": [{"id": 123, "grund": "Neue dokumentierte Ablehnung"}],
    })
    assert not pipeline.restore_current_reports(result, pipe.settings)
    assert result.ampel == "⛔" and not result.gesamtbericht


def test_different_basis_cannot_replace_one_part_of_a_matching_report(live_reports):
    pipe, _, scan = live_reports
    result = scan()
    pipe.run_llm([result], lambda _: None)
    correct_risk = result.risiko_analyse
    other = replace(result, stop_evidence="none")
    db.store_analysis(123, "risiko_analyse", "model", 5, "Other CSV risk",
                      basis=pipeline.report_basis_for(other, pipe.settings))
    assert pipeline.restore_current_reports(result, pipe.settings)
    assert result.risiko_analyse == correct_risk


def test_changed_criteria_refresh_flags_in_generated_prompt(live_reports, monkeypatch):
    pipe, _, scan = live_reports
    result = scan()
    pipe.run_llm([result], lambda _: None)
    pipe.settings["schranke_eq_dd_pct"] = 3
    monkeypatch.setattr(pipeline.llm_prompts, "load_prompt", lambda kind: "{kandidat_json}")
    pipe.llm.chat.reset_mock()
    assert pipe.run_llm([result], lambda _: None)["completed"] == 3
    sent = json.loads(pipe.llm.chat.call_args_list[0].args[0])
    assert sent["schranke_verletzt"] is True and sent["ampel"] == "🔴"
    assert result.schranke_verletzt and result.ampel == "🔴"


def test_saved_snapshot_hash_allows_reading_report_when_csv_is_offline(live_reports):
    pipe, _, scan = live_reports
    result = scan()
    pipe.run_llm([result], lambda _: None)
    offline = replace(result, trades_path="missing-snapshot.csv")
    assert pipeline.restore_current_reports(offline, pipe.settings)
    assert offline.gesamtbericht == result.gesamtbericht


def test_legacy_schema_migration_preserves_text_and_is_concurrent_safe():
    db.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute("CREATE TABLE analyses (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                     "signal_id INTEGER, kind TEXT, model TEXT, tokens INTEGER, text TEXT, created_at TEXT)")
        conn.execute("INSERT INTO analyses (kind, text) VALUES ('portfolio', 'historical text')")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: db.init_db(), range(4)))
    legacy = db.get_latest_analysis(None, "portfolio")
    assert legacy["text"] == "historical text" and legacy["basis"] is None
    assert db.get_latest_analysis(None, "portfolio", basis="new") is None
