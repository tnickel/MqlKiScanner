# -*- coding: utf-8 -*-
"""Seite „Alle Signale“ — unabhängige Statistikübersicht vor dem Workflow.

Eigene Seite (Nutzer-Wunsch 05.10.2026): ALLE gemeldeten Signale aller
Quellen als Liste, mit rein gerechneten Kennzahlen aus dem Trade-Cache
(Monatsrenditen, geometrischer Ertrag, Profitfaktor, Winrate, Trading-DD
aus geschlossenen Trades, Martingale-Schnellflag) — VOR dem KI-Workflow,
ohne selbst zu bewerten. Zeile wählen → Detailansicht mit Balkengrafik,
Konto-Kurve und Button zur Equity-Studie (Max-DD aus Kursen).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import pandas as pd
import streamlit as st

from mqlkiscanner import db, pipeline, signal_statistik
from mqlkiscanner.alle_signale_ui import render_detail, tabellen_zeile
from mqlkiscanner.ui_design import apply_theme, info_button, page_header

apply_theme()
page_header('ALLE SIGNALE', 'Unabhängige Statistik vor dem Workflow',
            'Alle gemeldeten Signale aller Quellen — rein aus dem Trade-Cache '
            'gerechnet, ohne KI und ohne Bewertung. Erst selber ein Bild '
            'machen, dann entscheidet der Workflow.')
with st.container(horizontal=True, vertical_alignment='center'):
    st.caption('Vorstufe: Kurve aus **geschlossenen** Trades (offenes Floating '
               'fehlt). Max-Drawdown inkl. Floating → Button in der Detailansicht '
               '(Equity-Studie). Ampel/Urteil bleiben beim Workflow.')
    info_button('alle_signale', key='alle_signale_info')

katalog = db.list_catalog()
stats_je_id = {zeile['signal_id']: (zeile.get('stats') or {}) for zeile in katalog}
alle = [r for r in pipeline.results_from_db()
        if getattr(r, 'source_kind', 'live') == 'live']

if not alle:
    st.info('Noch keine Signale in der Datenbank — erst auf der Scan-Seite '
            'Signale holen (Station 1) oder einen Scan starten.',
            icon=':material/info:')
    st.caption('→ Weiter geht es auf der Scan-Seite (Navigation links).')
    st.stop()

with st.container(horizontal=True):
    suche = st.text_input('Name oder Signal-ID', key='alle_signale_suche',
                          placeholder='z. B. Lexo oder 2000028')
    quellen = sorted({r.quelle for r in alle})
    gewaehlte_quellen = st.pills('Quelle', quellen, selection_mode='multi',
                                 key='alle_signale_quelle',
                                 default=quellen if len(quellen) <= 5 else None)
    nur_trades = st.toggle('Nur mit Trade-Cache', value=False,
                           key='alle_signale_nur_trades',
                           help='Nur Signale anzeigen, deren Trade-Export '
                                'bereits gespeichert ist (Export-Auswahl '
                                'top 30 je Quelle, Fix-IDs, gescannte Signale).')


@st.cache_data(persist='disk', show_spinner=False)
def _statistik_cached(trades_pfad: str, stats_json: str) -> dict | None:
    return signal_statistik.berechne(trades_pfad, json.loads(stats_json or '{}'))


def _statistik_fuer(result) -> dict | None:
    pfad = getattr(result, 'trades_path', '') or ''
    if not pfad or not Path(pfad).exists():
        return None
    rohstats = stats_je_id.get(result.id, {})
    return _statistik_cached(pfad, json.dumps(rohstats, sort_keys=True, default=str))


suche_cf = (suche or '').strip().casefold()
sichtbar = []
for r in alle:
    if suche_cf and suche_cf not in f'{r.name} {r.id}'.casefold():
        continue
    if gewaehlte_quellen and r.quelle not in gewaehlte_quellen:
        continue
    if nur_trades and not (getattr(r, 'trades_path', '') or ''):
        continue
    sichtbar.append(r)

st.caption(f'{len(sichtbar)} von {len(alle)} Signalen'
           + (f' · Quelle: {", ".join(gewaehlte_quellen)}' if gewaehlte_quellen else '')
           + f' · {sum(1 for r in sichtbar if getattr(r, "trades_path", ""))} mit Trade-Cache')

if not sichtbar:
    st.info('Kein Signal passt zu diesem Filter.', icon=':material/filter_alt:')
    st.stop()

with st.spinner('Statistiken aus dem Trade-Cache rechnen (einmalig — danach gecacht) …'):
    paare = [(r, _statistik_fuer(r)) for r in sichtbar]


def _prozent(titel: str):
    return st.column_config.NumberColumn(titel, format='%.2f')
df = pd.DataFrame([tabellen_zeile(r, s) for r, s in paare])
_gestylt = df.style
if 'RetDD (Vorbehalt)' in df.columns:
    # Vorbehaltlicher RetDD (Kursmessung unzuverlässig) immer orange —
    # gleiche dezente Konvention wie in der Ergebnistabelle.
    _gestylt = _gestylt.map(
        lambda v: 'background-color: rgba(249,115,22,0.12); color: #fb923c'
        if pd.notna(v) else '', subset=['RetDD (Vorbehalt)'])
st.dataframe(
    _gestylt,
    key='alle_signale_tabelle',
    on_select='rerun',
    selection_mode='single-row',
    hide_index=True,
    height=480,
    width="stretch",
    column_config={
        'Ampel': st.column_config.TextColumn('Ampel', help='Offizielle Engine-Ampel '
                                   '(nur Anzeige — diese Seite bewertet nicht)'),
        'Fix': st.column_config.TextColumn('Fix', help='📌 FIX = Signal-ID steht auf '
                                    'der Immer-scannen-Liste'),
        'Name': st.column_config.TextColumn('Name', width='medium'),
        'Quelle': st.column_config.TextColumn('Quelle'),
        'Plattform': st.column_config.TextColumn('Plattform'),
        'ID': st.column_config.NumberColumn('ID', format='%.0f'),
        'Wochen': st.column_config.NumberColumn('Wochen', format='%.0f'),
        'Abonnenten': st.column_config.NumberColumn('Abonnenten', format='%.0f'),
        'Drawdown % (Plattform)': _prozent('Drawdown % (Plattform)'),
        'Ertrag %/M (Plattform)': _prozent('Ertrag %/M (Plattform)'),
        'Gewinn %/M (geom.)': _prozent('Gewinn %/M (geom.)'),
        'Trading-DD % (Trades)': _prozent('Trading-DD % (Trades)'),
        'RetDD': st.column_config.NumberColumn('RetDD', format='%.2f',
                                    help='Gewinn %/Monat ÷ belastbar gemessener '
                                         'Max-Drawdown % (Equity inkl. Floating) — '
                                         'Mindestqualität 1,0'),
        'RetDD (Vorbehalt)': st.column_config.NumberColumn('RetDD (Vorbehalt)',
                                    format='%.2f',
                                    help='ORANGE = VORBEHALT: Gewinn %/Monat ÷ roher '
                                         'Kurs-Max-DD, dessen Zeitbasis/Kursabdeckung '
                                         'die Verlässlichkeitsprüfung NICHT bestanden '
                                         'hat (z. B. Grid-Positionen über '
                                         'Zeitwechsel-Grenzen). Nur orientierend — '
                                         'ohne belastbare Messung kein Grün'),
        'Profitfaktor': _prozent('Profitfaktor'),
        'Winrate %': st.column_config.NumberColumn('Winrate %', format='%.1f'),
        'Trades': st.column_config.NumberColumn('Trades', format='%.0f'),
        'Basis': st.column_config.TextColumn('Basis', help='Kapitalbasis: CSV = '
                                 'Einzahlungen im Export · Seite = Signalseite '
                                 '„Initial Deposit“ · implizit = Web-Balance − '
                                 'Trade-Netto · virtuell = 10.000-USD-Annahme'),
        'Forensik': st.column_config.TextColumn('Forensik'),
    })

csv = df.to_csv(index=False, sep=';').encode('utf-8-sig')
st.download_button('Gefilterte Tabelle als CSV', csv, 'alle-signale.csv',
                   'text/csv', key='alle_signale_download',
                   icon=':material/download:')

ereignis = st.session_state.get('alle_signale_tabelle')
gewaehlt_idx = None
if ereignis and ereignis.selection.rows:
    gewaehlt_idx = ereignis.selection.rows[0]

if gewaehlt_idx is not None:
    st.divider()
    gewaehlt = sichtbar[gewaehlt_idx]
    statistik = dict(paare[gewaehlt_idx][1] or {})
    render_detail(gewaehlt, statistik, key_prefix=f'alle_signale_detail_{gewaehlt.id}')
else:
    st.caption('Zeile anklicken für die Detailansicht: Monats-Balken, Konto-Kurve '
               'und Max-DD-Berechnung aus Kursen.')
