"""Gemessener Exportgewinn bleibt von Quellenangaben und Hochrechnungen getrennt."""
from copy import deepcopy
import io

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import abonnenten_analyse_ui as ui


def _entry(**changes):
    entry = {"signal_ref": 17, "quelle": "mql5", "id": 23, "name": "Synthetic profit",
             "account_currency": "USD", "forensik": {"stats": {"net": 1234.5}},
             "rendite_zeitraum_pct": 12.5, "cagr_jahr_pct": 102.7, "dauer_monate": 2,
             "zeit_von": "2026-08-20T00:00:00", "zeit_bis": "2026-10-20T00:00:00"}
    entry.update(changes)
    return entry


@pytest.mark.parametrize("account,stats_currency,expected", [
    ("USD", None, 1234.5),
    (None, "USD", 1234.5),
    ("usd", "USD", 1234.5),
    (None, None, None),
    ("EUR", None, None),
    ("USC", None, None),
    ("EUR", "USD", None),
    ("USD", "EUR", None),
])
def test_net_profit_requires_consistent_usd_evidence(account, stats_currency, expected):
    entry = _entry(account_currency=account,
                   forensik={"stats": {"net": 1234.5, "account_currency": stats_currency}})
    row = ui.ergebnis_tabelle([entry]).iloc[0]
    if expected is None:
        assert pd.isna(row["Nettogewinn USD"])
    else:
        assert row["Nettogewinn USD"] == expected


def test_missing_profit_and_returns_are_unknown_while_proven_zero_profit_is_zero():
    missing = _entry(forensik={"stats": {}}, rendite_zeitraum_pct=None, cagr_jahr_pct=None)
    zero = _entry(forensik={"stats": {"net": 0}})
    table = ui.ergebnis_tabelle([missing, zero])
    assert table.iloc[0][["Nettogewinn USD", "Rendite Exportfenster %", "Jahresrendite annualisiert %"]].isna().all()
    assert table.iloc[1]["Nettogewinn USD"] == 0


def test_csv_preserves_export_return_and_cagr_without_computing_or_changing_ranking():
    entry = _entry(rang=3, auswahlwert=82, retdd_jahr=4)
    original = deepcopy(entry)
    row = pd.read_csv(io.BytesIO(ui.ergebnis_csv([entry], {"id": "profit", "retdd_gewicht": 30})), sep=";").iloc[0]
    assert row["Nettogewinn USD"] == 1234.5
    assert row["Rendite Exportfenster %"] == 12.5
    assert row["Jahresrendite annualisiert %"] == 102.7
    assert "Hochrechnung aus 2 Monaten" in row["Rendite-Hinweis"]
    assert row["Rang"] == 3 and row["Auswahlwert"] == 82 and row["Jahres-RetDD"] == 4
    assert entry == original


def test_robo_source_values_never_become_measured_export_profit_or_annualized_return():
    entry = _entry(quelle="robo", auswertung_typ="quellenprofitabilitaet",
                   gewinn_usd=800, rendite_quelle_pct=25, rendite_quelle_monate=3)
    row = ui.ergebnis_tabelle([entry]).iloc[0]
    assert row[["Nettogewinn USD", "Rendite Exportfenster %", "Jahresrendite annualisiert %"]].isna().all()
    assert row["Quellengewinn USD"] == 800 and row["Quellrendite %"] == 25
    assert row["Rendite-Hinweis"] == ""


def test_detail_labels_short_history_year_return_as_projection_and_shows_export_profit():
    entry = _entry()
    at = AppTest.from_string("from mqlkiscanner.abonnenten_analyse_ui import _render_detail\n"
                             f"_render_detail({entry!r}, 'profit')", default_timeout=30).run()
    assert not at.exception
    metrics = {metric.label: metric.value for metric in at.metric}
    assert metrics["Nettogewinn im Exportfenster (USD)"] == "1.234,50"
    assert metrics["Rendite Exportfenster (%)"] == "12,50"
    assert metrics["Jahresrendite annualisiert (%)"] == "102,70"
    assert any("Hochrechnung aus 2 Monaten" in e.value and "kein beobachtetes volles Jahresergebnis" in e.value
               for e in at.caption)
    assert any(entry["zeit_von"] in e.value and entry["zeit_bis"] in e.value for e in at.caption)


def test_year_return_from_long_enough_history_keeps_annualization_label():
    entry = _entry(dauer_monate=18)
    assert "annualisierte Rendite" in ui._jahresrendite_hinweis(entry)
    assert "Hochrechnung" not in ui._jahresrendite_hinweis(entry)
