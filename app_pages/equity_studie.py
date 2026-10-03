# -*- coding: utf-8 -*-
"""Seite „Equity-Studie" — Equity-Drawdown aus echten Kursen nachgemessen.

Eigene Seite zur On-Demand-Studie (Nutzer-Wunsch 03.10.2026): Signal wählen,
dann wird der Equity-Drawdown stundenfein nachgemessen — realisierter Betrag
UND offener Betrag (floating) je Stunde, Kurse vom MT5-Referenzterminal,
GMT-Abgleich je Währungspaar. Gleiche Ansicht wie der Equity-DD-Button in
der Ergebnisstabelle, hier in voller Breite mit Konzept-Texten.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import streamlit as st

from mqlkiscanner import pipeline
from mqlkiscanner.equity_studie_ui import render_studie
from mqlkiscanner.ui_design import apply_theme, page_header

apply_theme()
page_header('EQUITY-STUDIE', 'Drawdown aus echten Kursen nachgemessen',
            'Der offizielle Equity-DD ist eine Broker-Selbstauskunft. '
            'Hier wird er aus der Trade-Historie und echten Kursen '
            'stundenfein rekonstruiert — inklusive der offenen Positionen.')

with st.expander('Wie wird gemessen?', expanded=False, icon=':material/science:'):
    st.markdown(
        '**Die Idee.** Für jede Stunde der Handelshistorie wird der Kontostand '
        'nachgebaut: **Startkapital + realisierte Gewinne (geschlossene '
        'Trades) + offener Betrag (floating)** aller dann offenen Positionen. '
        'Der offene Betrag wird mit dem echten Stunden-Schlusskurs '
        '(H1-Bar-Close) je Währungspaar bewertet. Der größte Rückfall dieser '
        'Kurve ist der nachgemessene Equity-Drawdown — die Zahl, die der '
        'Broker als „By Equity“ meldet, nur hier aus unabhängigen Kursen '
        'berechnet.')
    st.markdown(
        '**GMT-Abgleich je Währungspaar.** Trade-Zeiten sind Serverzeit des '
        'Signal-Brokers, Kurse Serverzeit des Referenz-Terminals. Der '
        'Versatz wird JE SYMBOL separat bestimmt: Open- und Close-Kurse der '
        'Trades müssen in der High-Low-Spanne der getroffenen H1-Bar liegen — '
        'der Versatz mit der höchsten Trefferquote gewinnt. Symbole mit zu '
        'wenigen Proben bekommen den Median der erkannten Symbole '
        '(offengelegt in der Tabelle).')
    st.markdown(
        '**Was fehlt, wird gemeldet.** Steht ein Kurs am Referenzterminal '
        '(Tickmill) nicht zur Verfügung, wird nur für die vorhandenen '
        'Währungspaare gerechnet — und jedes fehlende Symbol namentlich '
        'genannt, inklusive des Hinweises, dass der Drawdown ohne diese '
        'Symbole niedriger ausfallen kann, als er wirklich war. '
        'Stundenlücken in der Equity-Spur werden nicht interpoliert.')
    st.markdown(
        '**Bewertet wird hier nichts.** Die Studie misst und zeigt '
        '(realisierter Betrag, offener Betrag, Unterwasser-Phase, '
        'Risiko-Texte). Ampel, Score und Urteil bleiben verbindlich bei der '
        'Engine — diese Seite ändert keine Bewertung.')

results_live = [r for r in pipeline.results_from_db()
                if getattr(r, 'source_kind', 'live') == 'live'
                and getattr(r, 'trades_path', '')]
results = [r for r in results_live if Path(r.trades_path).exists()]

if not results:
    st.info('Kein Signal mit gespeicherter Trade-Liste verfügbar. Die Studie '
            'braucht die Trade-Datei aus dem letzten Scan (Cache) — bitte '
            'erst einen Scan starten (z. B. Teilscan auf der Scan-Seite).',
            icon=':material/info:')
    st.page_link('app_pages/scan.py', label='Zur Scan-Seite', icon=':material/arrow_forward:')
    st.page_link('app_pages/ergebnisse.py', label='Zu den Ergebnissen', icon=':material/arrow_forward:')
    st.stop()

st.caption(f'{len(results)} von {len(results_live)} Signalen mit vorhandener '
           'Trade-Datei — die übrigen müssten erst neu gescannt werden.')

auswahl = st.selectbox(
    'Signal',
    results,
    index=0,
    format_func=lambda r: (f"{getattr(r, 'ampel', '')} {getattr(r, 'name', '') or r.id} "
                           f"· #{r.id} · {getattr(r, 'quelle', 'mql5') or 'mql5'}"),
    key='eqdd_seite_signal')

if auswahl is not None:
    render_studie(auswahl, key_prefix='eqdd_seite')
