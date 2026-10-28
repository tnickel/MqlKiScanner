# -*- coding: utf-8 -*-
"""Styler-Zellenlimit: große Katalog-Tabellen bleiben renderbar.

Regression zu 28.10.2026: Streamlit brach die „Alle Signale"-Tabelle mit
StreamlitAPIException ab, sobald der Vollkatalog über pandas' Standardlimit
styler.render.max_elements (262 144 Zellen) wuchs (Stand: 370 224 Zellen =
7 713 Zeilen × 48 Spalten). styler_zellenlimit_anpassen muss das Prozess-
Limit VOR dem ersten .style-Aufbau auf die Tabellengröße heben.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

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


def test_limit_bleibt_bei_gleichzeitigen_sessions_monoton(monkeypatch):
    """Alten gelesenen Wert nach dem größeren Update nicht zurückschreiben."""
    original_get = pd.get_option
    pd.set_option('styler.render.max_elements', 100)
    klein_hat_gelesen, gross_fertig = threading.Event(), threading.Event()
    fehler = []

    def lese_option(name, *args, **kwargs):
        value = original_get(name, *args, **kwargs)
        if name == 'styler.render.max_elements' and threading.current_thread().name == 'klein':
            klein_hat_gelesen.set()
            # Ohne Lock endet groß hier zuerst; mit Lock kann groß erst nach
            # dem kleinen Schreiben fortfahren. Kein unbeschränktes Warten.
            gross_fertig.wait(0.2)
        return value

    def session(size):
        try:
            styler_zellenlimit_anpassen(SimpleNamespace(size=size))
        except Exception as exc:
            fehler.append(exc)
        finally:
            if threading.current_thread().name == 'gross':
                gross_fertig.set()

    monkeypatch.setattr(pd, 'get_option', lese_option)
    klein = threading.Thread(target=session, args=(370,), name='klein')
    gross = threading.Thread(target=session, args=(600,), name='gross')
    klein.start()
    assert klein_hat_gelesen.wait(2)
    gross.start()
    klein.join(3)
    gross.join(3)
    assert not klein.is_alive() and not gross.is_alive()
    assert not fehler
    assert original_get('styler.render.max_elements') == 600
