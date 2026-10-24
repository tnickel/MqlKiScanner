"""Entschiedene Hinweise bleiben sichtbar, fachliche Sperren bleiben wirksam."""
from __future__ import annotations

from copy import deepcopy
import io
import json
from types import SimpleNamespace

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import abonnenten_analyse_ui as ui


def _entry(**changes):
    hint = {"text": "Lotfolge prüfen", "beleg_refs": ["F001"]}
    entry = {"signal_ref": 17, "id": 23, "quellen_uid": "source-fixture", "quelle": "mql5",
             "name": "Synthetic strategy", "status": "fertig", "rang": 1,
             "auswahlwert": 90, "retdd_perzentil": 80, "retdd_jahr": 4,
             "review_pending": False, "ki_pruefhinweise": [hint],
             "ki_hinweisstatus": "Offene KI-Prüfhinweise: historische Meldung",
             "ki_klaerung_status": "geklaert", "ki_klaerung_basis": "verified-basis",
             "ki_klaerung_gesperrt": False,
             "ki_pruefentscheidungen": [{"hinweis": hint,
                 "herkunft": {"bericht_stufe": "kurztest", "bericht_basis": "original-basis"},
                 "entscheidung": "widerlegt", "begruendung": "Die unveränderte Lotfolge widerlegt den Hinweis.",
                 "basis": "verified-basis",
                 "beleg_refs": ["trade-sha:1", "trade-sha:2"]}],
             "kurztest": {"strategietyp": "Unklar", "martingale_einordnung": "kein_beleg",
                          "kurzurteil": "Originaler Kurztest bleibt erhalten."}}
    entry.update(changes)
    return entry


@pytest.mark.parametrize("changes", [
    {"review_pending": True},
    {"ki_klaerung_gesperrt": True},
    {"ki_klaerung_status": "nicht_beurteilbar", "ki_klaerung_gesperrt": True},
    {"ki_klaerung_status": "nicht_beurteilbar"},
])
def test_pending_or_blocked_review_never_exports_a_stale_candidate_rank(changes):
    entry = _entry(**changes)
    original = deepcopy(entry)
    table = ui.ergebnis_tabelle([entry])
    assert table[["Rang", "Auswahlwert", "RetDD-Perzentil"]].isna().all().all()
    assert table.iloc[0]["Jahres-RetDD"] == 4
    assert table.iloc[0]["Martingale"] == "kein_beleg"
    assert entry == original


def test_csv_preserves_original_hint_and_bound_decision_without_reopening_it():
    entry = _entry()
    original = deepcopy(entry)
    row = pd.read_csv(io.BytesIO(ui.ergebnis_csv([entry], {"id": "r", "retdd_gewicht": 70})), sep=";").iloc[0]
    assert row["KI-Prüfung"] == row["KI-Hinweisstatus"] == "Prüfung abgeschlossen"
    assert not row["KI-Prüfung offen"] and not row["KI-Kandidatensperre"]
    assert row["Rang"] == 1 and row["KI-Klärungsbasis"] == "verified-basis"
    assert json.loads(row["Ursprüngliche KI-Prüfhinweise"]) == entry["ki_pruefhinweise"]
    assert json.loads(row["KI-Prüfentscheidungen"]) == entry["ki_pruefentscheidungen"]
    assert entry == original


@pytest.mark.parametrize("decision,status,blocked", [
    ("widerlegt", "geklaert", False),
    ("bestaetigt", "geklaert", True),
    ("nicht_beurteilbar", "nicht_beurteilbar", True),
])
def test_detail_displays_decision_and_original_evidence_without_claiming_confirmed_martingale(decision, status, blocked):
    entry = _entry(ki_klaerung_status=status, ki_klaerung_gesperrt=blocked)
    entry["ki_pruefentscheidungen"][0]["entscheidung"] = decision
    at = AppTest.from_string(
        "from mqlkiscanner.abonnenten_analyse_ui import _render_detail\n"
        f"_render_detail({entry!r}, 'run-fixture')", default_timeout=30).run()
    assert not at.exception
    assert any("Entscheidungen zu KI-Prüfhinweisen" == e.label for e in at.expander)
    assert any("original-basis" in e.value and "trade-sha:1" in e.value for e in at.json)
    assert not any("historische Meldung" in e.value for e in at.caption)
    assert any("Martingale: kein_beleg" in e.value for e in at.markdown)
    if blocked:
        assert any("Kandidatenrang gesperrt" in e.value for e in at.warning)
        assert any("keine automatische Bestätigung von Martingale" in e.value for e in at.caption)
    else:
        assert not at.warning


def test_result_view_excludes_stale_blocked_rank_and_keeps_data_gap_visible(monkeypatch):
    candidate = _entry(name="Cleared candidate")
    blocked = _entry(signal_ref=18, name="Final data gap", rang=2, status="datenluecke",
                     data_done=False, grund="Kapitalbasis unbelegt", ki_klaerung_gesperrt=True,
                     ki_klaerung_status="nicht_beurteilbar")
    state = {"id": "review-fixture", "status": "teilweise", "phase": "ergebnis", "entries": [candidate, blocked],
             "total": 2, "done": 2, "laeuft": False, "retdd_gewicht": 70}
    backend = SimpleNamespace(laeufe=lambda: [{"id": state["id"], "status": state["status"]}],
                              zustand=lambda run_id: state)
    monkeypatch.setattr(ui, "_backend", lambda: backend)
    at = AppTest.from_string("from mqlkiscanner.abonnenten_analyse_ui import render_results\nrender_results()",
                             default_timeout=30).run()
    assert not at.exception
    assert at.dataframe[0].value["Strategie"].tolist() == ["Cleared candidate"]
    assert any("0 offen · 2 beendet · 1 mit Kandidatensperre" in e.value for e in at.caption)
    at.segmented_control(key="abonnenten_analyse_ansicht_review-fixture").set_value("Weitere Fälle").run()
    assert not at.exception
    row = at.dataframe[0].value.iloc[0]
    assert row["Strategie"] == "Final data gap" and row["Grund"] == "Kapitalbasis unbelegt"
    assert row["Prüfstatus"] == "datenluecke" and pd.isna(row["Rang"])


def test_optional_short_hint_preserves_provisional_rank_in_csv_and_counter():
    entry = _entry(review_pending=True, kurztest_optional=False,
                   trades_path="fixture.csv", forensik={"fixture": True}, trades=50, dauer_monate=2,
                   endpruefung_status="wartet")
    original = deepcopy(entry)
    state = {"id": "optional", "retdd_gewicht": 70, "kurztest_optional": True, "entries": [entry]}
    row = pd.read_csv(io.BytesIO(ui.ergebnis_csv([entry], state)), sep=";").iloc[0]
    assert row["Rang"] == 1 and row["KI-Prüfung offen"]
    assert row["Kurz-KI optional"] and "Addonhinweise" in row["KI-Prüfung"]
    assert row["Endprüfung"] == "Vorläufig; Endprüfung wartet"
    counts = ui._ki_zaehler(state, SimpleNamespace())
    assert counts["top5_gesamt"] == 1
    assert entry == original


@pytest.mark.parametrize("changes", [
    {"ki_klaerung_gesperrt": True},
    {"top5_befund": {"neue_pruefhinweise": [{"text": "Top-5-Prüfung offen"}]}},
    {"ki_pruefhinweis_quellen": [{"herkunft": {"bericht_stufe": "top5"}}]},
    {"endpruefung_status": "nicht_beurteilbar"},
])
def test_optional_short_analysis_never_clears_final_review_or_safety_block(changes):
    entry = _entry(review_pending=True, kurztest_optional=True, **changes)
    row = ui.ergebnis_tabelle([entry]).iloc[0]
    assert pd.isna(row["Rang"]) and pd.isna(row["Auswahlwert"])


def test_optional_short_flag_is_explicit_and_completed_end_review_is_visible():
    pending = _entry(review_pending=True)
    assert pd.isna(ui.ergebnis_tabelle([pending]).iloc[0]["Rang"])
    final = _entry(kurztest_optional=True, endpruefung_status="abgeschlossen")
    row = ui.ergebnis_tabelle([final]).iloc[0]
    assert row["Rang"] == 1 and row["Endprüfung"] == "Endprüfung abgeschlossen"


def test_decided_historical_top5_hint_does_not_turn_new_short_addon_into_a_rank_block():
    entry = _entry(review_pending=True, kurztest_optional=True)
    decision = entry["ki_pruefentscheidungen"][0]
    decision["herkunft"]["bericht_stufe"] = "top5"
    entry["ki_pruefhinweis_quellen"] = [{"hinweis": decision["hinweis"], "herkunft": decision["herkunft"]}]
    entry["top5_befund"] = {"neue_pruefhinweise": [decision["hinweis"]]}
    assert ui._top5_hinweise(entry) is False
    assert ui.ergebnis_tabelle([entry]).iloc[0]["Rang"] == 1


def test_actual_resolution_schema_preserves_decided_top5_with_later_open_short_addon():
    from mqlkiscanner import abonnenten_analyse_klaerung as kl

    entry = _entry(kurztest_optional=True, review_pending=True, top5_basis="deep-original",
                   data_basis="frozen-data", trades_sha256="trade-sha",
                   forensik={"stats": {"duplikate_entfernt": 0}}, endpruefung_status="abgeschlossen")
    hint = entry["ki_pruefhinweise"][0]
    origin = {"bericht_stufe": "top5", "bericht_basis": "deep-original",
              "data_basis": "frozen-data", "trades_sha256": "trade-sha"}
    entry["ki_pruefhinweis_quellen"] = [{"hinweis": deepcopy(hint), "herkunft": origin}]
    entry["top5_befund"] = {"neue_pruefhinweise": [deepcopy(hint)]}
    answer = {"schema_version": kl.RESOLUTION_VERSION, "signal_ref": entry["signal_ref"],
              "hinweis_basis": kl.resolution_basis(entry), "trades_sha256": entry["trades_sha256"],
              "entscheidungen": [{"hinweis_id": row["hinweis_id"], "entscheidung": "widerlegt",
                                   "auswirkung": "keine_sperre", "bewertungsrelevanz": "pflichtgrundlage",
                                   "begruendung": "Codezahl ist 0.",
                                   "beleg_refs": ["forensik.stats.duplikate_entfernt"]}
                                  for row in kl.hint_records(entry)]}
    kl.apply_resolution(entry, answer)
    assert isinstance(entry["ki_pruefentscheidungen"][0]["herkunft"], list)
    new_hint = {"text": "Zusätzlicher Kurztesthinweis", "beleg_refs": []}
    entry["ki_pruefhinweise"].append(new_hint)
    entry["ki_pruefhinweis_quellen"].append({"hinweis": deepcopy(new_hint),
        "herkunft": {"bericht_stufe": "kurztest", "bericht_basis": "new-addon"}})
    entry["review_pending"] = True
    assert ui._top5_hinweise(entry) is False
    row = ui.ergebnis_tabelle([entry]).iloc[0]
    assert row["Rang"] == 1 and "Addonhinweise" in row["KI-Prüfung"]
    assert "erneut zu prüfen" in row["Endprüfung"]
    entry["top5_basis"] = "changed-deep-report"
    assert ui._top5_hinweise(entry) is True
    assert pd.isna(ui.ergebnis_tabelle([entry]).iloc[0]["Rang"])


def test_inflow_csv_keeps_measured_net_change_separate_from_current_stock_and_pct():
    trend = {"delta_7": 5, "delta_7_pct": 5.263, "basis_7_ts": "2026-10-17T00:00:00",
             "aktuell_ts": "2026-10-24T00:00:00", "verified": True,
             "frischehinweis": "Neuester nativer Messpunkt vom 24.10.",
             "coverage": {"7_tage": True}, "basis_7": 95, "aktuell": 100}
    entry = _entry(abonnenten=100, abo_perzentil=99, abo_zufluss_perzentil=60, abo_trend=trend,
                   abo_quellen_durchschnitt=50, abo_quellen_referenz_n=200, abo_zufluss_skaliert=0.1)
    original = deepcopy(entry)
    state = {"id": "inflow", "retdd_gewicht": 30, "auswahl_modus": "abo_zufluss_retdd_v1"}
    row = pd.read_csv(io.BytesIO(ui.ergebnis_csv([entry], state)), sep=";").iloc[0]
    assert row["Abonnenten"] == 100 and row["Nettozuwachs 7 Tage"] == 5
    assert row["Nettozuwachs 7 Tage %"] == 5.263 and row["Zufluss-Perzentil"] == 60
    assert row["Auswahlbasis"] == "Normierter 7-Tage-Nettozuwachs und RetDD"
    assert row["Zufluss / Quellenmittel"] == 0.1 and row["Quellenmittel Abonnenten"] == 50
    assert row["Quellenmittel Anbieterzahl"] == 200
    assert row["Zufluss-Normierungsumfang"] == "Ursprüngliche eingefrorene Top-200-Auswahl je Quelle"
    assert row["Zufluss-Basiszeit"] == trend["basis_7_ts"] and row["Zufluss-Messzeit"] == trend["aktuell_ts"]
    assert row["Zufluss-Gewicht %"] == 70 and row["RetDD-Gewicht %"] == 30
    assert pd.isna(row["Abonnenten-Gewicht %"])
    assert json.loads(row["Zufluss-Beleg (JSON)"]) == trend
    assert entry == original


def test_missing_native_trend_is_unknown_instead_of_being_filled_with_current_stock():
    row = ui.ergebnis_tabelle([_entry(abonnenten=100)]).iloc[0]
    assert pd.isna(row["Nettozuwachs 7 Tage"]) and pd.isna(row["Nettozuwachs 7 Tage %"])
    assert pd.isna(row["Zufluss-Perzentil"])
    assert row["Abonnenten"] == 100


def test_actual_trend_schema_displays_known_age_and_interval_at_fixed_cutoff():
    trend = {"delta_7": 5, "delta_7_pct": 5.263, "basis_7_ts": "2026-10-17T00:00:00+02:00",
             "aktuell_ts": "2026-10-24T00:00:00+02:00", "verified": True,
             "messalter_tage": 0.25, "messabstand_7_tage": 7.0,
             "as_of": "2026-10-24T06:00:00+02:00", "fetched_at": "2026-10-24T08:18:00+02:00"}
    entry = _entry(abo_trend=trend)
    row = ui.ergebnis_tabelle([entry]).iloc[0]
    text = row["Zufluss-Frischehinweis"]
    assert "0.25 Tage" in text and "7.00 Tage" in text
    assert trend["as_of"] in text and trend["fetched_at"] in text
    assert "GET-Zeit ist keine Messfrische" in text
    assert row["Zufluss-Messalter Tage"] == 0.25 and row["Zufluss-Messabstand Tage"] == 7.0
    at = AppTest.from_string(
        "from mqlkiscanner.abonnenten_analyse_ui import _render_detail\n"
        f"_render_detail({entry!r}, 'run-fixture')", default_timeout=30).run()
    assert not at.exception
    assert any("0.25 Tage" in e.value and "7.00 Tage" in e.value for e in at.caption)
    assert not any("Frische des Zuwachsfensters nicht angegeben" in e.value for e in at.caption)
