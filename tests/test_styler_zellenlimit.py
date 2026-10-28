# -*- coding: utf-8 -*-
"""Styler-Zellenlimit: große Katalog-Tabellen bleiben renderbar.

Regression zu 28.10.2026: Streamlit brach die „Alle Signale"-Tabelle mit
StreamlitAPIException ab, sobald der Vollkatalog über pandas' Standardlimit
styler.render.max_elements (262 144 Zellen) wuchs (Stand: 370 224 Zellen =
7 713 Zeilen × 48 Spalten). styler_zellenlimit_anpassen muss das Prozess-
Limit VOR dem ersten .style-Aufbau auf die Tabellengröße heben.
"""
from __future__ import annotations

import pandas as pd
import pytest

from mqlkiscanner.app_ui import styler_zellenlimit_anpassen


@pytest.fixture(autouse=True)
def _limit_zuruecksetzen():
    alt = int(pd.get_option('styler.render.max_elements'))
    yield
    pd.set_option('styler.render.max_elements', alt)


def test_limit_hebt_auf_tabellengroesse():
    df = pd.DataFrame({'x': range(370_224)})
    vor = int(pd.get_option('styler.render.max_elements'))
    assert df.size > vor  # Stand 28.10. liegt über dem Standardlimit
    styler_zellenlimit_anpassen(df)
    # Exakt die Prüfung, die Streamlit in marshall_styler stellt:
    assert df.size <= int(pd.get_option('styler.render.max_elements'))


def test_kleine_tabelle_laesst_limit_unberuehrt():
    vor = int(pd.get_option('styler.render.max_elements'))
    styler_zellenlimit_anpassen(pd.DataFrame({'x': [1, 2, 3]}))
    assert int(pd.get_option('styler.render.max_elements')) == vor


def test_marshall_styler_nimmt_kataloggroesse_ohne_fehler_an():
    """Echter Beweis am Streamlit-Weg: rot ohne Fix (StreamlitAPIException
    „maximum number of cells"), grün mit styler_zellenlimit_anpassen."""
    from streamlit.elements.lib.pandas_styler_utils import marshall_styler
    from streamlit.proto.ArrowData_pb2 import ArrowData as ArrowDataProto

    df = pd.DataFrame({'x': range(270_000)})
    styler_zellenlimit_anpassen(df)
    proto = ArrowDataProto()
    marshall_styler(proto, df.style.format(na_rep=''), 'test-uuid')
