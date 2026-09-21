"""Results workspace: database catalog, session run, or archived run."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from hashlib import sha1
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import streamlit as st

from mqlkiscanner import (config, db, downloader_sync, pipeline, regelwerk,
                          scan_state, scan_worker, tiefen_batch, tradeserver_sync)
from mqlkiscanner.app_ui import (clear_report_selection, render_ampel_matrix, render_detail,
                                 render_downloader_docs_panel, render_report_panel,
                                 render_portfolio_pdf_viewer,
                                 render_results_table, results_to_dataframe,
                                 render_wechsel_karten, _gelbe_anzeige)
from mqlkiscanner.ui_design import (action_button, aktivitaets_banner, apply_theme,
                                    info_button, page_header, section_header,
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

    # Leichter Abgleich gegen den MqlDownloader, ohne neuen Scan und ohne
    # Neubewertung: nur Verlauf + PDFs, niemals Ampeln/Urteile/Scores.
    abgleich_spalte, abgleich_hinweis = st.columns([1, 2], gap="medium",
                                                   vertical_alignment="center")
    with abgleich_spalte:
        abgleich_klick = action_button(
            "MqlDownloader-Abgleich", key="results_downloader_sync",
            help_key="downloader_sync", icon=":material/sync:",
            disabled=not any(getattr(r, 'source_kind', 'live') == 'live' for r in results))
    with abgleich_hinweis:
        st.caption('Holt Abonnenten-Verläufe und Testreport-PDFs für die Signale '
                   'dieser Quelle aus dem lokalen Downloader — ohne MQL5-Abruf.')
    if abgleich_klick:
        ziele, gesehen = [], set()
        for r in results:
            if getattr(r, 'source_kind', 'live') != 'live' or not r.id or r.id in gesehen:
                continue
            gesehen.add(r.id)
            ziele.append((r.id, getattr(r, 'platform', '') or ''))
        if not downloader_sync.konfiguriert():
            st.info('MqlDownloader ist nicht konfiguriert. Base-URL im Admin-Bereich '
                    'unter „MqlDownloader“ hinterlegen.', icon=':material/settings_ethernet:')
        elif not ziele:
            st.info('Keine Live-Signale in dieser Quelle zum Abgleichen.')
        else:
            with st.status('MqlDownloader-Abgleich läuft …', expanded=True) as status:
                st.write(f'{len(ziele)} Signale: Abonnenten-Verlauf + Testreport-PDF-Prüfung.')
                banner = aktivitaets_banner('MqlDownloader-Abgleich läuft …')
                try:
                    summary = downloader_sync.sync_many(
                        ziele, progress=lambda done, total, sid: st.write(
                            f'Signal {done}/{total} · #{sid}'))
                finally:
                    banner.empty()
                if summary['abgebrochen']:
                    st.write('Abbruch: ' + summary['abgebrochen'])
                    status.update(label='Abgleich abgebrochen', state='error', expanded=False)
                else:
                    status.update(label='Abgleich abgeschlossen', state='complete', expanded=False)
            bilanz = (f"{summary['signale']} Signale · {summary['verlaufspunkte']} "
                      f"Verlaufspunkte gesichert · {summary['neue_pdfs']} neue "
                      "Testreport-PDFs · Bewertungen bleiben unberührt.")
            if summary['abgebrochen']:
                st.warning('Abgleich abgebrochen — bereits Geladenes bleibt gespeichert. '
                           + str(summary['abgebrochen']))
            elif summary['fehler']:
                st.warning(f"Abgleich mit {len(summary['fehler'])} Hinweis(en): {bilanz}")
            else:
                st.success(bilanz)

    # Einmal-Sync zum Tradeserver (MqlTradeMonitor): Tabelle + PDFs übertragen,
    # danach wird die Verbindung wieder getrennt. Bewertet nie neu.
    ts_spalte, ts_hinweis = st.columns([1, 2], gap="medium",
                                       vertical_alignment="center")
    with ts_spalte:
        ts_klick = action_button(
            "Tradeserver-Sync", key="results_tradeserver_sync",
            help_key="tradeserver_sync", icon=":material/cloud_upload:",
            disabled=not any(getattr(r, 'source_kind', 'live') == 'live'
                             for r in results))
    with ts_hinweis:
        st.caption('Überträgt diese Tabelle und alle zugehörigen PDFs zum '
                   'MqlTradeMonitor (Kachel „MqlKiScanner“) — verbinden, übertragen, '
                   'trennen.')
    if ts_klick:
        if not tradeserver_sync.konfiguriert():
            st.info('Kein Tradeserver konfiguriert. Base-URL und API-Key im '
                    'Admin-Bereich unter „Tradeserver“ hinterlegen.',
                    icon=':material/settings_ethernet:')
        elif not any(getattr(r, 'source_kind', 'live') == 'live' for r in results):
            st.info('Keine Live-Signale in dieser Quelle zum Übertragen.')
        else:
            with st.status('Tradeserver-Sync läuft …', expanded=True) as status:
                st.write('Anmeldung, Tabellen-Snapshot, Dokumente (nur Änderungen), '
                         'Abschluss — danach ist die Verbindung wieder getrennt.')
                banner = aktivitaets_banner('Tradeserver-Sync läuft …')
                try:
                    ts_summary = tradeserver_sync.sync_alle(
                        results, portfolio,
                        fresh_ids=fresh_ids,
                        progress=lambda done, total, label: st.write(
                            f'Dokument {done}/{total} · {label}'))
                finally:
                    banner.empty()
                if ts_summary['abgebrochen']:
                    st.write('Abbruch: ' + str(ts_summary['abgebrochen']))
                    status.update(label='Sync abgebrochen', state='error', expanded=False)
                else:
                    status.update(label='Sync abgeschlossen', state='complete', expanded=False)
            groesse_mb = ts_summary['bytes'] / 1024 / 1024
            ts_bilanz = (f"{ts_summary['signale']} Signale übertragen "
                         f"({ts_summary['gespeichert']} gespeichert, "
                         f"{ts_summary['geloescht']} am Server entfernt) · "
                         f"{ts_summary['uebertragen']} PDFs übertragen, "
                         f"{ts_summary['uebersprungen']} unverändert "
                         f"({groesse_mb:.1f} MB) · Dauer {ts_summary['dauer_s']} s · "
                         "Verbindung danach getrennt.")
            if ts_summary['abgebrochen']:
                st.warning('Sync abgebrochen — der Server behält den letzten '
                           'vollständigen Stand. ' + str(ts_summary['abgebrochen']))
            elif ts_summary['fehler']:
                st.warning(f"Sync mit {len(ts_summary['fehler'])} Hinweis(en): "
                           f"{ts_bilanz}")
                with st.expander('Hinweise im Detail', icon=':material/error_outline:'):
                    for zeile in ts_summary['fehler']:
                        st.caption(zeile)
            else:
                st.success(ts_bilanz)

@st.fragment(run_every=2.0)
def _tiefen_batch_fenster() -> None:
    """Live-Fortschritt der Batch-Erweiterte-KI-Analyse (tickt alle 2 s)."""
    batch = tiefen_batch.aktiver_batch()
    if batch is None:
        return
    total = max(1, batch["total"])
    if tiefen_batch.batch_laeuft():
        st.progress(
            batch["done"] / total,
            text=(f"Strategie {batch['done']}/{batch['total']} · "
                  f"aktuell: {batch['aktuell'] or '—'} · "
                  f"übersprungen: {batch['uebersprungen']} · "
                  f"Fehler: {batch['fehler']}"),
        )
        if st.button("Batch stoppen (nach der aktuellen Strategie)",
                     key="tiefe_batch_stop", icon=":material/stop_circle:"):
            tiefen_batch.batch_stoppen()
            st.rerun(scope="fragment")
        return
    dauer = str((batch.get("ende") or datetime.now()) - batch["start"]).split(".")[0]
    art = "Abbruch per Stop" if batch["abgebrochen"] else "abgeschlossen"
    (st.warning if batch["fehler"] else st.success)(
        f"Batch {art}: {batch['done']}/{batch['total']} bearbeitet · "
        f"{batch['uebersprungen']} übersprungen (bereits vorhanden) · "
        f"{batch['fehler']} Fehler · Dauer {dauer}",
        icon=":material/warning:" if batch["fehler"] else ":material/check_circle:",
    )
    if batch["fehler_liste"]:
        with st.expander(f"{batch['fehler']} Fehler im Detail",
                         icon=":material/error_outline:"):
            for zeile in batch["fehler_liste"]:
                st.caption(zeile)


# Gelber Batch-Start: Erweiterte KI-Analyse für alle Signale der Quelle,
# vorhandene werden übersprungen (fortsetzbar), läuft im Hintergrund-Thread.
with st.container(border=True):
    batch_spalte, batch_hinweis_spalte = st.columns([1, 2], gap="medium",
                                                    vertical_alignment="center")
    with batch_spalte:
        _gelbe_anzeige("tiefe_batch_start", True)
        batch_klick = st.button(
            "🟡 Erweiterte KI-Analyse für alle Strategien starten",
            key="tiefe_batch_start", type="primary",
            icon=":material/auto_awesome:",
            disabled=tiefen_batch.batch_laeuft() or scan_worker.active_run() is not None,
        )
    with batch_hinweis_spalte:
        st.caption("Läuft über alle Signale dieser Quelle mit Trade-Daten. "
                   "Vorhandene Tiefenanalysen werden übersprungen — dadurch "
                   "fortsetzbar. Pro Strategie mehrere Minuten, verbraucht Tokens.")
    if batch_klick:
        ziele, gesehen = [], set()
        for r in results:
            if (getattr(r, 'source_kind', 'live') != 'live' or not r.id
                    or not getattr(r, 'trades_path', '') or r.id in gesehen):
                continue
            gesehen.add(r.id)
            ziele.append(r)
        ok, meldung = tiefen_batch.batch_starten(ziele)
        if ok:
            st.toast(f"Batch gestartet: {len(ziele)} Strategien",
                     icon=":material/auto_awesome:")
            st.rerun()
        else:
            st.warning(meldung, icon=":material/info:")
_tiefen_batch_fenster()

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
        render_portfolio_pdf_viewer(
            report, key=f"results_portfolio_pdf_{'catalog' if catalog_portfolio else 'source'}")
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
source_signature = selected_run + '|' + '|'.join(
    repr((r.source_kind, r.id, r.trades_path, r.trades_sha256, r.name)) for r in results)
if st.session_state.get('_results_source') != source_signature:
    clear_report_selection()
    st.session_state.pop('downloader_doc_signal_id', None)
    st.session_state.pop('downloader_doc_identity', None)
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

# Wechsel-Protokoll (Nutzer-Anforderung): Farben werden bei jedem Scan
# aufgezeichnet; Wechsel speziell protokolliert und per Button einsehbar.
try:
    wechsel_gesamt = db.count_ampel_wechsel()
except Exception:
    wechsel_gesamt = 0


@st.dialog('⚡ Ampel-Wechsel-Protokoll', width='large')
def _wechsel_dialog() -> None:
    """Dauerhafte Wechselliste: Farbwechsel und gekippte Kriterien mit Begründung."""
    st.caption(
        'Jeder Eintrag ist ein protokollierter Wechsel aus der Datenbank — '
        'Farbwechsel (🟡→🟢, 🟢→🟡, …) oder ein gekipptes Einzelkriterium bei '
        'gleichbleibender Farbe (Frühindikator). Chronik-Beginn war die '
        'Einführung der Aufzeichnung; alte Läufe wurden bewusst nicht nachträglich importiert.')
    nur_farbe = st.toggle('Nur Farbwechsel anzeigen', key='wechsel_nur_farbe')
    wechsel = db.list_ampel_wechsel(limit=200, nur_farbwechsel=nur_farbe)
    if not wechsel:
        st.info('Keine Einträge für diesen Filter.', icon=':material/filter_alt:')
        return
    render_wechsel_karten(wechsel)
    with st.expander('Wechsel-Historie je Signal', icon=':material/history:'):
        chronik: dict[int, list] = {}
        for w in reversed(wechsel):
            chronik.setdefault(w['signal_id'], []).append(w)
        for sid, eintraege in sorted(chronik.items()):
            name = next((e.get('name') for e in eintraege if e.get('name')), f'#{sid}')
            band = ' → '.join(e['ampel_neu'] for e in reversed(eintraege))
            letzter = eintraege[-1]['ts'] if eintraege else ''
            st.markdown(f"**{name}** · #{sid} · {band} "
                        f"`{letzter}`")


with st.container(border=True):
    wcol, bcol = st.columns([1.6, 1], gap='small', vertical_alignment='center')
    with wcol:
        st.markdown(f":material/history: **{wechsel_gesamt} protokollierte Wechsel** "
                    "— Farbwechsel und gekippte Kriterien, dauerhaft in der Datenbank.")
    with bcol:
        if st.button(f'Wechsel-Protokoll ansehen' + (f' ({wechsel_gesamt})' if wechsel_gesamt else ''),
                     key='results_wechsel_open', icon=':material/history:',
                     type='primary' if wechsel_gesamt else 'secondary',
                     disabled=not wechsel_gesamt,
                     help='Öffnet die Wechselliste: welcher Wechsel, wann, warum '
                          '(je Kriterium alt → neu mit exakter Berechnung).'):
            _wechsel_dialog()

with st.container(border=True):
    section_header('Signale vergleichen', 'Filtern, dann eine Zeile für die vollständige Risikoprüfung auswählen.',
                   help_key='results_filter')
    c1, c2, c3 = st.columns([1.5, 1.7, 0.8])
    query = c1.text_input('Name oder Signal-ID', placeholder='Signal suchen …', key='results_search')
    view = c2.segmented_control('Tabellenansicht', ['Kompakt', 'Alle Kennzahlen', 'Ampeln'],
                                default='Kompakt', key='results_view')
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
        signature = sha1((source_signature + repr([
            (r.source_kind, r.id, r.trades_path, r.trades_sha256, r.name) for r in visible])
                          + repr(sorted(show_fresh or []))).encode()).hexdigest()[:12]
        if view == 'Ampeln':
            render_ampel_matrix(visible, config.load_settings())
            selected = None
            st.caption('Zeilen-Auswahl und Detailansicht sind in den Ansichten '
                       '„Kompakt“ und „Alle Kennzahlen“ verfügbar.')
        else:
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
render_downloader_docs_panel(results)
if selected is not None:
    render_detail(selected)

with st.expander('Regelwerk · Ausschlussliste', expanded=False,
                 icon=':material/gavel:'):
    section_header('Warum ist ein Signal ausgeschlossen?',
                   'Harte Engine-Regeln plus die kuratierten Kriterien '
                   'hinter data/known_signals.json.',
                   help_key='ausschlussliste')
    st.markdown(regelwerk.regelwerk_markdown(config.load_settings()))

if portfolio:
    _render_portfolio_report(portfolio)

if visible:
    with st.expander('Urteile im Überblick', expanded=False, icon=':material/summarize:'):
        for r in visible:
            with st.container(border=True):
                mark = ' · **NEU**' if r.id in fresh_ids else ''
                st.markdown(f'**{r.ampel} {r.name}** · #{r.id}{mark}')
                st.write(r.urteil or 'Noch kein Urteil vorhanden.')
