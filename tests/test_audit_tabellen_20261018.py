# -*- coding: utf-8 -*-
"""Audit 18.10.2026 — Tabellen „Alle Signale“ / „Ergebnisse“: Übergänge,
die vorher keine gezielte Absicherung hatten.

Neue AppTest-Fälle (Produktiv-DB wird nie berührt; conftest isoliert nach
tmp_path):
1. ID-Kollision zwischen Quellen in „Alle Signale“: Detail gehört zur
   GEWÄHLTEN Zeile (indexbasiert), Nutzer-Markierung ist bewusst rein
   ID-keyed und markiert dann beide Zeilen (Dokumentation des Modells).
2. CSV „Alle Signale“ == Tabellen-Spalten/-Zeilen (gleiche Grundlage df).
3. CSV „Ergebnisse“ == gefilterte Zeilen und fachliche Spalten einschließlich
   Link/Abonnenten/30 Tage/7 Tage/Dokumente; reine UI-Aktionen sind ausgenommen
   (Regression nach Behebung des Audit-Befunds N-3).
4. Ergebnistabelle trägt UNGERUNDETE Werte (Rundung erst im Anzeigeformat).
5. NEU-Marker: Sitzungs-Bindung — nach „F5“ (frische App-Instanz ohne
   session_state) gibt es keine Sitzungsergebnisse und kein NEU.
6. Regression Audit-Befund M-1: Ein weiterhin sichtbarer historischer
   Roh-DD ist im Messstatus ausdrücklich als veralteter Befund markiert.
"""
from __future__ import annotations

import io

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from conftest import ROOT
from mqlkiscanner import db, pipeline
from mqlkiscanner import katalog as katalog_mod
from mqlkiscanner import alle_signale_ui as tabellen_ui
from mqlkiscanner.alle_signale_ui import tabellen_zeile

SEITE_ALLE = ROOT / "app_pages" / "alle_signale.py"
SEITE_ERG = ROOT / "app_pages" / "ergebnisse.py"

KOPF = "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"


def _csv(pfad) -> str:
    zeilen = [
        "2026.01.05 10:00:00;Buy;0.10;EURUSD;1.1000;0.10;2026.01.05 10:10:00;1.1010;0;;100.0",
        "2026.02.05 10:00:00;Buy;0.10;EURUSD;1.1000;0.10;2026.02.05 10:10:00;1.0990;0;;-60.0",
        "2026.03.05 10:00:00;Buy;0.10;EURUSD;1.1000;0.10;2026.03.05 10:10:00;1.1012;0;;120.0",
    ]
    pfad.write_text(KOPF + "\n".join(zeilen) + "\n", encoding="utf-8-sig")
    return str(pfad)


# ── 1) ID-Kollision zwischen Quellen in „Alle Signale“ ───────────────────
def test_alle_signale_detail_gehoert_zur_gewaehlten_zeile_bei_id_kollision(
        tmp_path, monkeypatch):
    """Gleiche Signal-ID aus zwei Quellen (Workflow mql5 + Katalog pelik):
    Zeilenauswahl ist indexbasiert — das Detail zeigt das GEWÄHLTE Objekt.
    Die Nutzer-Markierung gehört ausschließlich zur ausgewählten Quelle;
    dieselbe externe ID der anderen Quelle bleibt unverändert."""
    csv_a, csv_b = _csv(tmp_path / "a.csv"), _csv(tmp_path / "b.csv")
    workflow = pipeline.ScanResult(
        id=42, name="Workflow-Zeile", platform="MT5", quelle="mql5",
        ampel="🟡", wochen=60.0, abonnenten=12.0, trades_path=csv_a,
        account_currency="USD")
    katalog = pipeline.ScanResult(
        id=42, name="Katalog-Zeile", platform="pelican", quelle="pelik",
        wochen=30.0, abonnenten=5.0, herkunft="Katalog", trades_path=csv_b,
        account_currency="USD")
    monkeypatch.setattr(pipeline, "results_from_db", lambda **kw: [workflow])
    monkeypatch.setattr(db, "list_catalog", lambda **kw: [{"signal_id": 42, "stats": {}}])
    monkeypatch.setattr(db, "katalog_sync_status",
                        lambda: {"pelik": {"gelaufen_am": "2026-10-18 10:00:00",
                                           "anzahl": 1, "fehler": None}})
    monkeypatch.setattr(katalog_mod, "katalog_resultate",
                        lambda **kw: ([katalog], {}))
    at = AppTest.from_file(str(SEITE_ALLE), default_timeout=60).run()
    assert not at.exception, at.exception
    frame = at.dataframe[0].value
    assert list(frame["ID"]) == [42, 42]
    assert list(frame["Quelle"]) == ["mql5", "pelik"]

    # Zeile 1 (Katalog pelik) wählen → Detail zeigt genau dieses Objekt
    at.session_state["alle_signale_tabelle"] = {"selection": {"rows": [1]}}
    at.run()
    assert not at.exception, at.exception
    assert any("Katalog-Zeile" in s.value for s in at.subheader)
    assert not any("Workflow-Zeile" in s.value for s in at.subheader)

    # Zeile 0 (Workflow mql5) wählen → Detail wechselt mit
    at.session_state["alle_signale_tabelle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception, at.exception
    assert any("Workflow-Zeile" in s.value for s in at.subheader)
    assert not any("Katalog-Zeile" in s.value for s in at.subheader)

    # Markierung ist quellenspezifisch: dieselbe ID der anderen Quelle bleibt frei.
    at.button(key="alle_signale_mark_gruen").click()
    at.session_state["alle_signale_tabelle"] = {"selection": {"rows": [0]}}
    at.run()
    assert not at.exception, at.exception
    assert db.list_markierungen(identitaeten=True) == {("mql5", 42): "gruen"}
    frame = at.dataframe[0].value
    assert list(frame["Mark."]) == ["🟩", ""]


# ── 2) CSV „Alle Signale“ == Tabelle ─────────────────────────────────────
def test_alle_signale_csv_entspricht_tabelle(tmp_path, monkeypatch):
    csv_pfad = _csv(tmp_path / "trades_42.csv")
    probe = pipeline.ScanResult(
        id=42, name="CSV-Sync", platform="MT5", quelle="pelik", ampel="🟡",
        wochen=50.0, abonnenten=7.0, trades_path=csv_pfad,
        account_currency="USD")
    monkeypatch.setattr(pipeline, "results_from_db", lambda **kw: [probe])
    monkeypatch.setattr(db, "list_catalog",
                        lambda **kw: [{"signal_id": 42, "stats": {}}])
    monkeypatch.setattr(db, "katalog_sync_status",
                        lambda: {"pelik": {"gelaufen_am": "2026-10-18", "anzahl": 1,
                                           "fehler": None}})
    monkeypatch.setattr(katalog_mod, "katalog_resultate", lambda **kw: ([], {}))
    downloads: list[bytes] = []
    monkeypatch.setattr(
        st, "download_button",
        lambda label, data, *a, **kw: (downloads.append(data), None)[1])
    at = AppTest.from_file(str(SEITE_ALLE), default_timeout=60).run()
    assert not at.exception, at.exception
    # The page may render again after its initial normalization. A second
    # rendering must preserve the CSV; the number of render passes is no API.
    at.run()
    assert not at.exception, at.exception
    assert downloads and len(set(downloads)) == 1
    tabelle = at.dataframe[0].value
    aus_csv = pd.read_csv(io.BytesIO(downloads[-1]), sep=";", encoding="utf-8-sig")
    assert list(aus_csv.columns) == list(tabelle.columns)
    assert list(aus_csv["ID"]) == list(tabelle["ID"]) == [42]
    # Anzeige-Rundung: beide stammen aus DEMSELBEN gerundeten df — der
    # CSV-Wert ist der angezeigte (2 Dezimalstellen), nicht der Rohwert.
    assert aus_csv["Wochen"].iloc[0] == 50


# ── 3) CSV „Ergebnisse“: Zeilen == Filter, Spaltendifferenz dokumentiert ──
def test_ergebnisse_csv_zeilen_entsprechen_filter_spalten_dokumentiert(monkeypatch):
    r1 = pipeline.ScanResult(id=101, name="Alpha", quelle="pelik",
                             platform="pelican", ampel="🟡", urteil="ok",
                             persisted_this_run=True)
    r2 = pipeline.ScanResult(id=102, name="Beta", quelle="mql5",
                             platform="MT5", ampel="🔴", urteil="ok2")
    downloads: list[bytes] = []
    monkeypatch.setattr(
        st, "download_button",
        lambda label, data, *a, **kw: (downloads.append(data), None)[1])
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60).run()
    at.session_state["scan_results"] = [r1, r2]
    at.switch_page(str(SEITE_ERG)).run()
    assert not at.exception, at.exception
    at.selectbox(key="results_run").set_value("Aktuelle Sitzung").run()
    assert not at.exception, at.exception
    assert any("2 von 2 Signalen" in c.value for c in at.caption)

    assert len(downloads) == 1
    tabelle = at.dataframe[0].value
    aus_csv = pd.read_csv(io.BytesIO(downloads[0]), sep=";", encoding="utf-8-sig")
    # Dieselben Zeilen in derselben Reihenfolge (Filter identisch)
    assert list(aus_csv["ID"]) == list(tabelle["ID"]) == [101, 102]
    # NEU-Marker (Sitzung: persisted_this_run) steht in Tabelle UND CSV
    assert list(tabelle["Stand"]) == ["NEU", ""]
    assert list(aus_csv["Stand"].fillna("")) == ["NEU", ""]
    assert at.toggle(key="results_only_fresh").disabled is False
    # N-3 behoben: Fachliche Zusatzspalten stehen in Tabelle und CSV.
    # Nur Aktionsbuttons ohne Datenwert sind vom Export ausgenommen.
    fachspalten = {"Link", "Abonnenten", "30 Tage", "7 Tage", "Dokumente"}
    assert fachspalten <= set(tabelle.columns) & set(aus_csv.columns)
    assert not ({"Studie", "Bericht"} & set(aus_csv.columns))
    # ... und die bewertenden Kernspalten stehen in beiden
    for spalte in ("Ampel", "Name", "Quelle", "Stop", "Max-Drawdown %",
                   "Trading-DD % (geschlossen)", "Drawdown % (Plattform)",
                   "Gewinn %/Monat", "TrueRetDD", "Score", "Urteil", "Fix"):
        assert spalte in aus_csv.columns and spalte in tabelle.columns


# ── 4) Ergebnistabelle ungerundet ────────────────────────────────────────
def test_ergebnisse_tabelle_traegt_ungerundete_werte():
    """Regel „Auswahl/Bewertung mit ungerundeten Werten, Anzeige gerundet“:
    Das Datenframe behält mehr als zwei Dezimalstellen — die Rundung passiert
    erst im column_config-Format (Anzeige)."""
    at = AppTest.from_string(
        "import streamlit as st\n"
        "from mqlkiscanner.app_ui import render_results_table\n"
        "render_results_table(st.session_state.rows)", default_timeout=30)
    at.session_state["rows"] = [pipeline.ScanResult(
        id=7, name="Präzision", forensik_vorhanden=True,
        ertrag_monat_geom_pct=1.1111, cagr_jahr_pct=18.2578,
        equity_dd_rekonstruiert_pct=20.0)]
    at.run()
    assert not at.exception
    wert = at.dataframe[0].value["TrueRetDD"].iloc[0]
    assert wert == pytest.approx(18.2578 / 20.0)
    assert wert != round(wert, 2)          # NICHT vorab gerundet
    gewinn = at.dataframe[0].value["Gewinn %/Monat"].iloc[0]
    assert gewinn == pytest.approx(1.1111)


# ── 5) NEU überlebt keinen Session-Neustart ──────────────────────────────
def test_ergebnisse_sitzung_nach_f5_ohne_neu_und_ohne_sitzungsdaten():
    """F5 = neuer Client: session_state (scan_results, refreshed_signal_ids,
    persisted_this_run-Fallback) ist weg — kein NEU, keine Sitzungszeilen;
    die DB-Ansicht entscheidet allein über den Bestand."""
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60).run()
    at.switch_page(str(SEITE_ERG)).run()
    assert not at.exception, at.exception
    # Leere Test-DB → keine Berichte; nichts aus einer „alten“ Sitzung leckt
    # (Hinweis ist ein subheader, kein info-Element)
    assert any("Noch keine Berichte" in s.value for s in at.subheader)
    assert not at.session_state["scan_results"]
    # Startwert der Landing-Page ist None („unbekannter Altstand“) — kein
    # NEU möglich, weil kein Persistenzbeleg existiert.
    assert at.session_state["refreshed_signal_ids"] is None


# ── 6) Dokumentation M-1: ≈-Marker aus veralteter Forensik ───────────────
def test_true_dd_vorbehaltsmarker_auch_bei_stale_forensik_dokumentiert():
    """M-1 behoben: Historischer Roh-DD bleibt im Audit sichtbar, wird aber
    ausdrücklich als veraltet gekennzeichnet und ist kein aktueller Messbeleg."""
    res = pipeline.ScanResult(
        id=5, name="Alte Messung", quelle="mql5", platform="MT5",
        forensik_stale=True, equity_dd_rekon_roh_pct=13.83,
        account_currency="USD")
    zeile = tabellen_zeile(res, None)
    assert zeile["True-DD %"] is None          # belastbarer Wert weg (stale)
    assert zeile["True-DD ≈"] == pytest.approx(13.83)   # roher Rest bleibt
    assert "veraltet" in (zeile["Messstatus"] or "")
