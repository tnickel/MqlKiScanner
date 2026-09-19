"""Results workspace: database catalog, session run, or archived run."""
from __future__ import annotations

import json
import sys
from hashlib import sha1
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import streamlit as st

from mqlkiscanner import config, db, pipeline, scan_state
from mqlkiscanner.app_ui import (clear_report_selection, render_detail, render_report_panel,
                                 render_results_table, results_to_dataframe)
from mqlkiscanner.ui_design import (apply_theme, info_button, page_header, section_header,
                                    urteile_farbig)

apply_theme()
hero_results_banner = Path(__file__).resolve().parents[1] / "assets" / "hero_results_banner.jpg"
page_header('ENTSCHEIDUNG', 'Risiken vergleichen, Evidenz prüfen',
            'Erst Schutz und Drawdown beurteilen, dann den Ertrag. Neue Bewertungen sind klar markiert.',
            image_path=str(hero_results_banner) if hero_results_banner.exists() else None)
st.session_state.setdefault('scan_results', [])
st.session_state.setdefault('last_run_file', None)
st.session_state.setdefault('refreshed_signal_ids', None)
scan_state.sync_worker_state(st.session_state)

with st.container(border=True):
    section_header('Datenquelle', 'Aktueller Katalog, diese Sitzung oder eine historische Momentaufnahme.',
                   help_key='results_runs')
    runs = sorted(config.RUNS_DIR.glob('*/results.json'), reverse=True)
    options = ['Datenbank (alle Berichte)', 'Aktuelle Sitzung'] + [str(p) for p in runs[:12]]

    def _fmt(p: str) -> str:
        if p.startswith('Datenbank') or p == 'Aktuelle Sitzung':
            return p
        return Path(p).parent.name

    selected_run = st.selectbox('Quelle', options, format_func=_fmt, key='results_run')
    freshness = st.session_state.get('refreshed_signal_ids')
    fresh_ids: set[int] = set(freshness or [])
    # Nur alte Sitzungsstände ohne explizite Frischeliste benötigen den Fallback.
    # [] bedeutet: Im letzten Lauf wurde kein Signaldatensatz aktualisiert.
    if freshness is None and st.session_state.scan_results:
        fresh_ids = {r.id for r in st.session_state.scan_results
                     if getattr(r, 'source_kind', 'live') == 'live'}

    if selected_run.startswith('Datenbank'):
        results = [r for r in pipeline.results_from_db()
                   if getattr(r, 'source_kind', 'live') == 'live']
        # Frisch aktualisierte Signale oben.
        results.sort(key=lambda r: (0 if r.id in fresh_ids else 1, (r.name or '').casefold()))
        portfolio = db.get_latest_analysis(None, 'portfolio')
        st.caption(
            f'Datenbank · {len(results)} Signale. '
            f'„NEU“ = im letzten Lauf Kennzahlen, Befunde oder Signalberichte neu gespeichert '
            f'({len(fresh_ids)} Stück); reine Übernahmen zählen nicht.'
        )
    elif selected_run == 'Aktuelle Sitzung':
        results = list(st.session_state.scan_results)
        portfolio = st.session_state.get('portfolio_result')
        if portfolio is None and st.session_state.get('portfolio_bericht'):
            portfolio = {'text': st.session_state.portfolio_bericht}
        st.caption('Nur die Ergebnisse des letzten Scans in dieser Sitzung.')
    else:
        try:
            data = json.loads(Path(selected_run).read_text(encoding='utf-8'))
            results = [pipeline.ScanResult(**{k: v for k, v in row.items()
                        if k in pipeline.ScanResult.__dataclass_fields__}) for row in data.get('ergebnisse', [])]
            portfolio = data.get('portfolio')
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            st.error(f'Der gespeicherte Lauf konnte nicht gelesen werden: {exc}')
            st.stop()
        st.caption(f'Archiv · {Path(selected_run).parent.name} · historische Momentaufnahme')
        fresh_ids = set()

# Das Portfolio stammt aus derselben Quelle wie die Signale. Alte Archive
# ohne Portfolio erhalten keinen heutigen Bericht aus dem Live-Katalog.
demo_only = bool(results) and all(getattr(r, 'source_kind', 'live') == 'demo'
                                  for r in results)
portfolio = None if demo_only or not isinstance(portfolio, dict) else portfolio


def _render_portfolio_report(report: dict) -> None:
    catalog_portfolio = selected_run.startswith('Datenbank')
    portfolio_title = ('Portfolio-Vorschlag · historischer Stand'
                       if catalog_portfolio else 'Portfolio-Vorschlag')
    section_header(
        portfolio_title,
        'Bericht über die bei seiner Erstellung berücksichtigten Signale. '
        'Die Tabellenfilter verändern ihn nicht.',
        help_key='portfolio_report',
    )
    with st.expander('Ausführlichen Portfolio-Bericht öffnen', expanded=False,
                     icon=':material/pie_chart:'):
        st.markdown('**Strategie-Mix, Assets und Gewichtung**')
        st.caption(f"Stand: {report.get('created_at') or 'nicht gespeichert'} · "
                   f"Modell: {report.get('model') or 'nicht gespeichert'} · Keine Anlageberatung.")
        if catalog_portfolio:
            st.info('Historische Momentaufnahme: Dieser Bericht wurde nicht mit den '
                    'aktuellen Katalogbewertungen abgeglichen.',
                    icon=':material/history:')
        if report.get('text'):
            st.markdown(urteile_farbig(report['text']), unsafe_allow_html=True)
        if issue := report.get('storage_error') or report.get('reason'):
            st.warning(f"Portfolio-Hinweis: {issue}")

if not results:
    with st.container(border=True):
        st.subheader('Noch keine Berichte in der Ansicht', icon=':material/manage_search:')
        st.write('Starte den Workflow oder lade Testdaten. Gespeicherte Auswertungen erscheinen hier unter „Datenbank“.')
        st.page_link('app_pages/scan.py', label='Zum Workflow', icon=':material/arrow_forward:')
    if portfolio:
        _render_portfolio_report(portfolio)
    st.stop()

# Never carry an open report from a different source or filter into this view.
source_signature = selected_run + '|' + '|'.join(str(r.id) for r in results)
if st.session_state.get('_results_source') != source_signature:
    clear_report_selection()
    st.session_state['_results_source'] = source_signature

section_header('Entscheidungsübersicht', 'Status der gewählten Datenquelle · fehlende Evidenz ist keine Entwarnung.',
               help_key='risk_status')
ampeln = [r.ampel for r in results]
with st.container(horizontal=True):
    st.metric('Signale', len(results), f"{ampeln.count('🟡')} Beobachtung",
              delta_color='off', border=True, icon=':material/radar:')
    st.metric('Kandidaten', ampeln.count('🟢'), border=True, icon=':material/check_circle:')
    st.metric('Risiko / Ausschluss', ampeln.count('🔴') + ampeln.count('⛔'),
              border=True, icon=':material/gpp_bad:')
    st.metric('Ohne Vollprüfung', ampeln.count('⚪'), border=True, icon=':material/help:')
st.caption(
    f"{len(results)} Signale insgesamt · {sum(1 for r in results if r.id in fresh_ids)} "
    "im letzten Lauf aktualisiert · leere Werte sind keine Entwarnung."
)

with st.container(border=True):
    section_header('Signale vergleichen', 'Filtern, dann eine Zeile für die vollständige Risikoprüfung auswählen.',
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
    st.caption(f'{len(visible)} von {len(results)} Signalen · Tabelle und CSV verwenden dieselben Filter.')
    show_fresh = fresh_ids if selected_run.startswith('Datenbank') or selected_run == 'Aktuelle Sitzung' else None
    if visible:
        signature = sha1((source_signature + repr([(r.id, r.name) for r in visible])
                          + repr(sorted(show_fresh or []))).encode()).hexdigest()[:12]
        selected = render_results_table(
            visible, key=f'ergebnisse_table_{signature}', compact=view != 'Alle Kennzahlen',
            fresh_ids=show_fresh)
        with st.container(horizontal=True, vertical_alignment='center', gap='xsmall'):
            csv = results_to_dataframe(visible, fresh_ids=show_fresh).drop(
                columns=['Bericht'], errors='ignore').to_csv(index=False, sep=';').encode('utf-8-sig')
            st.download_button('Gefilterte Tabelle als CSV', csv, 'mql-signale.csv', 'text/csv',
                               key='results_download', icon=':material/download:')
            info_button('results_runs', key='results_download_help')
    else:
        selected = None
        st.info('Keine Treffer. Entferne einen Statusfilter oder passe den Suchbegriff an.')

if st.session_state.get('report_signal_id') not in {r.id for r in visible}:
    clear_report_selection()
render_report_panel(visible)
if selected is not None:
    render_detail(selected)

if portfolio:
    _render_portfolio_report(portfolio)

if visible:
    with st.expander('Urteile im Überblick', expanded=False, icon=':material/summarize:'):
        for r in visible:
            with st.container(border=True):
                mark = ' · **NEU**' if r.id in fresh_ids else ''
                st.markdown(f'**{r.ampel} {r.name}** · #{r.id}{mark}')
                st.write(r.urteil or 'Noch kein Urteil vorhanden.')
