"""Critical checks of the follow-up review: keep unknowns and report provenance."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import abonnenten_analyse_ui as ui, db
from mqlkiscanner import equity_studie_ui as studie_ui


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("builder", [ui.ergebnis_tabelle, ui.daten_tabelle])
def test_numeric_text_is_not_a_reason_for_generic_numeric_coercion(builder):
    entry = {"quelle": "mql5", "id": 123, "name": "00123", "signal_ref": "000456"}
    table = builder([entry])
    assert table.iloc[0]["Strategie"] == "00123"
    assert table["Nettogewinn USD"].isna().all()
    assert pd.api.types.is_numeric_dtype(table["Nettogewinn USD"])


@pytest.mark.parametrize("with_curve", [False, True])
def test_sparkline_image_column_accepts_all_null_and_mixed_data_without_filling(with_curve):
    db.init_db()
    db.add_quelle("fake", "Synthetic", "http://fake.invalid")
    db.katalog_upsert_many("fake", [{"signal_id": sid, "name": f"Synthetic {sid}",
        "platform": "mt5", "url": "", "version": "mql5", "abonnenten": 3,
        "wochen": None, "risiko": None} for sid in (1, 2)])
    now = datetime.now()
    db.store_history_points(1, "mql5", [
        {"timestamp": (now - timedelta(days=1)).isoformat(), "subscribers": 3}], quelle="fake")
    if with_curve:
        db.store_history_points(1, "mql5", [
            {"timestamp": now.isoformat(), "subscribers": 4}], quelle="fake")
    app = AppTest.from_file(ROOT / "app_pages/abonnenten_statistik.py", default_timeout=30).run()
    assert not app.exception
    element = app.dataframe(key="abonnenten_tabelle_alle")
    images = element.value["Verlauf 30 T"]
    assert images.isna().sum() == (1 if with_curve else 2)
    if with_curve:
        assert images.dropna().iloc[0].startswith("data:image/png;base64,")
    else:
        arrow = pa.ipc.open_stream(element.proto.arrow_data.data).read_all()
        assert pa.types.is_null(arrow["Verlauf 30 T"].type)
    config = json.loads(element.proto.columns)
    assert config["Verlauf 30 T"]["type_config"]["type"] == "image"
    assert element.proto.HasField("placeholder") and element.proto.placeholder == ""


def _diagnose(data):
    app = AppTest.from_string(
        "from mqlkiscanner.equity_studie_ui import _symbol_diagnose\n"
        f"_symbol_diagnose({data!r})", default_timeout=20).run()
    assert not app.exception
    return app


def test_study_detail_shows_saved_broker_names_and_terminal_provenance():
    data = {"symbol_substitutionen": {"BITCOIN": "BTCUSD"}, "symbol_herkunft": {
        "BITCOIN": {"terminal": "synthetic-terminal-A", "broker_symbol": "BTCUSD"},
        "EURUSD": {"terminal": "synthetic-terminal-B", "broker_symbol": "EURUSD"}}}
    original = deepcopy(data)
    app = _diagnose(data)
    table = next(e.value for e in app.dataframe if "Verwendeter Brokername" in e.value)
    table = table.set_index("Trade-Symbol")
    assert table.loc["BITCOIN", "Verwendeter Brokername"] == "BTCUSD"
    assert table.loc["BITCOIN", "Kurs-Terminal"] == "synthetic-terminal-A"
    assert table.loc["EURUSD", "Zuordnung"] == "Identischer Brokername belegt"
    assert any("Namenszuordnung allein" in e.value for e in app.info)
    assert data == original


def test_old_study_without_name_evidence_does_not_claim_identical_broker_symbol():
    app = _diagnose({"symbol_feeds": {"EURUSD": "synthetic-terminal"}})
    assert not app.dataframe
    assert any("Kein gespeicherter Beleg" in e.value and "Brokername" in e.value for e in app.caption)


def test_study_detail_uses_selected_report_not_last_attempt_metadata():
    data = {"symbol_herkunft": {"BITCOIN": {"terminal": "selected-terminal", "broker_symbol": "BITCOIN"}},
            "symbol_substitutionen": {}, "kursdaten_versuche": [{
                "symbol_herkunft": {"BITCOIN": {"terminal": "later-terminal", "broker_symbol": "BTCUSD"}},
                "symbol_substitutionen": {"BITCOIN": "BTCUSD"}}]}
    app = _diagnose(data)
    table = next(e.value for e in app.dataframe if "Verwendeter Brokername" in e.value)
    assert table.iloc[0]["Verwendeter Brokername"] == "BITCOIN"
    assert table.iloc[0]["Kurs-Terminal"] == "selected-terminal"


@pytest.mark.parametrize("frame,label", [
    ("broker", "CSV-/Brokerzeit"),
    ("referenzkurszeit", "Referenzkurszeit (MT5-H1)"),
    (None, "Zeitbasis unbekannt"),
])
def test_plotly_axis_uses_saved_frame_without_timezone_or_coordinate_change(frame, label):
    stamp = int(datetime(2026, 1, 2, 12, 30, tzinfo=timezone.utc).timestamp())
    data = {"zeitbasis": {"frame": frame}, "kennzahlen": {}, "punkte": [
        {"t": stamp, "equity": 1000, "realisiert": 1000, "floating": 0, "messpunkt": True},
        {"t": stamp + 3600, "equity": 990, "realisiert": 1000, "floating": -10, "messpunkt": True}]}
    original = deepcopy(data)
    figure = studie_ui._chart(data, 1000, 50)
    assert figure.layout.xaxis2.title.text == label
    assert figure.data[0].x[0] == datetime(2026, 1, 2, 12, 30)
    assert figure.data[0].x[0].tzinfo is None
    assert studie_ui._als_datetime(None) is None
    assert data == original


def test_period_display_keeps_wall_time_digits_and_does_not_change_saved_iso_data():
    periods = [{"von": "2026-01-02T12:30:00+00:00", "bis": "2026-01-03T14:00:00+03:00",
                "bekannter_gmt_h": None}]
    original = deepcopy(periods)
    app = _diagnose({"zeitbasis": {"frame": "referenzkurszeit", "perioden": periods}})
    table = app.dataframe[0].value
    assert table.iloc[0]["von"] == "2026-01-02 12:30:00"
    assert table.iloc[0]["bis"] == "2026-01-03 14:00:00"
    assert any("Periodengrenzen: CSV-/Brokerzeit" in e.value for e in app.caption)
    assert periods == original


def test_coverage_plot_keeps_its_reference_frame_when_equity_curve_is_broker_frame():
    data = {"zeitbasis": {"frame": "broker"}, "ueberdeckung": [{"symbol": "EURUSD", "aktiv_h": 1,
        "segmente": [[1767357000, 1767360600]], "luecken": []}]}
    app = AppTest.from_string(
        "from mqlkiscanner.equity_studie_ui import _ueberdeckung_chart\n"
        f"_ueberdeckung_chart({data!r}, 'synthetic')", default_timeout=20).run()
    assert not app.exception
    figure = json.loads(app.get("plotly_chart")[0].proto.spec)
    assert figure["layout"]["xaxis"]["title"]["text"] == "Referenzkurszeit (MT5-H1)"
    assert not figure["data"][0]["x"][0].endswith(("Z", "+00:00"))
