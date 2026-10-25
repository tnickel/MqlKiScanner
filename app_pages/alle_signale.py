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
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import pandas as pd
import streamlit as st
from mqlkiscanner.signal_identity import identity_key, stable_identity_key

from mqlkiscanner import db, downloader_client, downloader_sync, katalog, pipeline, scan_worker
from mqlkiscanner import quellen
from mqlkiscanner import kapitalbasis, signal_statistik, studien_batch
from mqlkiscanner import tiefen_batch
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

_batch_run = tabellen_ui.studien_batch_merken(st.session_state, scan_worker.active_run())
_batch_tabellenstand = tabellen_ui.studien_batch_tabellenstand(_batch_run)
_lade_start = time.monotonic()
_lade_status = st.empty()
_lade_balken = st.empty()

# ── Abonnenten-Frische (Nutzer-Anforderung 25.10.) ───────────────────────
# Die Tabelle zeigt den Stand des letzten Client-Laufs, keine Live-Zahl —
# hier steht je Quelle, wann zuletzt WIRKLICH gemessen wurde (>24 h = ⚠),
# plus Button für die Frischmessung (Fortschritt auf Abonnentenstatistik).
# Bewusst OHNE eigenen scan_worker.active_run()-Aufruf: der Scan-Sperr-
# Zustand kommt aus _batch_run (aufrufzählergenaue Tests, AppTest-Fallen).
if sync_status:
    from mqlkiscanner import abonnenten_statistik as _abo_stat
    _frische = _abo_stat.juengste_messung(list(sync_status))
    _jetzt = datetime.now()
    _teile = []
    for _k, _ts in sorted(_frische.items()):
        if _ts is None:
            _teile.append(f"{_k} nie gemessen :red[⚠]")
            continue
        _stunden = (_jetzt - _ts).total_seconds() / 3600.0
        _teile.append(f"{_k} vor {_stunden:.0f} h"
                      + (" :red[⚠]" if _stunden > 24.0 else ''))
    st.caption('Abonnenten-Messung je Quelle: ' + ' · '.join(_teile)
               + ' — ⚠ älter als 24 h: Zahlen können hinter dem Broker zurückliegen.')
    _scan_laeuft = _batch_run is not None
    if _abo_stat.refresh_laeuft():
        st.caption(':blue[Abonnenten-Frischmessung läuft — Fortschritt und Ergebnis '
                   'auf der Seite „Abonnentenstatistik".]')
    elif st.button('Abonnentenzahlen frisch messen', key='alle_signale_abo_messen',
                   icon=':material/autorenew:', disabled=_scan_laeuft,
                   help='Startet denselben Zählerlauf wie auf der Abonnentenstatistik '
                        '(je Quelle Top 200, keine Tradelisten) und danach das Neu-'
                        'einlesen. Fortschritt und Ergebnis erscheinen dort; diese '
                        'Seite zeigt danach die aktuellen Zahlen. Gesperrt, während '
                        'ein Workflow-Scan läuft.'
                       if not _scan_laeuft else
                       'Gesperrt: Es läuft ein Workflow-Scan (dessen Stufe 0 '
                       'aktualisiert die Clients bereits).'):
        if _abo_stat.starte_refresh(messen=True, kuerzels=None):
            st.caption(':blue[Frischmessung gestartet — Fortschritt und Ergebnis '
                       'auf der Seite „Abonnentenstatistik". Diese Seite aktualisiert '
                       'die Zahlen nach Abschluss.]')
        else:
            st.caption('Es läuft bereits eine Abonnenten-Frischmessung.')


def _lade_phase(text: str):
    """Reale Arbeit zählen; Restzeit gilt nur für die laufende Phase."""
    phase_start = time.monotonic()
    letzte_anzeige = 0.0
    _lade_balken.empty()
    _lade_status.caption(f'{text} · vergangen {phase_start - _lade_start:.1f} s '
                         '· Restzeit noch unbekannt')

    def fortschritt(fertig: int, gesamt: int):
        nonlocal letzte_anzeige
        jetzt = time.monotonic()
        if fertig != gesamt and fertig and jetzt - letzte_anzeige < 0.2:
            return
        letzte_anzeige = jetzt
        rest = ((jetzt - phase_start) / fertig * (gesamt - fertig)
                if fertig else None)
        rest_text = f'≈ {rest:.1f} s' if rest is not None else 'unbekannt'
        _lade_status.caption(
            f'{text}: {fertig}/{gesamt} · vergangen {jetzt - _lade_start:.1f} s '
            f'· Rest dieser Phase {rest_text} (Schätzung)')
        _lade_balken.progress(fertig / gesamt if gesamt else 1.0)
    return fortschritt


_lade_phase('Gespeicherte Signale und Studien aus der Datenbank lesen')
_katalog_rows = db.list_catalog()
_studien = db.list_equity_studien(identitaeten=True)
_quellen_katalog = db.katalog_list()
_quellen_rows = db.list_quellen()
_quellen_artefakte = db.list_quellen_artefakte()
_mehrdeutige_ids = katalog.mehrdeutige_ids(
    {katalog.signal_identitaet(row) for row in _katalog_rows + _quellen_katalog})
gescannte = [r for r in pipeline.results_from_db(
                catalog_rows=_katalog_rows, studien=_studien,
                materialize_pdfs=False,
                progress=_lade_phase('Workflow-Signale aufbereiten'))
             if getattr(r, 'source_kind', 'live') == 'live']
katalog_resultate, katalog_stats = katalog.katalog_resultate(
    gescannt={katalog.signal_identitaet(r) for r in _katalog_rows}, studien=_studien,
    katalog_rows=_quellen_katalog, quellen_rows=_quellen_rows,
    artefakte=_quellen_artefakte,
    progress=_lade_phase('Lokalen Client-Katalog aufbereiten'))
alle = gescannte + katalog_resultate

if not alle:
    st.info('Noch keine Signale — oben „Katalog von den Clients laden“ '
            'klicken (dazu müssen die Monitor-Clients laufen) oder einen Scan '
            'starten.', icon=':material/info:')
    st.stop()

_workflow_stats = katalog.workflow_stats_bulk(
    gescannte, {identity_key(zeile): (zeile.get('stats') or {})
               for zeile in _katalog_rows},
    katalog_rows=_quellen_katalog, quellen_rows=_quellen_rows,
    artefakte=_quellen_artefakte)
stats_je_identitaet = {katalog.signal_identitaet(r): _workflow_stats.get(identity_key(r), {})
                     for r in gescannte}
stats_je_identitaet.update(katalog_stats)
_, _kapital_kalibrierbeleg = kapitalbasis.lade_kalibrierung_mit_beleg()
_kapital_kalibrierschluessel = tuple(_kapital_kalibrierbeleg.get(key) for key in
                                   ('status', 'sha256', 'datei_sha256'))
# Die Vorstufenstatistik löst die Kapitalbasis zentral auf. Gespeicherte
# Studien behalten ihre eigene belegte Basis; keine pauschale 10k-Injektion.

with st.container(horizontal=True):
    suche = st.text_input('🔍 Suchen — Name oder Signal-ID',
                          key='alle_signale_suche',
                          placeholder='Tippen zum Filtern: z. B. dino oder 1286742')
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
def _statistik_cached(trades_pfad: str, sha: str, stats_json: str,
                      rechenversion: str) -> dict | None:
    stats = json.loads(stats_json or '{}')
    stats['trades_sha256'] = sha
    return signal_statistik.berechne(trades_pfad, stats)


def _statistik_fuer(result) -> dict | None:
    waehrungsfehler = tabellen_ui.usd_statistik_fehler(result)
    if waehrungsfehler:
        return {'fehler': waehrungsfehler, 'waehrung_gesperrt': True}
    pfad = getattr(result, 'trades_path', '') or ''
    if not pfad or not Path(pfad).exists():
        return None
    rohstats = dict(stats_je_identitaet.get(katalog.signal_identitaet(result), {}))
    for feld in ('quelle', 'quellen_uid', 'signal_ref', 'id'):
        rohstats[feld] = getattr(result, feld, None)
    for feld in ('account_currency', 'broker_server'):
        rohstats.setdefault(feld, getattr(result, feld, None))
    # SHA im Cache-Schlüssel: Quellen-Artefakte werden bei Neu-Lieferung am
    # GLEICHEN Pfad überschrieben — ohne SHA bliebe die Statistik nach einem
    # Re-Download im Disk-Cache veraltet (Scan-Snapshots sind unveränderlich,
    # Katalog-Nachladungen nicht).
    return _statistik_cached(pfad, getattr(result, 'trades_sha256', '') or '',
                             json.dumps(rohstats, sort_keys=True, default=str),
                             f'2026-10-24-forex{pipeline.FORENSICS_VERSION}-kapitalmodell-v{kapitalbasis.VERSION}'
                             f'-{_kapital_kalibrierschluessel!r}')


suche_cf = (suche or '').strip().casefold()
markierungen = db.list_markierungen(identitaeten=True)
beobachtet_refs = db.list_beobachtungen()  # geteilt mit Abonnentenstatistik
dokumente_refs = db.downloader_reports_liste_alle()
kommentare = db.list_kommentare(identitaeten=True)
_mark_farben = {'Grün': 'gruen', 'Gelb': 'gelb', 'Orange': 'orange'}
gewaehlte_farben = {_mark_farben[w] for w in (mark_filter or [])}
sichtbar = []
for r in alle:
    if suche_cf and suche_cf not in f'{r.name} {r.id}'.casefold():
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
    if gewaehlte_farben and markierungen.get(identity_key(r)) not in gewaehlte_farben:
        continue
    sichtbar.append(r)

n_katalog = sum(1 for r in sichtbar if getattr(r, 'herkunft', '') == 'Katalog')
n_markiert_sichtbar = sum(1 for r in sichtbar if identity_key(r) in markierungen)
st.caption(f'{len(sichtbar)} von {len(alle)} Signalen'
           + (f' · {n_markiert_sichtbar} markiert' if n_markiert_sichtbar else '')
           + (f' · {n_katalog} nur Katalog' if n_katalog else '')
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
    run = tabellen_ui.studien_batch_merken(st.session_state, scan_worker.active_run())
    if run is None:
        return
    c = run.control
    refresh = tabellen_ui.studien_batch_refresh_noetig(
        run, st.session_state.get('_alle_signale_batch_tabellenstand') or {},
        jetzt=time.monotonic())
    if c.get('fertig'):
        st.info('Studien-Batch beendet: ' + (c.get('summary') or ''),
                icon=':material/task_alt:')
        if c.get('fehler'):
            waehrungsfehler = tabellen_ui.studien_batch_unbekannte_waehrungen(
                c['fehler'], alle)
            if waehrungsfehler:
                sichtbar = st.session_state.get('_alle_signale_waehrungsfehler_run') is run
                aktion = 'ausblenden' if sichtbar else 'anzeigen'
                if st.button(
                        f'Unbekannte Kontowährungen {aktion} ({len(waehrungsfehler)})',
                        key='alle_signale_batch_waehrungen', icon=':material/currency_exchange:'):
                    sichtbar = not sichtbar
                    st.session_state['_alle_signale_waehrungsfehler_run'] = run if sichtbar else None
                if sichtbar:
                    st.caption(
                        f'{len(waehrungsfehler)} betroffene Signale: Im beendeten Batch '
                        'war ihre Kontowährung nicht ausreichend belegt. '
                        '„Aktueller Nachweis“ zeigt den jetzt lokal vorhandenen Stand. '
                        'Die Liste umfasst auch durch die Seitenfilter ausgeblendete Signale.')
                    st.dataframe(
                        pd.DataFrame(waehrungsfehler), hide_index=True, height=420,
                        column_config={
                            'Signal öffnen': st.column_config.LinkColumn(display_text='öffnen'),
                        },
                        key='alle_signale_batch_waehrungen_tabelle')
            with st.expander(f'Fehler ({len(c["fehler"])})', icon=':material/warning:'):
                st.markdown('\n'.join(f'- {z}' for z in c['fehler']))
        if refresh:
            st.rerun(scope='app')
        return
    gesamt = c.get('gesamt') or 0
    aktuell = c.get('aktuell') or 0
    anteil = min(1.0, (aktuell / gesamt) if gesamt else 1.0)
    text = (f'Δ Signal {aktuell}/{gesamt} · Ø '
            f'{_dauer_text(c.get("dauer_je_s"))}/Signal · Rest ≈ '
            f'{_dauer_text(c.get("restzeit_s"))} · {c.get("aktuelles_signal") or c.get("phase", "")}')
    st.progress(anteil, text=text)
    st.caption(f'{c.get("gerechnet") or 0} Studien gespeichert · '
               f'{c.get("uebersprungen") or 0} übersprungen · '
               f'{len(c.get("fehler") or [])} Fehler · '
               'Neue Tabellenwerte werden etwa alle 15 Sekunden übernommen.')
    if st.button('Abbrechen', key='alle_signale_batch_abbruch',
                 icon=':material/cancel:'):
        c['abbruch'] = True
    if refresh:
        st.rerun(scope='app')


# Fragment NUR definieren reicht nicht — ohne Aufruf rendert nichts und der
# run_every-Timer startet nicht (genau deshalb fehlte der Balken, 08.10.).
# Erst nach der Datenaufbereitung die Drosselzeit starten. Sonst könnte ein
# langsamer Seitenaufbau den nächsten Rerun vor dem Tabellenrendern auslösen.
st.session_state['_alle_signale_batch_tabellenstand'] = {
    **_batch_tabellenstand, 'geladen_am': time.monotonic()}
_batch_fortschritt()


if st.session_state.get('alle_signale_batch_offen'):
    studien = db.list_equity_studien(identitaeten=True)
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
                tabellen_ui.studien_batch_merken(st.session_state, run)
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

_statistik_progress = _lade_phase('Statistiken aus dem Trade-Cache laden / rechnen')
_statistik_progress(0, len(sichtbar))
paare = []
for _nr, r in enumerate(sichtbar, 1):
    paare.append((r, _statistik_fuer(r)))
    _statistik_progress(_nr, len(sichtbar))


def _prozent(titel: str, breite: int = 86, help: str | None = None):
    return st.column_config.NumberColumn(titel, width=breite, format='%.2f',
                                         help=help)
_lade_phase('Tabelle und CSV aufbereiten')
_fix_ids = tabellen_ui._fix_ids()


def _tabellen_frame(tab_paare):
    df = pd.DataFrame([tabellen_zeile(r, s, markierungen, kommentare,
                                      fix_ids=_fix_ids,
                                      beobachtet=beobachtet_refs,
                                      dokumente=dokumente_refs)
                       for r, s in tab_paare])
    # Zahlen-Spalten strikt numerisch: None → NaN → LEERE Zelle statt „None“-
    # Text (Nutzer 08.10.2026: kompakte, lesbare Tabelle). Runden einmalig hier —
    # der Styler rendert die Werte dann ohne column_config-Formatierungs-Bridge.
    for _spalte in df.columns:
        if _spalte not in tabellen_ui.TEXT_SPALTEN:
            df[_spalte] = pd.to_numeric(df[_spalte], errors='coerce')
    return df.round(2)


# Nutzer-Markierungen: ganze Zeile dezent einfärben (grün/gelb/orange).
_MARK_BG = {'gruen': 'rgba(46,125,50,0.22)', 'gelb': 'rgba(214,168,0,0.20)',
            'orange': 'rgba(224,110,20,0.22)'}


def _mark_stil(zeile):
    farbe = next((k for k, e in tabellen_ui.MARKIERUNG_EMOJI.items()
                  if zeile.get('Mark.') == e), None)
    if not farbe:
        return [''] * len(zeile)
    return [f'background-color: {_MARK_BG[farbe]}'] * len(zeile)


def _virtueller_vorbehalt_stil(zeile):
    if 'Vorbehalt:' in str(zeile.get('Messstatus', '')):
        return ['color: #fb923c'] * len(zeile)
    return [''] * len(zeile)


def _tabelle_rendern(schluessel: str, tab_paare, dateiname: str) -> None:
    if not tab_paare:
        st.caption('Kein Signal in diesem Tab (Filter).')
        return
    df = _tabellen_frame(tab_paare)
    gestylt = df.style.format(na_rep='').apply(_mark_stil, axis=1)
    gestylt = gestylt.apply(_virtueller_vorbehalt_stil, axis=1,
                           subset=['True-DD USD', 'RetDD/Monat', 'Messstatus'])
    for _paar in (('True-DD %', 'True-DD ≈'), ('TrueRetDD', 'TrueRetDD ≈')):
        # Belastbar gemessen normal, vorbehaltlich orange (Marker in der
        # ≈-Spalte; pandas-apply übergibt mit subset NUR die genannten
        # Spalten, deshalb beide und Rückgabe je Zelle).
        if {_paar[0], _paar[1]} <= set(df.columns):
            def _vorbehalt_stil(zeile, marker=_paar[1]):
                if pd.isna(zeile[marker]):
                    return ['', '']
                stil = 'background-color: rgba(249,115,22,0.12); color: #fb923c'
                return [stil if pd.notna(zeile.iloc[0]) else '', stil]
            gestylt = gestylt.apply(_vorbehalt_stil, axis=1, subset=list(_paar))
    _identitaet = tuple(stable_identity_key(r) for r, _ in tab_paare)
    if st.session_state.get(f'_alle_signale_rows_{schluessel}') != _identitaet:
        st.session_state.pop(schluessel, None)
        st.session_state[f'_alle_signale_rows_{schluessel}'] = _identitaet
    st.dataframe(
        gestylt,
        key=schluessel,
        on_select='rerun',
        selection_mode='multi-row',
        hide_index=True,
        height=480,
        width="stretch",
        column_config={
        'Mark.': st.column_config.TextColumn('Mark.', width=44, help='Deine '
                                    'manuelle Markierung — setzen/entfernen: '
                                    'Zeile anklicken, dann Markierleiste '
                                    'unter der Tabelle'),
        'Komm.': st.column_config.TextColumn('Komm.', width=46, help='📋 = '
                                    'Kommentar vorhanden (warum aufgenommen / '
                                    'Fix-ID) — Zeile anklicken, dann '
                                    '„Kommentar bearbeiten" unter der Tabelle'),
        'Beob.': st.column_config.TextColumn('Beob.', width=48, help='👁 = auf '
                                    'der Beobachtungsliste (Tab „Beobachten“ '
                                    'der Abonnentenstatistik) — setzen/'
                                    'entfernen: Zeile anklicken, dann '
                                    '„👁 Beobachten“-Button unter der Tabelle. '
                                    'Gleicher Wert wie dort: einmal beobachtet '
                                    '= überall 👁.'),
        'Ber.': st.column_config.TextColumn('Ber.', width=52, help='📄 = '
                                    'KI-Analysen vorhanden (Trade-/Risiko-'
                                    'Analyse, Gesamtbericht, Tiefenanalyse; '
                                    '📄×N = N davon). Bericht öffnen: Ergebnisse-'
                                    'Seite bzw. Detailansicht. Katalog-Signale '
                                    'ohne Scan haben noch keine Analysen.'),
        'Doku': st.column_config.TextColumn('Doku', width=60, help='📑 = '
                                    'gespiegelte Testreport-PDFs (Testreports '
                                    'des MqlDownloader) — Anzahl ×N. Öffnen: '
                                    'Abonnentenstatistik → Zeile anklicken → '
                                    'Abschnitt „Dokumente“.'),
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
            help='Geometrisches Monatsmittel der EIGENEN Kurve '
                 '(zinseszins-wahr). Eine Modellbasis ist geschätzt, '
                 'keine belegte Kontorendite. Herkunft und Unsicherheit stehen daneben. Entfällt '
                 'ohne positive Kapitalbasis, bei nichtpositivem Endkapital '
                 'oder ohne positive Messdauer.'),
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
                 'mehr (Calmar-Gate seit 05.10.). Ohne positive '
                 'Equity-DD-Messung bleibt das Verhältnis undefiniert.'),
        'PF': _prozent('PF', 60, help='Summe positiver Trade-Profits ÷ Betrag '
                     'negativer Trade-Profits im Export. Ohne Verluste ist '
                     'der Nenner null; die Zelle bleibt undefiniert.'),
        'Win %': st.column_config.NumberColumn('Win %', width=58, format='%.1f',
                     help='Anteil profitabler Trades im lesbaren Export; '
                          'keine ungeprüfte Plattformangabe.'),
        'Trades': st.column_config.NumberColumn('Trades', width=64, format='%.0f',
                     help='Tatsächlich geparste Trades im lokalen Export. '
                          'Ohne Export unbekannt; ohne lesbare Trades null.'),
        'Basis': st.column_config.TextColumn('Basis', width=64, help='Kapitalbasis: CSV = '
                                 'Einzahlungen im Export · Seite = Signalseite '
                                 '„Initial Deposit“ · implizit = Web-Balance − '
                                 'Trade-Netto (historisch) · Lot/PnL = Lotschätzung · '
                                 'Lots grob = kalibrierte Lotschätzung · 10k-Modell = letzter Fallback'),
        'Forensik': st.column_config.TextColumn('Forensik', width=62),
        'Messstatus': st.column_config.TextColumn(
            'Messstatus', width=220,
            help='Basis und Qualität der gespeicherten Kursmessung. Virtuell '
                 'bedeutet geschätztes Modellkapital, keine nachgewiesene '
                 'Kontobasis. Vorbehalt nennt den konkreten Grund für eine '
                 'unvollständige oder gescheiterte Messung.'),
        })
    csv = df.to_csv(index=False, sep=';').encode('utf-8-sig')
    st.download_button('Gefilterte Tabelle als CSV', csv, dateiname,
                       'text/csv', key=f'alle_signale_download_{schluessel}',
                       icon=':material/download:')


# ── Tabs: Alle + je Broker (Nutzer-Wunsch 20.10., wie Abonnentenstatistik) ─
_tab_quellen = [k for k in (db.kanonische_quelle(q['kuerzel'])
                            for q in db.list_quellen(nur_aktiv=True))
                if any(r.quelle == k for r in alle)]
for r in alle:  # Quellen ohne aktive Registry-Zeile trotzdem zeigen
    if r.quelle not in _tab_quellen:
        _tab_quellen.append(r.quelle)
# Beobachtungsliste (Nutzer-Wunsch 20.10. spät): eigener ERSTER Tab, wie in
# der Abonnentenstatistik — gleiche Liste, gleicher Wert.
_beobachtete_paare = [(r, s) for r, s in paare
                      if getattr(r, 'signal_ref', None) in beobachtet_refs]
# Tab-Schlüssel → Quelle (None = Alle); der Alle-Tab behält den historischen
# Schlüssel 'alle_signale_tabelle' (Tests/Deep-Links injizieren genau den).
tab_definitionen = [('alle_signale_tabelle_beobachten', 'beobachten'),
                    ('alle_signale_tabelle', None)] + [
    (f"alle_signale_tabelle_{k.replace(' ', '_')}", k) for k in _tab_quellen]
_tab_objekte = st.tabs(
    [f'👁 Beobachten ({len(_beobachtete_paare)})', 'Alle']
    + [f'{quellen.anzeige_name({"kuerzel": k})} ({k})'
       for k in _tab_quellen])


def _tab_paare(tab_kuerzel):
    if tab_kuerzel == 'beobachten':
        return _beobachtete_paare
    return paare if tab_kuerzel is None else [
        (r, s) for r, s in paare if r.quelle == tab_kuerzel]


_select_all_intent = st.session_state.pop('_alle_signale_select_all', None)
if _select_all_intent:
    _intent_paare = _tab_paare(next(
        (k for s, k in tab_definitionen if s == _select_all_intent), None))
    st.session_state[_select_all_intent] = {
        'selection': {'rows': list(range(len(_intent_paare)))}}

for _nr, (_schluessel, _kuerzel) in enumerate(tab_definitionen):
    with _tab_objekte[_nr]:
        if _kuerzel == 'beobachten' and not _beobachtete_paare:
            st.caption('Noch nichts beobachtet — Zeile anklicken und in der '
                       'Markierleiste „👁 Beobachten“ klicken (oder in der '
                       'Abonnentenstatistik; dieselbe Liste).')
        else:
            _tabelle_rendern(_schluessel, _tab_paare(_kuerzel), _datei := (
                'alle-signale.csv' if _kuerzel is None
                else f'alle-signale-{_kuerzel if _kuerzel != "beobachten" else "beobachten"}.csv'))
            _selection_spalte = st.columns(2)
            if _selection_spalte[0].button(
                    f'☰ Alle im Tab auswählen ({len(_tab_paare(_kuerzel))})',
                    key=f'alle_signale_select_all_{_schluessel}',
                    icon=':material/select_all:',
                    help='Setzt das Häkchen für jede Zeile DIESES Tabs '
                         '(Mehrfachauswahl — danach z. B. KI-Analysen im '
                         'Sammelschalter unter der Tabelle).'):
                # Intent statt direktem State-Schreiben: Der Widget-State
                # darf erst im NÄCHSTEN Lauf VOR der Materialisierung gesetzt
                # werden (sonst StreamlitWidgetAlreadyInstantiatedError).
                st.session_state['_alle_signale_select_all'] = _schluessel
                st.rerun()
            if _selection_spalte[1].button(
                    'Auswahl leeren', key=f'alle_signale_clear_{_schluessel}',
                    icon=':material/deselect:'):
                st.session_state.pop(_schluessel, None)
                st.rerun()
_lade_balken.empty()
_lade_status.caption(f'Übersicht geladen in {time.monotonic() - _lade_start:.1f} s')

def _ausgewaehlte_zeile():
    """Zeilenauswahl über ALLE Tabs lesen — als DataframeState ODER als dict.

    Letzteres ist der offizielle Weg für programmatische Selektionen
    (st.session_state[key] = {'selection': {'rows': [0]}}) und macht den
    Zustand in AppTest- wie Deep-Link-Szenarien setzbar. Rückgabe:
    (Tab-Schlüssel, [Zeilenindizes]) des ersten Tabs mit einer Auswahl.
    """
    for _schluessel, _k in tab_definitionen:
        zustand = st.session_state.get(_schluessel)
        if not zustand:
            continue
        selection = getattr(zustand, 'selection', None)
        if selection is None and isinstance(zustand, dict):
            selection = zustand.get('selection')
        if selection is None:
            continue
        rows = getattr(selection, 'rows', None)
        if rows is None and isinstance(selection, dict):
            rows = selection.get('rows')
        if rows:
            return _schluessel, [int(r) for r in rows]
    return None


_gewaehlt_tab = _ausgewaehlte_zeile()
_tab_paar_liste = (_tab_paare(next(k for s, k in tab_definitionen
                                   if s == _gewaehlt_tab[0]))
                   if _gewaehlt_tab else [])
gewaehlt_nrs = _gewaehlt_tab[1] if _gewaehlt_tab else []
gewaehlt_idx = (gewaehlt_nrs[0] if len(gewaehlt_nrs) == 1 else None)

if len(gewaehlt_nrs) > 1:
    # Sammelschalter (Nutzer-Wunsch 20.10.): mehrere Häkchen → KI-Batch.
    _ki_ziele = [_tab_paar_liste[i][0] for i in gewaehlt_nrs
                 if i < len(_tab_paar_liste)]
    st.divider()
    _ki_ok = (len(_ki_ziele) <= 50
              and not tiefen_batch.batch_laeuft()
              and scan_worker.active_run() is None)
    _ki_hilfe = ('Erweiterte KI-Analyse (LLM-Tiefenanalyse) für die '
                 'gewählten Signale im Hintergrund starten — vorhandene '
                 'aktuelle werden übersprungen, es läuft fortsetzbar. '
                 'Pro Signal mehrere Minuten und Tokenverbrauch. Fehlende '
                 'Trade-Daten werden vorher von der Quelle nachgeladen '
                 '(auch OHNE vorhandene Forensik möglich; die Analyse '
                 'bewertet die Ampel nie neu).')
    if len(_ki_ziele) > 50:
        st.warning(f'{len(_ki_ziele)} Signale ausgewählt — bitte auf '
                   'höchstens 50 je Batch begrenzen (Token-Schutz). '
                   'Besser je Broker-Tab wählen.', icon=':material/warning:')
    if st.button(f'🤖 KI-Tiefenanalysen für {len(_ki_ziele)} Signale starten',
                 key='alle_signale_ki_batch', type='primary',
                 disabled=not _ki_ok, icon=':material/auto_awesome:',
                 help=_ki_hilfe):
        _nachgeladen, _fehlend = [], []
        with st.spinner('Fehlende Trade-Daten von den Quellen nachladen …'):
            for _ziel in _ki_ziele:
                if getattr(_ziel, 'trades_path', '')                         and Path(_ziel.trades_path).exists():
                    continue
                try:
                    katalog.lade_signal_daten(_ziel)
                    _nachgeladen.append(_ziel.id)
                except Exception as _exc:  # Einzelfehler: Batch meldet es
                    _fehlend.append(f"{getattr(_ziel, 'name', _ziel.id)}: "
                                    f"{type(_exc).__name__}")
        _nutzbar = [r for r in _ki_ziele
                    if getattr(r, 'trades_path', '')
                    and Path(r.trades_path).exists()]
        ok, meldung = tiefen_batch.batch_starten(_nutzbar)
        if ok:
            st.toast(f'KI-Batch gestartet: {len(_nutzbar)} Signale'
                     + (f' · {len(_nachgeladen)} Trade-Exporte nachgeladen'
                        if _nachgeladen else ''), icon=':material/auto_awesome:')
            st.rerun()
        else:
            st.warning(meldung, icon=':material/info:')
        if _fehlend:
            with st.expander(f'Ohne Trade-Daten geblieben ({len(_fehlend)})',
                             icon=':material/error_outline:'):
                for _z in _fehlend[:30]:
                    st.caption(_z)

if gewaehlt_idx is not None and 0 <= gewaehlt_idx < len(_tab_paar_liste):
    st.divider()
    gewaehlt = _tab_paar_liste[gewaehlt_idx][0]
    statistik = dict(_tab_paar_liste[gewaehlt_idx][1] or {})
    if int(gewaehlt.id) in _mehrdeutige_ids:
        st.warning('Diese Signal-ID kommt in mehreren Quellen vor. Trades und Kennzahlen '
                   'werden einschließlich Studien, Markierungen, Kommentaren und Fix-IDs je Quelle getrennt.')
    # Nutzer-Markierung (Nutzer 08.10.2026): Farbe setzen oder durch erneutes
    # Anklicken der aktiven Farbe abwählen — persistent je Signal-ID.
    aktiv_farbe = markierungen.get(identity_key(gewaehlt))
    with st.container(horizontal=True, vertical_alignment='center'):
        st.caption(f'Markierung für #{gewaehlt.id} '
                   f'({getattr(gewaehlt, "name", "") or ""}):')
        for farbe, label in (('gruen', '🟩 Grün'), ('gelb', '🟨 Gelb'),
                             ('orange', '🟧 Orange')):
            if st.button(('✓ ' if aktiv_farbe == farbe else '') + label,
                         key=f'alle_signale_mark_{farbe}',
                         type='primary' if aktiv_farbe == farbe else 'secondary'):
                db.setze_markierung(int(gewaehlt.id),
                                    None if aktiv_farbe == farbe else farbe, quelle=identity_key(gewaehlt)[0])
                st.rerun()
        if aktiv_farbe and st.button('Markierung entfernen',
                                     key='alle_signale_mark_keine',
                                     icon=':material/block:'):
            db.setze_markierung(int(gewaehlt.id), None, quelle=identity_key(gewaehlt)[0])
            st.rerun()
        # Beobachten-Schalter (Nutzer-Wunsch 20.10.): geteilt mit der
        # Abonnentenstatistik — dieselbe Liste, derselbe Wert. Widget-Key
        # enthält den Zustand (AppTest-Falle 15: kein veralteter Klick).
        _beobachtet_ist = getattr(gewaehlt, 'signal_ref', None) in beobachtet_refs
        if st.button('Beobachtung entfernen' if _beobachtet_ist else '👁 Beobachten',
                     key=f"alle_signale_beob_{getattr(gewaehlt, 'signal_ref', 'x')}"
                         f"_{int(_beobachtet_ist)}",
                     type='secondary' if _beobachtet_ist else 'primary',
                     icon=':material/visibility_off:' if _beobachtet_ist
                     else ':material/visibility:',
                     help='Setzt das Signal auf die gemeinsame Beobachtungsliste '
                          '(Tab „Beobachten“ der Abonnentenstatistik; dort auch '
                          'Mehrfachauswahl möglich).'):
            db.setze_beobachtung(int(gewaehlt.id), not _beobachtet_ist,
                                 quelle=identity_key(gewaehlt)[0])
            st.rerun()
        # Doku (Testreport-PDFs) nachladen — funktioniert OHNE Trades
        # (reiner REST-Download vom Client; anders als die KI-Berichte).
        if st.button('📑 Doku nachladen',
                     key='alle_signale_doku_laden',
                     icon=':material/cloud_download:',
                     help='Testreport-PDFs dieses Signals von der Quelle '
                          'anfordern und lokal spiegeln (Lesen/Download: '
                          'Abonnentenstatistik → Zeile → Dokumente).'):
            try:
                with st.spinner('Doku von der Quelle laden …'):
                    _neue = downloader_sync.sync_reports(
                        int(gewaehlt.id), str(getattr(gewaehlt, 'platform', '')),
                        quelle=identity_key(gewaehlt)[0])
                if _neue:
                    st.success(f'{len(_neue)} neue PDF(s) gespiegelt.')
                else:
                    st.info('Die Quelle hat keine (weiteren) PDFs für dieses '
                            'Signal.')
            except downloader_sync.downloader_client.DownloaderError as exc:
                st.warning(f'Nachladen fehlgeschlagen — {exc}',
                           icon=':material/warning:')

    # Freitext-Kommentar (Nutzer 09.10.2026): warum aufgenommen / Fix-ID —
    # langes Feld, Bearbeitung im Dialog (Doppelklick auf Canvas-Zellen ist
    # in st.dataframe technisch nicht abfangbar; Klick+Button ist das
    # Streamlit-Äquivalent).
    _selected_identity = stable_identity_key(gewaehlt)
    if st.session_state.get('_alle_signale_detail_identity') != _selected_identity:
        st.session_state.pop('alle_signale_komm_text', None)
        st.session_state['alle_signale_komm_dialog'] = False
        st.session_state['_alle_signale_detail_identity'] = _selected_identity
    if st.button(('📋 Kommentar bearbeiten' if db.get_kommentar(int(gewaehlt.id), quelle=identity_key(gewaehlt)[0])
                  else '💬 Kommentar hinzufügen'),
                 key='alle_signale_komm_btn', icon=':material/edit_note:'):
        st.session_state['alle_signale_komm_dialog'] = True
    if db.get_kommentar(int(gewaehlt.id), quelle=identity_key(gewaehlt)[0]):
        with st.expander('Kommentar', icon=':material/notes:'):
            st.markdown(db.get_kommentar(int(gewaehlt.id), quelle=identity_key(gewaehlt)[0]))
    if st.session_state.get('alle_signale_komm_dialog'):
        @st.dialog('Kommentar', width='large')
        def _komm_dialog() -> None:
            st.caption(f'#{gewaehlt.id} · {getattr(gewaehlt, "name", "")} · '
                       'Warum aufgenommen? Warum Fix-ID? Was beobachten?')
            text = st.text_area('Kommentar', value=db.get_kommentar(int(gewaehlt.id), quelle=identity_key(gewaehlt)[0]),
                                height=220, key='alle_signale_komm_text',
                                label_visibility='collapsed')
            col1, col2 = st.columns(2)
            if col1.button('Speichern', type='primary',
                           key='alle_signale_komm_save',
                           icon=':material/save:'):
                db.setze_kommentar(int(gewaehlt.id), text, quelle=identity_key(gewaehlt)[0])
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
                         key=f'alle_signale_fetch_{stable_identity_key(gewaehlt)}',
                         icon=':material/download:'):
                try:
                    with st.spinner('Lade Trades + Kennzahlen von der Quelle …'):
                        gewaehlt.quelle_id, gewaehlt.quelle_version = quelle_id, version
                        pfad, _ = katalog.lade_signal_daten(gewaehlt)
                        artefakt = db.get_quellen_artefakt(
                            quelle_id, int(gewaehlt.id), version, 'trades')
                        gewaehlt.trades_path = pfad
                        gewaehlt.trades_sha256 = (artefakt or {}).get('sha256') or ''
                        stats_je_identitaet[katalog.signal_identitaet(gewaehlt)] = katalog.metrics_stats(gewaehlt)
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
        render_detail(gewaehlt, statistik, key_prefix=f'alle_signale_detail_{stable_identity_key(gewaehlt)}')
else:
    st.caption('Zeile anklicken für die Detailansicht: Monats-Balken, Konto-Kurve '
               'und Max-DD-Berechnung aus Kursen. Katalog-Zeilen laden ihre '
               'Trades beim ersten Klick on demand von der Quelle.')


# ── Tiefenbatch-Fortschritt (Muster Ergebnisseite, eigene Keys) ────────────
@st.fragment(run_every=2.0)
def _alle_tiefen_fortschritt() -> None:
    batch = tiefen_batch.aktiver_batch()
    if batch is None:
        st.session_state.pop('_alle_tiefen_batch_stand', None)
        return
    # Auto-Refresh (Nutzer-Wunsch 20.10.): fertige Analysen sollen SOFORT
    # lesbar sein — gedrosselter App-Rerun bei done-Anstieg, Abschluss
    # sofort (Muster studien_batch_refresh_noetig).
    _stand = (batch.get("done") or 0, batch.get("total") or 0,
              bool(batch.get("fertig")))
    if tabellen_ui.tiefen_batch_refresh_noetig(
            _stand, st.session_state.get('_alle_tiefen_batch_stand'),
            st.session_state.get('_alle_tiefen_refresh_am') or 0.0,
            jetzt=time.monotonic()):
        st.session_state['_alle_tiefen_refresh_am'] = time.monotonic()
        st.rerun(scope='app')
    st.session_state['_alle_tiefen_batch_stand'] = _stand
    total = max(1, batch["total"])
    if tiefen_batch.batch_laeuft():
        st.progress(
            batch["done"] / total,
            text=(f"KI-Batch {batch['done']}/{batch['total']} · aktuell: "
                  f"{batch['aktuell'] or '—'} · übersprungen: "
                  f"{batch['uebersprungen']} · Fehler: {batch['fehler']}"),
        )
        if st.button("KI-Batch stoppen (nach der aktuellen Strategie)",
                     key="alle_signale_ki_stop", icon=":material/stop_circle:"):
            tiefen_batch.batch_stoppen()
            st.rerun(scope="fragment")
    else:
        dauer = str((batch.get("ende") or datetime.now())
                    - batch["start"]).split(".")[0]
        art = ("Abbruch per Stop" if batch["abgebrochen"]
               else "abgeschlossen")
        (st.warning if batch["fehler"] else st.success)(
            f"KI-Batch {art}: {batch['done']}/{batch['total']} bearbeitet · "
            f"{batch['uebersprungen']} übersprungen · {batch['fehler']} Fehler "
            f"· Dauer {dauer}",
            icon=":material/warning:" if batch["fehler"]
            else ":material/check_circle:")


_alle_tiefen_fortschritt()
