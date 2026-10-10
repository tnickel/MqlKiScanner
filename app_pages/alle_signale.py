# -*- coding: utf-8 -*-
"""Seite „Alle Signale“ — unabhängige Statistikübersicht vor dem Workflow.

Eigene Seite (Nutzer-Wunsch 05.10.2026): ALLE gemeldeten Signale aller
Quellen als Liste, mit rein gerechneten Kennzahlen aus dem Trade-Cache
(Monatsrenditen, geometrischer Ertrag, Profitfaktor, Winrate, Trading-DD
aus geschlossenen Trades, Martingale-Schnellflag) — VOR dem KI-Workflow,
ohne selbst zu bewerten. Zeile wählen → Detailansicht mit Balkengrafik,
Konto-Kurve und Button zur Equity-Studie (Max-DD aus Kursen).

Vollkatalog (Nutzer-Wunsch 08.10.2026): Gezeigt wird ALLES, was die
Clients melden — der Workflow-Vorfilter (Mindestalter/Mindestabo) bleibt
bewusst beim Scan. Dazu lädt ein Button die Vollkataloge der Datenquellen
in die eigene Katalog-Tabelle (katalog.katalog_sync); Zeilen ohne
lokalen Trade-Cache lassen sich per Klick on demand nachladen, sodass
Detailansicht und Equity-Studie (realer Drawdown) für JEDES gemeldete
Signal laufen. Filter (Suche, Quelle, Herkunft, Abonnenten, Wochen,
Trade-Cache) blättern die Liste nur lokal auf.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import pandas as pd
import streamlit as st

from mqlkiscanner import db, downloader_client, katalog, pipeline, scan_worker
from mqlkiscanner import signal_statistik, studien_batch
from mqlkiscanner import alle_signale_ui as tabellen_ui
from mqlkiscanner.alle_signale_ui import render_detail, tabellen_zeile
from mqlkiscanner.ui_design import apply_theme, info_button, page_header

apply_theme()
page_header('ALLE SIGNALE', 'Unabhängige Statistik vor dem Workflow',
            'ALLE gemeldeten Signale aller Clients — auch die, die der '
            'Workflow-Vorfilter (Mindestalter/-abo) aussortieren würde. Rein '
            'aus dem Trade-Cache gerechnet, ohne KI und ohne Bewertung; '
            'gefiltert wird hier selbst. Erst selber ein Bild machen, dann '
            'entscheidet der Workflow.')
with st.container(horizontal=True, vertical_alignment='center'):
    st.caption('Vorstufe: Kurve aus **geschlossenen** Trades (offenes Floating '
               'fehlt). Max-Drawdown inkl. Floating → Button in der Detailansicht '
               '(Equity-Studie). Ampel/Urteil bleiben beim Workflow.')
    info_button('alle_signale', key='alle_signale_info')

# ── Vollkatalog der Clients ──────────────────────────────────────────────
sync_status = db.katalog_sync_status()
if not sync_status:
    # Erster Start: einmalig ziehen (Fehler je Quelle vermerkt — kein
    # Retry-Loop bei Reruns; der Button unten holt sie jederzeit wieder).
    with st.spinner('Kataloge der Clients laden (erster Start) …'):
        katalog.sync()
    sync_status = db.katalog_sync_status()

with st.container(horizontal=True, vertical_alignment='center'):
    if st.button('Katalog von den Clients laden', key='alle_signale_sync',
                 icon=':material/sync:',
                 help='ALLE gemeldeten Signale aus den REST-Katalogen der '
                      'aktiven Datenquellen (VantageMonitor & Co.) holen und '
                      'lokal ablegen. Betrifft nur diese Übersicht — der '
                      'Workflow-Scan filtert weiterhin nach Alter/Abonnenten.'):
        with st.spinner('Kataloge der Clients laden …'):
            katalog.sync()
        st.rerun()
    fehlerhaft = {k: w['fehler'] for k, w in sync_status.items() if w.get('fehler')}
    if fehlerhaft:
        st.caption(':red[Client(s) nicht erreichbar: '
                  + ', '.join(sorted(fehlerhaft)) + ' — Katalog ggf. veraltet.]')
    else:
        st.caption('Katalog: '
                   + ' · '.join(f"{k} {w.get('anzahl') or 0}"
                                for k, w in sorted(sync_status.items()))
                   + (f" — Stand {max((w.get('gelaufen_am') or '')[:16] for w in sync_status.values())}"
                      if sync_status else ''))

gescannte = [r for r in pipeline.results_from_db()
             if getattr(r, 'source_kind', 'live') == 'live']
katalog_resultate, katalog_stats = katalog.katalog_resultate()
alle = gescannte + katalog_resultate

if not alle:
    st.info('Noch keine Signale — oben „Katalog von den Clients laden“ '
            'klicken (dazu müssen die Monitor-Clients laufen) oder einen Scan '
            'starten.', icon=':material/info:')
    st.stop()

stats_je_id = {zeile['signal_id']: (zeile.get('stats') or {})
               for zeile in db.list_catalog()}
stats_je_id.update(katalog_stats)
# Virtuelle Studien (Batch, 08.10.): die 10k-Annahme in die Vorstufen-
# Statistik koppeln — so rechnet Gewinn %/M und Trading-DD % sinnvoll statt
# verzerrt ohne Basis (klar als „Basis: virtuell" gekennzeichnet).
for _sid, _studie in db.list_equity_studien().items():
    if _studie.get('virtuell'):
        stats_je_id.setdefault(int(_sid), {}).setdefault(
            'kapitalbasis_virtual_usd', 10_000.0)

with st.container(horizontal=True):
    suche = st.text_input('🔍 Suchen — Name oder Signal-ID',
                          key='alle_signale_suche',
                          placeholder='Tippen zum Filtern: z. B. dino oder 1286742')
    quellen = sorted({r.quelle for r in alle})
    gewaehlte_quellen = st.pills('Quelle', quellen, selection_mode='multi',
                                 key='alle_signale_quelle',
                                 default=quellen if len(quellen) <= 5 else None)
    herkunft = st.radio('Herkunft', ['Alle', 'Workflow (gescannt)', 'Katalog (neu)'],
                        horizontal=True, key='alle_signale_herkunft',
                        help='Workflow = bereits gescannt (mit Ampel/Forensik) · '
                             'Katalog = nur im Client-Katalog gemeldet, noch '
                             'nicht Teil des Workflow-Scans')
    nur_trades = st.toggle('Nur mit Trade-Cache', value=False,
                           key='alle_signale_nur_trades',
                           help='Nur Signale anzeigen, deren Trade-Export '
                                'bereits gespeichert ist. Katalog-Zeilen ohne '
                                'Cache laden sie per Zeilenauswahl on demand.')
    min_abo = st.number_input('Min. Abonnenten', min_value=0, value=0, step=1,
                              key='alle_signale_min_abo')
    min_wochen = st.number_input('Min. Wochen', min_value=0.0, value=0.0,
                                 step=1.0, key='alle_signale_min_wochen')
    mark_filter = st.pills('Markierung', ['Grün', 'Gelb', 'Orange'],
                           selection_mode='multi', key='alle_signale_mark_pills',
                           help='Zeigt nur deine manuell markierten Signale '
                                '(Zeile anklicken → Markierleiste unter der '
                                'Tabelle). Nichts gewählt = alle Signale; alle '
                                'drei gewählt = alle markierten.')


@st.cache_data(persist='disk', show_spinner=False)
def _statistik_cached(trades_pfad: str, sha: str, stats_json: str) -> dict | None:
    return signal_statistik.berechne(trades_pfad, json.loads(stats_json or '{}'))


def _statistik_fuer(result) -> dict | None:
    pfad = getattr(result, 'trades_path', '') or ''
    if not pfad or not Path(pfad).exists():
        return None
    rohstats = stats_je_id.get(result.id, {})
    # SHA im Cache-Schlüssel: Quellen-Artefakte werden bei Neu-Lieferung am
    # GLEICHEN Pfad überschrieben — ohne SHA bliebe die Statistik nach einem
    # Re-Download im Disk-Cache veraltet (Scan-Snapshots sind unveränderlich,
    # Katalog-Nachladungen nicht).
    return _statistik_cached(pfad, getattr(result, 'trades_sha256', '') or '',
                             json.dumps(rohstats, sort_keys=True, default=str))


suche_cf = (suche or '').strip().casefold()
markierungen = db.list_markierungen()
kommentare = db.list_kommentare()
_mark_farben = {'Grün': 'gruen', 'Gelb': 'gelb', 'Orange': 'orange'}
gewaehlte_farben = {_mark_farben[w] for w in (mark_filter or [])}
sichtbar = []
for r in alle:
    if suche_cf and suche_cf not in f'{r.name} {r.id}'.casefold():
        continue
    if gewaehlte_quellen and r.quelle not in gewaehlte_quellen:
        continue
    if herkunft == 'Workflow (gescannt)' and getattr(r, 'herkunft', '') != 'Workflow':
        continue
    if herkunft == 'Katalog (neu)' and getattr(r, 'herkunft', '') != 'Katalog':
        continue
    if nur_trades and not (getattr(r, 'trades_path', '') or ''):
        continue
    if min_abo and (getattr(r, 'abonnenten', None) or 0) < min_abo:
        continue
    if min_wochen and (getattr(r, 'wochen', None) or 0) < min_wochen:
        continue
    if gewaehlte_farben and markierungen.get(int(r.id)) not in gewaehlte_farben:
        continue
    sichtbar.append(r)

n_katalog = sum(1 for r in sichtbar if getattr(r, 'herkunft', '') == 'Katalog')
n_markiert_sichtbar = sum(1 for r in sichtbar if int(r.id) in markierungen)
st.caption(f'{len(sichtbar)} von {len(alle)} Signalen'
           + (f' · {n_markiert_sichtbar} markiert' if n_markiert_sichtbar else '')
           + (f' · {n_katalog} nur Katalog' if n_katalog else '')
           + (f' · Quelle: {", ".join(gewaehlte_quellen)}' if gewaehlte_quellen else '')
           + f' · {sum(1 for r in sichtbar if getattr(r, "trades_path", ""))} mit Trade-Cache')

# ── Batch „Lücken füllen“ (Nutzer 08.10.2026) ────────────────────────────
# Rechnet für Signale OHNE Equity-Messung den echten Max-Drawdown aus Kursen
# (Workflow-Rechnung, ohne LLM) + Vorstufen-Kennzahlen, persistiert in
# equity_studien — danach stehen True-DD %/≈/USD und TrueRetDD in der Tabelle.

def _dauer_text(s: float | None) -> str:
    if s is None:
        return '—'
    if s < 10:
        # Schnelle Signale (Studien mit wenig Kursaufwand): Komma zeigen,
        # sonst steht da „Ø 0 s/Signal" (Nutzer-Screenshot 08.10.).
        return f'{s:.1f}'.replace('.', ',') + ' s'
    s = int(s)
    return f'{s // 60} Min {s % 60} s' if s >= 60 else f'{s} s'


@st.fragment(run_every=2.0)
def _batch_fortschritt() -> None:
    run = scan_worker.active_run()
    if not run or run.workflow.get('typ') != 'studien_batch':
        return
    c = run.control
    if c.get('fertig'):
        st.info('Studien-Batch beendet: ' + (c.get('summary') or ''),
                icon=':material/task_alt:')
        if c.get('fehler'):
            with st.expander(f'Fehler ({len(c["fehler"])})', icon=':material/warning:'):
                st.markdown('\n'.join(f'- {z}' for z in c['fehler'][:50]))
        if not c.get('uebernommen'):
            c['uebernommen'] = True
            st.rerun()          # Tabelle einmalig mit den neuen Werten neu laden
        return
    gesamt = c.get('gesamt') or 0
    aktuell = c.get('aktuell') or 0
    anteil = min(1.0, (aktuell / gesamt) if gesamt else 1.0)
    text = (f'Δ Signal {aktuell}/{gesamt} · Ø '
            f'{_dauer_text(c.get("dauer_je_s"))}/Signal · Rest ≈ '
            f'{_dauer_text(c.get("restzeit_s"))} · {c.get("aktuelles_signal") or c.get("phase", "")}')
    st.progress(anteil, text=text)
    if st.button('Abbrechen', key='alle_signale_batch_abbruch',
                 icon=':material/cancel:'):
        c['abbruch'] = True


# Fragment NUR definieren reicht nicht — ohne Aufruf rendert nichts und der
# run_every-Timer startet nicht (genau deshalb fehlte der Balken, 08.10.).
_batch_fortschritt()


if st.session_state.get('alle_signale_batch_offen'):
    studien = db.list_equity_studien()
    jobs, erledigt = studien_batch.luecken_sammeln(
        alle, studien, trades_nachladen=True)
    with st.container(border=True):
        st.markdown(
            f'**{len(jobs)} Signale** haben noch keinen echten Drawdown '
            f'(True-DD) und werden berechnet: Trade-Cache sicherstellen → '
            f'Vorstufen-Kennzahlen (ohne LLM) → Equity-Studie aus H1-Kursen. '
            f'Ohne belegbare Kapitalbasis entsteht ehrlich nur **True-DD USD** '
            f'(kein Prozentwert). **{erledigt}** Signale sind bereits belegt.')
        nur_luecken = st.checkbox(
            'Bereits berechnete Signale überspringen (nur Lücken füllen)',
            value=True, key='alle_signale_batch_nur_luecken')
        nachladen = st.checkbox(
            'Fehlende Trades von den Clients nachladen',
            value=True, key='alle_signale_batch_nachladen',
            help='Signale ohne Trade-Cache holen Trades + Kennzahlen on demand '
                 'vom jeweiligen Monitor-Client (SHA-geprüfter Cache).')
        col1, col2 = st.columns(2)
        if col1.button('Rechnen starten', type='primary',
                       key='alle_signale_batch_start',
                       icon=':material/play_arrow:'):
            run = studien_batch.starten(alle, nur_luecken=nur_luecken,
                                        trades_nachladen=nachladen)
            if run is None:
                st.error('Es läuft bereits ein Workflow-Scan oder Studien-Batch '
                         '— bitte warten, bis dieser fertig ist.',
                         icon=':material/hourglass_top:')
            else:
                st.session_state['alle_signale_batch_offen'] = False
                st.rerun()
        if col2.button('Schließen', key='alle_signale_batch_schliessen'):
            st.session_state['alle_signale_batch_offen'] = False
            st.rerun()
elif scan_worker.active_run() is None:
    if st.button('Lücken füllen — Drawdown & Kennzahlen rechnen',
                 key='alle_signale_batch',
                 icon=':material/calculate:',
                 help='Für alle Signale ohne echte Drawdown-Messung: '
                      'Vorstufen-Kennzahlen + Equity-Studie aus H1-Kursen '
                      '(ohne LLM). Fragt vorher, ob bereits Berechnete '
                      'übersprungen werden sollen.'):
        st.session_state['alle_signale_batch_offen'] = True
        st.rerun()

if not sichtbar:
    st.info('Kein Signal passt zu diesem Filter.', icon=':material/filter_alt:')
    st.stop()

with st.spinner('Statistiken aus dem Trade-Cache rechnen (einmalig — danach gecacht) …'):
    paare = [(r, _statistik_fuer(r)) for r in sichtbar]


def _prozent(titel: str, breite: int = 86, help: str | None = None):
    return st.column_config.NumberColumn(titel, width=breite, format='%.2f',
                                         help=help)
df = pd.DataFrame([tabellen_zeile(r, s, markierungen, kommentare)
                       for r, s in paare])
# Zahlen-Spalten strikt numerisch: None → NaN → LEERE Zelle statt „None“-
# Text (Nutzer 08.10.2026: kompakte, lesbare Tabelle). Runden einmalig hier —
# der Styler rendert die Werte dann ohne column_config-Formatierungs-Bridge.
for _spalte in df.columns:
    if _spalte not in tabellen_ui.TEXT_SPALTEN:
        df[_spalte] = pd.to_numeric(df[_spalte], errors='coerce')
df = df.round(2)
_gestylt = df.style.format(na_rep='')   # NaN → leere Zelle (pandas-Styler!)
# Nutzer-Markierungen: ganze Zeile dezent einfärben (grün/gelb/orange).
_MARK_BG = {'gruen': 'rgba(46,125,50,0.22)', 'gelb': 'rgba(214,168,0,0.20)',
            'orange': 'rgba(224,110,20,0.22)'}

def _mark_stil(zeile):
    farbe = next((k for k, e in tabellen_ui.MARKIERUNG_EMOJI.items()
                  if zeile.get('Mark.') == e), None)
    if not farbe:
        return [''] * len(zeile)
    return [f'background-color: {_MARK_BG[farbe]}'] * len(zeile)
_gestylt = _gestylt.apply(_mark_stil, axis=1)
for _paar in (('True-DD %', 'True-DD ≈'),
              ('TrueRetDD', 'TrueRetDD ≈')):
    # Belastbar gemessen normal, vorbehaltlich orange (Marker in der
    # ≈-Spalte; pandas-apply übergibt mit subset NUR die genannten
    # Spalten, deshalb beide und Rückgabe je Zelle) — gleiche dezente
    # Konvention wie in der Ergebnistabelle.
    if {_paar[0], _paar[1]} <= set(df.columns):
        def _vorbehalt_stil(zeile, marker=_paar[1]):
            if pd.isna(zeile[marker]):
                return ['', '']
            return ['background-color: rgba(249,115,22,0.12); color: #fb923c', '']
        _gestylt = _gestylt.apply(_vorbehalt_stil, axis=1, subset=list(_paar))
st.dataframe(
    _gestylt,
    key='alle_signale_tabelle',
    on_select='rerun',
    selection_mode='single-row',
    hide_index=True,
    height=480,
    width="stretch",
    column_config={
        # Kompakte Tabelle (Nutzer 08.10.2026): kurze Überschriften + feste
        # Pixelbreiten; die langen Erklärungen leben im Hover-Help.
        'Mark.': st.column_config.TextColumn('Mark.', width=44, help='Deine '
                                    'manuelle Markierung — setzen/entfernen: '
                                    'Zeile anklicken, dann Markierleiste '
                                    'unter der Tabelle'),
        'Komm.': st.column_config.TextColumn('Komm.', width=46, help='📋 = '
                                    'Kommentar vorhanden (warum aufgenommen / '
                                    'Fix-ID) — Zeile anklicken, dann '
                                    '„Kommentar bearbeiten" unter der Tabelle'),
        'Ampel': st.column_config.TextColumn('Ampel', width=52,
                                   help='Offizielle Engine-Ampel '
                                   '(nur Anzeige — diese Seite bewertet nicht)'),
        'Fix': st.column_config.TextColumn('Fix', width=62,
                                    help='📌 FIX = Signal-ID steht auf '
                                    'der Immer-scannen-Liste'),
        'Name': st.column_config.TextColumn('Name', width=150),
        'Link': st.column_config.LinkColumn(
            'Link', width=44, display_text='↗',
            help='Öffnet die Signalseite beim Original-Anbieter (MQL5, '
                 'Vantage & Co.) in einem neuen Browser-Tab'),
        'Quelle': st.column_config.TextColumn('Quelle', width=58),
        'Herkunft': st.column_config.TextColumn('Herkunft', width=76, help='Workflow = '
                                    'bereits gescannt · Katalog = nur im '
                                    'Client-Katalog gemeldet (Ampel/Forensik '
                                    'entstehen erst im Scan)'),
        'Plattform': st.column_config.TextColumn('Plattform', width=72),
        'ID': st.column_config.NumberColumn('ID', width=76, format='%.0f'),
        'Wochen': st.column_config.NumberColumn('Wochen', width=62, format='%.0f'),
        'Abonnenten': st.column_config.NumberColumn('Abonn.', width=62, format='%.0f'),
        # ── Drawdown-Block: die vier DD-Spalten direkt nebeneinander ───────
        'Plattform-DD %': st.column_config.NumberColumn(
            'Plattform-DD %', width=86, format='%.2f',
            help='Broker-/Client-Selbstauskunft (maxDrawDown bzw. By '
                 'Equity) — nicht zwischen Plattformen vergleichbar, kein '
                 'Beweis. Vantage rechnet Peak-zu-Tief vom Equity-'
                 'Höchststand (High Water Mark), MQL5 „By Equity“ ist '
                 'offener Verlust ÷ aktuelle Balance'),
        'Trading-DD %': _prozent(
            'Trading-DD %',
            help='Größter Rückgang der Kurve GESCHLOSSENER Trades '
                 '(virtuelle Kapitalbasis) — ohne Floating, fällt ohne '
                 'belegbare Kapitalbasis verzerrt hoch aus'),
        'True-DD %': st.column_config.NumberColumn(
            'True-DD %', width=70, format='%.1f',
            help='ECHTER Max-Drawdown: Equity inkl. schwebender Verluste '
                 '(offene Positionen), aus der Kursmessung des letzten '
                 'Scans — der Nenner von TrueRetDD/Calmar. Normal = '
                 'belastbar gemessen; ORANGE ≈ = nur roh gemessen '
                 '(Kursmessung nicht bestanden). Fehlt er ganz: Equity-DD-'
                 'Studie im Detail öffnen'),
        'True-DD ≈': st.column_config.NumberColumn(
            'True-DD ≈', width=66, format='%.1f',
            help='Technischer Marker: steht der Wert hier (orange), ist die '
                 'True-DD-Zahl vorbehaltlich — der rohe Kurs-Max-DD statt '
                 'der belastbaren Messung'),
        'True-DD USD': st.column_config.NumberColumn(
            'True-DD USD', width=86, format='%.2f',
            help='Echter Max-Drawdown in USD (Equity inkl. schwebender '
                 'Verluste, aus H1-Kursen) — basis-unabhängig und damit auch '
                 'bei Signalen OHNE belegbare Kapitalbasis (z. B. Vantage) '
                 'belegbar, wo der Prozentwert ehrlich leer bleibt. Aus dem '
                 'Batch „Lücken füllen“'),
        # ── Ertrag/Effizienz ───────────────────────────────────────────────
        'Plattform %/M': st.column_config.NumberColumn(
            'Plattform %/M', width=86, format='%.2f',
            help='Plattform-/Client-Selbstauskunft Rendite pro Monat '
                 '(30-Tage-Fenster je Client) — nicht unabhängig geprüft'),
        'Geom. %/M': _prozent(
            'Geom. %/M',
            help='Geometrisches Monatsmittel der EIGENEN virtuellen Kurve '
                 '(zinseszins-wahr); entfällt ohne belegbare Kapitalbasis'),
        'TrueRetDD': st.column_config.NumberColumn(
            'TrueRetDD', width=70, format='%.2f',
            help='ECHTER Jahres-Calmar: CAGR ÷ '
                 'gemessenem Max-Drawdown der Equity '
                 'INKL. schwebender Verluste (aus '
                 'Kursen, nie Close-DD) — entscheidet '
                 'das Grün-Gate (ab 3,0). Normal = '
                 'belastbar; ORANGE ≈ = vorbehaltlich '
                 '(Kursmessung nicht bestanden)'),
        'TrueRetDD ≈': st.column_config.NumberColumn(
            'TrueRetDD ≈', width=78, format='%.2f',
            help='Technischer Marker: steht der Wert hier (orange), '
                 'ist die angezeigte TrueRetDD-Zahl '
                 'vorbehaltlich — Calmar mit '
                 'dem rohen Kurs-Max-DD'),
        'RetDD/Monat': st.column_config.NumberColumn(
            'RetDD/Monat', width=80, format='%.2f',
            help='Monats-Variante: geometrische '
                 'Monatsrendite ÷ Max-Drawdown % '
                 '(Equity inkl. Floating) — '
                 'Anzeigewert, entscheidet nicht '
                 'mehr (Calmar-Gate seit 05.10.)'),
        'PF': _prozent('PF', 60),
        'Win %': st.column_config.NumberColumn('Win %', width=58, format='%.1f'),
        'Trades': st.column_config.NumberColumn('Trades', width=64, format='%.0f'),
        'Basis': st.column_config.TextColumn('Basis', width=64, help='Kapitalbasis: CSV = '
                                 'Einzahlungen im Export · Seite = Signalseite '
                                 '„Initial Deposit“ · implizit = Web-Balance − '
                                 'Trade-Netto · virtuell = 10.000-USD-Annahme'),
        'Forensik': st.column_config.TextColumn('Forensik', width=62),
    })

csv = df.to_csv(index=False, sep=';').encode('utf-8-sig')
st.download_button('Gefilterte Tabelle als CSV', csv, 'alle-signale.csv',
                   'text/csv', key='alle_signale_download',
                   icon=':material/download:')

def _ausgewaehlte_zeile(schluessel: str) -> int | None:
    """Zeilenauswahl der Tabelle lesen — als DataframeState ODER als dict.

    Letzteres ist der offizielle Weg für programmatische Selektionen
    (st.session_state[key] = {'selection': {'rows': [0]}}) und macht den
    Zustand in AppTest- wie Deep-Link-Szenarien setzbar.
    """
    zustand = st.session_state.get(schluessel)
    if not zustand:
        return None
    selection = getattr(zustand, 'selection', None)
    if selection is None and isinstance(zustand, dict):
        selection = zustand.get('selection')
    if selection is None:
        return None
    rows = getattr(selection, 'rows', None)
    if rows is None and isinstance(selection, dict):
        rows = selection.get('rows')
    return rows[0] if rows else None


gewaehlt_idx = _ausgewaehlte_zeile('alle_signale_tabelle')

if gewaehlt_idx is not None:
    st.divider()
    gewaehlt = sichtbar[gewaehlt_idx]
    statistik = dict(paare[gewaehlt_idx][1] or {})
    # Nutzer-Markierung (Nutzer 08.10.2026): Farbe setzen oder durch erneutes
    # Anklicken der aktiven Farbe abwählen — persistent je Signal-ID.
    aktiv_farbe = markierungen.get(int(gewaehlt.id))
    with st.container(horizontal=True, vertical_alignment='center'):
        st.caption(f'Markierung für #{gewaehlt.id} '
                   f'({getattr(gewaehlt, "name", "") or ""}):')
        for farbe, label in (('gruen', '🟩 Grün'), ('gelb', '🟨 Gelb'),
                             ('orange', '🟧 Orange')):
            if st.button(('✓ ' if aktiv_farbe == farbe else '') + label,
                         key=f'alle_signale_mark_{farbe}',
                         type='primary' if aktiv_farbe == farbe else 'secondary'):
                db.setze_markierung(int(gewaehlt.id),
                                    None if aktiv_farbe == farbe else farbe)
                st.rerun()
        if aktiv_farbe and st.button('Markierung entfernen',
                                     key='alle_signale_mark_keine',
                                     icon=':material/block:'):
            db.setze_markierung(int(gewaehlt.id), None)
            st.rerun()

    # Freitext-Kommentar (Nutzer 09.10.2026): warum aufgenommen / Fix-ID —
    # langes Feld, Bearbeitung im Dialog (Doppelklick auf Canvas-Zellen ist
    # in st.dataframe technisch nicht abfangbar; Klick+Button ist das
    # Streamlit-Äquivalent).
    if st.button(('📋 Kommentar bearbeiten' if db.get_kommentar(int(gewaehlt.id))
                  else '💬 Kommentar hinzufügen'),
                 key='alle_signale_komm_btn', icon=':material/edit_note:'):
        st.session_state['alle_signale_komm_dialog'] = True
    if db.get_kommentar(int(gewaehlt.id)):
        with st.expander('Kommentar', icon=':material/notes:'):
            st.markdown(db.get_kommentar(int(gewaehlt.id)))
    if st.session_state.get('alle_signale_komm_dialog'):
        @st.dialog('Kommentar', width='large')
        def _komm_dialog() -> None:
            st.caption(f'#{gewaehlt.id} · {getattr(gewaehlt, "name", "")} · '
                       'Warum aufgenommen? Warum Fix-ID? Was beobachten?')
            text = st.text_area('Kommentar', value=db.get_kommentar(int(gewaehlt.id)),
                                height=220, key='alle_signale_komm_text',
                                label_visibility='collapsed')
            col1, col2 = st.columns(2)
            if col1.button('Speichern', type='primary',
                           key='alle_signale_komm_save',
                           icon=':material/save:'):
                db.setze_kommentar(int(gewaehlt.id), text)
                st.session_state['alle_signale_komm_dialog'] = False
                st.rerun()
            if col2.button('Verwerfen', key='alle_signale_komm_cancel'):
                st.session_state['alle_signale_komm_dialog'] = False
                st.rerun()
        _komm_dialog()
    ist_katalog = getattr(gewaehlt, 'herkunft', '') == 'Katalog'
    if not (getattr(gewaehlt, 'trades_path', '') or ''):
        # Zeile ohne lokalen Trade-Cache: wenn sich eine Quellen-Referenz
        # auflösen lässt (Katalog-Zeile immer; gescanntes Quellen-Signal mit
        # fehlgeschlagenem Export über das Kürzel), Daten on demand holen —
        # danach laufen Statistik, Detailansicht und Equity-Studie normal.
        ref = katalog.quellen_referenz(gewaehlt)
        if ref is not None:
            quelle_id, version = ref
            st.info(
                f'„{getattr(gewaehlt, "name", gewaehlt.id)}“ hat noch keinen '
                'lokalen Trade-Cache. Einmalig von der Quelle laden, dann '
                'rechnet die Übersicht alle Kennzahlen und die Equity-Studie '
                '(realer Drawdown) läuft ebenfalls.', icon=':material/cloud_download:')
            if st.button('Trades + Kennzahlen von der Quelle laden',
                         key=f'alle_signale_fetch_{gewaehlt.id}',
                         icon=':material/download:'):
                try:
                    with st.spinner('Lade Trades + Kennzahlen von der Quelle …'):
                        gewaehlt.quelle_id, gewaehlt.quelle_version = quelle_id, version
                        pfad, _ = katalog.lade_signal_daten(gewaehlt)
                        artefakt = db.get_quellen_artefakt(
                            quelle_id, int(gewaehlt.id), version, 'trades')
                        gewaehlt.trades_path = pfad
                        gewaehlt.trades_sha256 = (artefakt or {}).get('sha256') or ''
                        stats_je_id[int(gewaehlt.id)] = katalog.metrics_stats(gewaehlt)
                        statistik = _statistik_fuer(gewaehlt) or statistik
                    if ist_katalog:
                        # Katalog-Zeilen sind nach dem Rerun persistent bedient
                        # (katalog_resultate liest die Artefakte neu).
                        st.rerun()
                    # Gescannte Zeile: In-Memory-Setzung wirkt bis zum nächsten
                    # Seitenladen; ein Scan-Lauf persistiert sie regulär.
                except downloader_client.DownloaderError as exc:
                    st.error(f'Laden fehlgeschlagen: {exc}',
                             icon=':material/error_outline:')
        else:
            # Weder Nachladen möglich (keine Quellen-Referenz) noch Cache —
            # das Detail trotzdem zeigen (KPIs „—", Anbieter-Link, Studien-
            # Button mit klarer Fehlermeldung): Zustand wie vor dem
            # Vollkatalog-Feature, kein stiller Informationsverlust.
            st.caption('Kein Trade-Cache und keine Quellen-Referenz — die '
                       'Trade-Liste kommt über einen Scan-Lauf '
                       '(oder Nachladen, sobald eine Quelle sie liefert).')
    if (getattr(gewaehlt, 'trades_path', '') or '') or not ist_katalog:
        render_detail(gewaehlt, statistik, key_prefix=f'alle_signale_detail_{gewaehlt.id}')
else:
    st.caption('Zeile anklicken für die Detailansicht: Monats-Balken, Konto-Kurve '
               'und Max-DD-Berechnung aus Kursen. Katalog-Zeilen laden ihre '
               'Trades beim ersten Klick on demand von der Quelle.')
