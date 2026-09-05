"""Results workspace: database catalog, session run, or archived run."""
from __future__ import annotations

import json
import sys
from hashlib import sha1
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import streamlit as st

from mqlkiscanner import config, db, pipeline
from mqlkiscanner.app_ui import render_detail, render_report_panel, render_results_table, results_to_dataframe
from mqlkiscanner.ui_design import (apply_theme, info_button, page_header, section_header,
                                    urteile_farbig)

apply_theme()
page_header('Auswertung / Evidenz vor Entscheidung', 'Ergebnisse im Überblick',
            'Alle gespeicherten Berichte aus der Datenbank — neu aktualisierte Läufe sind markiert.')
st.session_state.setdefault('scan_results', [])
st.session_state.setdefault('last_run_file', None)
st.session_state.setdefault('refreshed_signal_ids', [])

with st.container(border=True):
    section_header('Datenstand', 'Datenbank, aktuelle Sitzung oder einen gespeicherten Lauf.',
                   help_key='results_runs')
    runs = sorted(config.RUNS_DIR.glob('*/results.json'), reverse=True)
    options = ['Datenbank (alle Berichte)', 'Aktuelle Sitzung'] + [str(p) for p in runs[:12]]

    def _fmt(p: str) -> str:
        if p.startswith('Datenbank') or p == 'Aktuelle Sitzung':
            return p
        return Path(p).parent.name

    selected_run = st.selectbox('Quelle', options, format_func=_fmt, key='results_run')
    fresh_ids: set[int] = set(st.session_state.get('refreshed_signal_ids') or [])
    if not fresh_ids and st.session_state.scan_results:
        fresh_ids = {r.id for r in st.session_state.scan_results}

    if selected_run.startswith('Datenbank'):
        results = pipeline.results_from_db()
        # Frisch aktualisierte Signale oben.
        results.sort(key=lambda r: (0 if r.id in fresh_ids else 1, (r.name or '').casefold()))
        st.caption(
            f'Datenbank · {len(results)} Signale. '
            f'„NEU“ = im letzten Lauf dieser Sitzung aktualisiert ({len(fresh_ids)} Stück).'
        )
    elif selected_run == 'Aktuelle Sitzung':
        results = list(st.session_state.scan_results)
        st.caption('Nur die Ergebnisse des letzten Scans in dieser Sitzung.')
    else:
        try:
            data = json.loads(Path(selected_run).read_text(encoding='utf-8'))
            results = [pipeline.ScanResult(**{k: v for k, v in row.items()
                        if k in pipeline.ScanResult.__dataclass_fields__}) for row in data.get('ergebnisse', [])]
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            st.error(f'Der gespeicherte Lauf konnte nicht gelesen werden: {exc}')
            st.stop()
        st.caption(f'Archiv · {Path(selected_run).parent.name} · historische Momentaufnahme')
        fresh_ids = set()

# Station 5: globaler Portfolio-Bericht (DB, signal_id=0, kind='portfolio') —
# sichtbar auch ohne gespeicherte Signale, daher vor dem Leer-Stop.
portfolio = db.get_latest_analysis(0, 'portfolio')
if portfolio:
    with st.container(border=True):
        section_header('Portfolio-Vorschlag', 'KI-Empfehlung über alle Signale: Strategie-Mix, Assets, Gewichtung.',
                       help_key='portfolio_report')
        st.caption(f"Stand: {portfolio['created_at']} · Modell: {portfolio['model']} · Keine Anlageberatung.")
        st.markdown(urteile_farbig(portfolio['text']), unsafe_allow_html=True)

if not results:
    with st.container(border=True):
        st.subheader('Noch keine Berichte in der Ansicht', icon=':material/manage_search:')
        st.write('Starte den Workflow oder lade Testdaten. Gespeicherte Auswertungen erscheinen hier unter „Datenbank“.')
        st.page_link('app_pages/scan.py', label='Zum Workflow', icon=':material/arrow_forward:')
    st.stop()

# Never carry an open report from a different source or filter into this view.
source_signature = selected_run + '|' + '|'.join(str(r.id) for r in results)
if st.session_state.get('_results_source') != source_signature:
    st.session_state.pop('report_signal_id', None)
    st.session_state['_results_source'] = source_signature

section_header('Risikobild', 'Bewertungen der Engine · zuerst die Evidenz prüfen.', help_key='risk_status')
ampeln = [r.ampel for r in results]
columns = st.columns(5)
columns[0].metric('Signale', len(results))
columns[1].metric('Neu / aktualisiert', sum(1 for r in results if r.id in fresh_ids))
columns[2].metric('Kandidaten', ampeln.count('🟢'))
columns[3].metric('Beobachtung', ampeln.count('🟡'))
columns[4].metric('Risiko / Ausschluss', ampeln.count('🔴') + ampeln.count('⛔'))
st.caption(f"Vorprüfung ohne vollständige Trade-Forensik: {ampeln.count('⚪')} · leere Werte sind keine Entwarnung.")

with st.container(border=True):
    section_header('Signale vergleichen', 'Suchen → Zeile auswählen → Details und Bericht prüfen.',
                   help_key='results_filter')
    c1, c2, c3 = st.columns([2, 1, 1])
    query = c1.text_input('Name oder Signal-ID', placeholder='Signal suchen …', key='results_search')
    view = c2.segmented_control('Tabellenansicht', ['Kompakt', 'Alle Kennzahlen'], default='Kompakt',
                                key='results_view')
    only_fresh = c3.toggle('Nur NEU', value=False, key='results_only_fresh',
                           disabled=not fresh_ids)
    labels = {'🟢': 'Kandidat', '🟡': 'Beobachtung', '🔴': 'Risiko-Flag', '⛔': 'Ausgeschlossen', '⚪': 'Vorprüfung'}
    statuses = st.pills('Statusfilter', list(labels), selection_mode='multi',
                        format_func=lambda s: f'{s} {labels[s]}', key='results_status')
    # Archiv/leere Frische: Session-State des Toggles nicht anwenden.
    apply_fresh = bool(only_fresh and fresh_ids)
    visible = [r for r in results if (not statuses or r.ampel in statuses)
               and (not query.strip() or query.strip().casefold() in f'{r.name} {r.id}'.casefold())
               and (not apply_fresh or r.id in fresh_ids)]
    st.caption(f'{len(visible)} von {len(results)} Signalen angezeigt · Tabellenansicht und Export verwenden dieselben Filter.')
    show_fresh = fresh_ids if selected_run.startswith('Datenbank') or selected_run == 'Aktuelle Sitzung' else None
    if visible:
        signature = sha1((source_signature + repr([(r.id, r.name) for r in visible])
                          + repr(sorted(show_fresh or []))).encode()).hexdigest()[:12]
        sel_id = render_results_table(
            visible, key=f'ergebnisse_table_{signature}', compact=view != 'Alle Kennzahlen',
            fresh_ids=show_fresh)
        with st.container(horizontal=True, vertical_alignment='center', gap='xsmall'):
            csv = results_to_dataframe(visible, fresh_ids=show_fresh).drop(
                columns=['Bericht'], errors='ignore').to_csv(index=False, sep=';').encode('utf-8-sig')
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
                mark = ' · **NEU**' if r.id in fresh_ids else ''
                st.markdown(f'**{r.ampel} {r.name}** · #{r.id}{mark}')
                st.write(r.urteil or 'Noch kein Urteil vorhanden.')
