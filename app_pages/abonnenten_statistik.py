# -*- coding: utf-8 -*-
"""Seite „Abonnentenstatistik“ — wohin laufen die meisten Nutzer? (doc/24).

Nutzer-Wunsch 20.10.2026: zentrale Übersicht der Abonnentenzahlen ALLER
Quellen-Clients mit Zuwächsen (seit letzter Messung / 7 Tage / 30 Tage),
je Quelle ein Tab plus „Alle“. Vorbild ist das Abonnentenstatistik-Fenster
des MqlDownloader, inklusive der Sparkline-Minigrafik „Verlauf 30 T“;
Die aktuelle Oberfläche zeigt Messwerte und Datenlücken; weitere Beschaffung
beginnt ausschließlich nach einer ausdrücklichen Schaltflächenaktion.

Die Statistik beobachtet und misst. Stufe 1 beschafft Daten und Trades und
berechnet Zufluss, Profitabilität, Floating-Equity-DD und RetDD.
Refresh-Modell
(Nutzer-Entscheidung 20.10.2026): Stufe A „nur neu lesen“ (Kataloge +
Historien der Clients spiegeln) und Stufe B „frisch messen ohne
Tradelisten“ (Clients laden NUR Katalog/Abonnenten neu; POST /update
tradelisten=false, katalogMaxAlterH=0 erzwingt die Neumessung trotz
3-Tage-Regel). Der Abonnentenrefresh lädt keine Tradelisten.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from mqlkiscanner import abonnenten_statistik, client_updates, db, quellen, scan_worker
from mqlkiscanner import downloader_client, katalog, pipeline
from mqlkiscanner import abonnenten_analyse_ui
from mqlkiscanner.ui_design import apply_theme, page_header

apply_theme()
page_header('ABONNENTENSTATISTIK', 'Wohin laufen die Nutzer?',
            'Aktuelle Abonnentenzahlen aller Client-Quellen mit Zuwachs '
            'seit letzter Messung, über 7 Tage und über 30 Tage — sortiert '
            'nach dem größten 30-Tage-Zuwachs. Stufe 1 sammelt Daten und '
            'Trades für die gemeinsame Tabelle aus Zufluss, Nettogewinn, '
            'Rendite, Floating-Equity-DD und RetDD. Ein getrennt gekennzeichnetes '
            'Startkapital-Modell lässt sich aus vorhandenen Daten berechnen; '
            'echte Messungen und Modellwerte bleiben unterscheidbar. '
            'Fehlende Werte und offene Datenpunkte bleiben sichtbar.')
with st.container(horizontal=True, vertical_alignment='center'):
    st.caption('Datenbasis: gespeicherte Abonnenten-Historien. Neue Messpunkte '
               'stammen aus den Client-Historien; bloßes Neulesen bestätigt '
               'keine neue Messung. '
               'Mindestens ein Abonnent ist Anzeige-Standard.')

# ── Refresh: Dialog (Stufe A lesen / Stufe B frisch messen) ───────────────



@st.dialog('🔄 Abonnentenzahlen aktualisieren', width='large')
def _refresh_dialog():
    aktiv = db.list_quellen(nur_aktiv=True)
    if not aktiv:
        st.warning('Keine aktive Datenquelle konfiguriert (Einstellungen → '
                   'Datenquellen).', icon=':material/warning:')
        return
    st.markdown('**Wie soll aktualisiert werden?**')
    modus = st.radio(
        'Modus', ['Nur neu lesen (schnell)',
                  'Frisch messen — ohne Tradelisten'],
        label_visibility='collapsed',
        help='Lesen spiegelt Katalog + Abonnenten-Historien der Clients in '
             'den Scanner (Sekunden bis wenige Minuten; Zahlen so frisch wie '
             'der letzte Client-Lauf). Frisch messen stößt die Clients an, '
             'NUR ihre Abonnentenzahlen neu zu laden — keine Tradelisten; '
             'je Quelle höchstens 200 Anbieter mit mindestens einem Abonnenten, '
             'absteigend nach Abonnenten; ohne Einzelprofile oder Statistiken.')
    messen = modus == 'Frisch messen — ohne Tradelisten'
    kuerzels: list[str] = []
    if messen:
        if scan_worker.active_run() is not None:
            st.info('Es läuft gerade ein Workflow-Scan — dessen Stufe 0 '
                    'aktualisiert die Clients bereits. Frisch messen ist '
                    'gesperrt, bis der Scan beendet ist; nur neu lesen geht.',
                    icon=':material/hourglass_top:')
            messen = False
        else:
            st.markdown('**Bei welchen Clients frisch messen?** '
                        '(danach wird überall neu gelesen)')
            col_check, col_info = st.columns([1.1, 1.6])
            with col_check:
                for q in aktiv:
                    kuerzel = db.kanonische_quelle(q['kuerzel'])
                    # Nutzer-Entscheidung 20.10.: Monitore an, MQL5 aus —
                    # der MqlDownloader-Crawl dauert und braucht den Login.
                    if st.checkbox(f'{quellen.anzeige_name(q)} ({kuerzel})',
                                   value=kuerzel != 'mql5',
                                   key=f'abonnenten_refresh_b_{kuerzel}'):
                        kuerzels.append(str(q['kuerzel']))
            with col_info:
                st.caption('Umfang je gewählter Quelle:')
                for q in aktiv:
                    kuerzel = db.kanonische_quelle(q['kuerzel'])
                    st.caption(f"• {quellen.anzeige_name(q)}: "
                               'bis zu 200 Anbieter, meiste Abonnenten zuerst')
                st.caption('MQL4 und MQL5 teilen sich die 200 Plätze. Die gewählten Clients laufen parallel — die '
                           'Gesamtdauer ist die des langsamsten. Ein Login '
                           'kann zwischendurch nötig sein; der Status zeigt '
                           'das an.')
    if st.button('Aktualisieren', type='primary', icon=':material/refresh:',
                 disabled=messen and not kuerzels):
        if abonnenten_statistik.starte_refresh(messen=messen,
                                               kuerzels=kuerzels or None):
            st.session_state['_abonnenten_refresh_uebernommen'] = False
            st.rerun()
        else:
            st.warning('Es läuft bereits ein Abonnenten-Refresh — siehe '
                       'Status unten.', icon=':material/hourglass_top:')


_STATUS_ZEICHEN = {'gruen': '🟢', 'blau': '🔵', 'gelb': '🟡',
                   'rot': '🔴', 'grau': '⚪'}


@st.fragment(run_every=2.0)
def _refresh_fortschritt() -> None:
    zustand = abonnenten_statistik.refresh_zustand()
    if not zustand.get('laeuft') and not zustand.get('fertig'):
        return
    beleg = abonnenten_statistik.refresh_anzeige(zustand)
    if zustand.get('laeuft'):
        st.caption(f"Aktiver Abonnenten-Refresh · Lauf {beleg['kennung']} · "
                   f"gestartet {beleg['gestartet']}")
        if zustand.get('phase') == 'clients':
            st.info('Frisch messen (ohne Tradelisten) läuft — Status je '
                    'Client:', icon=':material/sync:')
            for kuerzel, z in sorted((zustand.get('quellen') or {}).items()):
                zeichen = _STATUS_ZEICHEN.get(
                    client_updates.STATUS_FARBE.get(z.get('status'), 'grau'), '⚪')
                text = z.get('detail') or z.get('phase') or z.get('status') or ''
                fortschritt = (f" · {z.get('done') or 0}/{z.get('total') or 0}"
                               if z.get('total') else '')
                st.caption(f"{zeichen} **{kuerzel}**: {text}{fortschritt}")
                if z.get('job_id'):
                    st.caption(f"Client-Job {z['job_id']} · Stand {z.get('geaendert') or 'unbekannt'}")
        else:
            st.info('Abonnentenzahlen neu einlesen …', icon=':material/sync:')
        log = list(zustand.get('logs') or [])
        if log:
            with st.expander('Verlauf', expanded=False):
                st.code('\n'.join(log[-25:]))
        if st.button('Abbrechen', key='abonnenten_refresh_stopp',
                     icon=':material/cancel:'):
            abonnenten_statistik.stoppe_refresh()
        return
    if st.session_state.get('_abonnenten_refresh_uebernommen_lauf') != beleg['kennung']:
        st.session_state['_abonnenten_refresh_uebernommen_lauf'] = beleg['kennung']
        st.session_state['_abonnenten_refresh_uebernommen'] = True
        st.rerun(scope='app')
    st.caption(f"Abgeschlossener Abonnenten-Refresh · {beleg['status']} · "
               f"beendet {beleg['beendet']}")
    with st.expander(f"Ergebnis des abgeschlossenen Refreshs · {beleg['status']}",
                     expanded=beleg['frisch']):
        st.caption(f"Lauf {beleg['kennung']} · gestartet {beleg['gestartet']} · "
                   f"beendet {beleg['beendet']}. Dieser Beleg beschreibt diesen Refresh; "
                   "er ist keine Liveaussage über die Clients oder spätere Aktualisierungen.")
        summary = zustand.get('summary')
        if summary:
            teile = []
            for kuerzel, eintrag in sorted((summary.get('quellen') or {}).items()):
                errors = eintrag.get('fehler') or []
                fehler = eintrag.get('abgebrochen') or (
                    errors if isinstance(errors, str) else '; '.join(map(str, errors)))
                teile.append(f"{kuerzel}: {eintrag.get('anzahl') or 0} Signale"
                             + (f" — FEHLER IN DIESEM LAUF: {fehler}" if fehler else ''))
            if any(e.get('fehler') or e.get('abgebrochen')
                   for e in (summary.get('quellen') or {}).values()):
                st.warning('Der abgeschlossene Refresh meldete Fehler: '
                           + ' · '.join(teile), icon=':material/warning:')
            else:
                st.success('Der abgeschlossene Refresh war erfolgreich: ' + ' · '.join(teile),
                           icon=':material/task_alt:')
        elif zustand.get('fehler'):
            st.error(f'Fehler im abgeschlossenen Refresh — {zustand["fehler"]}',
                     icon=':material/error:')
        elif zustand.get('stopp'):
            st.info('Dieser Refresh wurde abgebrochen. Es wird kein erfolgreicher Abschluss behauptet.')
        for kuerzel, client in sorted((zustand.get('quellen') or {}).items()):
            st.caption(f"Client-Beleg {kuerzel} · Job {client.get('job_id') or 'nicht überliefert'} · "
                       f"damaliger Status {client.get('status') or 'unbekannt'} · "
                       f"Stand {client.get('geaendert') or 'unbekannt'}")
        if zustand.get('logs'):
            st.code('\n'.join(map(str, zustand['logs'][-25:])))


with st.container(horizontal=True, vertical_alignment='center'):
    if st.button('Abonnentenzahlen aktualisieren', key='abonnenten_refresh',
                 icon=':material/refresh:',
                 disabled=abonnenten_statistik.refresh_laeuft(),
                 help='Stufe A „nur neu lesen“ (schnell) oder Stufe B '
                      '„frisch messen ohne Tradelisten“ — die Clients laden '
                      'dann NUR Katalog/Abonnenten neu. Tradelisten lädt '
                       'dieser Zählerrefresh nicht.'):
        _refresh_dialog()
    abonnenten_analyse_ui.render_daten_start_button()
    stand = db.katalog_sync_status()
    if stand:
        st.caption('Katalog-Stand: '
                   + ' · '.join(f"{k} {w.get('anzahl') or 0}"
                                for k, w in sorted(stand.items()))
                   + " — zuletzt gespiegelt "
                     f"{max((w.get('gelaufen_am') or '')[:16] for w in stand.values())}")

_refresh_fortschritt()
abonnenten_analyse_ui.render_daten_results()

# ── Daten ─────────────────────────────────────────────────────────────────
st.subheader('Gespeicherte Abonnentenverläufe')
zeilen = abonnenten_statistik.zeilen(dokumente={}, berichte_zaehler={}, ampeln={})
_abonnenten_stufen = abonnenten_statistik.mit_zuwachs_ampel(zeilen)
_beobachtet_refs = db.list_beobachtungen()
for _z in zeilen:
    _z['beobachtet'] = _z['signal_ref'] in _beobachtet_refs
if not zeilen:
    st.info('Noch keine Abonnenten-Daten — oben „Abonnentenzahlen '
            'aktualisieren“ klicken (dazu muss mindestens ein Client '
            'laufen).', icon=':material/info:')
    st.stop()

with st.container(horizontal=True):
    suche = st.text_input('🔍 Suchen — Name oder Signal-ID',
                          key='abonnenten_suche',
                          placeholder='z. B. tradefx oder 2380965')
    min_abo = st.number_input('Min. Abonnenten', min_value=0, value=1, step=1,
                              key='abonnenten_min_abo',
                              help='Nutzer-Vorgabe: mindestens 1 Abonnent. '
                                   'Der Sync spiegelt trotzdem den Vollkatalog '
                                   '(auch 0) — hier wird nur angezeigt. Der '
                                   'Tab „Beobachten“ ignoriert diesen Filter '
                                   'bewusst: beobachtete Signale bleiben auch '
                                   'bei 0 Abonnenten sichtbar.')

suche_cf = (suche or '').strip().casefold()
def _trifft_suche(z: dict) -> bool:
    return not suche_cf or suche_cf in f"{z['name']} {z['signal_id']}".casefold()

sichtbar = [z for z in zeilen
            if (z['abonnenten'] or 0) >= min_abo and _trifft_suche(z)]
# Beobachtungsliste (Nutzer-Wunsch 20.10.): bewusst OHNE Min.-Abonnenten-
# Filter — ein beobachtetes Signal bleibt sichtbar, selbst wenn es auf 0 fällt.
beobachtungs_zeilen = [z for z in zeilen
                       if z['signal_ref'] in _beobachtet_refs and _trifft_suche(z)]

# ── Tabs: Beobachten + Alle + je Quelle ────────────────────────────────────
st.caption('EIN Haken am Zeilenanfang → Detailansicht (Verlaufs-Chart, '
           'Messpunkte, Beobachten-Button) · MEHRERE Haken → Sammelschalter '
           '„auf Beobachtungsliste setzen/entfernen“ unter der Tabelle · '
           f'👁 = auf der Beobachtungsliste ({len(beobachtungs_zeilen)} von '
           f'{len(_beobachtet_refs)} beobachteten Signalen sichtbar).')
quellen_reihenfolge = [db.kanonische_quelle(q['kuerzel'])
                       for q in db.list_quellen(nur_aktiv=True)]
vorhandene_quellen = [k for k in quellen_reihenfolge
                      if any(z['quelle'] == k for z in zeilen)]
for z in zeilen:  # Quellen ohne aktive Registry-Zeile trotzdem zeigen
    if z['quelle'] not in vorhandene_quellen:
        vorhandene_quellen.append(z['quelle'])


def _tab_schluessel(kuerzel: str | None) -> str:
    return 'alle' if not kuerzel else kuerzel.replace(' ', '_')


tabs = st.tabs(['Beobachten', 'Alle']
               + [f'{quellen.anzeige_name({"kuerzel": k})} ({k})'
                  for k in vorhandene_quellen])
# Tab-Schlüssel → Zeilen (EINE Definition für Rendern UND Detail-Auflösung)
tab_definitionen = [
    ('beobachten', beobachtungs_zeilen, True),
    ('alle', sichtbar, True),
] + [(_tab_schluessel(k), [z for z in sichtbar if z['quelle'] == k], False)
     for k in vorhandene_quellen]

@st.cache_data(persist='disk', show_spinner=False, max_entries=50_000)
def _sparkline_data_url(werte: tuple, trend: int) -> str | None:
    """Sparkline als eingebettete PNG-Daten-URL (ImageColumn).

    Gecacht auf Platte — die Kurven ändern sich nur mit neuen Messpunkten
    (2×/Woche-Rhythmus), Reruns sind damit gratis. Gemessen 20.10.:
    3.139 Kurven in 0,4 s, ≈0,6 MB Payload für die Gesamt-Tabelle.
    """
    roh = abonnenten_statistik.sparkline_png(werte, trend=trend)
    if roh is None:
        return None
    return 'data:image/png;base64,' + base64.b64encode(roh).decode('ascii')


def _sparkline_url(zeile: dict) -> str | None:
    verlauf = zeile.get('verlauf30') or []
    if len(verlauf) < 2:
        return None
    trend = verlauf[-1][1] - verlauf[0][1]
    return _sparkline_data_url(tuple(w for _, w in verlauf), trend)


_AMPEL_EMOJI = {'gruen': '🟢', 'gelb': '🟡', 'orange': '🟠', 'rot': '🔴'}
_AMPEL_BG = {'gruen': 'rgba(46,125,50,0.22)', 'gelb': 'rgba(214,168,0,0.20)',
             'orange': 'rgba(224,110,20,0.22)', 'rot': 'rgba(198,40,40,0.22)'}
_AMPEL_FG = {'gruen': '#4caf50', 'gelb': '#e0b400', 'orange': '#fb923c',
             'rot': '#ef5350'}


def _tabellen_daten(tab_zeilen: list[dict], mit_quelle: bool) -> pd.DataFrame:
    """Sortierter DataFrame eines Tabs — EINE Sortierung für Tabelle UND
    Detail (die Zeilenauswahl der Tabelle indiziert hier herein)."""
    daten = [{
        'Beob.': '👁' if z.get('beobachtet') else '',
        'Signal': z['name'], 'ID': z['signal_id'],
        **({'Quelle': z['quelle']} if mit_quelle else {}),
        'Plattform': z['version'],
        'Abonnenten': z['abonnenten'],
        'Δ seit Messung': z['delta_letzt'],
        'Δ 7 Tage': z['delta_7'],
        'Ampel (Zuwachs)': _AMPEL_EMOJI.get(z.get('zuwachs_ampel'), ''),
        'Δ 7 Tage %': z['delta_7_pct'],
        'Δ 30 Tage': z['delta_30'],
        'Verlauf 30 T': _sparkline_url(z),
        'Letzte Messung': (z['stand'].strftime('%d.%m. %H:%M')
                           if z['stand'] else None),
        'URL': quellen.oeffnen_url(z['quelle'], z['signal_id'], z['url']),
        '_ref': z['signal_ref'],
        '_ampel': z.get('zuwachs_ampel') or '',
    } for z in tab_zeilen]
    df = pd.DataFrame(daten)
    if df.empty:
        return df
    # Bewusst FLOAT statt Int64: Streamlit rendert pd.NA (nullable Int64)
    # in Zellen als Text „None" (Nutzer-Screenshot 20.10.), float-NaN dagegen
    # als leere Zelle (na_rep des Stylers greift).
    for spalte in ('ID', 'Abonnenten', 'Δ seit Messung', 'Δ 7 Tage',
                   'Δ 7 Tage %', 'Δ 30 Tage'):
        df[spalte] = pd.to_numeric(df[spalte], errors='coerce')
    return df.sort_values(['Δ 30 Tage', 'Δ 7 Tage', 'Abonnenten'],
                          ascending=False, na_position='last').reset_index(drop=True)


def _delta_stil(wert) -> str:
    if pd.isna(wert):
        return ''
    if wert > 0:
        return 'color: #4caf50; font-weight: 600'
    if wert < 0:
        return 'color: #ef5350; font-weight: 600'
    return 'color: gray'


_DELTA_SPALTEN = ['Δ seit Messung', 'Δ 7 Tage', 'Δ 30 Tage']


def _tabelle_rendern(tab_zeilen: list[dict], schluessel: str,
                     mit_quelle: bool) -> None:
    if not tab_zeilen:
        st.caption('Keine Signale in diesem Tab (Filter/Quelle).')
        return
    with_zuwachs = sum(1 for z in tab_zeilen if (z['delta_7'] or 0) > 0)
    groesster = max(tab_zeilen, key=lambda z: (z['delta_30'] is not None,
                                               z['delta_30'] or 0,
                                               z['abonnenten'] or 0))
    neueste = max((z['stand'] for z in tab_zeilen if z['stand']), default=None)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric('Signale', f"{len(tab_zeilen):,}".replace(',', '.'))
    k2.metric('Mit Zuwachs (7 T)', with_zuwachs)
    k3.metric('Größter Zuwachs (30 T)',
              (f"{groesster['delta_30']:+d}"
               if groesster['delta_30'] is not None else '–'),
              help=(f"{groesster['name']} · aktuell "
                    f"{groesster['abonnenten'] if groesster['abonnenten'] is not None else '?'} "
                    f"Abonnenten" if groesster['delta_30'] is not None else None))
    k4.metric('Neueste Messung',
              neueste.strftime('%d.%m. %H:%M') if neueste else '–')
    # Farblegende (Nutzer-Feedback 20.10.): Die Zuwachs-STUFE ist je Broker
    # gegen dessen gestutzten Durchschnitt gerechnet — +246 ist bei Pelican
    # normal, bei MQL5 (Ø ~40 Abonnenten) unmöglich. Absolute Δ-Spalten
    # behalten die einfache Vorzeichen-Farbe; „Δ 7 Tage %“ und die Ampel-
    # Spalte tragen die Broker-relative Stufe.
    stufen = abonnenten_statistik.zuwachs_stufen(tab_zeilen)
    if stufen:
        schnitte = ' · '.join(
            f"{q} Ø {s['durchschnitt_pct']:+.1f} %".replace('.', ',')
            + f" (n={s['anzahl']})"
            for q, s in sorted(stufen.items()))
        st.caption('**Zuwachs-Stufe je Broker** (Ø = gestutzter Durchschnitt '
                   'von Δ 7 Tage %, oberste 5 % nicht gezählt, nur Signale '
                   'mit ≥ 1 Abonnent): ' + schnitte)
    st.caption('🟢 über dem Broker-Ø (wachsend) · 🟡 wachsend, unter dem Ø · '
               ':orange[🟠 Verlust] · :red[🔴 starker Verlust > 10 % des '
               'Bestands] · leer = unverändert/kein Vergleichspunkt. '
               'Absolute Δ-Zahlen: :green[grün] = Zuwachs, :red[rot] = '
               'Verlust. Zuwachs allein belegt keine geringe Verlustgefahr; '
               'die gemessenen Risikokennzahlen stehen in der Datentabelle oben.')
    df = _tabellen_daten(tab_zeilen, mit_quelle)

    def _delta_zeilen_stil(zeile):
        return [_delta_stil(wert) for wert in zeile]

    def _ampel_stil(zeile):
        """Tönung der Δ-7-Tage-%-Zelle nach Broker-Stufe (Marker-Spalte
        _ampel steuert mit; pandas-apply mit subset liefert beide)."""
        stufe = zeile.iloc[1]
        if stufe not in _AMPEL_BG or pd.isna(zeile.iloc[0]):
            return ['', '']
        stil = (f'background-color: {_AMPEL_BG[stufe]}; '
                f'color: {_AMPEL_FG[stufe]}; font-weight: 600')
        return [stil, '']

    gestylt = (df.style.format(na_rep='', formatter={
        'Δ seit Messung': lambda w: '' if pd.isna(w) else f'{w:+.0f}',
        'Δ 7 Tage': lambda w: '' if pd.isna(w) else f'{w:+.0f}',
        'Δ 7 Tage %': lambda w: '' if pd.isna(w)
        else f'{w:+.1f} %'.replace('.', ','),
        'Δ 30 Tage': lambda w: '' if pd.isna(w) else f'{w:+.0f}',
    }).apply(_delta_zeilen_stil, axis=1, subset=_DELTA_SPALTEN)
              .apply(_ampel_stil, axis=1, subset=['Δ 7 Tage %', '_ampel']))
    konfig = {
        'Beob.': st.column_config.TextColumn(
            'Beob.', width=52,
            help='👁 = Signal steht auf deiner Beobachtungsliste (Tab '
                 '„Beobachten“). Setzen/entfernen: Zeile anklicken → Button '
                 'unter der Tabelle. Beobachtete Signale bleiben im '
                 'Beobachten-Tab auch bei 0 Abonnenten sichtbar.'),
        'Signal': st.column_config.TextColumn('Signal', width=150),
        'ID': st.column_config.NumberColumn('ID', width=76, format='%.0f'),
        'Plattform': st.column_config.TextColumn('Plattform', width=76),
        'Abonnenten': st.column_config.NumberColumn(
            'Abos', width=64, format='%.0f',
            help='Abonnenten — aktueller Stand aus der neuesten Messung'),
        'Δ seit Messung': st.column_config.NumberColumn(
            'Δ\nMessung', width=72,
            help='Differenz zur vorherigen Messung — :green[grün] = Zuwachs, '
                 ':red[rot] = Verlust, grau = unverändert. „–“ = erst eine '
                 'Messung vorhanden (keine falsche 0).'),
        'Δ 7 Tage': st.column_config.NumberColumn(
            'Δ\n7 Tage', width=66,
            help='Abonnenten-Differenz zum Messpunkt vor ~7 Tagen (±3 Tage '
                 'Toleranz) — :green[grün] = Zuwachs, :red[rot] = Verlust. '
                 '„–“ = noch kein belastbarer Vergleichspunkt.'),
        'Ampel (Zuwachs)': st.column_config.TextColumn(
            'Zuwachs', width=62,
            help='Broker-relative Stufe von Δ 7 Tage %: 🟢 über dem Ø der '
                 'eigenen Quelle (gestutzter Durchschnitt, oberste 5 % '
                 'nicht gezählt) · 🟡 wachsend, unter dem Ø · 🟠 Verlust · '
                 '🔴 starker Verlust (> 10 % des Bestands in 7 Tagen) · '
                 'leer = unverändert oder kein Vergleichspunkt. So zeigt '
                 'je Broker-Tab sofort, wo Dessen stärkste Signale stehen — '
                 '+246 ist bei Pelican normal, bei MQL5 unmöglich.'),
        'Δ 7 Tage %': st.column_config.NumberColumn(
            'Δ\n7 T %', width=70,
            help='Relative Änderung: Δ 7 Tage im Verhältnis zum Abonnenten-'
                 'STAND des Vergleichspunkts (z. B. +246 bei 1.400 Abonnenten '
                 '= +17,5 %). Erst damit sind große und kleine Signale '
                 'vergleichbar — +5 bei 5 Abonnenten ist +100 %. „–“ = '
                 'Vergleichspunkt fehlt oder Stand war 0 (aus 0 wachsen ist '
                 'prozentual undefiniert — dann sagt die absolute Zahl mehr). '
                 'Die Zellenfarbe ist die Broker-relative Stufe.'),
        'Δ 30 Tage': st.column_config.NumberColumn(
            'Δ\n30 Tage', width=66,
            help='Abonnenten-Differenz zum Messpunkt vor ~30 Tagen (±3 Tage '
                 'Toleranz) — :green[grün] = Zuwachs, :red[rot] = Verlust. '
                 '„–“ = noch kein 27–33 Tage alter Messpunkt vorhanden. '
                 'Die Spalte füllt sich je Quelle, sobald das Vergleichsfenster '
                 'die ersten Messpunkte erreicht: Robo ab 23.10., Pelican/Vantage '
                 'ab 24.10., MQL5 ab 25.10., Zulu ab 31.10.2026 — je regelmäßiger '
                 'gemessen wird, desto voller wird sie.'),
        'Verlauf 30 T': st.column_config.ImageColumn(
            'Verlauf\n30 T', width=112,
            help='Minigrafik der Abonnentenentwicklung über die letzten '
                 '30 Tage (relativ zur neuesten Messung) — :green[grüne] '
                 'Kurve = netto Zuwachs, :red[rote] = netto Verlust, grau = '
                 'unverändert. Leer = weniger als 2 Messpunkte im Fenster. '
                 'Die große Kurve gibt es per Zeilenauswahl unten.'),
        'Letzte Messung': st.column_config.TextColumn(
            'Messung', width=92,
            help='Zeitpunkt des neuesten gespeicherten Messpunkts. Neue '
                 'Punkte übernehmen den Messzeitpunkt des Clients. Frühere '
                 'Scanner-Sync-Punkte bleiben historisch erhalten und '
                 'werden durch Neulesen nicht erneut bestätigt.'),
        'URL': st.column_config.LinkColumn('Anbieter', width=74,
                                           display_text='öffnen ↗'),
        # Hilfsspalten verstecken (None = Spalte ausblenden): _ref für die
        # Detail-Zuordnung, _ampel als Stil-Marker für die %-Zelle.
        '_ref': None, '_ampel': None,
    }
    if mit_quelle:
        konfig['Quelle'] = st.column_config.TextColumn('Quelle', width=80)
    st.dataframe(gestylt, key=f'abonnenten_tabelle_{schluessel}',
                 on_select='rerun', selection_mode='multi-row',
                 hide_index=True,
                 height=min(640, 40 + 33 * len(df)), width='stretch',
                 column_config=konfig)
    st.download_button(
        'Tabelle als CSV',
        df.drop(columns=['_ref', '_ampel', 'Verlauf 30 T']).to_csv(
            sep=';', index=False, encoding='utf-8-sig').encode('utf-8-sig'),
        file_name=f'abonnentenstatistik-{schluessel}.csv', mime='text/csv',
        key=f'abonnenten_csv_{schluessel}', icon=':material/download:')


for _tab_nr, (_tab_key, _tab_zeilen, _tab_mit_quelle) in enumerate(tab_definitionen):
    with tabs[_tab_nr]:
        if _tab_key == 'beobachten' and not _tab_zeilen:
            st.caption('Noch nichts beobachtet — Zeile in einem Tab anklicken '
                       '(Kreis am Zeilenanfang) und dort „👁 Beobachten“ '
                       'klicken. Beobachtete Signale bleiben hier sichtbar, '
                       'auch wenn sie auf 0 Abonnenten fallen.')
        else:
            _tabelle_rendern(_tab_zeilen, _tab_key, mit_quelle=_tab_mit_quelle)

# ── Auswahl: EINE Zeile → Detail · MEHRERE → Sammel-Beobachten ─────────────
def _ausgewaehlte_zeile():
    """Zeilenauswahl über alle Tabs lesen (DataframeState ODER dict).

    Mehrfachauswahl (Häkchen am Zeilenanfang): liefert ALLE gewählten
    Zeilen des ersten Tabs mit einer Auswahl."""
    for schluessel in [key for key, _, _ in tab_definitionen]:
        zustand = st.session_state.get(f'abonnenten_tabelle_{schluessel}')
        if not zustand:
            continue
        selection = getattr(zustand, 'selection', None)
        if selection is None and isinstance(zustand, dict):
            selection = zustand.get('selection')
        reihen = [int(r) for r in ((selection or {}).get('rows') or [])]
        if reihen:
            return schluessel, reihen
    return None


_gewaehlt = _ausgewaehlte_zeile()
if _gewaehlt is not None:
    schluessel, reihe_nrs = _gewaehlt
    tab_eintrag = next((e for e in tab_definitionen if e[0] == schluessel), None)
    df_detail = (_tabellen_daten(tab_eintrag[1], mit_quelle=True)
                 if tab_eintrag else pd.DataFrame())
    gueltige_nrs = [nr for nr in reihe_nrs if nr < len(df_detail)]
    if len(gueltige_nrs) > 1:
        # Sammelleiste (Nutzer-Wunsch 20.10.): mehrere Häkchen → alle auf
        # einmal beobachten/entfernen. Gemischte Auswahl wird sauber
        # getrennt: der Setzen-Button erfasst nur die noch nicht beobachteten,
        # der Entfernen-Button nur die beobachteten Signale.
        refs = [int(df_detail.iloc[nr]['_ref']) for nr in gueltige_nrs]
        neue = [r for r in refs if r not in _beobachtet_refs]
        alte = [r for r in refs if r in _beobachtet_refs]
        st.divider()
        st.caption(f'**{len(gueltige_nrs)} Signale ausgewählt** — für die '
                   'Detailansicht/Verlauf nur EIN Häkchen setzen.')
        col_add, col_del = st.columns(2)
        if neue and col_add.button(
                f'👁 {len(neue)} auf Beobachtungsliste setzen',
                key='abonnenten_beob_bulk_add', type='primary',
                icon=':material/visibility:'):
            for ref in neue:
                db.setze_beobachtung(None, True, signal_ref=ref)
            st.rerun()
        if alte and col_del.button(
                f'👁 {len(alte)} Beobachtung entfernen',
                key='abonnenten_beob_bulk_del',
                icon=':material/visibility_off:'):
            for ref in alte:
                db.setze_beobachtung(None, False, signal_ref=ref)
            st.rerun()
    elif gueltige_nrs:
        reihe_nr = gueltige_nrs[0]
        zeile = df_detail.iloc[reihe_nr]
        signal_ref = int(zeile['_ref'])
        st.divider()
        left, right = st.columns([1.6, 1])
        with left:
            st.subheader(f"{zeile['Signal']} · #{int(zeile['ID'])}")
            abo = (int(zeile['Abonnenten'])
                   if pd.notna(zeile['Abonnenten']) else '—')
            st.caption(f"Quelle {zeile['Quelle']} · Plattform "
                       f"{zeile['Plattform']} · {abo} Abonnenten")
        with right:
            # Beobachten-Schalter (Nutzer-Wunsch 20.10.): Widget-Key enthält
            # den Zustand — nach dem Umschalten entsteht ein frisches Widget
            # mit richtigem Label, kein veralteter Klick (AppTest-Falle 15).
            ist_beobachtet = signal_ref in _beobachtet_refs
            if st.button('👁 Beobachtung entfernen' if ist_beobachtet
                         else '👁 Beobachten',
                         key=f'abonnenten_beob_{signal_ref}_{int(ist_beobachtet)}',
                         type='secondary' if ist_beobachtet else 'primary',
                         icon=':material/visibility:'
                         if not ist_beobachtet else ':material/visibility_off:',
                         help='Auf die Beobachtungsliste setzen — das Signal '
                              'erscheint dann im Tab „Beobachten“ und bleibt '
                              'dort auch bei 0 Abonnenten sichtbar.'):
                db.setze_beobachtung(None, not ist_beobachtet,
                                     signal_ref=signal_ref)
                st.rerun()
            # Bewusst kein st.page_link: In Einzelseiten-AppTests ist die
            # Seiten-Registry leer (StreamlitPageNotFoundError, Memory
            # „apptest-fallen“ Nr. 1) — Textverweis reicht.
            st.caption('Vertiefen: **Alle Signale** öffnen und die ID '
                       f'**{int(zeile["ID"])}** in die Suche eingeben '
                       '(Statistik, Trades, Equity-Studie).')
        punkte = [p for p in db.get_history(None, version=str(zeile['Plattform']),
                                            signal_ref=signal_ref)
                  if p.get('subscribers') is not None]
        punkte.sort(key=lambda p: str(p['ts']))
        if punkte:
            xs = [str(p['ts'])[:16].replace('T', ' ') for p in punkte]
            ys = [int(p['subscribers']) for p in punkte]
            fig = go.Figure(go.Scatter(
                x=xs, y=ys, mode='lines+markers',
                line={'shape': 'hv', 'color': '#8a6d1f'},
                hovertemplate='%{x}<br>%{y} Abonnenten<extra></extra>'))
            fig.update_layout(margin={'l': 10, 'r': 10, 't': 36, 'b': 10},
                              height=300, yaxis={'title': 'Abonnenten'},
                              xaxis={'title': 'Messung'}, showlegend=False)
            st.plotly_chart(fig, width='stretch',
                            key=f'abonnenten_verlauf_{signal_ref}')
            detail_df = pd.DataFrame([{
                'Messung': str(p['ts'])[:16].replace('T', ' '),
                'Abonnenten': int(p['subscribers']),
                'Δ': (int(p['change']) if p.get('change') is not None else None),
                'Version': p['version'],
            } for p in reversed(punkte)])
            with st.expander(f'Messpunkte ({len(punkte)}) — neueste zuerst',
                             expanded=False):
                st.dataframe(detail_df, hide_index=True, height=260,
                             key=f'abonnenten_punkte_{signal_ref}')
        if not punkte:
            st.caption('Keine Messpunkte gespeichert — Zahlen stammen allein '
                       'aus dem Katalog („Aktualisieren“ holt die Historie).')
        # ── Trades als CSV (Nutzer-Wunsch 20.10.) ─────────────────────────
        # Dieselbe SHA-geprüfte On-demand-Kette wie „Alle Signale“: Klick
        # lädt den Trade-Export der Quelle (Cache), danach Download-Button.
        _trades_key = f'abonnenten_trades_pfad_{signal_ref}'
        _trades_pfad = st.session_state.get(_trades_key)
        with st.expander('⬇ Trades als CSV', expanded=bool(_trades_pfad)):
            if _trades_pfad and Path(_trades_pfad).exists():
                st.download_button(
                    f"⬇ trades-{zeile['Quelle']}-{int(zeile['ID'])}.csv",
                    data=Path(_trades_pfad).read_bytes(),
                    file_name=f"trades-{zeile['Quelle']}-{int(zeile['ID'])}.csv",
                    mime='text/csv',
                    key=f'abonnenten_trades_dl_{signal_ref}')
                st.caption(f"Datei im Cache: {Path(_trades_pfad).name}")
            else:
                st.caption('Lädt den Trade-Export dieser Quelle für das '
                           'Signal (SHA-geprüfter Cache — der zweite Klick '
                           'ist gratis). Es werden KEINE Bewertungen '
                           'angestoßen, nur der Download.')
                if st.button('⬇ Trades von der Quelle laden',
                             key=f'abonnenten_trades_laden_{signal_ref}',
                             icon=':material/cloud_download:'):
                    try:
                        _probe = pipeline.ScanResult(
                            id=int(zeile['ID']), name=str(zeile['Signal']),
                            platform='', url=str(zeile['URL']),
                            quelle=str(zeile['Quelle']), herkunft='Katalog')
                        _pfad, _ = katalog.lade_signal_daten(_probe)
                        st.session_state[_trades_key] = _pfad
                        st.rerun()
                    except (downloader_client.DownloaderError,
                            ValueError) as _exc:
                        st.warning(f'Trades nicht ladbar — {_exc}',
                                   icon=':material/warning:')
