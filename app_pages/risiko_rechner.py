# -*- coding: utf-8 -*-
"""Max-Risiko-Rechner — eigene Seite (Nutzer-Wunsch 21.10.2026).

Trades importieren (oder Signal aus der DB wählen), maximale
Risikoberechnung anstoßen, ausführlichen PDF-Bericht erhalten.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mqlkiscanner import kapitalbasis, katalog, pipeline  # noqa: E402
from mqlkiscanner.risiko_rechner import (  # noqa: E402
    baue_pdf, berechne_csv, berechne_signal, closed_dd_prozent, CLOSED_DD_VERSION)
from mqlkiscanner.ui_design import apply_theme, page_header  # noqa: E402

apply_theme()
page_header(
    'MAX-RISIKO-RECHNER',
    'Maximaler Drawdown inklusive offener Trades',
    'Der Closed-DD sieht nur geschlossene Trades. Diese Rechnung baut die '
    'Equity-Kurve auf echten H1-Kursen nach — inklusive der Verluste, die '
    'offene Positionen zwischendurch hatten. Trades importieren oder Signal '
    'wählen, starten, PDF erhalten. Bewertet nichts, schreibt nichts in die DB.')

with st.expander('Wie wird gemessen?', expanded=False, icon=':material/science:'):
    st.markdown(
        '**Gleiche Messtechnik wie die Equity-DD-Studie.** Für jede Stunde der '
        'Handelshistorie: Startkapital + realisierte Ergebnisse + offener Betrag '
        '(floating) aller damals offenen Positionen, bewertet zum H1-Bar-Schluss. '
        'Der maximale Rückfall dieser Kurve ist der gesuchte Max-DD. GMT-Versatz '
        'je Symbol per Preisabgleich; Kursdaten kommen über das gemeinsame '
        'Lauf-Lock aus den konfigurierten MetaTrader-Terminals (Cache zuerst). '
        'Bei geschätztem Startkapital sind Drawdown und Renditen Modellwerte; '
        'Methode und Unsicherheit stehen im Ergebnis.')
    st.markdown(
        '**Was der Closed-DD übersieht.** Eine geschlossene Kurve kann 2 % zeigen, '
        'während offene Positionen zwischenzeitlich 30 % des Kontos unter Wasser '
        'standen. Genau diese Differenz steht hinter dem roten Warnhinweis im '
        'Bericht. Grenzen bleiben: H1-Schlusskurse (keine Intrabar-Tiefs), aktuell '
        'offene Positionen fehlen im Export, Beträge müssen USD sein.')
    st.markdown(
        '**Keine Bewertung.** Diese Seite misst nur — Ampel, Score und Urteil '
        'bleiben verbindlich bei der Engine.')

_ZIEL = 'mrr_ergebnis'
tab_import, tab_db = st.tabs(['📥 Trade-CSV importieren', '🗄️ Signal aus Datenbank'])

with tab_import:
    c1, c2 = st.columns([3, 2])
    with c1:
        datei = st.file_uploader(
            'Trade-Export (CSV) — MT5-Positions- oder MT4-Orderbuch-Format; '
            'Beträge in USD', type=['csv'], key='mrr_datei')
    with c2:
        name = st.text_input('Bezeichnung (frei, für den Bericht)', value='',
                             key='mrr_name')
        start_manuell = st.number_input(
            'Startkapital USD — 0 = automatisch: Beleg, Lotschätzung, grobe Schätzung, 10k-Fallback',
            min_value=0.0, value=0.0, step=100.0, key='mrr_startkap')
    broker = st.text_input('Broker-Server (optional — beeinflusst Kontraktgrößen)',
                           value='', key='mrr_broker')
    if st.button('⚡ Maximale Risikoberechnung starten', type='primary',
                 disabled=datei is None, key='mrr_start'):
        if datei is None:
            st.warning('Bitte zuerst eine Trade-CSV auswählen.')
        else:
            ablage = ROOT / '.tmp' / 'mrr_importe'
            ablage.mkdir(parents=True, exist_ok=True)
            pfad = ablage / f"{datei.name}"
            pfad.write_bytes(datei.getvalue())
            fehler = None
            try:
                with st.status('Maximale Risikoberechnung läuft …', expanded=True) as status:
                    bar = st.progress(0.0, text='starte …')

                    def p(anteil, text):
                        bar.progress(min(anteil, 1.0), text=f"{int(anteil * 100)} % · {text}")

                    ergebnis = berechne_csv(
                        pfad,
                        # Only this form uses 0 as the explicit "automatic"
                        # sentinel. The calculation API uses None instead.
                        startkapital_manuell=None if start_manuell == 0 else start_manuell,
                        name=name or datei.name,
                        broker=broker or None,
                        progress=p)
                    status.update(
                        label=f"Fertig — Messstatus: {ergebnis.get('status')}"
                              + (" (belastbar)" if (ergebnis.get('kennzahlen') or {}).get('verlaesslich')
                                 else ' (mit Vorbehalten)'),
                        state='complete')
                st.session_state[_ZIEL] = ergebnis
            except RuntimeError as exc:
                fehler = str(exc)
            except Exception as exc:  # noqa: BLE001 — klare Meldung statt Absturz
                fehler = f"{type(exc).__name__}: {exc}"
            if fehler:
                st.error(fehler, icon=':material/error:')

with tab_db:
    results_live = [r for r in pipeline.results_from_db(materialize_pdfs=False)
                    if getattr(r, 'source_kind', 'live') == 'live'
                    and getattr(r, 'trades_path', '')]
    _katalog_ergebnisse, _ = katalog.katalog_resultate()
    results_live += [r for r in _katalog_ergebnisse if getattr(r, 'trades_path', '')]
    treffer = [r for r in results_live if Path(r.trades_path).exists()]
    if not treffer:
        st.info('Kein Signal mit gespeicherter Trade-Liste — bitte erst scannen '
                '(z. B. Teilscan) oder oben eine CSV importieren.',
                icon=':material/info:')
    else:
        st.caption(f'{len(treffer)} Signale mit vorhandener Trade-Datei.')
        auswahl = st.selectbox(
            'Signal', treffer, index=None,
            format_func=lambda r: (f"{getattr(r, 'ampel', '')} {getattr(r, 'name', '') or r.id} "
                                   f"· #{r.id} · {getattr(r, 'quelle', 'mql5') or 'mql5'}"),
            key='mrr_signal')
        if auswahl is not None and st.button('⚡ Maximale Risikoberechnung starten',
                                             type='primary', key='mrr_start_db'):
            fehler = None
            try:
                with st.status('Maximale Risikoberechnung läuft …', expanded=True) as status:
                    bar = st.progress(0.0, text='starte …')

                    def p(anteil, text):
                        bar.progress(min(anteil, 1.0), text=f"{int(anteil * 100)} % · {text}")

                    ergebnis = berechne_signal(auswahl, progress=p)
                    status.update(
                        label=f"Fertig — Messstatus: {ergebnis.get('status')}",
                        state='complete')
                st.session_state[_ZIEL] = ergebnis
            except RuntimeError as exc:
                fehler = str(exc)
            except Exception as exc:  # noqa: BLE001
                fehler = f"{type(exc).__name__}: {exc}"
            if fehler:
                st.error(fehler, icon=':material/error:')

# ------------------------------------------------------------- Ergebnis
ergebnis = st.session_state.get(_ZIEL)
if ergebnis is not None:
    k = ergebnis.get('kennzahlen') or {}
    st.subheader(f"Ergebnis · {ergebnis.get('meta', {}).get('name', '—')}")
    capital_meta = ergebnis.get('meta') or {}
    capital_details = capital_meta.get('kapitalbasis_details') or ergebnis.get('kapitalbasis_details')
    capital_source = capital_details or capital_meta.get('startkapital_quelle')
    st.caption('Kapitalbasis: ' + kapitalbasis.beschreibung(capital_source))
    if kapitalbasis.ist_modellquelle(capital_source):
        st.warning('Virtuelle Modellstudie: Prozent-DD und Renditen beruhen auf geschätztem '
                   'Startkapital, keine nachgewiesenen Kontokennzahlen.')
    if capital_details:
        with st.expander('Kapitalbasis: Herkunft, Unsicherheit und Belege'):
            st.json(capital_details)
    if ergebnis.get('status') != 'ok':
        st.warning(f"Messung nicht vollständig: {ergebnis.get('grund') or ergebnis.get('status')}",
                   icon=':material/warning:')
    m1, m2, m3, m4 = st.columns(4)
    m1.metric('Max-DD inkl. offener Trades',
              '—' if k.get('equity_dd_pct') is None
              else f"{k['equity_dd_pct']:.2f} %".replace('.', ','))
    m2.metric('Max-DD (USD)',
              '—' if k.get('equity_dd_usd') is None else f"{k['equity_dd_usd']:,.0f} USD")
    m3.metric('Kurs-Abdeckung',
              '—' if k.get('abdeckung_pct') is None else f"{k['abdeckung_pct']:.1f} %")
    m4.metric('Stärkster Floating-Verlust',
              '—' if k.get('floating_min_usd') is None else f"{k['floating_min_usd']:,.0f} USD")
    closing_pct = closed_dd_prozent(ergebnis)
    if closing_pct is not None and ergebnis.get('closed_dd_version', 1) < CLOSED_DD_VERSION:
        st.caption('Gespeicherter Closed-DD aus einer älteren Berechnung; neue Berechnungen verwenden die gemeinsame Drawdown-Methodik.')
    if closing_pct is not None and k.get('equity_dd_pct') is not None:
        if k['equity_dd_pct'] - closing_pct > 10.0:
            st.error(f"⚠️ Die geschlossene Kurve unterschätzt das Risiko massiv: "
                     f"Closed-DD {closing_pct:.1f} % gegenüber "
                     f"Max-DD {k['equity_dd_pct']:.1f} % inklusive offener Trades.",
                     icon=':material/report:')
        else:
            st.caption(f"Vergleich: eigener Closed-DD {closing_pct:.2f} %.")
    ohne = ergebnis.get('symbole_ohne_kurse') or []
    if ohne:
        st.warning(f"Symbole ohne Kurse (floating unbekannt, DD kann unterschätzt sein): "
                   f"{', '.join(map(str, ohne))}", icon=':material/warning:')
    if ergebnis.get('kennzahlen', {}).get('verlaesslich') is False:
        st.caption('Messung mit Vorbehalten (Abdeckung unter 95 %, FX-Lücke oder '
                   'Zeitbasis uneinheitlich) — Details im PDF.')
    try:
        pdf_pfad, seiten = baue_pdf(ergebnis)
        with open(pdf_pfad, 'rb') as fh:
            st.download_button(
                f'📄 PDF-Bericht herunterladen ({seiten} Seiten)',
                data=fh.read(),
                file_name=pdf_pfad.name,
                mime='application/pdf',
                key='mrr_pdf_dl')
        st.caption(f'PDF zusätzlich gespeichert unter: {pdf_pfad}')
    except Exception as exc:  # noqa: BLE001
        st.error(f"PDF-Erzeugung fehlgeschlagen: {type(exc).__name__}: {exc}",
                 icon=':material/error:')
