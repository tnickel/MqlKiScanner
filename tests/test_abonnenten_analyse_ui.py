"""Recherche-UI und beide Promptverträge, ohne Quellen-/Modellaufrufe."""
from __future__ import annotations

import io
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import abonnenten_analyse_ui as ui
from mqlkiscanner import config, db
from mqlkiscanner.llm import prompt_fill, prompts
from mqlkiscanner.llm.client import LlmError


class _Backend:
    def __init__(self):
        self.state = {}
        self.started = []
        self.stopped = []
        self.resumed = []

    def laeufe(self):
        return [{"id": "run1", "status": self.state["status"],
                 "created_at": "2026-10-23 15:00"}] if self.state else []

    def zustand(self, run_id=None):
        return self.state

    def starten(self, quellen, settings=None, retdd_gewicht=70, dd_grenze=None):
        self.started.append((quellen, retdd_gewicht, dd_grenze))
        self.state = {"id": "run1", "status": "laeuft", "phase": "berechnet",
                      "detail": "Test", "laeuft": True, "total": 2, "done": 1,
                      "entries": [], "logs": ["synthetischer Testlauf"],
                      "retdd_gewicht": retdd_gewicht, "dd_grenze": dd_grenze}
        return "run1"

    def stoppen(self, run_id=None):
        self.stopped.append(run_id)
        self.state.update(laeuft=False, status="abgebrochen")

    def fortsetzen(self, run_id):
        self.resumed.append(run_id)
        self.state.update(laeuft=True, status="laeuft")
        return True


@pytest.fixture
def backend(monkeypatch):
    backend = _Backend()
    monkeypatch.setattr(ui, "_backend", lambda: backend)
    monkeypatch.setattr(ui.scan_worker, "active_run", lambda: None)
    db.init_db()
    db.add_quelle("mql5", "MQL", "http://fake.invalid:8123")
    db.add_quelle("pelik", "Pelican", "http://fake.invalid:8124")
    return backend


def _app():
    return AppTest.from_string("""
from mqlkiscanner.abonnenten_analyse_ui import render_start_button, render_results
render_start_button()
render_results()
""", default_timeout=30).run()


def test_dialog_defaults_start_and_no_automatic_start(backend):
    at = _app()
    assert not at.exception, at.exception
    assert backend.started == []
    at.button(key="abonnenten_analyse_oeffnen").click().run()
    assert not at.exception, at.exception
    assert at.multiselect(key="abonnenten_analyse_quellen").value == ["mql5", "pelik"]
    assert at.slider(key="abonnenten_analyse_start_retdd").value == 70
    assert at.toggle(key="abonnenten_analyse_start_dd_aktiv").value is False
    assert not at.number_input
    assert any("2 Monate und 50" in x.value for x in at.info)
    at.button(key="abonnenten_analyse_start").click().run()
    assert not at.exception, at.exception
    assert backend.started == [(["mql5", "pelik"], 70.0, None)]
    at.run()
    assert len(backend.started) == 1


def test_dialog_save_defaults_and_optional_limit(backend):
    config.save_settings({"unrelated": "preserve"})
    at = _app()
    at.button(key="abonnenten_analyse_oeffnen").click().run()
    at.multiselect(key="abonnenten_analyse_quellen").set_value(["pelik"]).run()
    at.toggle(key="abonnenten_analyse_start_dd_aktiv").set_value(True).run()
    at.number_input(key="abonnenten_analyse_start_dd").set_value(65.0)
    at.slider(key="abonnenten_analyse_start_retdd").set_value(90.0)
    at.checkbox(key="abonnenten_analyse_standard").check()
    at.button(key="abonnenten_analyse_start").click().run()
    assert not at.exception, at.exception
    assert backend.started == [(["pelik"], 90.0, 65.0)]
    saved = config.load_settings()
    assert saved["unrelated"] == "preserve"
    assert saved["abonnenten_analyse_dd_grenze"] == 65
    assert saved["abonnenten_analyse_retdd_gewicht"] == 90
    assert saved["abonnenten_analyse_quellen"] == ["pelik"]


def test_missing_new_prompt_blocks_only_research_start(backend):
    prompts.PROMPT_FILES["abonnenten_top5"].unlink()
    assert prompts.fehlende_vorlagen() == []
    assert prompts.fehlende_vorlagen(prompts.ABONNENTEN_PROMPT_KEYS) == ["abonnenten_top5"]
    at = _app()
    at.button(key="abonnenten_analyse_oeffnen").click().run()
    assert not at.exception, at.exception
    assert at.button(key="abonnenten_analyse_start").disabled
    assert any("abonnenten_top5" in e.value for e in at.error)


def test_progress_stop_resume_and_row_detail_are_source_bound(backend):
    backend.starten(["mql5", "pelik"])
    backend.state["entries"] = [
        {"signal_ref": "one", "id": 42, "quelle": "mql5", "name": "Erster",
         "rang": 1, "status": "kandidat", "retdd_jahr": 4.5,
         "messhinweis": "H1 erfasst keine Intrabar-Tiefs.",
         "ki_fehler": "Top-5-Bericht noch offen",
         "kurztest": {"strategietyp": "Trendfolge", "kurzurteil": "Erster Befund"},
         "bericht_markdown": "# Bericht der ersten Quelle"},
        {"signal_ref": "two", "id": 42, "quelle": "pelik", "name": "Zweiter",
         "rang": None, "status": "datenluecke", "grund": "Kapitalbasis unbelegt"},
    ]
    at = _app()
    assert not at.exception, at.exception
    assert len(at.dataframe[0].value) == 1
    key = next(x.key for x in at.dataframe if "analyse_tabelle" in x.key)
    at.session_state[key] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception, at.exception
    assert any("Bericht der ersten Quelle" in x.value for x in at.markdown)
    assert any("Intrabar-Tiefs" in x.value for x in at.caption)
    assert any("Top-5-Bericht noch offen" in x.value for x in at.warning)
    at.segmented_control(key="abonnenten_analyse_ansicht_run1").set_value("Alle").run()
    assert len(at.dataframe[0].value) == 2
    at.button(key="abonnenten_analyse_stop_run1").click().run()
    assert backend.stopped == ["run1"]
    at.button(key="abonnenten_analyse_resume_run1").click().run()
    assert backend.resumed == ["run1"]


def test_default_editor_persists_without_changing_workflow_risk(backend):
    config.save_settings({"schranke_eq_dd_pct": 37})
    at = AppTest.from_string("""
from mqlkiscanner import config
from mqlkiscanner.abonnenten_analyse_ui import render_defaults_editor
render_defaults_editor(config.load_settings())
""").run()
    at.slider(key="admin_abonnenten_analyse_retdd").set_value(80.0)
    at.button(key="admin_abonnenten_standard").click().run()
    assert not at.exception, at.exception
    assert config.load_settings()["abonnenten_analyse_retdd_gewicht"] == 80
    assert config.load_settings()["abonnenten_analyse_dd_grenze"] is None
    assert config.load_settings()["schranke_eq_dd_pct"] == 37


def test_csv_preserves_missing_numbers_and_source_identity():
    entries = [{"signal_ref": "a", "id": 42, "quelle": "mql5", "name": "=unsafe",
                "rang": 1, "retdd_jahr": 3.25, "messhinweis": "H1-Messung",
                "zeit_von": "2026-08-01", "zeit_bis": "2026-10-23",
                "trades_sha256": "abc123", "abo_referenz_n": 1000},
               {"signal_ref": "b", "id": 42, "quelle": "pelik", "name": "Andere"}]
    data = ui.ergebnis_csv(entries, {"id": "r", "retdd_gewicht": 70, "dd_grenze": None})
    df = pd.read_csv(io.BytesIO(data), sep=";")
    assert df["Strategie"].tolist() == ["'=unsafe", "Andere"]
    assert df["signal_ref"].tolist() == ["a", "b"]
    assert pd.isna(df.iloc[1]["Jahres-RetDD"])
    assert (df["RetDD-Gewicht %"] == 70).all()
    assert df.iloc[0]["Messhinweis"] == "H1-Messung"
    assert df.iloc[0]["Handel von"] == "2026-08-01"
    assert df.iloc[0]["Handel bis"] == "2026-10-23"
    assert df.iloc[0]["Trade-SHA256"] == "abc123"
    assert df.iloc[0]["Abo-Referenzanzahl"] == 1000


def _quellenwerte(**changes):
    entry = {"signal_ref": "robo-profit", "id": 42, "quelle": "robo", "name": "Quellenstrategie",
             "auswertung_typ": "quellenprofitabilitaet", "status": "quellenwerte",
             "gewinn_usd": 1234.56, "rendite_quelle_pct": 21.4,
             "rendite_quelle_monate": 0, "rating_balance_usd": 6000.0,
             "profitabilitaet": "positiv", "daten_gelesen_am": "2026-10-23T15:30:00+02:00",
             "finanzdaten_stand": None, "messhinweis": "Rating-Angaben der Quelle, kein gemessener Equity-DD.",
             "eligible": False, "data_complete": True}
    entry.update(changes)
    return entry


@pytest.mark.parametrize("months,label", [(0, "Gesamtzeitraum laut Quelle"),
                                          (1, "1 Monat laut Quelle"),
                                          (3, "3 Monate laut Quelle"),
                                          (None, "Zeitraum unbekannt")])
def test_source_profit_csv_keeps_original_yield_and_period_without_annualization(months, label):
    entry = _quellenwerte(rendite_quelle_monate=months, rang=7, retdd_jahr=999,
                         equity_dd_pct=555, ertrag_monat_geom_pct=111, auswahlwert=88,
                         kurztest={"kurzurteil": "alter KI-Text"}, bericht_markdown="alter Bericht")
    df = pd.read_csv(io.BytesIO(ui.ergebnis_csv([entry], {"id": "source", "retdd_gewicht": 70})), sep=";")
    row = df.iloc[0]
    assert row["Quellengewinn USD"] == 1234.56
    assert row["Quellrendite %"] == 21.4
    assert row["Renditezeitraum (Quelle)"] == label
    assert row["Quellenwerte gelesen am"] == entry["daten_gelesen_am"]
    assert row["Finanzdatenstand (Quelle)"] == "unbekannt – kein Quellenstand angegeben"
    for column in ("Jahres-RetDD", "Equity-DD %", "Geom. %/Monat", "Rang", "Auswahlwert",
                   "KI-Kurzurteil", "Vollbericht"):
        assert pd.isna(row[column]), column
    assert "Quellengewinn positiv; RetDD nicht bestimmbar" in row["Basisbewertung"]
    assert row["Quellen-Messhinweis"] == entry["messhinweis"]


@pytest.mark.parametrize("state,expected", [("positiv", "Quellengewinn positiv"),
                                           ("negativ", "Quellengewinn negativ"),
                                           ("unveraendert", "Quellengewinn unverändert"),
                                           ("unbekannt", "Quellengewinn nicht bestimmbar")])
def test_source_profit_detail_is_code_assessment_not_missing_or_fabricated_ai(state, expected):
    entry = _quellenwerte(profitabilitaet=state, kurztest={"kurzurteil": "alter KI-Text"},
                         bericht_markdown="alter Bericht", ki_fehler="alter KI-Fehler")
    at = AppTest.from_string(f"""
from mqlkiscanner.abonnenten_analyse_ui import _render_detail
_render_detail({entry!r}, 'source-fixture')
""").run()
    assert not at.exception, at.exception
    body = "\n".join(e.value for kind in ("markdown", "caption", "warning")
                     for e in getattr(at, kind))
    assert expected + "; RetDD nicht bestimmbar" in body
    assert "KI-Kurztest noch nicht vorhanden" not in body
    assert "alter KI" not in body and "alter Bericht" not in body
    assert "Finanzdatenstand laut Quelle: unbekannt" in body
    assert "GET-Zeitpunkt belegt keine Frische" in body
    assert "Gesamtzeitraum laut Quelle" in body
    assert at.metric[0].label == "Gewinn laut Quelle (USD)"
    assert at.metric[1].label == "Rendite laut Quelle (%)"


def test_source_profit_view_is_separate_from_retdd_candidates(backend):
    backend.starten(["mql5", "robo"])
    backend.state["entries"] = [
        {"signal_ref": "measured", "id": 42, "quelle": "mql5", "name": "Gemessener Kandidat",
         "rang": 1, "retdd_jahr": 4.5, "equity_dd_pct": 12.3, "status": "fertig"},
        _quellenwerte(rang=8),
        {"signal_ref": "gap", "id": 43, "quelle": "mql5", "name": "Offene Datenlücke",
         "status": "datenluecke", "grund": "Kursdaten fehlen"},
    ]
    at = _app()
    assert not at.exception, at.exception
    assert at.dataframe[0].value["Strategie"].tolist() == ["Gemessener Kandidat"]
    at.segmented_control(key="abonnenten_analyse_ansicht_run1").set_value("Quellenprofitabilität").run()
    assert not at.exception, at.exception
    assert at.dataframe[0].value["Strategie"].tolist() == ["Quellenstrategie"]
    assert at.dataframe[0].value.iloc[0]["Quellrendite %"] == 21.4
    assert pd.isna(at.dataframe[0].value.iloc[0]["Jahres-RetDD"])
    key = next(x.key for x in at.dataframe if "analyse_tabelle" in x.key)
    at.session_state[key] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception, at.exception
    assert any("Quellengewinn positiv; RetDD nicht bestimmbar" in x.value for x in at.markdown)
    at.segmented_control(key="abonnenten_analyse_ansicht_run1").set_value("Weitere Fälle").run()
    assert at.dataframe[0].value["Strategie"].tolist() == ["Offene Datenlücke"]
    at.segmented_control(key="abonnenten_analyse_ansicht_run1").set_value("Alle").run()
    assert len(at.dataframe[0].value) == 3


def test_research_pending_source_is_progress_and_real_source_failure_stays_visible(backend):
    backend.starten(["mql5", "pelik"])
    backend.state["snapshot_quellen"] = {
        "mql5": {"status": "laeuft", "grund": "Liste wird gelesen"},
        "pelik": {"status": "fehler", "grund": "Login fehlgeschlagen"},
    }
    at = _app()
    assert not at.exception, at.exception
    assert any("Liste wird gelesen" in e.value for e in at.info)
    assert not any("Liste wird gelesen" in e.value for e in at.warning)
    assert any("Login fehlgeschlagen" in e.value for e in at.warning)
    assert any("Ausgewählter Rechercheauftrag: run1" in e.value for e in at.caption)


def _ki_entry(index, **changes):
    entry = {"signal_ref": index, "id": index, "quelle": "mql5", "name": f"KI {index}",
             "trades_path": "synthetic.csv", "forensik": {"belegt": True},
             "trades": 50, "dauer_monate": 2, "data_done": True, "status": "ki_offen",
             "rang": index if index <= 5 else None}
    entry.update(changes)
    return entry


def test_ki_progress_does_not_present_748_provider_outcomes_as_completed_ai(backend):
    backend.starten(["mql5", "robo"])
    backend.state.update(phase="kurzanalysen", total=800, done=748,
                         detail="Ungültige KI-Antwort KI 1 (2/2): gespeicherter Fehler",
                         updated_at="2026-10-23T22:00:00+02:00",
                         logs=["2026-10-23T21:45:00+02:00 Ungültige KI-Antwort KI 1 (2/2): gespeicherter Fehler"],
                         entries=[*[_quellenwerte(signal_ref=f"robo-{i}") for i in range(200)],
                                  *[{"signal_ref": f"gap-{i}", "status": "datenluecke"} for i in range(547)],
                                  {"signal_ref": "excluded", "status": "ausgeschlossen"},
                                  *[_ki_entry(i) for i in range(1, 53)]])
    at = _app()
    assert not at.exception, at.exception
    metrics = {metric.label: metric.value for metric in at.metric}
    assert metrics["KI-Kurztests vorhanden"] == "0/52"
    assert metrics["Top-5-Analysen vorhanden"] == "0/5"
    assert metrics["Anbieter mit KI-Fehler"] == "0"
    assert at.get("progress")[0].proto.value == 0
    assert any("Anbieter-Endstände: 748/800" in e.value for e in at.caption)
    assert any("Letzte gespeicherte Meldung (2026-10-23T21:45:00+02:00)" in e.value
               and "gespeicherter Fehler" in e.value for e in at.caption)
    assert any("Auftrag zuletzt gespeichert: 2026-10-23T22:00:00+02:00" in e.value for e in at.caption)
    assert not any("läuft" in e.value and "gespeicherter Fehler" in e.value for e in at.caption)
    backend.state["entries"][-52].update(kurztest={"kurzurteil": "Gespeichert"}, status="fertig")
    backend.state["entries"][-51].update(ki_fehler="Antwort ungültig", status="ki_fehler")
    at.run()
    assert not at.exception, at.exception
    metrics = {metric.label: metric.value for metric in at.metric}
    assert metrics["KI-Kurztests vorhanden"] == "1/52"
    assert metrics["Anbieter mit KI-Fehler"] == "1"
    assert len(backend.started) == 1 and not backend.stopped and not backend.resumed


def test_message_stamp_is_not_invented_from_later_run_update():
    state = {"detail": "Zusammenfassung ohne Logzeit", "updated_at": "2026-10-23T22:00:00+02:00",
             "logs": ["2026-10-23T21:00:00+02:00 Eine andere Meldung"]}
    assert ui._meldungszeit(state) is None


def test_top5_progress_counts_saved_reports_and_keeps_errors_separate(backend):
    backend.starten(["mql5"])
    backend.state.update(phase="top5_analysen", entries=[_ki_entry(i, kurztest={"kurzurteil": "OK"})
                                                        for i in range(1, 8)])
    backend.state["entries"][0]["bericht_markdown"] = "# Gespeicherter Vollbericht"
    backend.state["entries"][1].update(bericht_markdown="# Analyse vorhanden, PDF fehlt",
                                      ki_fehler="PDF konnte nicht erstellt werden", status="ki_fehler")
    at = _app()
    assert not at.exception, at.exception
    metrics = {metric.label: metric.value for metric in at.metric}
    assert metrics["KI-Kurztests vorhanden"] == "7/7"
    assert metrics["Top-5-Analysen vorhanden"] == "2/5"
    assert metrics["Anbieter mit KI-Fehler"] == "1"
    assert at.get("progress")[0].proto.value == 40
    assert any("Arbeitsschritt dieses Auftrags: Ausführliche Top-5-Analysen" in e.value for e in at.caption)


def test_ki_counter_uses_backend_pure_selection_without_recalculating_gates(backend, monkeypatch):
    seen = []

    def possible(entry):
        seen.append(entry["id"])
        return entry["id"] == 7

    monkeypatch.setattr(backend, "_ki_possible", possible, raising=False)
    counts = ui._ki_zaehler({"entries": [{"id": 7, "kurztest": {"kurzurteil": "OK"}}, {"id": 8}]}, backend)
    assert seen == [7, 8]
    assert counts["kurz_fertig"] == counts["kurz_gesamt"] == 1


@pytest.fixture
def ki_ledger(backend, monkeypatch):
    reads = []
    row = {"status": "reserved", "created_at": "2026-10-23T22:01:00+02:00"}

    class LedgerConnection:
        def execute(self, sql, params):
            assert sql.startswith("SELECT status,created_at FROM calls")
            assert params == ("run1",)
            reads.append(sql)
            return self

        def fetchone(self):
            return row

    class LedgerStore:
        @contextmanager
        def connection(self):
            yield LedgerConnection()

    monkeypatch.setattr(backend, "Store", LedgerStore, raising=False)
    backend.starten(["mql5"])
    backend.state.update(phase="kurzanalysen", entries=[_ki_entry(1)])
    return backend.state, row, reads


def test_ki_reservation_is_read_only_and_does_not_claim_active_network_request(ki_ledger):
    state, row, reads = ki_ledger
    at = _app()
    assert not at.exception, at.exception
    assert len(reads) == 1
    assert any("Letzter KI-Arbeitsschritt reserviert seit " + row["created_at"] in e.value
               and "belegt keinen aktuell laufenden Netzaufruf" in e.value for e in at.caption)
    row["status"] = "response"
    at.run()
    assert not any("reserviert seit" in e.value for e in at.caption)


@pytest.mark.parametrize("change,current", [({}, False), ({"laeuft": False}, True),
                                           ({"status": "angehalten"}, True),
                                           ({"phase": "trades_und_equity"}, True)])
def test_no_ledger_read_for_archived_stopped_or_non_ai_run(ki_ledger, backend, change, current):
    state, _, reads = ki_ledger
    state.update(change)
    assert ui._letzte_ki_reservierung(state, backend, aktueller_lauf=current) is None
    assert reads == []


def test_incomplete_finished_source_selection_warns_but_keeps_candidates_visible(backend):
    backend.starten(["vant", "mql5"])
    backend.state["snapshot_quellen"] = {
        "vant": {"status": "fertig", "anzahl": 200,
                 "abonnenten_katalog": {"complete": False, "reached_end": True,
                                         "scanned_providers": 340, "skipped_positions": [8, 17],
                                         "months": 1, "sort": "2"}},
        "mql5": {"status": "fertig", "anzahl": 200},
    }
    backend.state["entries"] = [
        {"signal_ref": 11, "id": 42, "quelle": "vant", "name": "Vantage Kandidat",
         "rang": 1, "retdd_jahr": 4.5, "abo_referenz_n": 200, "status": "fertig"},
        {"signal_ref": 12, "id": 42, "quelle": "mql5", "name": "MQL Kandidat",
         "rang": 2, "retdd_jahr": 4.0, "abo_referenz_n": 200, "status": "fertig"},
    ]
    at = _app()
    assert not at.exception, at.exception
    assert any("vant: Vorläufige Abonnentenauswahl" in e.value for e in at.warning)
    assert any("2 API-Positionen ausgelassen" in e.value for e in at.warning)
    assert any("Vollständige Top 200 nicht belegt" in e.value for e in at.warning)
    rows = at.dataframe[0].value
    assert rows["Strategie"].tolist() == ["Vantage Kandidat", "MQL Kandidat"]
    assert rows.iloc[0]["Rang"] == 1
    assert rows.iloc[0]["Abonnentenreferenz vollständig"] == False
    assert rows.iloc[0]["Ausgelassene API-Positionen"] == "8, 17"
    assert rows.iloc[0]["Geprüfte Kataloganbieter"] == 340
    assert rows.iloc[1]["Auswahlhinweis"] == ""
    assert "abo_referenz_vollstaendig" not in backend.state["entries"][0], "UI must not mutate the frozen task"
    key = next(e.key for e in at.dataframe if "analyse_tabelle" in e.key)
    at.session_state[key] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception, at.exception
    assert sum("Vorläufige Abonnentenauswahl" in e.value for e in at.warning) == 2


def test_selection_coverage_csv_is_explicit_and_source_bound_without_inventing_missing_providers():
    entries = [{"id": 42, "quelle": "vant", "name": "Auswertbar", "rang": 1, "abo_referenz_n": 200},
               {"id": 42, "quelle": "mql5", "name": "Alte Quelle"}]
    state = {"id": "selection", "snapshot_quellen": {
        "vant": {"status": "fertig", "abonnenten_katalog": {
            "complete": False, "scanned_providers": 340, "skipped_positions": [8, 17]}}}}
    rows = pd.read_csv(io.BytesIO(ui.ergebnis_csv(entries, state)), sep=";")
    first, older = rows.iloc[0], rows.iloc[1]
    assert first["Abonnentenreferenz vollständig"] == False
    assert first["Ausgelassene API-Positionen"] == "8, 17"
    assert first["Geprüfte Kataloganbieter"] == 340
    assert "Vollständige Top 200 nicht belegt" in first["Auswahlhinweis"]
    assert "200 erfassten Anbietern" in first["Auswahlhinweis"]
    assert pd.isna(older["Abonnentenreferenz vollständig"])
    assert pd.isna(older["Ausgelassene API-Positionen"])
    assert pd.isna(older["Auswahlhinweis"])
    assert "abo_referenz_vollstaendig" not in entries[0]


def test_selection_coverage_without_skips_is_not_assumed_incomplete_or_warned(backend):
    backend.starten(["mql5"])
    backend.state["snapshot_quellen"] = {"mql5": {"status": "fertig", "anzahl": 200}}
    backend.state["entries"] = [{"id": 42, "quelle": "mql5", "name": "Alt", "rang": 1}]
    at = _app()
    assert not at.exception, at.exception
    assert not at.warning
    assert at.dataframe[0].value.iloc[0]["Auswahlhinweis"] == ""
    complete = ui.ergebnis_tabelle([{"abo_referenz_vollstaendig": True}]).iloc[0]
    assert complete["Abonnentenreferenz vollständig"] == True
    assert complete["Auswahlhinweis"] == ""


def test_research_archive_errors_are_explicitly_bound_to_selected_historical_run(backend, monkeypatch):
    backend.starten(["mql5"])
    backend.state.update(status="teilweise", laeuft=False, fehler="Alte Quellenausnahme")
    monkeypatch.setattr(backend, "laeufe", lambda: [
        {"id": "latest", "created_at": "2026-10-23 17:00", "status": "laeuft"},
        {"id": "run1", "created_at": "2026-10-23 15:00", "status": "teilweise"},
    ])
    at = _app()
    at.selectbox(key="abonnenten_analyse_lauf").set_value("run1").run()
    assert not at.exception, at.exception
    assert any("früheren Rechercheauftrag" in e.value for e in at.info)
    assert any("Fehler dieses Rechercheauftrags: Alte Quellenausnahme" in e.value for e in at.warning)
    assert any("Ausgewählter Rechercheauftrag: run1" in e.value for e in at.caption)


@pytest.fixture
def native_progress(backend, monkeypatch):
    source_id = db.add_quelle("zulu", "Zulu", "http://fake.invalid:8125")
    source = db.get_quelle(source_id)
    backend.starten(["zulu"])
    backend.state.update(phase="trades_und_equity", updated_at="2026-10-23T19:30:00+02:00",
                         detail="zulu:429450: aktuelle vollständige Quelldaten beschaffen …",
                         entries=[{"signal_ref": 44, "id": 429450, "quelle": "zulu",
                                   "quelle_id": source_id, "quellen_uid": source["quellen_uid"],
                                   "quelle_version": "zulu", "status": "rechnet", "name": "Test"}])
    job = {"jobId": "zulu-own-job", "state": "running", "phase": "tradelisten",
           "done": 30000, "total": 49164, "message": "Trades werden geladen",
           "startedAt": "2026-10-23T17:30:01Z", "finishedAt": None,
           "ergebnis": {"providerId": "429450", "version": "zulu"}}
    reads = []

    class ReadOnlyClient:
        def update_status(self):
            reads.append("GET /update/status")
            return job

    def client(quelle, timeout=None):
        assert quelle == source
        assert timeout == 1.0
        return ReadOnlyClient()

    monkeypatch.setattr(ui.quellen, "client_fuer_quelle", client)
    ui._quellenstatus.clear()
    yield backend.state, job, reads
    ui._quellenstatus.clear()


def test_live_native_progress_is_source_bound_read_only_and_cached(native_progress):
    state, job, reads = native_progress
    at = _app()
    assert not at.exception, at.exception
    text = "\n".join(e.value for e in at.caption)
    assert "Quellenclient · zulu:429450 · tradelisten · 30.000/49.164" in text
    assert "Trades werden geladen" in text and "Job zulu-own-job" in text
    assert state["detail"] in text
    assert len(at.get("progress")) == 2
    at.run()
    assert not at.exception, at.exception
    assert reads == ["GET /update/status"]


@pytest.mark.parametrize("change", [
    {"state": "done"}, {"state": "error"}, {"state": "login_required"}, {"state": "idle"},
    {"finishedAt": "2026-10-23T17:50:00Z"}, {"jobId": ""},
    {"ergebnis": {"providerId": "429451", "version": "zulu"}},
    {"ergebnis": {"providerId": "429450", "version": "mql5"}},
    {"ergebnis": {}}, {"ergebnis": None},
    {"startedAt": "2026-10-23T17:10:00Z"}, {"startedAt": None},
])
def test_unrelated_old_or_terminal_native_job_is_not_current_progress(native_progress, change):
    state, job, reads = native_progress
    job.update(change)
    assert ui._laufender_quellenfortschritt(state, aktueller_lauf=True) is None
    assert len(reads) == 1


@pytest.mark.parametrize("change", [
    {"laeuft": False}, {"status": "angehalten"}, {"phase": "kurztests"},
    {"entries": []},
])
def test_no_native_query_for_stopped_or_other_phase(native_progress, change):
    state, _, reads = native_progress
    state.update(change)
    assert ui._laufender_quellenfortschritt(state, aktueller_lauf=True) is None
    assert reads == []


def test_no_native_query_for_archive_ambiguous_task_or_changed_source(native_progress):
    state, _, reads = native_progress
    assert ui._laufender_quellenfortschritt(state, aktueller_lauf=False) is None
    state["entries"].append(dict(state["entries"][0], signal_ref=45))
    assert ui._laufender_quellenfortschritt(state, aktueller_lauf=True) is None
    state["entries"].pop()
    state["entries"][0]["quellen_uid"] = "foreign-source-owner"
    assert ui._laufender_quellenfortschritt(state, aktueller_lauf=True) is None
    assert reads == []


def test_native_status_timeout_stays_silent_and_preserves_saved_detail(native_progress, monkeypatch):
    state, _, reads = native_progress

    class UnavailableClient:
        def update_status(self):
            raise TimeoutError("test timeout")

    monkeypatch.setattr(ui.quellen, "client_fuer_quelle", lambda *args, **kwargs: UnavailableClient())
    at = _app()
    assert not at.exception, at.exception
    assert not at.error and not at.warning
    assert not any("Quellenclient" in e.value for e in at.caption)
    assert any(state["detail"] in e.value for e in at.caption)


def test_additional_progress_does_not_break_ui_if_source_registry_is_unreadable(native_progress, monkeypatch):
    state, _, reads = native_progress

    def unavailable_source(source_id):
        raise OSError("test registry temporarily unavailable")

    monkeypatch.setattr(ui.db, "get_quelle", unavailable_source)
    at = _app()
    assert not at.exception, at.exception
    assert any(state["detail"] in e.value for e in at.caption)
    assert not at.error and not at.warning
    assert reads == []


def test_unknown_and_explicit_source_financial_stamps_never_use_get_time_as_fallback():
    rows = ui.ergebnis_tabelle([_quellenwerte(gewinn_usd=0, rendite_quelle_pct=0),
                               _quellenwerte(finanzdaten_stand="2026-09-30T22:00:00Z")])
    assert rows.iloc[0]["Quellengewinn USD"] == 0
    assert rows.iloc[0]["Quellrendite %"] == 0
    assert rows.iloc[0]["Finanzdatenstand (Quelle)"] == "unbekannt – kein Quellenstand angegeben"
    assert rows.iloc[1]["Finanzdatenstand (Quelle)"] == "2026-09-30T22:00:00Z"
    assert rows.iloc[1]["Quellenwerte gelesen am"] == "2026-10-23T15:30:00+02:00"


@pytest.mark.parametrize("key", prompts.ABONNENTEN_PROMPT_KEYS)
def test_research_prompt_is_complete_and_has_no_old_policy(key):
    values = {name: '{"payload": "literal {regeln_retdd}"}'
              for name in prompts.prompt_placeholders(key)}
    text = prompt_fill.build_abonnenten_prompt(key, **values)
    assert "{laufprofil_json}" not in text
    assert "unter drei Monaten" not in text
    assert "unter 3 Monaten" not in text
    assert "{regeln_retdd}" in text  # Fremdtext wird nicht erneut expandiert.
    assert "\x00" not in text
    before = prompts.prompt_fingerprint([key])
    prompts.save_prompt(key, prompts.load_prompt(key) + "\nWeitere klare Vorgabe.")
    assert prompts.prompt_fingerprint([key]) != before
    prompts.PROMPT_FILES[key].unlink()
    with pytest.raises(prompts.PromptFehlt):
        prompts.load_prompt(key)
    prompts.reset_prompt(key)
    assert prompts.load_prompt(key) == prompts.DEFAULTS[key]


@pytest.mark.parametrize("extra", ["{regeln_retdd}", "{unknown_slot}"])
def test_research_builder_rejects_unscoped_old_rules_and_unknown_slots(extra):
    key = "abonnenten_kurztest"
    prompts.save_prompt(key, prompts.load_prompt(key) + "\n" + extra)
    with pytest.raises(LlmError):
        prompt_fill.build_abonnenten_prompt(
            key, laufprofil_json="{}", kandidat_json="{}", forensik_json="{}", trades_json="[]")


def test_admin_research_group_can_edit_and_reset_missing_template(backend):
    from mqlkiscanner import downloader_sync, tradeserver_sync
    # Die bestehende Admin-Seite zeigt ansonsten Verbindungsstatus an.
    backend_status = {"ok": False, "konfiguriert": False}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(downloader_sync, "verbindungs_status", lambda: backend_status)
        patch.setattr(tradeserver_sync, "verbindungs_status", lambda: backend_status)
        page = Path(__file__).resolve().parents[1] / "app_pages" / "admin.py"
        at = AppTest.from_file(str(page), default_timeout=60).run()
        assert not at.exception, at.exception
        at.segmented_control(key="admin_prompt_group").set_value("Abonnentenstatistik").run()
        assert not at.exception, at.exception
        assert at.segmented_control(key="admin_prompt_choice").options == [
            prompts.prompt_metadata(key)["label"] for key in prompts.ABONNENTEN_PROMPT_KEYS]
        at.text_input(key="admin_abonnenten_kurztest_modell").set_value("custom-model")
        at.button(key="admin_abonnenten_kurztest_modell_save").click().run()
        assert config.load_settings()["abonnenten_kurztest_modell"] == "custom-model"
        prompts.PROMPT_FILES["abonnenten_kurztest"].unlink()
        at.run()
        assert not at.exception, at.exception
        at.button(key="admin_prompt_reset").click().run()
        assert not at.exception, at.exception
        assert prompts.load_prompt("abonnenten_kurztest") == prompts.DEFAULTS["abonnenten_kurztest"]
