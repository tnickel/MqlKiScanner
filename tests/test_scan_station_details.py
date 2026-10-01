# -*- coding: utf-8 -*-
"""Station details must open with the current session's data."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import config, db, downloader_sync, pipeline

ROOT = Path(__file__).resolve().parents[1]
STATIONS = (
    ("listen", "Station 1"),
    ("kandidaten", "Station 2"),
    ("forensik", "Station 3"),
    ("llm", "Station 4"),
    ("portfolio", "Station 5"),
    ("downloader", "Station 6"),
)


@pytest.fixture(autouse=True)
def no_connection_probe(monkeypatch):
    """Station details read saved data; connection badges do not contact servers."""
    monkeypatch.setattr(downloader_sync, "verbindungs_status", lambda **kwargs: {
        "konfiguriert": False, "ok": False, "quellen": [],
    })
    config.save_settings({**config.load_settings(), "rest_api_enabled": False})


def _app(station: str | None = None) -> AppTest:
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    if station:
        at.query_params = {"station": station, "unrelated": "keep-me"}
    return at


def _dialog(at: AppTest):
    assert not at.exception, at.exception
    dialogs = at.get("dialog")
    assert len(dialogs) == 1
    return dialogs[0]


def _text(elements) -> str:
    return "\n".join(
        item.value for kind in ("markdown", "caption", "info", "warning")
        for item in elements.get(kind)
    )


@pytest.mark.parametrize("station,title", STATIONS)
def test_legacy_station_url_opens_explanation_and_table(station, title):
    at = _app(station).run()
    dialog = _dialog(at)
    assert title in dialog.proto.dialog.title
    assert "Was passiert hier?" in _text(dialog)
    assert dialog.get("dataframe"), "Jede Station benötigt ihre Detailtabelle"
    assert "station" not in at.query_params
    assert at.query_params["unrelated"] == ["keep-me"]
    at.run()
    assert not at.exception, at.exception
    assert not at.get("dialog"), "Die Stations-URL darf den Dialog nicht erneut öffnen"


def test_station_one_shows_dynamic_sources_and_saved_signals():
    db.init_db()
    db.add_quelle("custom_a", "Meine Quelle A", "http://source-a.invalid", aktiv=True)
    db.add_quelle("custom_b", "Meine Quelle B", "http://source-b.invalid", aktiv=True)
    config.save_settings({**config.load_settings(), "listen_modus": "quellen"})
    rows = [
        {"id": 1001, "name": "Alpha", "quelle": "custom_a", "wochen": 30,
         "abonnenten": 7, "status": "AUSGEWAEHLT", "grund": "Vorfilter bestanden"},
        {"id": 1002, "name": "Beta", "quelle": "custom_a", "wochen": 40,
         "abonnenten": 8, "status": "AUSGEWAEHLT", "grund": "Vorfilter bestanden"},
        {"id": 2001, "name": "Gamma", "quelle": "custom_b", "wochen": 50,
         "abonnenten": 9, "status": "AUSGEWAEHLT", "grund": "Vorfilter bestanden"},
    ]
    (config.DATA_DIR / "auswahl_begruendung.json").write_text(json.dumps({
        "zeitstempel": "2026-10-02 09:00:00", "top_n_export": 10, "eintraege": rows,
    }), encoding="utf-8")
    at = _app("listen").run()
    dialog = _dialog(at)
    tables = dialog.get("dataframe")
    assert len(tables) == 2
    sources, signals = (table.value for table in tables)
    rest_sources = sources[sources["Zugriff"] == "REST"]
    assert set(rest_sources["Quelle"]) == {"Meine Quelle A", "Meine Quelle B"}
    assert rest_sources.set_index("Kürzel")["Geladene Signale"].to_dict() == {
        "custom_a": 2, "custom_b": 1,
    }
    assert sources.loc[sources["Zugriff"] == "MQL5-Direkt", "Im Scan aktiv"].tolist() == ["Nein"]
    assert set(signals["Signal"]) == {"Alpha", "Beta", "Gamma"}
    assert set(signals["Quelle"]) == {"custom_a", "custom_b"}


@pytest.mark.parametrize("station", ["forensik", "llm"])
def test_station_details_read_scan_results_from_current_session(station):
    result = pipeline.ScanResult(
        id=1001, name="Aktuelles Signal", ampel="🟡", forensik_vorhanden=True,
        score=67.0, trading_dd_pct=12.5, ertrag_monat_pct_forensik=8.0,
        trade_analyse="Trade-Bericht", risiko_analyse="Risiko-Bericht",
        gesamtbericht="Gesamt-Bericht", kurzfassung="Sitzungsbefund",
    )
    at = _app(station)
    at.session_state["scan_results"] = [result]
    at.run()
    dialog = _dialog(at)
    table = dialog.get("dataframe")[0].value
    assert list(table["Signal"]) == ["Aktuelles Signal"]
    if station == "forensik":
        assert table.loc[0, "Trading-DD %"] == 12.5
        assert table.loc[0, "Ertrag/M"] == 8.0
    else:
        assert table.loc[0, "Trade-Analyse"] == "✓"
        assert table.loc[0, "Risiko-Analyse"] == "✓"
        assert table.loc[0, "Gesamtbericht"] == "✓"
        assert table.loc[0, "Kurzfassung"] == "Sitzungsbefund"


def test_portfolio_station_reads_saved_session_text_fallback():
    at = _app("portfolio")
    at.session_state["portfolio_bericht"] = "PORTFOLIO AUS AKTUELLER SITZUNG"
    at.run()
    assert "PORTFOLIO AUS AKTUELLER SITZUNG" in _text(_dialog(at))


def test_component_station_event_opens_dialog_without_discarding_session():
    """Send the CCv2 trigger payload used by double-clicks to the real app."""
    at = _app().run()
    assert not at.exception, at.exception
    stepper = next(item for item in at.get("bidi_component")
                   if item.key == "scan_station_stepper")
    rendered = json.loads(stepper.proto.json)["html"]
    assert all(f'data-station="{station}"' in rendered for station, _ in STATIONS)
    result = pipeline.ScanResult(id=1001, name="BLEIBT IN DER SITZUNG",
                                 forensik_vorhanden=True, ampel="🟡")
    at.session_state["scan_results"] = [result]
    at.query_params = {"unrelated": "keep-me"}
    widget_states = at._tree.get_widget_states()
    # AppTest does not serialize unsupported CCv2 widgets automatically.
    state = widget_states.widgets.add()
    state.id = stepper.proto.id
    state.json_value = "{}"
    trigger = widget_states.widgets.add()
    trigger.id = f"$$STREAMLIT_INTERNAL_KEY_{stepper.proto.id}__events"
    trigger.json_trigger_value = json.dumps([{"event": "station", "value": "forensik"}])
    at._run(widget_states)
    dialog = _dialog(at)
    assert "Station 3" in dialog.proto.dialog.title
    assert dialog.get("dataframe")[0].value.loc[0, "Signal"] == "BLEIBT IN DER SITZUNG"
    assert at.session_state["scan_results"][0] is result
    assert at.query_params == {"unrelated": ["keep-me"]}
    assert "_scan_station_dialog" not in at.session_state


def test_station_one_distinguishes_direct_and_rest_signals_from_session():
    db.init_db()
    rest_id = db.add_quelle("mql5", "Mein Downloader", "http://mql5.invalid", aktiv=False)
    custom_id = db.add_quelle("custom", "Weitere Quelle", "http://custom.invalid", aktiv=True)
    db.store_quell_pruefung(rest_id, {"status": "fehler", "text": "Technische Details"})
    config.save_settings({**config.load_settings(), "listen_modus": "beides"})
    (config.DATA_DIR / "auswahl_begruendung.json").write_text(json.dumps({
        "eintraege": [{"id": 9999, "name": "VERALTET", "quelle": "mql5"}],
    }), encoding="utf-8")
    at = _app("listen")
    at.session_state["scan_signals"] = [
        {"id": 1001, "name": "Direkt von MQL5"},
        {"id": 1002, "name": "Aus dem Downloader", "quelle_kuerzel": "mql5", "quelle_id": rest_id},
        {"id": 2001, "name": "Aus weiterer Quelle", "quelle_kuerzel": "custom", "quelle_id": custom_id},
    ]
    at.run()
    sources, signals = (table.value for table in _dialog(at).get("dataframe"))
    source_rows = sources.set_index(["Kürzel", "Zugriff"])
    assert source_rows.loc[("mql5", "MQL5-Direkt"), "Geladene Signale"] == 1
    assert source_rows.loc[("mql5", "REST"), "Geladene Signale"] == 1
    assert source_rows.loc[("mql5", "REST"), "Im Scan aktiv"] == "Nein"
    assert source_rows.loc[("mql5", "REST"), "Letzter Verbindungstest"] == "Nicht erreichbar"
    assert source_rows.loc[("custom", "REST"), "Geladene Signale"] == 1
    signal_rows = signals.set_index("Signal")
    assert set(signal_rows.index) == {"Direkt von MQL5", "Aus dem Downloader", "Aus weiterer Quelle"}
    assert signal_rows.loc["Direkt von MQL5", "Zugriff"] == "MQL5-Direkt"
    assert signal_rows.loc["Aus dem Downloader", "Zugriff"] == "REST"
    assert signal_rows.loc["Aus weiterer Quelle", "Quelle"] == "custom"
