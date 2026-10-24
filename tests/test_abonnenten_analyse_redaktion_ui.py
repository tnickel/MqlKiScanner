"""Unbestätigte Auswahlen und vorläufige Texte werden keine Endfreigaben."""
from copy import deepcopy
import io
import json
from types import SimpleNamespace

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import abonnenten_analyse_ui as ui


def _entry(**changes):
    entry = {"signal_ref": 7, "id": 23, "quelle": "mql5", "name": "Synthetic final",
             "rang": 1, "status": "fertig", "data_done": True, "eligible": True,
             "retdd_jahr": 4, "endpruefung_status": "abgeschlossen", "review_pending": False,
             "bericht_markdown": "# Korrigierter Bericht", "bericht_redaktion_verlangt": True,
             "bericht_redaktion_status": "geprueft", "bericht_redaktion_basis": "editorial-basis",
             "bericht_redaktion_bericht_sha256": "original-report-sha",
             "bericht_markdown_original": "# Ursprünglicher fehlerhafter Entwurf",
             "bericht_redaktion_korrekturen": [{"alt": "Unbelegte Aussage", "neu": "Belegte Aussage",
                 "begruendung": "Der Codewert widerlegt den ursprünglichen Text.", "beleg_refs": ["F001"]}],
             "bericht_redaktion_result": {"status": "geprueft", "korrekturen": 1}}
    entry.update(changes)
    return entry


@pytest.fixture
def review_verdict(monkeypatch):
    verdict = {"current": False, "seen": []}
    original_import = ui.import_module

    def current(entry):
        verdict["seen"].append(entry)
        return verdict["current"]

    def import_module(name):
        return (SimpleNamespace(has_current_review=current)
                if name == "mqlkiscanner.abonnenten_analyse_redaktion" else original_import(name))

    monkeypatch.setattr(ui, "import_module", import_module)
    return verdict


def test_stored_checked_status_and_report_text_alone_do_not_make_a_valid_end_report(review_verdict):
    entry = _entry()
    table = ui.ergebnis_tabelle([entry])
    assert not table.iloc[0]["Endbericht geprüft"]
    assert "nicht aktuell belegt" in table.iloc[0]["Berichtsredaktion"]
    assert "Vorläufig" in table.iloc[0]["Endprüfung"]
    assert review_verdict["seen"]
    unapproved_csv = pd.read_csv(io.BytesIO(ui.ergebnis_csv([entry], {"id": "draft", "retdd_gewicht": 30})), sep=";")
    assert pd.isna(unapproved_csv.iloc[0]["Geprüfter Endbericht (Markdown)"])
    review_verdict["current"] = True
    row = ui.ergebnis_tabelle([entry]).iloc[0]
    assert row["Endbericht geprüft"]
    assert row["Berichtsredaktion"] == "Berichtsredaktion geprüft"


def test_csv_retains_original_text_and_bound_corrections_as_audit_material(review_verdict):
    review_verdict["current"] = True
    entry = _entry()
    original = deepcopy(entry)
    row = pd.read_csv(io.BytesIO(ui.ergebnis_csv([entry], {"id": "editorial", "retdd_gewicht": 30})), sep=";").iloc[0]
    assert row["Endbericht geprüft"] and row["Berichtsredaktion verlangt"]
    assert row["Geprüfter Endbericht (Markdown)"] == entry["bericht_markdown"]
    assert row["Redaktionsbasis"] == entry["bericht_redaktion_basis"]
    assert row["Redaktion Berichts-SHA256"] == "original-report-sha"
    assert row["Ursprünglicher Berichtsentwurf (Prüfgegenstand)"] == entry["bericht_markdown_original"]
    assert json.loads(row["Berichtskorrekturen (JSON)"]) == entry["bericht_redaktion_korrekturen"]
    assert json.loads(row["Redaktionsprüfung (JSON)"]) == entry["bericht_redaktion_result"]
    assert entry == original


def test_review_binding_uses_raw_entry_before_display_marks_missing_selection_unconfirmed(review_verdict):
    review_verdict["current"] = True
    entry = _entry(abo_referenz_vollstaendig=None, _bericht_redaktion_aktuell=False)
    state = {"id": "old-frozen", "auswahl_modus": "abo_zufluss_retdd_v1", "retdd_gewicht": 30,
             "snapshot_quellen": {"mql5": {"status": "fertig", "anzahl": 200}}}
    shown = ui._mit_abo_auswahl(entry, state)
    assert shown["abo_referenz_vollstaendig"] is False
    assert shown["_bericht_redaktion_aktuell"] is True
    assert all(seen["abo_referenz_vollstaendig"] is None for seen in review_verdict["seen"])
    assert ui._endbericht_gueltig(shown)
    csv = pd.read_csv(io.BytesIO(ui.ergebnis_csv([entry], state)), sep=";")
    assert csv.iloc[0]["Endbericht geprüft"]
    assert not any(column.startswith("_") for column in csv.columns)


def test_actual_editorial_digest_remains_bound_to_original_selection_metadata():
    from mqlkiscanner import abonnenten_analyse_redaktion as redaction
    from mqlkiscanner.abonnenten_analyse_ki import digest

    original_report = "# Ursprünglicher Bericht\nVeraltete Aussage."
    entry = _entry(abo_referenz_vollstaendig=None, top5_basis="deep-original",
                   top5_befund={"bericht_markdown": original_report}, bericht_markdown=original_report)
    answer = {"schema_version": redaction.REVIEW_VERSION, "signal_ref": entry["signal_ref"],
              "pruefbasis": redaction.review_basis(entry), "original_bericht_sha256": digest(original_report),
              "korrekturen": [{"alt": "Veraltete Aussage.", "neu": "Korrigierte Aussage.",
                  "begruendung": "Ursprünglicher globaler Auswahlbeleg fehlt.",
                  "beleg_refs": ["berichtsfakten.auswahl_global_bestaetigt"]}], "offene_pflichtfragen": []}
    redaction.apply_review(entry, answer)
    assert redaction.has_current_review(entry)
    shown = ui._mit_abo_auswahl(entry, {"auswahl_modus": "abo_zufluss_retdd_v1"})
    assert shown["abo_referenz_vollstaendig"] is False
    assert redaction.has_current_review(shown) is False, "The strict backend digest must not normalize display annotations"
    assert shown["_bericht_redaktion_aktuell"] is True
    assert ui._endbericht_gueltig(shown)
    row = pd.read_csv(io.BytesIO(ui.ergebnis_csv([entry], {
        "id": "bound", "auswahl_modus": "abo_zufluss_retdd_v1", "retdd_gewicht": 30})), sep=";").iloc[0]
    assert row["Endbericht geprüft"] and "ursprünglicher Auswahlbeleg fehlt" in row["Auswahlhinweis"]


def test_detail_distinguishes_editorial_draft_and_auditable_corrections(review_verdict):
    entry = _entry()
    at = AppTest.from_string("from mqlkiscanner.abonnenten_analyse_ui import _render_detail\n"
                             f"_render_detail({entry!r}, 'editorial')", default_timeout=30).run()
    assert not at.exception
    assert any("Vorläufiger Berichtsentwurf" in e.label for e in at.expander)
    assert not any(e.label == "Ausführliche Top-5-Analyse" for e in at.expander)
    assert any(e.label == "Ursprünglicher Berichtsentwurf als Prüfgegenstand" for e in at.expander)
    assert any("Unbelegte Aussage" in e.value and "Belegte Aussage" in e.value for e in at.json)


@pytest.mark.parametrize("flag", [None, "missing"])
def test_new_mode_missing_selection_proof_is_explicit_without_invented_skipped_slots(flag):
    entry = {"id": 23, "quelle": "mql5", "name": "Frozen provider", "rang": 1}
    if flag is None:
        entry["abo_referenz_vollstaendig"] = None
    state = {"id": "original", "auswahl_modus": "abo_zufluss_retdd_v1", "retdd_gewicht": 30,
             "snapshot_quellen": {"mql5": {"status": "fertig", "anzahl": 200}}}
    original = deepcopy(entry)
    shown = ui._mit_abo_auswahl(entry, state)
    assert shown["abo_referenz_vollstaendig"] is False
    assert "ursprünglicher Auswahlbeleg fehlt" in shown["abo_auswahl_hinweis"]
    assert "abo_ausgelassene_positionen" not in shown
    assert "abo_katalog_geprueft" not in shown
    row = pd.read_csv(io.BytesIO(ui.ergebnis_csv([entry], state)), sep=";").iloc[0]
    assert not row["Abonnentenreferenz vollständig"]
    assert "globale Top 200 unbestätigt" in row["Auswahlhinweis"]
    assert pd.isna(row["Ausgelassene API-Positionen"]) and pd.isna(row["Geprüfte Kataloganbieter"])
    assert entry == original


@pytest.mark.parametrize("proof", [
    {"abonnenten_auswahl": {"verified": True}},
    {"abonnenten_katalog": {"complete": True}},
])
def test_new_mode_uses_explicit_saved_selection_proof(proof):
    shown = ui._mit_abo_auswahl({"id": 23, "quelle": "mql5"}, {
        "auswahl_modus": "abo_zufluss_retdd_v1", "snapshot_quellen": {"mql5": {"status": "fertig", **proof}}})
    assert shown["abo_referenz_vollstaendig"] is True
    assert not ui._abo_auswahlhinweis(shown)


def test_decided_nonessential_unknown_risk_remains_visible_without_a_new_rank_block():
    entry = _entry(bericht_redaktion_verlangt=False, bericht_redaktion_status=None,
                   ki_klaerung_status="geklaert", ki_klaerung_gesperrt=False,
                   ki_pruefentscheidungen=[{"entscheidung": "nicht_beurteilbar",
                       "auswirkung": "dokumentierter_risikohinweis",
                       "hinweis": {"text": "Zusatzrisiko außerhalb des Exportfensters"},
                       "begruendung": "Der aktuelle offene Bestand ist im Export nicht belegt.", "beleg_refs": ["F001"]}])
    row = ui.ergebnis_tabelle([entry]).iloc[0]
    assert row["Rang"] == 1 and row["KI-Prüfung"] == "Prüfung abgeschlossen"
    at = AppTest.from_string("from mqlkiscanner.abonnenten_analyse_ui import _render_detail\n"
                             f"_render_detail({entry!r}, 'risk')", default_timeout=30).run()
    assert not at.exception
    assert any("Dokumentierter Risikohinweis; keine zusätzliche Kandidatensperre" in e.value for e in at.caption)
    assert any("aktuelle offene Bestand" in e.value for e in at.markdown)
