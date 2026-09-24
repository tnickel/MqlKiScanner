# -*- coding: utf-8 -*-
"""Interaction regressions for the real multipage Streamlit entry point."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.proto.TextInput_pb2 import TextInput as TextInputProto
from streamlit.testing.v1 import AppTest

from conftest import warte_auf_lauf
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
    assert "Signale holen" in body and "KI-Bericht" in body and "Portfolio" in body
    assert at.button(key="scan_start").label == "Full-Scan"
    assert at.button(key="scan_gelbgruen").label == "Teilscan"
    # Sektionskopf der Analyse-Zentrale (Titel ist ein subheader, hier die Caption)
    assert "fünf nachvollziehbare Stationen" in body
    assert "Signallisten und Handelsdaten von MQL5 laden" in body
    # Die alte Story-Reihe ist entfernt: Beschreibungen stecken jetzt im Stepper.
    assert body.count("Signallisten und Handelsdaten") == 1


def test_verification_button_loads_raw_data_and_saves_isolated_run():
    """The shipped nine exports must still pass through the actual engine."""
    at = _run_main(timeout=180)
    at.button(key="scan_verify").click().run()
    warte_auf_lauf(at, timeout_s=120)
    assert not at.exception, at.exception
    results = at.session_state["scan_results"]
    assert len(results) == 9
    assert any(result.ampel in ("🟢", "🟡") for result in results)
    run_file = Path(at.session_state["last_run_file"])
    assert run_file.is_relative_to(config.RUNS_DIR)
    payload = json.loads(run_file.read_text(encoding="utf-8"))
    assert len(payload["ergebnisse"]) == len(results)


def test_scan_page_shows_problems_with_explanations():
    """„Probleme“ statt „Fehler“: Zähler + großer Erklär-Dialog je Signal."""
    from mqlkiscanner.pipeline import ScanResult

    at = _run_main()
    at.session_state["scan_results"] = [
        ScanResult(id=2367701, name="LUBOTFX", platform="MT5",
                   fehler="ValueError: Keine anwendbare Kontraktspec "
                          "(cross_broker=false): USOUSD-ECN"),
        ScanResult(id=2308093, name="UpFuji MT4", platform="MT4",
                   fehler="ValueError: Forensik unvollständig: Kapitalbasis unbekannt: "
                          "keine Einzahlungen vor dem ersten Trade im Export"),
        ScanResult(id=1, name="Gut", platform="MT5", forensik_vorhanden=True),
    ]
    at.run()
    assert not at.exception, at.exception
    buttons = [b for b in at.button if b.key == "scan_show_problems"]
    assert buttons, "Probleme-Button fehlt trotz problematischer Ergebnisse"
    assert "2 Probleme ansehen" in buttons[0].label
    assert any(m.label == "Probleme" and m.value == "2" for m in at.metric), \
        "Metrik heißt nicht mehr „Probleme“ mit richtigem Zähler"
    buttons[0].click().run()
    assert not at.exception, at.exception
    text = "\n".join(m.value for m in at.markdown) + "\n".join(c.value for c in at.caption)
    assert "Broker-Kontrakt nicht verifiziert" in text, \
        "Brokerabhängige Kontraktspec wird missverständlich als unbekanntes Instrument gezeigt"
    assert "Broker-Suffix bereits entfernt" in text
    assert "Kapitalbasis unbekannt" in text, "Kategorie Kapitalbasis fehlt im Dialog"
    assert "contract_specs.json" in text, "Handlungs-Hinweis zum Freigeben fehlt"


def test_scan_page_shows_waiting_stopwatch_for_long_model_calls():
    """Stoppuhr pro Meldung: zählt hoch, Hinweis ab 2 Minuten ohne neue Meldung."""
    import threading
    import time as time_mod
    from datetime import datetime as _dt

    at = _run_main()
    # Echten (kurzlebigen) Thread hinterlegen, sonst greift der
    # Unterbrechungs-Wächter der Seite und beendet den Scheinlauf sofort.
    keeper = threading.Thread(target=time_mod.sleep, args=(15,), daemon=True)
    keeper.start()
    wf = at.session_state["scan_workflow"]
    wf.update(status="running", started_at=_dt.now().isoformat(timespec="seconds"),
              activity="Schreibe Gesamtbericht für #2306053",
              activity_at=time_mod.time() - 150)
    wf["steps"]["llm"].update(status="running", total=81, done=45,
                              detail="45/81 Berichte gespeichert",
                              signal_current=5, signal_total=60)
    at.session_state["scan_thread"] = keeper
    at.run()
    assert not at.exception, at.exception
    page = "\n".join(m.value for m in at.markdown)
    assert "mks-clock--wait" in page, "Warte-Stoppuhr fehlt"
    assert "Σ Gesamt" in page
    assert "LLM-Antwort" in page
    assert "Signale 5/60" in page
    assert "02:30" in page, "Stoppuhr zeigt nicht 150 s als 02:30 an"
    assert "keine neue Meldung" in page, "Langwarte-Hinweis fehlt ab 2 Minuten"
    keeper.join(timeout=16)


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


def test_results_page_wechsel_protokoll_button_und_dialog():
    """Wechsel werden protokolliert und per Button in der Wechselliste sichtbar."""
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from mqlkiscanner import ampel_verlauf

    class _Zeit(_dt):
        _now = _dt(2026, 9, 21, 12, 0, 0)

        @classmethod
        def now(cls, tz=None):
            return cls._now

    settings = {"schranke_eq_dd_pct": 30.0, "min_ertrag_pct_monat": 5.0}
    monkey = pytest.MonkeyPatch()
    monkey.setattr(ampel_verlauf, "datetime", _Zeit)
    try:
        ampel_verlauf.erfasse_bewertung(
            pipeline.ScanResult(id=7654321, name="Wechsel Signal", ampel="🟡",
                                score=4.2, urteil="Forensik bestanden"), settings)
        _Zeit._now += _td(seconds=1)
        ampel_verlauf.erfasse_bewertung(
            pipeline.ScanResult(id=7654321, name="Wechsel Signal", ampel="🟢",
                                score=4.0, urteil="Kandidat"), settings)
    finally:
        monkey.undo()

    at = _run_main()
    at.session_state["scan_results"] = [pipeline.ScanResult(id=7654321, name="Wechsel Signal")]
    at.switch_page("app_pages/ergebnisse.py").run()
    assert not at.exception, at.exception
    at.selectbox(key="results_run").set_value("Aktuelle Sitzung").run()
    button = at.button(key="results_wechsel_open")
    assert "(1)" in button.label and not button.disabled
    button.click().run()
    assert not at.exception, at.exception
    body = _body(at)
    assert "Wechsel Signal" in body and "🟡 → 🟢" in body
    assert "protokollierte Wechsel" in body


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
    warte_auf_lauf(at)
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
        # Wird im Worker-Thread ausgeführt — kein st.* hier.
        snapshots.append(list(files))
        return [pipeline.ScanResult(id=1234560 + len(snapshots), name=Path(files[0]).stem,
                                    forensik_vorhanden=True)]

    monkeypatch.setattr(pipeline.ScanPipeline, "analyze_local_files", staticmethod(analyze_one))
    at = _run_main()
    at.button(key="scan_verify").click().run()
    warte_auf_lauf(at)
    assert not at.exception, at.exception
    # Jede Datei einzeln und in Reihenfolge an den Lauf übergeben.
    assert [Path(f).name for files in snapshots for f in files] == \
        ["first.csv", "second.csv", "third.json"]
    workflow = at.session_state["scan_workflow"]
    assert workflow["status"] == "complete"
    assert workflow["steps"]["forensik"]["done"] == 3
    assert workflow["steps"]["forensik"]["total"] == 3
    assert workflow["steps"]["forensik"]["status"] == "complete"
    assert all(workflow["steps"][step]["status"] == "skipped"
               for step in ("listen", "kandidaten", "llm", "portfolio"))


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


def test_sidebar_info_erklaert_scan_und_agenten():
    """Das i am Arbeitsbereich öffnet die Erklärung Scan vs. Agenten."""
    at = _run_main()
    at.button(key="ui_info_sidebar_arbeitsbereich").click().run()
    assert not at.exception, at.exception
    dialogs = at.get("dialog")
    assert dialogs, "Sidebar-i muss die Arbeitsbereich-Erklärung öffnen"
    text = "\n".join(md.value for md in dialogs[0].markdown)
    assert "Agenten" in text and "Wachdienst" in text
    assert "auf Knopfdruck" in text
    assert "Der Unterschied in einem Satz" in text
    at.button(key="ui_help_close").click().run()
    assert not at.exception, at.exception


def test_standalone_llm_without_key_is_skipped():
    at = _run_main()
    at.session_state["scan_results"] = [pipeline.ScanResult(
        id=1234567, name="Forensik vorhanden", forensik_vorhanden=True)]
    at.run()
    at.button(key="scan_llm").click().run()
    warte_auf_lauf(at)
    assert not at.exception, at.exception
    step = at.session_state["scan_workflow"]["steps"]["llm"]
    assert step["status"] == "skipped"
    assert step["done"] == 0
    assert "Key" in step["detail"]
    assert not at.session_state["scan_results"][0].gesamtbericht
    pstep = at.session_state["scan_workflow"]["steps"]["portfolio"]
    assert pstep["status"] == "skipped" and "Key" in pstep["detail"]


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
