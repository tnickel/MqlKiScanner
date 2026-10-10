# -*- coding: utf-8 -*-
"""Seite „FAQ“ — die Fragen des Nutzers, aus der Praxis beantwortet.

Nutzer-Wunsch 08.10.2026: Die im Alltag tatsächlich gestellten Fragen
(wo ist DINO, wann lädt die Liste, fehlen Trade-Zeiten, High-Watermark,
„haben wir die besten“ …) sollen als FAQ in der Web-App stehen — und
stetig wachsen. Die Inhalte liegen zentral in `faq_inhalte.py`
(FAQ_KATEGORIEN — neue Frage einfach anhängen, die Seite rendert selbst).

Features: Freitextsuche über Frage + Antwort, Kategorien mit
aufklappbaren Fragen, Fragen-Anzahl je Kategorie in der Überschrift.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import streamlit as st

from mqlkiscanner import faq_inhalte
from mqlkiscanner.ui_design import apply_theme, page_header

apply_theme()
page_header('FAQ', 'Häufige Fragen — aus der Praxis beantwortet',
            'Die Fragen, die im Alltag tatsächlich aufgekommen sind: wo '
            'Signale herkommen, warum Werte leer bleiben, was die '
            'Drawdown-Spalten unterscheidet, wie die Ampel entscheidet. '
            'Antworten beschreiben den Ist-Zustand — die Sammlung wächst mit.')

suche = st.text_input('Frage oder Stichwort suchen', key='faq_suche',
                      placeholder='z. B. Drawdown, DINO, Kapitalbasis, Equity-Studie …')
suche_cf = (suche or '').strip().casefold()

gesamt = len(faq_inhalte.alle_fragen())
treffer = 0
for kategorie in faq_inhalte.FAQ_KATEGORIEN:
    gefiltert = [(frage, antwort) for frage, antwort in kategorie['fragen']
                 if not suche_cf
                 or suche_cf in frage.casefold()
                 or suche_cf in antwort.casefold()]
    if not gefiltert:
        continue
    treffer += len(gefiltert)
    titel = kategorie['titel']
    if suche_cf:
        titel += f" — {len(gefiltert)} Treffer"
    st.subheader(f"{kategorie.get('icon', '')} {titel}".strip())
    for frage, antwort in gefiltert:
        with st.expander(frage):
            st.markdown(antwort)

if suche_cf:
    if not treffer:
        st.info('Keine Frage passt zu dieser Suche — Stichwort anders versuchen '
                '(z. B. „Drawdown“, „Katalog“, „Trades“).',
                icon=':material/search_off:')
    else:
        st.caption(f'{treffer} von {gesamt} Fragen gefunden.')
else:
    st.caption(f'{gesamt} Fragen — neue Fragen landen in `faq_inhalte.py` '
               'und erscheinen hier automatisch.')
