"""Regressionen für wiederholte Prüfungen, Demo-Isolation und Einstellungsgrenzen."""
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from conftest import ROOT, warte_auf_lauf
from mqlkiscanner import config, db, pipeline, secrets_store


def scan_page():
    return AppTest.from_file(str(ROOT / "app_pages/scan.py"), default_timeout=30)


def click_and_finish(at, key):
    at.button(key=key).click().run()
    warte_auf_lauf(at)
    assert not at.exception


@pytest.mark.parametrize("page", ["scan", "admin"])
def test_saved_large_filter_values_render_on_both_pages(page):
    config.save_settings({**config.load_settings(), "top_n_export": 51,
                          "min_wochen": 261, "min_abonnenten": 1001})
    at = AppTest.from_file(str(ROOT / f"app_pages/{page}.py"), default_timeout=30).run()
    assert not at.exception
    keys = (["set_topn", "set_wochen", "set_abo"] if page == "scan" else
            ["admin_topn", "admin_weeks", "admin_subscribers"])
    assert [at.number_input(key=key).value for key in keys] == [51, 261, 1001]


def test_repeated_station_three_replaces_previous_results(monkeypatch):
    counter = iter(["first", "second"])
    monkeypatch.setattr(pipeline.ScanPipeline, "analyze_candidate",
                        lambda *a, **k: pipeline.ScanResult(id=123, name=next(counter)))
    at = scan_page()
    at.session_state["scan_candidates"] = [{"id": 123}]
    at.run()
    click_and_finish(at, "step_btn_forensik")
    click_and_finish(at, "step_btn_forensik")
    assert [(r.id, r.name) for r in at.session_state["scan_results"]] == [(123, "second")]


def test_repeated_demo_replaces_live_and_previous_demo_results(monkeypatch, tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "sample.csv").write_text("stub", encoding="utf-8")
    monkeypatch.setattr(config, "RAW_DIR", raw)

    def demo(*args, **kwargs):
        result = pipeline.ScanResult(id=123, name="demo", forensik_vorhanden=True)
        result.source_kind = "demo"
        return [result]

    monkeypatch.setattr(pipeline.ScanPipeline, "analyze_local_files", demo)
    at = scan_page()
    at.session_state["scan_results"] = [pipeline.ScanResult(id=987, name="live")]
    at.run()
    click_and_finish(at, "scan_verify")
    click_and_finish(at, "scan_verify")
    assert [r.id for r in at.session_state["scan_results"]] == [123]
    assert at.session_state["refreshed_signal_ids"] == []


def test_demo_cannot_enter_expert_llm_or_portfolio_actions(monkeypatch):
    monkeypatch.setattr(secrets_store, "get_secret", lambda key: "test-key")
    llm = Mock(side_effect=AssertionError("demo must not enter LLM"))
    portfolio = Mock(side_effect=AssertionError("demo must not enter portfolio"))
    monkeypatch.setattr(pipeline.ScanPipeline, "run_llm", llm)
    monkeypatch.setattr(pipeline.ScanPipeline, "run_portfolio", portfolio)
    result = pipeline.ScanResult(id=123, name="demo", forensik_vorhanden=True)
    result.source_kind = "demo"
    at = scan_page()
    at.session_state["scan_results"] = [result]
    at.run()
    assert at.button(key="scan_llm").disabled
    click_and_finish(at, "step_btn_llm")
    click_and_finish(at, "step_btn_portfolio")
    assert not llm.called and not portfolio.called


def test_only_new_rechecks_legacy_demo_catalog_entry(monkeypatch):
    result = pipeline.ScanResult(id=123, name="legacy demo", forensik_vorhanden=True)
    result.source_kind = "demo"
    monkeypatch.setattr(pipeline, "results_from_db", lambda *a: [result])
    analyze = Mock(return_value=pipeline.ScanResult(id=123, name="live"))
    monkeypatch.setattr(pipeline.ScanPipeline, "analyze_candidate", analyze)
    at = scan_page()
    at.session_state["scan_candidates"] = [{"id": 123}]
    at.run()
    at.toggle(key="scan_nur_neue").set_value(True).run()
    click_and_finish(at, "step_btn_forensik")
    assert analyze.call_count == 1
    assert at.session_state["scan_results"][0].name == "live"


def test_database_view_hides_legacy_demo_without_deleting_it():
    db.init_db()
    db.upsert_signal(123, name="legacy demo", platform="CSV",
                     stats={"forensik_ok": True})
    db.store_forensik(123, {"score": 4.7})
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30).run()
    at.switch_page("app_pages/ergebnisse.py").run()
    assert not at.exception
    assert any("Noch keine Berichte" in item.value for item in at.subheader)
    assert db.get_signal(123)["platform"] == "CSV"


def test_demo_session_hides_live_global_portfolio():
    db.init_db()
    db.store_analysis(0, "portfolio", "model", 1, "LIVE_PORTFOLIO_SENTINEL")
    result = pipeline.ScanResult(id=123, name="demo", forensik_vorhanden=True)
    result.source_kind = "demo"
    at = AppTest.from_file(str(ROOT / "app_pages/ergebnisse.py"), default_timeout=30)
    at.session_state["scan_results"] = [result]
    at.run()
    at.selectbox(key="results_run").set_value("Aktuelle Sitzung").run()
    assert not at.exception
    assert not any("LIVE_PORTFOLIO_SENTINEL" in item.value for item in at.markdown)
    assert any(item.value == "1" for item in at.metric if item.label == "Signale")
