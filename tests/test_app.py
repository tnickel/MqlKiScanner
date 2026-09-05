# -*- coding: utf-8 -*-
"""Interaction regressions for the real multipage Streamlit entry point."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.proto.TextInput_pb2 import TextInput as TextInputProto
from streamlit.testing.v1 import AppTest

from mqlkiscanner import config, pipeline, secrets_store
from mqlkiscanner.llm import prompts

ROOT = Path(__file__).resolve().parents[1]


def _run_main(timeout: int = 60) -> AppTest:
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=timeout)
    at.run()
    assert not at.exception, at.exception
    return at


def _page(path: str) -> AppTest:
    at = _run_main()
    at.switch_page(f"app_pages/{path}.py").run()
    assert not at.exception, at.exception
    return at


def _body(at: AppTest) -> str:
    return "\n".join(
        element.value
        for kind in ("markdown", "caption", "success", "warning", "error", "info")
        for element in getattr(at, kind)
    )


def test_app_boots_without_exception():
    at = _run_main()
    assert at.sidebar.markdown, "Sidebar status is missing"


def test_scan_page_renders_steps():
    at = _run_main()
    body = _body(at)
    assert "Signale holen" in body and "KI-Bericht" in body
    assert "Starte Workflow" in body
    assert "Daten holen" in body and "Computer prüft" in body


def test_verification_button_loads_raw_data_and_saves_isolated_run():
    """The shipped nine exports must still pass through the actual engine."""
    at = _run_main(timeout=180)
    at.button(key="scan_verify").click().run()
    assert not at.exception, at.exception
    results = at.session_state["scan_results"]
    assert len(results) == 9
    assert any(result.ampel in ("🟢", "🟡") for result in results)
    run_file = Path(at.session_state["last_run_file"])
    assert run_file.is_relative_to(config.RUNS_DIR)
    payload = json.loads(run_file.read_text(encoding="utf-8"))
    assert len(payload["ergebnisse"]) == len(results)


def test_results_db_marks_refreshed_signals_as_neu():
    from mqlkiscanner import db

    db.init_db()
    db.upsert_signal(2265877, name="Gold Reaper DB Test", platform="MT4",
                     stats={"eq_dd_pct": 7.0, "ertrag_monat_pct": 10.0})
    db.store_forensik(2265877, {
        "score": 4.7, "ampel": "⚪", "stop_nachweis": "kein Nachweis",
        "martingale_flag": False, "trading_dd": {"pct": 5.0, "usd": 1.0},
        "peak_exposure": {"positionen": 1, "netto_lots": 0.1, "schock_usd": 500.0},
    })
    at = _run_main()
    at.session_state["refreshed_signal_ids"] = [2265877]
    at.switch_page("app_pages/ergebnisse.py").run()
    assert not at.exception, at.exception
    assert at.selectbox(key="results_run").value.startswith("Datenbank")
    df = at.dataframe[0].value
    assert "Stand" in df.columns
    row = df.loc[df["ID"] == 2265877].iloc[0]
    assert row["Stand"] == "NEU"
    assert list(df["ID"])[0] == 2265877, "NEU-Signale sollen oben stehen"


def test_results_page_renders_session_results():
    at = _run_main()
    at.session_state["scan_results"] = [pipeline.ScanResult(id=1234567, name="Test Signal")]
    at.switch_page("app_pages/ergebnisse.py").run()
    assert not at.exception, at.exception
    at.selectbox(key="results_run").set_value("Aktuelle Sitzung").run()
    assert not at.exception, at.exception
    assert at.dataframe, "Result table is missing"
    assert list(at.dataframe[0].value["ID"]) == [1234567]


@pytest.mark.parametrize("api_key", ["", "fake-ui-test-key.DO-NOT-USE-987654321"])
def test_admin_page_handles_missing_or_present_key_without_disclosure(api_key):
    if api_key:
        secrets_store.save_secrets(glm_api_key=api_key)
    at = _page("admin")
    body = _body(at)
    if api_key:
        assert api_key not in body
        assert "Wirksamer Key: vorhanden" in body
    else:
        assert "Wirksamer Key: nicht hinterlegt" in body
    password_fields = [field for field in at.text_input if field.proto.type == TextInputProto.PASSWORD]
    assert len(password_fields) >= 2, "GLM key and MQL5 password require password widgets"


def test_live_scan_failure_remains_an_error_after_rerun(monkeypatch):
    def failed_crawl(self, on_progress, log):
        log("Liste 1/4 angefragt")
        raise RuntimeError("Simulierter Verbindungsfehler")

    monkeypatch.setattr(pipeline.ScanPipeline, "crawl", failed_crawl)
    at = _run_main()
    at.button(key="scan_start").click().run()
    assert not at.exception, at.exception
    workflow = at.session_state["scan_workflow"]
    assert workflow["status"] == "error"
    assert workflow["steps"]["listen"]["status"] == "error"
    assert workflow["steps"]["forensik"]["status"] != "complete"
    assert "Simulierter Verbindungsfehler" in _body(at)
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["scan_workflow"]["steps"]["listen"]["status"] == "error"


def test_verification_exposes_each_file_and_skips_online_steps(tmp_path, monkeypatch):
    raw = tmp_path / "verification"
    raw.mkdir()
    for name in ("first.csv", "second.csv", "third.json"):
        (raw / name).write_text("test fixture", encoding="utf-8")
    monkeypatch.setattr(config, "RAW_DIR", raw)
    snapshots = []

    def analyze_one(files, settings):
        import streamlit as st

        current = dict(st.session_state["scan_workflow"]["steps"]["forensik"])
        snapshots.append((list(files), current))
        return [pipeline.ScanResult(id=1234560 + len(snapshots), name=Path(files[0]).stem,
                                    forensik_vorhanden=True)]

    monkeypatch.setattr(pipeline.ScanPipeline, "analyze_local_files", staticmethod(analyze_one))
    at = _run_main()
    at.button(key="scan_verify").click().run()
    assert not at.exception, at.exception
    assert len(snapshots) == 3
    for index, (files, state) in enumerate(snapshots):
        assert len(files) == 1
        assert state["status"] == "running"
        assert state["done"] == index
        assert state["total"] == 3
        assert Path(files[0]).name in state["detail"]
    workflow = at.session_state["scan_workflow"]
    assert workflow["status"] == "complete"
    assert workflow["steps"]["forensik"]["done"] == 3
    assert workflow["steps"]["forensik"]["status"] == "complete"
    assert all(workflow["steps"][step]["status"] == "skipped"
               for step in ("listen", "kandidaten", "llm"))


def test_prompt_reset_updates_saved_template_and_visible_editor():
    key = "trade_analyse"
    edited = prompts.load_prompt(key) + "\nZusätzliche Testanweisung."
    prompts.save_prompt(key, edited)
    at = _page("admin")
    assert at.text_area(key=f"prompt_{key}").value == edited
    at.text_area(key=f"prompt_{key}").set_value(edited + "\nUngespeicherte Änderung.").run()
    at.button(key="admin_prompt_reset").click().run()
    assert not at.exception, at.exception
    assert prompts.load_prompt(key) == prompts.DEFAULTS[key]
    assert at.text_area(key=f"prompt_{key}").value == prompts.DEFAULTS[key]
    at.run()
    assert not at.exception, at.exception
    assert at.text_area(key=f"prompt_{key}").value == prompts.DEFAULTS[key]


def test_prompt_save_rejects_missing_data_placeholders():
    key = "trade_analyse"
    original = prompts.load_prompt(key)
    at = _page("admin")
    at.text_area(key=f"prompt_{key}").set_value("Prompt ohne notwendige Daten.").run()
    at.button(key="admin_prompt_save").click().run()
    assert not at.exception, at.exception
    assert at.error
    assert prompts.load_prompt(key) == original


def test_custom_model_settings_render_and_save_without_losing_other_settings():
    config.save_settings({**config.DEFAULT_SETTINGS, "model_stufe1": "custom-fast-model",
                          "model_stufe2": "custom-strong-model", "top_n_export": 7})
    at = _page("admin")
    assert at.selectbox(key="admin_model1").value == "custom-fast-model"
    assert at.selectbox(key="admin_model2").value == "custom-strong-model"
    at.number_input(key="admin_budget").set_value(2_000_000)
    at.button(key="admin_models_save").click().run()
    assert not at.exception, at.exception
    settings = config.load_settings()
    assert settings["llm_max_total_tokens"] == 2_000_000
    assert settings["model_stufe1"] == "custom-fast-model"
    assert settings["model_stufe2"] == "custom-strong-model"
    assert settings["top_n_export"] == 7


def test_action_help_opens_explanation_without_starting_scan():
    at = _run_main()
    at.button(key="ui_info_scan_verify_help").click().run()
    assert not at.exception, at.exception
    assert at.button(key="ui_help_close")
    assert not at.session_state["scan_results"]
    assert not at.session_state["last_run_file"]
    dialog = at.get("dialog")
    assert dialog, "Context help must open a dialog"
    at.button(key="ui_help_close").click().run()
    assert not at.exception, at.exception
    assert not at.session_state["scan_results"]


def test_standalone_llm_without_key_is_skipped():
    at = _run_main()
    at.session_state["scan_results"] = [pipeline.ScanResult(
        id=1234567, name="Forensik vorhanden", forensik_vorhanden=True)]
    at.run()
    at.button(key="scan_llm").click().run()
    assert not at.exception, at.exception
    step = at.session_state["scan_workflow"]["steps"]["llm"]
    assert step["status"] == "skipped"
    assert step["done"] == 0
    assert "Key" in step["detail"]
    assert not at.session_state["scan_results"][0].gesamtbericht


def test_results_search_and_status_filter_apply_to_table_and_verdicts():
    at = _run_main()
    at.session_state["scan_results"] = [
        pipeline.ScanResult(id=1234561, name="Alpha", ampel="🟢", urteil="UNIQUE_GREEN_VERDICT"),
        pipeline.ScanResult(id=1234562, name="Beta", ampel="🔴", urteil="UNIQUE_BETA_VERDICT"),
        pipeline.ScanResult(id=1234563, name="Alphabet", ampel="🔴", urteil="UNIQUE_ALPHABET_VERDICT"),
    ]
    at.switch_page("app_pages/ergebnisse.py").run()
    assert not at.exception, at.exception
    at.selectbox(key="results_run").set_value("Aktuelle Sitzung").run()
    assert not at.exception, at.exception
    at.text_input(key="results_search").set_value("Alpha").run()
    assert not at.exception, at.exception
    assert list(at.dataframe[0].value["ID"]) == [1234561, 1234563]
    assert "UNIQUE_BETA_VERDICT" not in _body(at)

    status_filter = next(widget for widget in at.get("button_group") if widget.key == "results_status")
    status_filter.set_value(["🔴"]).run()
    assert not at.exception, at.exception
    assert list(at.dataframe[0].value["ID"]) == [1234563]
    assert "UNIQUE_GREEN_VERDICT" not in _body(at)
    assert "UNIQUE_ALPHABET_VERDICT" in _body(at)
    assert len(at.session_state["scan_results"]) == 3, "Filtering must retain the original run"


def test_browsing_archive_keeps_current_session_results():
    saved = pipeline.ScanPipeline.save_run([pipeline.ScanResult(id=7654321, name="Archived")], {})
    at = _run_main()
    at.session_state["scan_results"] = [pipeline.ScanResult(id=1234567, name="Current")]
    at.switch_page("app_pages/ergebnisse.py").run()
    assert not at.exception, at.exception
    at.selectbox(key="results_run").set_value("Aktuelle Sitzung").run()
    assert not at.exception, at.exception
    current_option = at.selectbox(key="results_run").value
    at.selectbox(key="results_run").set_value(saved).run()
    assert not at.exception, at.exception
    assert list(at.dataframe[0].value["ID"]) == [7654321]
    assert at.session_state["scan_results"][0].id == 1234567
    at.selectbox(key="results_run").set_value(current_option).run()
    assert not at.exception, at.exception
    assert list(at.dataframe[0].value["ID"]) == [1234567]
