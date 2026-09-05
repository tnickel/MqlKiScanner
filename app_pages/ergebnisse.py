"""Results workspace: one filtered view, explicit archive provenance."""
from __future__ import annotations

import json
import sys
from hashlib import sha1
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import streamlit as st

from mqlkiscanner import config, pipeline
from mqlkiscanner.app_ui import render_detail, render_report_panel, render_results_table, results_to_dataframe
from mqlkiscanner.ui_design import apply_theme, info_button, page_header, section_header

apply_theme()
page_header('Auswertung / Evidenz vor Entscheidung', 'Ergebnisse im Überblick',
            'Signale vergleichen, Risiken einordnen und die Belege hinter jedem Urteil prüfen.')
st.session_state.setdefault('scan_results', [])
st.session_state.setdefault('last_run_file', None)

with st.container(border=True):
    section_header('Datenstand', 'Aktuelle Sitzung oder einen gespeicherten Lauf öffnen.', help_key='results_runs')
    runs = sorted(config.RUNS_DIR.glob('*/results.json'), reverse=True)
    selected_run = st.selectbox('Lauf', ['Aktuelle Sitzung'] + [str(p) for p in runs[:12]],
                               format_func=lambda p: p if p == 'Aktuelle Sitzung' else Path(p).parent.name,
                               key='results_run')
    if selected_run == 'Aktuelle Sitzung':
        results = st.session_state.scan_results
        st.caption('Ergebnisse des letzten Scans in dieser Sitzung. Archive werden separat angezeigt.')
    else:
        try:
            data = json.loads(Path(selected_run).read_text(encoding='utf-8'))
            results = [pipeline.ScanResult(**{k: v for k, v in row.items()
                        if k in pipeline.ScanResult.__dataclass_fields__}) for row in data.get('ergebnisse', [])]
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            st.error(f'Der gespeicherte Lauf konnte nicht gelesen werden: {exc}')
            st.stop()
        st.caption(f'Archiv · {Path(selected_run).parent.name} · historische Momentaufnahme')

if not results:
    with st.container(border=True):
        st.subheader('Dein erster Prüfbericht beginnt mit einem Scan', icon=':material/manage_search:')
        st.write('Starte einen Online-Scan oder prüfe die vorhandenen Verifikations-Datensätze ohne Login. Danach stehen hier Kennzahlen und Signal-Details bereit.')
        st.page_link('app_pages/scan.py', label='Zur Scan-Seite', icon=':material/arrow_forward:')
    st.stop()

# Never carry an open report from a different source or filter into this view.
source_signature = selected_run + '|' + '|'.join(str(r.id) for r in results)
if st.session_state.get('_results_source') != source_signature:
    st.session_state.pop('report_signal_id', None)
    st.session_state['_results_source'] = source_signature

section_header('Risikobild des Laufs', 'Bewertungen der Engine · zuerst die Evidenz prüfen.', help_key='risk_status')
ampeln = [r.ampel for r in results]
columns = st.columns(4)
columns[0].metric('Signale gesamt', len(results))
columns[1].metric('Kandidaten', ampeln.count('🟢'))
columns[2].metric('Beobachtung', ampeln.count('🟡'))
columns[3].metric('Risiko / Ausschluss', ampeln.count('🔴') + ampeln.count('⛔'))
st.caption(f"Vorprüfung ohne vollständige Trade-Forensik: {ampeln.count('⚪')} · leere Werte sind keine Entwarnung.")

with st.container(border=True):
    section_header('Signale vergleichen', 'Suchen → Zeile auswählen → Details und Bericht prüfen.', help_key='results_filter')
    c1, c2 = st.columns([2, 1])
    query = c1.text_input('Name oder Signal-ID', placeholder='Signal suchen …', key='results_search')
    view = c2.segmented_control('Tabellenansicht', ['Kompakt', 'Alle Kennzahlen'], default='Kompakt', key='results_view')
    labels = {'🟢': 'Kandidat', '🟡': 'Beobachtung', '🔴': 'Risiko-Flag', '⛔': 'Ausgeschlossen', '⚪': 'Vorprüfung'}
    statuses = st.pills('Statusfilter', list(labels), selection_mode='multi',
                        format_func=lambda s: f'{s} {labels[s]}', key='results_status')
    visible = [r for r in results if (not statuses or r.ampel in statuses)
               and (not query.strip() or query.strip().casefold() in f'{r.name} {r.id}'.casefold())]
    st.caption(f'{len(visible)} von {len(results)} Signalen angezeigt · Tabellenansicht und Export verwenden dieselben Filter.')
    if visible:
        signature = sha1((source_signature + repr([(r.id, r.name) for r in visible])).encode()).hexdigest()[:12]
        sel_id = render_results_table(visible, key=f'ergebnisse_table_{signature}', compact=view != 'Alle Kennzahlen')
        with st.container(horizontal=True, vertical_alignment='center', gap='xsmall'):
            csv = results_to_dataframe(visible).drop(columns=['Bericht'], errors='ignore').to_csv(index=False, sep=';').encode('utf-8-sig')
            st.download_button('Gefilterte Tabelle als CSV', csv, 'mql-signale.csv', 'text/csv',
                               key='results_download', icon=':material/download:')
            info_button('results_runs', key='results_download_help')
    else:
        sel_id = None
        st.info('Keine Treffer. Entferne einen Statusfilter oder passe den Suchbegriff an.')

if st.session_state.get('report_signal_id') not in {r.id for r in visible}:
    st.session_state.pop('report_signal_id', None)
render_report_panel(visible)
if sel_id is not None:
    selected = next((r for r in visible if r.id == sel_id), None)
    if selected:
        render_detail(selected)

if visible:
    with st.expander('Urteile im Überblick', expanded=False, icon=':material/summarize:'):
        for r in visible:
            with st.container(border=True):
                st.markdown(f'**{r.ampel} {r.name}** · #{r.id}')
                st.write(r.urteil or 'Noch kein Urteil vorhanden.')
