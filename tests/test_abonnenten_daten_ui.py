"""Aktuelle Stufe-1-Oberfläche: Daten, vollständige Auswahl und keine Berichtsaktionen."""
from copy import deepcopy
from hashlib import sha256
import io
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import abonnenten_analyse as backend_module
from mqlkiscanner import abonnenten_analyse_ui as ui
from mqlkiscanner import abonnenten_statistik, db
from mqlkiscanner.llm import prompts


def _entries():
    return [
        {"signal_ref": 1, "id": 23, "quelle": "mql5", "name": "Measured", "abonnenten": 20,
         "account_currency": "USD", "forensik": {"stats": {"net": 123.5}}, "eligible": True,
         "data_done": True, "equity_dd_pct": 12.5, "retdd_jahr": 4, "dauer_monate": 3, "trades": 100,
         "rendite_zeitraum_pct": 10, "equity": {"abdeckung_pct_raw": 98.5},
         "abo_trend": {"verified": True, "delta_7": 4, "coverage": {"7_tage": True}},
         "status": "ki_fehler", "review_pending": True, "ki_klaerung_gesperrt": True,
         "kurztest": {"kurzurteil": "PRIVATE SHORT ARTIFACT"}, "bericht_markdown": "PRIVATE REPORT ARTIFACT",
         "ki_fehler": "PRIVATE MODEL ERROR", "bericht_redaktion_result": {"private": "PRIVATE EDITORIAL"}},
        {"signal_ref": 2, "id": 24, "quelle": "pelik", "name": "Incomplete", "abonnenten": 10,
         "data_done": False, "eligible": False, "status": "datenluecke", "grund": "Kapitalbasis fehlt"},
        {"signal_ref": 3, "id": 25, "quelle": "robo", "name": "Source profit", "abonnenten": 12,
         "data_done": True, "auswertung_typ": "quellenprofitabilitaet", "gewinn_usd": 800,
         "rendite_quelle_pct": 25, "rendite_quelle_monate": 3, "equity_dd_pct": 2, "retdd_jahr": 5},
    ]


class DataBackend:
    rank_datamodus = staticmethod(backend_module.rank_datamodus)

    def __init__(self):
        self.states = {"old": {"id": "old", "created_at": "2026-10-23", "updated_at": "2026-10-24",
            "status": "wartet_budget", "phase": "top5_analysen", "detail": "PRIVATE MODEL PROGRESS",
            "logs": ["PRIVATE MODEL LOG"], "quellen": ["mql5", "pelik", "robo"], "entries": _entries()}}
        self.started = []
        self.cloned = []
        self.resumed = []

    def laeufe(self):
        return [{"id": key, "created_at": row["created_at"]} for key, row in reversed(self.states.items())]

    def zustand(self, run_id):
        return self.states[run_id]

    def starten(self, *args, **kwargs):
        raise AssertionError("Historical report workflow must never start")

    fortsetzen = starten

    def daten_starten(self, chosen, **kwargs):
        self.started.append((chosen, kwargs))
        self._new()
        return "data"

    def _new(self):
        self.states["data"] = {**deepcopy(self.states["old"]), "id": "data", "workflow_modus": "daten_ohne_ki_v1",
                               "daten_status": "teilweise", "daten_vollstaendig": False, "laeuft": False}

    def daten_aus_lauf(self, run_id, *, fortsetzen=False):
        self.cloned.append((run_id, fortsetzen))
        self._new()
        return "data"

    def daten_fortsetzen(self, run_id):
        self.resumed.append(run_id)
        self.states[run_id].update(laeuft=True, daten_status="laeuft")
        return True


@pytest.fixture
def backend(monkeypatch):
    backend = DataBackend()
    monkeypatch.setattr(ui, "_backend", lambda: backend)
    return backend


def _app():
    return AppTest.from_string("""
from mqlkiscanner.abonnenten_analyse_ui import render_daten_start_button, render_daten_results
render_daten_start_button()
render_daten_results()
""", default_timeout=30).run()


def test_first_table_keeps_every_selected_provider_and_ignores_historical_report_flags(backend, monkeypatch):
    original = deepcopy(backend.states)
    monkeypatch.setattr(ui, "_redaktion_geprueft", lambda *a, **k: pytest.fail("No report module in stage 1"))
    at = _app()
    assert not at.exception
    table = at.dataframe[0].value
    assert set(table["Strategie"]) == {"Measured", "Incomplete", "Source profit"}
    measured = table.set_index("Strategie").loc["Measured"]
    assert measured["Datenrang"] == 1, "Historical model flags must not remove a measured strategy"
    assert measured["Nettogewinn USD"] == 123.5 and measured["Max. gemessener Equity-DD %"] == 12.5
    assert table.set_index("Strategie").loc["Incomplete", "Status"] == "Datenlücke"
    assert not any("Kurz" in metric.label or "Top-5" in metric.label for metric in at.metric)
    visible = "\n".join(str(e.value) for kind in (at.caption, at.markdown, at.info, at.warning) for e in kind)
    assert "PRIVATE" not in visible
    assert not any("Analyse fortsetzen" == button.label for button in at.button)
    assert backend.states == original and not backend.started and not backend.resumed and not backend.cloned


def test_data_csv_has_only_measurements_and_preserves_unknowns_and_source_profit():
    data = ui.daten_csv(_entries(), {"id": "old"})
    frame = pd.read_csv(io.BytesIO(data), sep=";").set_index("Strategie")
    assert "PRIVATE" not in data.decode("utf-8-sig")
    assert not any(any(word in column for word in ("KI", "Bericht", "JSON", "Prompt", "Budget")) for column in frame.columns)
    assert pd.isna(frame.loc["Incomplete", "Nettogewinn USD"])
    assert pd.isna(frame.loc["Incomplete", "Nettozuwachs 7 Tage"])
    assert frame.loc["Source profit", "Quellengewinn USD"] == 800
    assert pd.isna(frame.loc["Source profit", "Max. gemessener Equity-DD %"])
    assert pd.isna(frame.loc["Source profit", "Jahres-RetDD"])
    assert pd.isna(frame.loc["Source profit", "Nettogewinn USD"])


def test_historical_data_requires_explicit_new_data_job_before_data_only_resume(backend):
    at = _app()
    assert not any(str(button.key).startswith("abonnenten_daten_resume_") for button in at.button)
    at.button(key="abonnenten_daten_clone_old").click().run()
    assert not at.exception
    assert backend.cloned == [("old", False)] and not backend.resumed
    at.button(key="abonnenten_daten_resume_data").click().run()
    assert not at.exception
    assert backend.resumed == ["data"]


def test_start_dialog_has_no_prompt_key_or_parallelism_prerequisite(backend, monkeypatch):
    db.init_db()
    db.add_quelle("mql5", "MQL", "http://fake.invalid")
    # Frische-Schranke (25.10.): Ohne frische Messung ist der Start-Button
    # gesperrt — der Test misst frisch, damit er den Startweg erreicht.
    from datetime import datetime, timedelta
    db.store_history_points(7, "mql5", [{
        "timestamp": (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds"),
        "subscribers": 9}], quelle="mql5")
    monkeypatch.setattr(prompts, "fehlende_vorlagen", lambda *a, **k: pytest.fail("No prompt checks"))
    at = _app()
    at.button(key="abonnenten_daten_oeffnen").click().run()
    assert not at.exception
    assert not at.number_input
    # Nutzer-Entscheidung 24.10. abends: Vor dem Start wird gefragt, ob nur
    # fehlende Tradelisten geladen (Fortsetzen nach Abbruch) oder alle
    # überschrieben werden; Standard ist "nur fehlende".
    assert len(at.radio(key="abonnenten_daten_tradelisten").options) == 2
    at.button(key="abonnenten_daten_start").click().run()
    assert not at.exception
    assert backend.started == [(["mql5"], {"retdd_gewicht": 30, "dd_grenze": None,
                                           "tradelisten_modus": "fehlt",
                                           "akzeptiere_veraltete_abos": False})]


def test_page_open_never_starts_download_or_reads_saved_report_artifacts(backend, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No automatic downloads or report reads on page open")

    monkeypatch.setattr(abonnenten_statistik, "sync", forbidden)
    monkeypatch.setattr(db, "analyses_zaehler_alle", forbidden)
    monkeypatch.setattr(db, "get_latest_analysis", forbidden)
    monkeypatch.setattr(db, "downloader_reports_liste_alle", forbidden)
    page = Path(__file__).resolve().parents[1] / "app_pages" / "abonnenten_statistik.py"
    at = AppTest.from_file(page, default_timeout=30).run()
    assert not at.exception
    assert len(at.dataframe[0].value) == 3
    assert not any(any(word in str(button.label) for word in ("PDF", "Doku", "Analyse")) for button in at.button)


def test_selected_stage1_detail_offers_only_verified_saved_trade_export(tmp_path):
    raw = b"Time;Type;Volume\n2026.10.01;Buy;0.01\n"
    path = tmp_path / "frozen.csv"
    path.write_bytes(raw)
    entry = {**_entries()[0], "trades_path": str(path), "trades_sha256": sha256(raw).hexdigest(),
             "trade_history_complete": True}
    script = "from mqlkiscanner.abonnenten_analyse_ui import _render_daten_detail\n" + f"_render_daten_detail({entry!r}, {{'id':'frozen'}})"
    at = AppTest.from_string(script, default_timeout=30).run()
    assert not at.exception
    assert any(e.proto.label == "Gespeicherten Trade-Export herunterladen" for e in at.get("download_button"))
    assert any("Vollständigkeit des gelieferten Exportfensters belegt" in e.value for e in at.caption)
    path.write_bytes(b"changed")
    at.run()
    assert not at.exception
    assert not at.get("download_button")
    assert any("Trade-Export nicht belegt" in e.value for e in at.warning)


def test_missing_trade_count_is_not_zero_and_unproven_export_is_not_complete():
    entry = {**_entries()[1], "trades": 0}
    row = ui.daten_tabelle([entry]).iloc[0]
    assert pd.isna(row["Trades"])
    assert "nicht belegt" in row["Trade-Export-Status"]


def _model(**changes):
    model = {"version": "abonnenten_modellkapital_v1", "status": "berechnet", "grund": "",
             "startkapital_usd": 2500, "kapital_methode": "Lotschätzung",
             "kapital_hinweis": "Belegte Referenz und medianes Volumen verwendet.",
             "kapital_details": {"referenzen": 3, "median_lot": 0.1},
             "annahme_kapitalfluesse": "keine", "ignorierte_kapitalfluesse": 2,
             "nettogewinn_usd": 123.5, "rendite_zeitraum_pct": 4.94, "cagr_jahr_pct": 24,
             "equity_dd_pct": 6, "equity_dd_usd": 180, "retdd_jahr": 4,
             "closing_dd_pct": 2, "closing_dd_usd": 55, "waehrung": "USD",
             "trade_sha256": "model-trade-sha", "trade_anzahl": 100,
             "zeit_von": "2026-08-01", "zeit_bis": "2026-10-01", "h1_abdeckung_pct": 99,
             "berechnet_am": "2026-10-24T10:30:00+02:00"}
    model.update(changes)
    return model


def test_model_values_and_measured_values_are_separate_in_table_and_csv():
    entry = {**_entries()[0], "modell": _model(equity_dd_pct=8, retdd_jahr=3)}
    original = deepcopy(entry)
    row = ui.daten_tabelle([entry]).iloc[0]
    assert row["Modell-Startkapital USD"] == 2500
    assert row["Modell-Kapitalbasis/Herkunft"] == "Lotschätzung"
    assert row["Modell-Kapitalhinweis"] == entry["modell"]["kapital_hinweis"]
    assert row["Modell-Equity-DD inkl. Floating %"] == 8 and row["Modell-Jahres-RetDD"] == 3
    assert row["Max. gemessener Equity-DD %"] == 12.5 and row["Jahres-RetDD"] == 4
    exported = pd.read_csv(io.BytesIO(ui.daten_csv([entry])), sep=";").iloc[0]
    assert exported["Modell-Kapitalflussannahme"] == "keine"
    assert exported["Im Modell ignorierte Kapitalflüsse"] == 2
    assert "median_lot: 0.1" in exported["Modell-Kapitaldetails"]
    assert "annualisierte Modellwerte" in exported["Modell-Annahmehinweis"]
    assert entry == original


def test_model_capital_fallback_does_not_invent_missing_floating_dd_or_retdd():
    entry = {**_entries()[0], "modell": _model(startkapital_usd=10000, kapital_methode="10k-Fallback",
              status="datenluecke", equity_dd_pct=None, equity_dd_usd=None, retdd_jahr=None, closing_dd_pct=22,
              grund="H1-Kurse fehlen")}
    row = ui.daten_tabelle([entry]).iloc[0]
    assert row["Modell-Startkapital USD"] == 10000 and row["Modellstatus"] == "datenluecke"
    assert pd.isna(row["Modell-Equity-DD inkl. Floating %"]) and pd.isna(row["Modell-Jahres-RetDD"])
    assert row["Modell-Closing-DD %"] == 22 and row["Max. gemessener Equity-DD %"] == 12.5
    no_model = ui.daten_tabelle([_entries()[0]]).iloc[0]
    assert pd.isna(no_model["Modell-Startkapital USD"])
    assert pd.isna(no_model["Modell-Equity-DD inkl. Floating %"])


def test_model_zero_dd_is_zero_but_undefined_retdd_stays_unknown():
    row = ui.daten_tabelle([{**_entries()[0], "modell": _model(
        status="eingeschraenkt", equity_dd_pct=0, retdd_jahr=None)}]).iloc[0]
    assert row["Modell-Equity-DD inkl. Floating %"] == 0
    assert pd.isna(row["Modell-Jahres-RetDD"])


def test_native_import_gap_is_visible_without_changing_the_saved_model():
    entry = {**_entries()[0], "modell": _model(status="datenluecke", equity_dd_pct=None,
             retdd_jahr=None, grund="Gesicherter Trade-Snapshot fehlt"),
             "native_cache_import": {"status": "datenluecke", "grund": "Positionsschluss liegt vor der Eröffnung"}}
    original = deepcopy(entry)
    row = ui.daten_tabelle([entry]).iloc[0]
    assert "Positionsschluss liegt vor der Eröffnung" in row["Modellgrund"]
    assert row["Lokaler Tradeimport-Status"] == "datenluecke"
    assert pd.isna(row["Modell-Equity-DD inkl. Floating %"])
    assert entry == original


@pytest.mark.parametrize("ignored", [2, {"anzahl": 2, "waehrung": "EUR",
                                        "einzahlungen_nativ": 1000, "auszahlungen_nativ": -100}])
def test_model_detail_discloses_capital_method_and_ignored_known_flows(ignored):
    entry = {**_entries()[0], "modell": _model(ignorierte_kapitalfluesse=ignored)}
    at = AppTest.from_string("from mqlkiscanner.abonnenten_analyse_ui import _render_daten_detail\n"
                             f"_render_daten_detail({entry!r}, {{'id':'model'}})", default_timeout=30).run()
    assert not at.exception
    assert any("keine Ein- oder Auszahlungen" in e.value and "2" in e.value for e in at.caption)
    assert any("Lotschätzung" in e.value and entry["modell"]["kapital_hinweis"] in e.value for e in at.caption)
    assert any("median_lot" in e.value for e in at.json)


def test_ignored_native_flows_keep_count_and_currency_separate_in_csv():
    flows = {"anzahl": 2, "waehrung": "EUR", "einzahlungen_nativ": 1000, "auszahlungen_nativ": -100}
    entry = {**_entries()[0], "modell": _model(ignorierte_kapitalfluesse=flows)}
    row = pd.read_csv(io.BytesIO(ui.daten_csv([entry])), sep=";").iloc[0]
    assert row["Im Modell ignorierte Kapitalflüsse"] == 2
    assert row["Ignorierte Einzahlungen (nativ)"] == 1000
    assert row["Ignorierte Auszahlungen (nativ)"] == -100
    assert row["Währung ignorierter Kapitalflüsse"] == "EUR"


def test_model_stock_start_removed_and_legacy_resume_stays_labelled(backend, monkeypatch):
    # Nutzer-Entscheidung 24.10. abends: Der separate Start einer
    # „Modellberechnung aus Bestand" ist entfernt; der Datenauftrag lädt
    # selbst Tradelisten. Historische Bestandsläufe bleiben lesbar.
    backend._new()
    backend.states["data"].update(modell_nur_bestand=True, kapitalmodell_aktiv=True)
    backend.states["data"]["entries"][0]["modell"] = _model()
    at = _app()
    assert not at.exception
    assert not any(str(button.key).startswith("abonnenten_modell_start") for button in at.button)
    # Zahlen am Button (Nutzer-Wunsch 25.10.): geladen/offen sofort sichtbar
    # (Fixture: 2 von 3 Einträgen mit data_done).
    label = at.button(key="abonnenten_daten_resume_data").label
    assert label.startswith("Berechnung aus Bestand fortsetzen — ")
    assert "2/3 geladen, 1 offen" in label
    assert any("30 % Modell-Jahres-RetDD" in e.value for e in at.caption)
    assert any("10.000-USD-Annahme" in e.value for e in at.caption)
    assert set(at.dataframe[0].value["Strategie"]) == {"Measured", "Incomplete", "Source profit"}


def test_model_progress_separates_inherited_facts_and_final_scenario_counts(backend):
    backend._new()
    state = backend.states["data"]
    state.update(modell_nur_bestand=True, kapitalmodell_aktiv=True, laeuft=True,
                 daten_status="laeuft", modell_bearbeitet=1)
    state["entries"][0]["modell"] = _model()
    at = _app()
    assert not at.exception
    assert any("Übernommene Messdaten: 2/3" in e.value for e in at.caption)
    assert any("Modellbearbeitung: 1/3" in e.value for e in at.caption)
    assert at.get("progress")[0].proto.value == 33
    for entry in state["entries"][1:]:
        entry["modell"] = _model(startkapital_usd=10000, status="datenluecke", equity_dd_pct=None, retdd_jahr=None)
    state.update(laeuft=False, daten_status="teilweise", modell_bearbeitet=3, modell_abgeschlossen=True,
                 daten_workflow_abgeschlossen=True, modell_anzahl_mit_startkapital=3,
                 modell_anzahl_mit_dd=1, modell_anzahl_mit_retdd=1)
    at.run()
    assert not at.exception
    metrics = {metric.label: metric.value for metric in at.metric}
    assert metrics["Modell-Startkapital"] == "3/3"
    assert metrics["Modell-Floating-DD"] == metrics["Modell-Jahres-RetDD"] == "1/3"
    assert any("Modellbearbeitung: 3/3" in e.value for e in at.caption)
    assert not backend.started and not backend.cloned and not backend.resumed


@pytest.fixture
def fragments(monkeypatch):
    """Observe the public fragment configuration while retaining native widgets."""
    native_fragment = ui.st.fragment
    registrations = []

    def fragment(*, run_every=None):
        def decorate(body):
            registrations.append((run_every, body))
            return native_fragment(body, run_every=run_every)
        return decorate

    monkeypatch.setattr(ui.st, "fragment", fragment)
    return registrations


@pytest.mark.parametrize("changes, interval", [
    ({"workflow_modus": "daten_ohne_ki_v1", "status": "laeuft", "laeuft": True}, 2.0),
    ({"workflow_modus": "daten_ohne_ki_v1", "status": "geplant", "laeuft": False}, 2.0),
    ({"workflow_modus": "daten_ohne_ki_v1", "status": "abgeschlossen", "laeuft": False}, None),
    ({"workflow_modus": "daten_ohne_ki_v1", "status": "teilweise", "laeuft": False}, None),
    ({"workflow_modus": "daten_ohne_ki_v1", "status": "unterbrochen", "laeuft": False,
      "daten_status": "laeuft"}, None),
    ({"status": "laeuft", "laeuft": True}, None),
])
def test_data_polling_only_for_running_or_starting_data_jobs(backend, fragments, monkeypatch, changes, interval):
    backend.states["old"].update(changes)
    reads = []
    read = backend.zustand
    monkeypatch.setattr(backend, "zustand", lambda run_id: (reads.append(run_id), read(run_id))[1])
    at = _app()
    assert not at.exception
    assert [item[0] for item in fragments] == [interval]
    assert reads == ["old"], "Choosing the timer must not load the full 800-entry state twice"
    assert not backend.started and not backend.cloned and not backend.resumed


def test_periodic_data_completion_reconfigures_fragment_without_a_timer(backend, fragments, monkeypatch):
    backend._new()
    backend.states["data"].update(status="laeuft", daten_status="laeuft", laeuft=True)
    at = _app()
    assert not at.exception and fragments[-1][0] == 2.0
    periodic_callback = fragments[-1][1]
    backend.states["data"].update(status="teilweise", daten_status="teilweise", laeuft=False,
                                  daten_workflow_abgeschlossen=True)
    reruns = []
    native_rerun = ui.st.rerun

    def rerun(*, scope):
        reruns.append(scope)
        raise RuntimeError("completion app rerun")

    monkeypatch.setattr(ui.st, "rerun", rerun)
    with pytest.raises(RuntimeError, match="completion app rerun"):
        periodic_callback()
    assert reruns == ["app"]
    monkeypatch.setattr(ui.st, "rerun", native_rerun)
    at.run()
    assert not at.exception and fragments[-1][0] is None
    assert any("Datenablauf beendet" in item.value for item in at.warning)


def test_dataset_selection_and_explicit_resume_update_polling(backend, fragments):
    backend._new()
    at = _app()
    assert not at.exception and fragments[-1][0] is None
    at.button(key="abonnenten_daten_resume_data").click().run()
    assert not at.exception and fragments[-1][0] == 2.0
    selection_key = at.selectbox[0].key
    at.selectbox(key=selection_key).select("old").run()
    assert not at.exception and fragments[-1][0] is None
    assert at.session_state["abonnenten_daten_lauf"] == "old"
    at.selectbox(key=selection_key).select("data").run()
    assert not at.exception and fragments[-1][0] == 2.0
    assert at.session_state["abonnenten_daten_lauf"] == "data"
    assert backend.resumed == ["data"] and not backend.started and not backend.cloned
