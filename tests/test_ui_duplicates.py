# -*- coding: utf-8 -*-
"""Regression: doppelte Element-Keys, wenn dieselbe Hilfe-Sektion zweimal
auf einer Seite erscheint (Seiten-Aufklapper + ⛔-Detailansicht)."""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

SEITE = '''\
import streamlit as st
from mqlkiscanner.pipeline import ScanResult
from mqlkiscanner.ui_design import section_header
from mqlkiscanner.app_ui import render_detail

# Konstellation der Ergebnisseite: Der Regelwerk-Aufklapper und die
# geoeffnete Detailansicht eines ausgeschlossenen Signals nutzen denselben
# help_key ("ausschlussliste") — die i-Buttons muessen trotzdem eindeutige
# Element-Keys haben.
with st.expander("Regelwerk · Ausschlussliste"):
    section_header("Warum ist ein Signal ausgeschlossen?",
                   help_key="ausschlussliste")
render_detail(ScanResult(id=2306053, name="Kenni Trades Gold Breakout",
                         platform="MT4", ampel="⛔",
                         urteil="Ausgeschlossen: Testgrund"))
'''


def test_kein_doppelter_hilfe_key_bei_gesperrtem_signal(tmp_path):
    seite = tmp_path / "detail_mit_ausschluss.py"
    seite.write_text(SEITE, encoding="utf-8")
    at = AppTest.from_file(str(seite), default_timeout=30)
    at.run()
    assert not at.exception, at.exception
