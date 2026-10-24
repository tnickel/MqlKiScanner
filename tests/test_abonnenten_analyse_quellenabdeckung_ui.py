"""Quellenabdeckung des eingefrorenen Auftrags ohne neue Quellenabfragen."""
from copy import deepcopy

import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import abonnenten_analyse_ui as ui


@pytest.fixture
def coverage_state():
    entries = []
    for index in range(200):
        mql = {"signal_ref": index + 1, "quelle": "mql5", "data_done": True,
               "eligible": index < 39, "retdd_jahr": 4, "status": "fertig"}
        if index < 37:
            mql["abo_trend"] = {"verified": True, "delta_7": 0, "coverage": {"7_tage": True}}
        if index < 5:
            mql.update(endpruefung_status="abgeschlossen", bericht_markdown="Verified final report")
        entries.append(mql)
        entries.append({"signal_ref": 1000 + index, "quelle": "pelik", "data_done": False,
                        "status": "datenluecke", "grund": "Session ungültig (historischer Datenversuch)"})
        entries.append({"signal_ref": 2000 + index, "quelle": "robo", "data_done": True,
                        "auswertung_typ": "quellenprofitabilitaet", "eligible": True,
                        "retdd_jahr": 5, "rang": 1, "gewinn_usd": 500})
        entries.append({"signal_ref": 3000 + index, "quelle": "zulu", "data_done": False,
                        "status": "fertig", "kurztest": {"kurzurteil": "Addon vorhanden"},
                        "grund": "Kapitalbasis fehlt"})
    snapshots = {source: {"status": "fertig", "stand": "2026-10-23T16:11:32+02:00", "anzahl": 200}
                 for source in ("mql5", "pelik", "robo", "zulu")}
    snapshots["vant"] = {"status": "fehler", "grund": "API-Fehler 1223; keine Auswahl übernommen"}
    return {"id": "frozen-coverage", "quellen": ["mql5", "pelik", "robo", "zulu", "vant"],
            "entries": entries, "snapshot_quellen": snapshots, "kurztest_optional": True}


def test_frozen_source_coverage_keeps_retdd_trends_and_source_profit_separate(coverage_state, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Coverage must not query current sources or storage")

    monkeypatch.setattr(ui.db, "list_quellen", forbidden)
    monkeypatch.setattr(ui.quellen, "client_fuer_quelle", forbidden)
    original = deepcopy(coverage_state)
    table = ui.quellenabdeckung_tabelle(coverage_state).set_index("Quelle")
    assert table.index.tolist() == ["mql5", "pelik", "robo", "zulu", "vant"]
    assert table.loc["mql5", "Eingefrorene Anbieter"] == 200
    assert table.loc["mql5", "Für RetDD-Auswahl geeignet"] == 39
    assert table.loc["mql5", "Native 7-Tage-Trends"] == 37
    assert table.loc["mql5", "Endberichte abgeschlossen"] == 5
    assert table.loc["robo", "Separate Quellenwerte"] == 200
    assert table.loc["robo", "RetDD-Daten vollständig"] == 0
    assert table.loc["robo", "Für RetDD-Auswahl geeignet"] == 0
    assert table.loc["pelik", "RetDD-Daten vollständig"] == 0
    assert "200 gespeicherte Datenlücken: Session ungültig" in table.loc["pelik", "Historische offene Punkte"]
    assert table.loc["zulu", "RetDD-Daten vollständig"] == 0
    assert table.loc["vant", "Eingefrorene Anbieter"] == 0
    assert "1223" in table.loc["vant", "Historische offene Punkte"]
    assert table.loc["pelik", "Historischer Snapshotstand"] == "2026-10-23T16:11:32+02:00"
    assert coverage_state == original


def test_source_coverage_caption_never_calls_old_session_failure_a_current_login_block(coverage_state):
    at = AppTest.from_string("""
import streamlit as st
from mqlkiscanner.abonnenten_analyse_ui import _render_quellenabdeckung
_render_quellenabdeckung(st.session_state['coverage_state'])
""", default_timeout=30)
    at.session_state["coverage_state"] = coverage_state
    at.run()
    assert not at.exception
    assert any("Historischer Auftragsstand, kein aktueller Verbindungs- oder Loginstatus" in e.value for e in at.caption)
    assert any("Robo-Gewinnangaben" in e.value and "nicht als vollständige RetDD-Daten" in e.value for e in at.caption)
    assert not at.warning and not at.error
    assert at.table[0].value["Quelle"].tolist() == ["mql5", "pelik", "robo", "zulu", "vant"]


def test_end_report_and_native_trend_need_their_completed_stored_proof():
    state = {"quellen": ["mql5"], "entries": [
        {"quelle": "mql5", "endpruefung_status": "abgeschlossen", "bericht_markdown": ""},
        {"quelle": "mql5", "endpruefung_status": "abgeschlossen", "bericht_markdown": "Old",
         "review_pending": True},
        {"quelle": "mql5", "endpruefung_status": "abgeschlossen", "bericht_markdown": "Old",
         "ki_klaerung_gesperrt": True},
        {"quelle": "mql5", "abo_trend": {"verified": True, "delta_7": 2}},
        {"quelle": "mql5", "abo_trend": {"verified": False, "delta_7": 2, "coverage": {"7_tage": True}}},
    ]}
    row = ui.quellenabdeckung_tabelle(state).iloc[0]
    assert row["Endberichte abgeschlossen"] == 0
    assert row["Native 7-Tage-Trends"] == 0
