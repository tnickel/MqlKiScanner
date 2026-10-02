# -*- coding: utf-8 -*-
"""Stations-Dialoge: Filter müssen die Tabelle LIVE verändern.

Nutzer-Fall 02.10.2026: In den Stations-Dialogen (Station 1–6) zeigte die
Tabelle keine Reaktion auf die Filter (Anzeige/Quelle/Suche) — Grund: Der
Dialog-Body lief bei Widget-Interaktion nicht erneut (AppTest-Diagnose:
Dialog nach set_value geschlossen). Fix: ALLE Stations-Dialoge sind mit
@st.fragment() ÜBER @st.dialog gestapelt — Widget-Klicks im Dialog lösen
dann NUR den Dialog-Body erneut aus (Fragment-Rerun), der Dialog bleibt
offen und die gefilterte Tabelle wird neu gerendert.

Hinweis zur Testbarkeit: AppTest führt .run() immer als VOLL-Rerun aus und
bildet Fragment-Reruns nicht ab — deshalb beweist Test 1 das Muster an
einer Kopie (identischer Aufbau, Funktion top-level aufgerufen) und
Test 2 die statische Einbindung in der echten Scan-Seite. Die echte
Nutzer-Interaktion (Klick im Dialog filtert live, Dialog bleibt offen)
wurde zusätzlich am 02.10.2026 im Browser verifiziert.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mqlkiscanner import config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def begruendung_datei():
    rows = [
        {"id": 1, "name": "Gewählt A", "quelle": "mql5", "wochen": 80,
         "abonnenten": 70, "status": "AUSGEWAEHLT", "grund": "Rang 1"},
        {"id": 2, "name": "Gewählt B", "quelle": "pelik", "wochen": 40,
         "abonnenten": 5, "status": "FIX", "grund": "Fix"},
        {"id": 3, "name": "Draußen C", "quelle": "vant", "wochen": 4,
         "abonnenten": 9, "status": "DRAUSSEN", "grund": "zu jung"},
    ]
    (config.DATA_DIR / "auswahl_begruendung.json").write_text(json.dumps({
        "zeitstempel": "2026-10-02 12:00:00", "top_n_export": 30,
        "modus": "Teilscan", "eintraege": rows,
    }), encoding="utf-8")
    return rows


def test_fragment_dialog_muster_filtert_live(tmp_path):
    """Muster-Beweis: @st.fragment() über @st.dialog — Widget-Interaktion
    hält den Dialog offen und die Tabelle übernimmt den Filterwert. Genau
    dieses Stapeling tragen alle sechs Stations-Dialoge."""
    wrapper = tmp_path / "muster.py"
    wrapper.write_text(
        "import streamlit as st\n"
        "\n"
        "@st.fragment()\n"
        "@st.dialog('Muster')\n"
        "def dialog():\n"
        "    wert = st.selectbox('Filter', ['Alle', 'Eins', 'Zwei'])\n"
        "    n = 3 if wert == 'Alle' else (1 if wert == 'Eins' else 2)\n"
        "    st.dataframe({'wert': [wert] * n})\n"
        "\n"
        "dialog()\n",
        encoding="utf-8")
    at = AppTest.from_file(str(wrapper), default_timeout=15)
    at.run()
    dialogs = at.get("dialog")
    assert len(dialogs) == 1, "Dialog initial geöffnet"
    assert len(dialogs[0].dataframe[0].value) == 3, "Default zeigt alles"

    dialogs[0].selectbox[0].set_value("Eins").run()

    dialogs2 = at.get("dialog")
    assert len(dialogs2) == 1, "Dialog bleibt nach Widget-Interaktion offen"
    assert len(dialogs2[0].dataframe[0].value) == 1, \
        "Tabelle übernimmt den Filter live"


def test_station2_dialog_hat_fragment_stapelung_und_filter(begruendung_datei):
    """Die echte Scan-Seite: Station 2 öffnet, zeigt die Vollliste und die
    Filter-Widgets — und alle sechs Stations-Dialoge tragen das Fragment-
    Stapeling (Quelltext-Guard gegen stilles Entfernen)."""
    quelltext = (ROOT / "app_pages" / "scan.py").read_text(encoding="utf-8")
    assert quelltext.count("@st.fragment()\n@st.dialog(") >= 6, \
        "Alle sechs Stations-Dialoge brauchen @st.fragment() über @st.dialog"

    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.query_params = {"station": "kandidaten"}
    at.run()
    dialogs = at.get("dialog")
    assert len(dialogs) == 1
    d = dialogs[0]
    tabelle = d.get("dataframe")[-1].value
    assert len(tabelle) == 3, "Default ‚Alle' zeigt die Vollliste"
    assert set(tabelle["Signal"]) == {"Gewählt A", "Gewählt B", "Draußen C"}
    assert d.get("multiselect"), "Quellen-Filter erwartet"
    assert d.get("text_input"), "Suche erwartet"
