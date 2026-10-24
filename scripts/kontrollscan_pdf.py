# -*- coding: utf-8 -*-
"""PDF-Teil des unabhängigen Kontrollscans (siehe kontrollscan_bericht.py).

reportlab + Pillow, Fonts aus dem Projekt (pdf_reports._register_fonts).
Im PDF bewusst KEINE Emoji-Zeichen (Vera-Font hat keine) — Ampeln als
farbige Wörter (GRÜN/GELB/ROT/GRAU/GESPERRT).
"""
from __future__ import annotations

import html
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / '.tmp'

FONT = 'MKS-Vera'
FONT_BOLD = 'MKS-Vera-Bold'

AMPEL_FARBE = {
    '🟢': colors.HexColor('#2E7D32'),
    '🟡': colors.HexColor('#F9A825'),
    '🔴': colors.HexColor('#C62828'),
    '⚪': colors.HexColor('#9E9E9E'),
    '⛔': colors.HexColor('#212121'),
}
AMPEL_TEXT = {'🟢': 'GRÜN', '🟡': 'GELB', '🔴': 'ROT', '⚪': 'GRAU', '⛔': 'GESPERRT'}
AMPEL_HEX = {'🟢': '#2E7D32', '🟡': '#F9A825', '🔴': '#C62828', '⚪': '#9E9E9E', '⛔': '#212121'}
AMPEL_RGB = {k: (int(v.red * 255), int(v.green * 255), int(v.blue * 255)) for k, v in AMPEL_FARBE.items()}


def _ampel_inline(ampel) -> str:
    """Farbiger Ampel-HTML-Schnipsel: Punkt + gefärbtes Wort (statt Farbname in Schwarz)."""
    hexf = AMPEL_HEX.get(ampel, '#616161')
    return f'<font color="{hexf}"><b>• {_ampel_text(ampel)}</b></font>'

GRAU = colors.HexColor('#616161')


def _fonts_laden():
    from mqlkiscanner.pdf_reports import _register_fonts

    _register_fonts()


def _pil_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    import reportlab

    d = Path(reportlab.__file__).resolve().parent / 'fonts'
    return ImageFont.truetype(str(d / ('VeraBd.ttf' if bold else 'Vera.ttf')), size)


def de(v, nd=2, faktor=1.0, suffix=''):
    if v is None:
        return '—'
    return f'{v * faktor:.{nd}f}'.replace('.', ',') + suffix


def esc(t) -> str:
    # Zeichen, die die eingebettete Vera-Schrift nicht darstellen kann
    # (Emoji, Variation-Selektoren, ZWJ), rausfiltern — sonst Tofu-Kästchen.
    raus = []
    for ch in str(t):
        o = ord(ch)
        if (0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF
                or 0x2B00 <= o <= 0x2BFF or o in (0xFE0F, 0x200D, 0x20E3)):
            continue
        raus.append(ch)
    return html.escape(''.join(raus).strip(), quote=False)


def _stil(name, **kw) -> ParagraphStyle:
    basis = dict(fontName=FONT, fontSize=9.5, leading=13.5, textColor=colors.HexColor('#212121'))
    basis.update(kw)
    return ParagraphStyle(name, **basis)


# ------------------------------------------------------------------ Charts


def scatter_png(pfad: Path, punkte: list, schranke: float) -> None:
    w, h = 1500, 900
    ml, mr, mt, mb = 90, 30, 110, 90
    basis = PILImage.new('RGB', (w, h), 'white')
    img = ImageDraw.Draw(basis)
    f = _pil_font(26)
    fk = _pil_font(22)
    xmax = max([p[0] for p in punkte] + [60.0])
    ymax = 80.0

    def X(x):
        return ml + (w - ml - mr) * min(x, xmax) / xmax

    def Y(y):
        return h - mb - (h - mt - mb) * min(y, ymax) / ymax

    img.line([(ml, mt - 12), (ml, h - mb), (w - mr, h - mb)], fill=(90, 90, 90), width=2)
    schritt = max(10, int(xmax / 6 / 10) * 10)
    for i in range(0, int(xmax) + 1, schritt):
        img.line([(X(i), h - mb), (X(i), h - mb + 8)], fill=(90, 90, 90), width=2)
        img.text((X(i) - 18, h - mb + 14), str(i), font=fk, fill=(70, 70, 70))
    for i in range(0, int(ymax) + 1, 20):
        img.line([(ml - 8, Y(i)), (ml, Y(i))], fill=(90, 90, 90), width=2)
        img.text((14, Y(i) - 12), str(i), font=fk, fill=(70, 70, 70))
    if schranke <= xmax:
        img.line([(X(schranke), mt - 12), (X(schranke), h - mb)], fill=(198, 40, 40), width=2)
        img.text((X(schranke) + 6, mt - 10), f'DD-Referenz {de(schranke, 0)} %',
                 font=fk, fill=(198, 40, 40))
    for x, y, ampel, nr, *_rest in punkte:
        farbe = AMPEL_RGB.get(ampel, (120, 120, 120))
        r = 9 if nr is None else 13
        img.ellipse([X(x) - r, Y(y) - r, X(x) + r, Y(y) + r], fill=farbe)
        if nr is not None:
            img.text((X(x) + 10, Y(y) - 13), str(nr), font=fk, fill=(20, 20, 20))
    img.text((ml, 10), 'RetDD/Jahr auf H1-Max-DD (Anzeige bis 80)',
             font=f, fill=(30, 30, 30))
    img.text((ml, h - 40), 'eigener Max-DD % (H1-Rekonstruktion inkl. offener/floating Trades)',
             font=fk, fill=(70, 70, 70))
    lx = ml
    for k, label in AMPEL_TEXT.items():
        farbe = AMPEL_RGB.get(k, (120, 120, 120))
        img.ellipse([lx, 55, lx + 16, 71], fill=farbe)
        img.text((lx + 24, 50), f'Engine {label}', font=fk, fill=farbe)
        lx += 250
    pfad.parent.mkdir(parents=True, exist_ok=True)
    basis.save(pfad)


def balken_png(pfad: Path, zeilen: list, titel: str) -> None:
    n = len(zeilen)
    rh = 44
    w = 1500
    h = 90 + n * rh + 30
    basis = PILImage.new('RGB', (w, h), 'white')
    img = ImageDraw.Draw(basis)
    f = _pil_font(26, bold=True)
    fk = _pil_font(23)
    ml, mr = 560, 160
    vmax = min(max([z[1] for z in zeilen] + [1.0]), 60.0)  # Anzeige-Cap: Extreme spreizen den Maßstab nicht
    img.text((ml - 545, 16), titel, font=f, fill=(30, 30, 30))
    for i, (name, wert, ampel) in enumerate(zeilen):
        y = 70 + i * rh
        farbe = AMPEL_RGB.get(ampel, (120, 120, 120))
        img.text((10, y + 6), name[:44], font=fk, fill=(40, 40, 40))
        breit = int((w - ml - mr) * min(wert, vmax) / vmax)
        img.rectangle([ml, y + 6, ml + breit, y + rh - 18], fill=farbe)
        img.text((ml + breit + 10, y + 6), de(wert, 1), font=fk, fill=(30, 30, 30))
    pfad.parent.mkdir(parents=True, exist_ok=True)
    basis.save(pfad)


def monat_png(pfad: Path, monate: list) -> None:
    monate = monate[-36:]
    w, h = 1100, 330
    basis = PILImage.new('RGB', (w, h), 'white')
    img = ImageDraw.Draw(basis)
    fk = _pil_font(20)
    if not monate:
        img.text((10, 10), 'keine Monatsrenditen (Basis unbekannt)', font=fk, fill=(120, 120, 120))
        pfad.parent.mkdir(parents=True, exist_ok=True)
        basis.save(pfad)
        return
    ymax = max([abs(v) * 100 for _k, v in monate] + [1.0])
    bw = (w - 40) / len(monate)
    null = h / 2
    img.line([(20, null), (w - 10, null)], fill=(150, 150, 150), width=2)
    for i, (key, v) in enumerate(monate):
        p = v * 100
        bh = (h / 2 - 40) * abs(p) / ymax
        x0 = 25 + i * bw
        if p >= 0:
            img.rectangle([x0, null - bh, x0 + bw - 3, null], fill=(46, 125, 50))
        else:
            img.rectangle([x0, null, x0 + bw - 3, null + bh], fill=(198, 40, 40))
    img.text((25, 4), f'Monatsrenditen % (TWR, eigene Rechnung) - {monate[0][0]} bis {monate[-1][0]}',
             font=fk, fill=(60, 60, 60))
    img.text((25, h - 26), f'Skala +-{de(ymax, 1)} %', font=fk, fill=(120, 120, 120))
    pfad.parent.mkdir(parents=True, exist_ok=True)
    basis.save(pfad)


# --------------------------------------------------------------- Tabellen


def _tabelle(daten: list, breiten, header=False, font=8.6) -> Table:
    t = Table(daten, colWidths=breiten, repeatRows=1 if header else 0)
    stil = [
        ('FONTNAME', (0, 0), (-1, -1), FONT),
        ('FONTSIZE', (0, 0), (-1, -1), font),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#212121')),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#BDBDBD')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]
    if header:
        stil += [
            ('FONTNAME', (0, 0), (-1, 0), FONT_BOLD),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ECEFF1')),
        ]
    t.setStyle(TableStyle(stil))
    # Linksbündig: schmalere Tabellen würden sonst zentriert und wirken
    # neben vollbreiten Geschwistern eingerückt.
    t.hAlign = 'LEFT'
    return t


def _ampel_text(ampel) -> str:
    return AMPEL_TEXT.get(ampel, '—')


# ------------------------------------------------------------------- PDF


def baue_pdf(*, pdf_pfad, heute, datenstand, grund, roh, fehler, engine, shortlist,
             gruen_zweifelhaft, uebersehen, dd_abweichungen, unbewertbar_basis,
             kurz_liste, bewertbar, h1_unvollstaendig, ranking) -> int:
    _fonts_laden()
    titel_stil = _stil('t', fontName=FONT_BOLD, fontSize=21, leading=26)
    h2 = _stil('h2', fontName=FONT_BOLD, fontSize=13.5, leading=17, spaceBefore=10, spaceAfter=4)
    text = _stil('p')
    klein = _stil('k', fontSize=8.3, leading=11.5, textColor=GRAU)

    story = []

    def P(s, stil=None):
        story.append(Paragraph(s, stil or text))

    def _name_ref(r):
        return roh[r]['meta'].get('name') or f'ref {r}'

    # ------------------------------------------------ 1. Deckblatt
    ampel_zaehler = {}
    for ref in roh:
        a = (engine.get(ref) or {}).get('ampel')
        if a:
            ampel_zaehler[a] = ampel_zaehler.get(a, 0) + 1
    ampel_html = ' &nbsp;·&nbsp; '.join(
        f'<font color="{AMPEL_HEX.get(a, "#616161")}"><b>• {_ampel_text(a)} {n}</b></font>'
        for a, n in sorted(ampel_zaehler.items(), key=lambda kv: -kv[1]))
    P('Unabhängiger Kontrollscan', titel_stil)
    P('Welche Signale könnten nach eigener Rechnung noch gut sein?',
      _stil('u', fontSize=13, leading=17, textColor=GRAU))
    story.append(Spacer(1, 10))
    n_h1 = sum(1 for e in bewertbar if e.get('h1_status') in ('ok', 'ok_teilmessung'))
    deck = [
        ['Erstellungsdatum', heute.strftime('%d.%m.%Y %H:%M')],
        ['Datenstand Trade-Dateien', str(datenstand)],
        ['Geprüfte Signale (mit Trade-Daten)', str(len(roh) + len(fehler))],
        ['davon erfolgreich ausgewertet', str(len(roh))],
        ['Daten-/Analysefehler', str(len(fehler))],
        ['Bewertbar (belastbarer Max-DD, kein K.o.)', str(len(bewertbar))],
        ['Kapitalbasis nicht verwendbar', str(len(unbewertbar_basis))],
        ['Davon mit Modellkapital gerechnet', str(sum(bool(e.get('kapitalbasis_modell')) for e in roh.values()))],
        ['Engine-Ampeln der geprüften Signale', '__AMPEL__'],
        ['Bewertungsprinzip', 'Der Ertrag muss das Risiko bezahlen — RetDD auf dem selbst '
         'gemessenen Max-DD inkl. offener Trades (H1-Reko). Hohe DD schließt nicht aus, '
         'kurze Historie wird gekennzeichnet.'],
    ]
    deck_zellen = [
        [Paragraph(esc(a), text),
         Paragraph(ampel_html, text) if b == '__AMPEL__' else Paragraph(esc(b), text)]
        for a, b in deck
    ]
    story.append(_tabelle(deck_zellen, [68 * mm, 102 * mm], font=9))
    story.append(Spacer(1, 8))
    P('Dieser Bericht ist eine unabhängige Zweitprüfung neben dem Regelwerk des Scanners. '
      'Die Engine-Ampel wurde erst NACH der eigenen Bewertung als Vergleich herangezogen. '
      'Keine Anlageberatung; historische Rendite ist keine Prognose.', klein)
    story.append(PageBreak())

    # ------------------------------------------------ 2. Methodik
    P('Vorgehen und eigene Kriterien', h2)
    P('<b>Datenbasis:</b> neueste Roh-Trade-Datei je Signal (Tabelle trade_files), '
      'Metadaten aus Katalog-/Signaltabellen. Format-Parsing über den projekteigenen '
      'neutralen CSV-Parser (Summenzeilen, Kontobewegungs-Zeilen, Tausender-Trennzeichen). '
      'Forensik-Werte und KI-Berichte der Engine wurden bewusst erst nach der eigenen '
      'Bewertung gelesen (Gegencheck-Abschnitt).')
    P('<b>Eigene Rechnung je Signal:</b> Netto-PnL (alle Trades), TWR-Monatsrenditen auf '
      'der ausgewiesenen Kapitalbasis (Teilperioden je Kontofluss), '
      'Jahres-CAGR aus dem Gesamt-TWR-Faktor über die echte Zeitspanne '
      '(Jahr = 365,2425 Tage), längste Verlustserie, Winrate, '
      'Martingale-Median (Lot-Verhältnis nach Verlust; Flag ab größer 1,3), maximale '
      'gleichzeitige Positionen und Netto-Lots, Historienlänge und letzter Trade.')
    P('<b>Bewertung:</b> Kernmetrik ist der eigene RetDD — Jahres-Calmar (CAGR / Max-DD) '
      'und RetDD/Monat (geometrische Monatsrendite / Max-DD). <b>Nenner ist AUSSCHLIESSLICH '
      'der selbst gemessene Max-DD inklusive offener (floating) Trades aus der H1-'
      'Rekonstruktion (Nutzer-Regel 21.10.2026: der Drawdown der geschlossenen Kurve hat '
      'für die Bewertung keine Aussagekraft und wird nicht ausgewiesen).</b> Bewertbar ist '
      'nur, was eine belastbare H1-Messung hat (Status ok/ok_teilmessung) — Signale mit '
      'unvollständiger Messung stehen unter Datenqualität. Die konfigurierte DD-Schranke '
      '(50 %) erscheint nur als Referenzlinie. Harte K.o.s bleiben allein: Ausschlussliste '
      '(known_signals.json), Martingale-Signatur, Inaktivität (letzter Trade mehr als '
      '60 Tage zurück), Mikrobasis unter 100 USD (Prozentwerte nicht übertragbar). '
      'Historie unter 3 Monate wird als kurze Historie gekennzeichnet — kein Ausschluss, '
      'aber wenig belastbar. Eine Modellbasis bleibt eine hypothetische Kontogroesse; '
      'ihre Rendite-/DD-/RetDD-Werte sind Modellwerte, keine belegten Kontowerte.')
    P('<b>Gemeinsame Kapitalaufloesung:</b> positive CSV-Einzahlungen vor Handelsbeginn '
      'haben Vorrang, danach belegtes Quellen-Anfangskapital. Fehlt dieses, gilt derselbe '
      'programmweite Schaetzer: gepruefter unabhaengiger Closing-DD-Anker oder stabile '
      'Lot-/PnL-Regression, grobe vergleichbare Lotskalibrierung, zuletzt die offen benannte '
      'Annahme 10.000 USD. Herkunft, Unsicherheit, Export-SHA und gegebenenfalls '
      'Kalibrierungs-SHA stehen je Kandidat. Ein bekanntes nichtpositives CSV-Netto wird '
      'nicht durch Modellkapital ersetzt. Vorhandene Ein-/Auszahlungen bleiben erhalten; '
      'separate Kontokosten werden einmal als Ergebnis gebucht. Native USD-Waehrung '
      'muss belegt sein. Der Gegencheck verwendet dieselbe Kapitalmethodik wie die '
      'Engine und ist in diesem Teil keine unabhaengige Validierung des Schaetzers.')
    P('<b>Max-DD inkl. offener Trades (H1-Rekonstruktion):</b> Für prüfbare Signale '
      'wird die PRODUKTIONSfunktion des Projekts gerechnet '
      '(forensics/equity_rekonstruktion.rekonstruiere): Equity-Kurve auf H1-Raster mit '
      'realisiertem UND offenem (floating) PnL, Auto-GMT per Preisabgleich. Kursquelle '
      'ist ausschließlich der vorhandene H1-Cache (data/kursdaten.db, read-only) — '
      'kein Terminal, kein Nachladen; Symbole ohne Cache-Bars bleiben ehrlich ohne Kurse '
      '(Status ok_teilmessung). Status ok/ok_teilmessung gilt als belastbar und ist der '
      'EINZIGE Nenner: RetDD/Jahr = CAGR (eigene Rechnung) / Max-DD (H1-Reko). '
      '<b>Alle Rangfolgen und Kennzahlen dieses Berichts nutzen ausschließlich diesen '
      'Max-DD.</b>')
    P('<b>Grenzen der eigenen Rechnung:</b> H1-Schlusskurse — Verluste INNERHALB einer '
      'Stunde (Intrabar-Tiefs) bleiben unbekannt, der echte Max-DD kann höher sein; '
      'aktuell offene Positionen fehlen im Export. Kopiergebühren, Slippage und '
      'Spread-Differenzen sind nicht enthalten. Die Engine misst denselben Kanal mit '
      'Terminal-Zugriff; deutliche Abweichungen (mehr als 10 Prozentpunkte) stehen in '
      'der Abweichungstabelle.')
    story.append(PageBreak())

    # --------------------------------- 2b. Empfehlungen in Reihenfolge
    P('Die Empfehlungen in Reihenfolge', h2)
    P('Bewertet wurde NUR mit dem selbst gemessenen Max-DD inklusive offener Trades '
      '(H1-Rekonstruktion) — ein Signal ist hier nur gelistet, wenn diese Messung belastbar '
      'ist. Die Reihenfolge folgt dem RetDD/Jahr (Ertrag je Risiko; höher = besser). '
      'Alle Werte: eigene Rechnung aus den Roh-Trades.', text)
    story.append(Spacer(1, 6))

    def _empfehlungstext(e) -> str:
        profit = e.get('ertrag_monat_geom_pct') or 0.0
        maxdd = e.get('h1_dd_pct_raw') or 0.0
        ret = e.get('retdd_jahr_h1') or 0.0
        basis = e.get('startkapital') or 0.0
        monate = e.get('historie_monate') or 0.0
        netto_m = e.get('netto_monat_usd') or 0.0
        win = (e.get('winrate') or 0.0) * 100.0
        serie = e.get('max_verlustserie') or 0
        teile = [
            f"{de(profit, 1)} % Profit/Monat (Ø {de(netto_m, 0, 1, ' USD')} je Monat) bei einem "
            f"Max-DD von {de(maxdd, 1)} % inkl. offener Trades — der Jahres-Ertrag bezahlt "
            f"den maximalen Rückfall {de(ret, 1)}-fach."
        ]
        if e.get('kapitalbasis_modell'):
            from mqlkiscanner.kapitalbasis import beschreibung
            details = e.get('kapitalbasis_details') or {}
            teile.append(f"Modellkapital {de(basis, 0, 1, ' USD')}: "
                         f"{beschreibung(details or e.get('kapitalbasis_quelle'))}. "
                         "Prozent- und RetDD-Werte gelten nur unter dieser Kapitalannahme.")
        elif basis >= 5000:
            teile.append(f"Ausgewiesene Kapitalbasis {de(basis, 0, 1, ' USD')}; "
                         "die Uebertragbarkeit haengt von den Kopierbedingungen ab.")
        elif basis >= 500:
            teile.append(f"Kapitalbasis {de(basis, 0, 1, ' USD')} — brauchbar; Lot-Faktor "
                         "moderat wählen.")
        else:
            teile.append(f"Kleine Basis ({de(basis, 0, 1, ' USD')}) — Mindestlot-Effekte "
                         "verzerren Prozentwerte beim Kopieren, deshalb nur mit kleinem "
                         "Lot-Faktor.")
        if monate >= 12:
            teile.append(f"{de(monate, 0)} Monate Historie — belastbare Beweislänge.")
        elif monate >= 6:
            teile.append(f"{de(monate, 0)} Monate Historie — für die Messung ausreichend, "
                         "aber noch jung.")
        teile.append(f"Winrate {de(win, 0)} %, längste Verlustserie {serie} Trades, "
                     f"{e.get('n_trades', 0)} Trades insgesamt.")
        if e.get('kurze_historie'):
            teile.append("Vorbehalt: Historie unter 3 Monate — Werte noch wenig belastbar.")
        return ' '.join(teile)

    n_empf = 0
    for i, e in enumerate(ranking, start=1):
        farbe = '#2E7D32' if e['stufe'] == 'A' and not e.get('kapitalbasis_modell') else '#E65100'
        stufe_wort = ('MODELL-VORAUSWAHL' if e.get('kapitalbasis_modell') else
                      'EMPFOHLEN' if e['stufe'] == 'A' else 'EMPFOHLEN MIT VORBEHALT')
        P(f'<font color="{farbe}"><b>{i}. {esc(e["meta"].get("name") or e["ref"])} '
          f'({de(e.get("h1_dd_pct_raw"), 1)} % Max-DD · {de(e.get("ertrag_monat_geom_pct"), 1)} % '
          f'Profit/Monat · RetDD {de(e["retdd_jahr_h1"], 1)} · {stufe_wort})</b></font>', text)
        P(_empfehlungstext(e), klein)
        story.append(Spacer(1, 4))
        n_empf += 1
    if not n_empf:
        P('keine Kandidaten über der Orientierungsschwelle', klein)
    story.append(Spacer(1, 6))
    P('<b>Wie lesen Sie diese Liste?</b> Rang 1 hat den besten Ertrag je erlittenem Risiko. '
      '„Empfohlen" (grün) heißt: belastbare Messung und mindestens 3 Monate Historie. '
      '„Mit Vorbehalt" (orange): gleiche Qualität der Rechnung, aber unter 3 Monate '
      'Historie. „Modell-Vorauswahl" (Stufe M, orange) bleibt unabhaengig von der '
      'Historienlaenge unter dem Vorbehalt einer geschaetzten Kapitalbasis. '
      'Keine der Empfehlungen ersetzt Ihre eigene Prüfung — Kopiergebühren, '
      'Slippage und die Wahl des Lot-Faktors sind nicht enthalten.', klein)
    story.append(PageBreak())
    P('Gesamtübersicht: eigene Effizienz vs. Engine-Ampel', h2)
    short_refs = {e['ref']: i + 1 for i, e in enumerate(shortlist)}
    punkte = []
    for ref, erg in roh.items():
        if erg.get('retdd_jahr_h1') is not None and erg.get('h1_dd_pct_raw') is not None:
            punkte.append((erg['h1_dd_pct_raw'], erg['retdd_jahr_h1'],
                           (engine.get(ref) or {}).get('ampel'), short_refs.get(ref)))
    p1 = TMP / 'kontrollscan_scatter.png'
    scatter_png(p1, punkte, grund['dd_schranke'])
    story.append(Image(str(p1), width=172 * mm, height=103 * mm))
    story.append(Spacer(1, 6))
    P('<b>Was diese Grafik zeigt:</b> Jeder Punkt ist ein bewertetes Signal. Die horizontale '
      'Achse ist der selbst gemessene Max-DD in Prozent (inkl. offener Trades) — <b>weiter '
      'links = weniger maximaler Rückfall erlitten</b>. Die vertikale Achse ist der RetDD/Jahr '
      '(Ertrag geteilt durch diesen Max-DD) — <b>weiter oben = besser</b>: Das Signal hat aus '
      'jedem Prozent Risiko mehr Ertrag geholt. <b>Die besten Signale stehen also links oben.</b> '
      'Die rote Linie ist die konfigurierte DD-Schranke (50 %) — sie ist nur eine Referenz, '
      'kein Ausschlusskriterium. Die Farbe jedes Punktes zeigt, welche Ampel die Engine dem '
      'Signal gegeben hat (grün/gelb/rot/grau/schwarz) — wo ein farblich „guter" Punkt weit '
      'unten rechts liegt oder ein „schlechter" oben links, widerspricht die eigene Rechnung '
      'der Engine; diese Fälle stehen im Abweichungs-Kapitel. Nummerierte Punkte verweisen '
      'auf die Shortlist-Kapitel-Seiten.', klein)
    story.append(Spacer(1, 10))
    zeilen = [(e['meta'].get('name', str(e['ref'])), e['retdd_jahr_h1'],
               (engine.get(e['ref']) or {}).get('ampel')) for e in bewertbar[:15]]
    p2 = TMP / 'kontrollscan_balken.png'
    balken_png(p2, zeilen, 'Eigene RetDD/Jahr auf dem Max-DD inkl. offener Trades — Top 15 '
                           '(Balkenfarbe = Engine-Ampel)')
    with PILImage.open(p2) as chart:
        chart_width, chart_height = chart.size
    story.append(Image(str(p2), width=172 * mm, height=172 * mm * chart_height / chart_width))
    story.append(Spacer(1, 6))
    P('<b>Was diese Grafik zeigt — und wie lang ein Balken sein sollte:</b> Jeder Balken ist '
      'das RetDD/Jahr eines Signals: der Jahres-Ertrag geteilt durch den selbst gemessenen '
      'Max-DD inkl. offener Trades. <b>Der LÄNGERE Balken ist immer der bessere</b> — er '
      'bedeutet, dass das Signal für jedes Prozent erlittenen Rückfalls mehr Jahres-Ertrag '
      'geliefert hat. Die Zahl am Balkenende ist der genaue Wert; als ordentlich gilt ab '
      f'{de(grund["min_calmar"], 1)} (Orientierungsschwelle, wie ein Jahres-Calmar), Spitzenwerte '
      'liegen darüber deutlich höher. <b>Die Balkenfarbe ist KEINE Bewertung dieser Liste</b> — '
      'sie zeigt nur, welche Ampel die Engine dem Signal gegeben hat (grün/gelb/rot/grau). '
      'Gerade der Widerspruch „roter Balken, aber hoher Wert" ist ein typischer Kontrollfund: '
      'Die eigene Rechnung mit dem echten Max-DD bewertet das Signal besser als die Engine.', klein)
    story.append(PageBreak())

    # ------------------------------------------- 3b. Profit + Empfehlungs-Ranking
    P('Profit je Monat und Empfehlungs-Ranking (eigene Rechnung)', h2)
    P('<b>Profit/Monat</b> = geometrische TWR-Monatsrendite auf der ausgewiesenen Kapitalbasis '
      '(Leermonate zählen). <b>Netto/Monat</b> = handelndes Netto-PnL je Monat in USD. '
      '<b>RetDD/Jahr</b> = CAGR ÷ Max-DD — Nenner ist AUSSCHLIESSLICH der selbst '
      'gemessene Max-DD inkl. offener Trades (H1-Reko); Orientierungsschwelle '
      f'{de(grund["min_calmar"], 1)}. Hohe DD schließt nicht aus — sie muss bezahlt sein.', text)
    story.append(Spacer(1, 4))
    kopf = ['Rang', 'Signal', 'Quelle', 'Basis', 'Mon.', 'Max-DD', 'Profit/M',
            'Netto/M', 'RetDD', 'Stufe']
    zeilen_r = [kopf]
    for i, e in enumerate(ranking, start=1):
        h1 = e.get('h1_dd_pct_raw')
        maxdd_txt = de(h1, 1) if h1 is not None else '—'
        if e.get('h1_status') == 'ok_teilmessung':
            maxdd_txt += ' *'
        if e['stufe'] == 'A':
            stufe_zelle = Paragraph('<font color="#2E7D32"><b>A</b></font>', text)
        else:
            stufe_zelle = Paragraph(f'<font color="#E65100"><b>{esc(e["stufe"])}</b></font>', text)
        zeilen_r.append([
            str(i),
            Paragraph(esc(e['meta'].get('name') or e['ref']), text),
            esc(e['meta'].get('quelle') or '—'),
            de(e.get('startkapital'), 0) + (' M' if e.get('kapitalbasis_modell') else ''),
            de(e.get('historie_monate'), 0),
            maxdd_txt,
            de(e.get('ertrag_monat_geom_pct'), 2),
            de(e.get('netto_monat_usd'), 0),
            de(e['retdd_jahr_h1'], 1),
            stufe_zelle,
        ])
    if len(zeilen_r) > 1:
        story.append(_tabelle(zeilen_r, [9 * mm, 38 * mm, 13 * mm, 15 * mm, 10 * mm, 16 * mm,
                                         17 * mm, 18 * mm, 14 * mm, 12 * mm], header=True, font=7.8))
    else:
        P('keine Kandidaten über der Orientierungsschwelle', klein)
    story.append(Spacer(1, 4))
    P('* Teilmessung — einzelne Symbole ohne Kurse, Max-DD auf den betrachteten Symbolen '
      'gemessen. <b>Spalten:</b> Basis = verwendete Kapitalbasis in USD, Zusatz M = '
      'Modellkapital · Mon. = Historie in '
      'Monaten · Max-DD % = selbst gemessener maximaler Drawdown inkl. offener Trades '
      '(H1-Reko) · Profit/M = geometrische Monatsrendite · Netto/M = durchschnittliches '
      'Handelsergebnis je Monat in USD · RetDD = Jahres-Ertrag geteilt durch den Max-DD '
      '(höher = besser; die Orientierungsschwelle liegt bei '
      f'{de(grund["min_calmar"], 1)}). <b>Stufe:</b> '
      '<font color="#2E7D32"><b>A</b></font> = empfohlen (RetDD über der Schwelle, '
      'mindestens 3 Monate Historie) · <font color="#E65100"><b>B</b></font> = mit '
      'Vorbehalt (gleiche Rechnung, aber unter 3 Monate Historie) · '
      '<font color="#E65100"><b>M</b></font> = Modell-Vorauswahl, keine belegte Kontogroesse.', klein)
    story.append(PageBreak())

    # ------------------------------------------------ 4. Shortlist
    P('Shortlist — könnten noch gut sein (eigene Rechnung)', h2)
    P('Sortiert nach eigenem RetDD/Jahr auf dem Max-DD inkl. offener Trades. Keine finale '
      'Empfehlung — diese Liste ist die Vorauswahl für die intensive Einzelfallprüfung. '
      '<b>Zu den Monats-Grafiken je Kandidat:</b> Jeder Balken ist ein Monat (grün = '
      'Gewinnmonat, rot = Verlustmonat), gemessen als Rendite auf der ausgewiesenen Kapitalbasis '
      'dieses Kontos. Wichtig ist das Muster: viele kleine grüne Balken mit wenigen kurzen '
      'roten passen zu einer stabilen Strategie; ein einziger hoher grüner Balken zwischen '
      'vielen roten bedeutet, dass die Gesamtrendite aus wenigen Ereignissen stammt und '
      'spröde ist. Bei Modellkapital sind die Renditen hypothetisch. '
      'Die Skala steht unter jeder Grafik.', klein)
    for i, e in enumerate(shortlist, start=1):
        ref = e['ref']
        eng = engine.get(ref) or {}
        meta = e['meta']
        story.append(Spacer(1, 8))
        kopf = (f"<b>{i}. {esc(meta.get('name') or ref)}</b> — Quelle {esc(meta.get('quelle') or '—')}"
                f" · Anbieter-ID {esc(meta.get('externe_id') or '—')} · Plattform {esc(meta.get('platform') or '—')}")
        if e['kurze_historie']:
            kopf += ' — <font color="#E65100"><b>KURZE HISTORIE UNTER 3 MONATEN — WENIG BELASTBAR, GENAUER ANSCHAUEN</b></font>'
        if e.get('kleiner_dd_nenner'):
            kopf += (' — <font color="#E65100"><b>WINZIGER DD-NENNER (unter 1 %) — RetDD-Verhältnis '
                     'gespreizt,	genauer anschauen</b></font>')
        if e.get('kapitalbasis_modell'):
            kopf += ' — <font color="#E65100"><b>MODELLKAPITAL - KEINE BELEGTE KONTOGROESSE</b></font>'
        P(kopf, h2)
        if meta.get('url'):
            P(esc(meta['url']), klein)
        zeilen = [
            ['Kennzahl', 'Wert', 'Quelle'],
            ['Eigener RetDD/Jahr (auf Max-DD)', de(e['retdd_jahr_h1'], 2), 'eigene Rechnung'],
            ['Eigener RetDD/Monat (auf Max-DD)', de(e.get('retdd_monat_h1'), 2), 'eigene Rechnung'],
            ['Max-DD inkl. offener Trades (H1-Reko)',
             ((de(e['h1_dd_pct_raw'], 2, 1, ' %') + f" — Status {e.get('h1_status')}, "
               + (f"Abdeckung {de(e.get('h1_abdeckung_pct'), 1)} %" if e.get('h1_abdeckung_pct') is not None else 'ohne Angabe'))
              if e.get('h1_dd_pct_raw') is not None
              else f"nicht messbar ({e.get('h1_grund') or e.get('h1_status') or '—'})"),
             'eigene Rechnung'],
            ['CAGR/Jahr', de(e['cagr'], 1, 100, ' %'), 'eigene Rechnung'],
            ['Profit/Monat (geom., TWR)', de(e.get('ertrag_monat_geom_pct'), 2, 1, ' %'), 'eigene Rechnung'],
            ['Netto-PnL je Monat', de(e.get('netto_monat_usd'), 0, 1, ' USD'), 'eigene Rechnung'],
            ['Netto-PnL gesamt', de(e['netto_gesamt'], 0, 1, ' USD'), 'eigene Rechnung'],
            ['Verwendete Kapitalbasis', de(e['startkapital'], 0, 1, ' USD'),
             'Modell' if e.get('kapitalbasis_modell') else 'CSV / Quellenbeleg'],
            ['Historie', f"{de(e['historie_monate'], 1)} Monate · {e['n_trades']} Trades · "
                         f"letzter Trade {e['letzter_trade'][:10]}", 'eigene Rechnung'],
            ['Winrate / max. Verlustserie',
             f"{de(e['winrate'], 0, 100, ' %')} / {e['max_verlustserie']} Trades", 'eigene Rechnung'],
            ['Martingale-Median (Lot nach Verlust)', de(e['martingale_median'], 2), 'eigene Rechnung'],
            ['Peak gleichzeitige Positionen / max. Lots',
             f"{e['peak_positionen']} / {de(e['peak_abs_lots'], 2)} Lots", 'eigene Rechnung'],
            ['Symbole', ', '.join(e['symbole'][:8]) + (' …' if len(e['symbole']) > 8 else ''), 'eigene Rechnung'],
            ['Engine-DD (H1-Kurse, inkl. Floating)', de(eng.get('engine_dd_reko'), 2, 1, ' %'), 'Engine'],
            ['Engine-Calmar (RetDD/Jahr)', de(eng.get('engine_calmar'), 2), 'Engine'],
            ['Engine-Ampel', _ampel_text(eng.get('ampel')), 'Engine'],
            ['Abonnenten / Wochen', f"{esc(meta.get('abonnenten'))} / {esc(meta.get('wochen'))}", 'Plattform'],
        ]
        from mqlkiscanner.kapitalbasis import beschreibung
        details = e.get('kapitalbasis_details') or {}
        proof = details.get('beleg') or {}
        calibration = proof.get('kalibrierung') or {}
        zeilen.insert(9, ['Kapitalherkunft', beschreibung(details or e.get('kapitalbasis_quelle')),
                          'gemeinsamer Resolver'])
        if e.get('kapitalbasis_modell'):
            zeilen.insert(10, ['Kapitalunsicherheit', details.get('unsicherheit') or 'Modellannahme',
                              'Modellannahme'])
        evidence = 'Trade-SHA: ' + str(proof.get('trades_sha256') or 'nicht angegeben')
        if calibration.get('sha256'):
            evidence += '; Kalibrierung-SHA: ' + calibration['sha256']
        zeilen.insert(11, ['Kapitalbeleg', evidence, 'SHA / Herkunft'])
        daten = [zeilen[0]]
        for z in zeilen[1:]:
            if z[0] == 'Engine-Ampel':
                daten.append([Paragraph(esc(z[0]), text),
                              Paragraph(_ampel_inline(eng.get('ampel')), text),
                              Paragraph(esc(z[2]), text)])
            else:
                daten.append([Paragraph(esc(c), text) for c in z])
        story.append(_tabelle(daten, [64 * mm, 78 * mm, 28 * mm], header=True))
        story.append(Spacer(1, 5))
        p3 = TMP / f'kontrollscan_monat_{ref}.png'
        monat_png(p3, list(e.get('monatsrenditen', {}).items()))
        story.append(Image(str(p3), width=150 * mm, height=45 * mm))
        if e.get('h1_dd_pct_raw') is not None and eng.get('engine_dd_reko') is not None:
            d = e['h1_dd_pct_raw'] - eng['engine_dd_reko']
            if abs(d) > 10.0:
                P(f'Abweichung zum Engine-DD: {de(d, 1, 1, " pp")} — plausible Gründe: andere '
                  'Kapitalbasis, Teilmessung oder Kursfenster.', klein)
    story.append(PageBreak())

    # ------------------------------------------------ 5. Abweichungen
    P('Abweichungen zwischen eigener Prüfung und Engine', h2)
    P('<font color="#C62828"><b>• Grün zweifelhaft</b></font> — Engine GRÜN, aber die eigene '
      'Rechnung findet ein K.o.-Kriterium oder einen RetDD unter der Orientierungsschwelle:', text)
    if gruen_zweifelhaft:
        gz = [['Signal', 'Engine', 'Befund der eigenen Rechnung']]
        for r in gruen_zweifelhaft:
            e = roh[r]
            grund_txt = '; '.join(e['ko_kriterien']) or (
                f"eigener RetDD/Jahr {de(e.get('retdd_jahr_h1'), 2)} unter {de(grund['min_calmar'], 1)}")
            gz.append([Paragraph(esc(_name_ref(r)), text),
                       Paragraph(_ampel_inline((engine.get(r) or {}).get('ampel')), text),
                       Paragraph(esc(grund_txt), text)])
        story.append(_tabelle(gz, [55 * mm, 18 * mm, 97 * mm], header=True))
    else:
        P('keine — alle Engine-GRÜN-Signale bestehen die eigene Prüfung.', klein)
    story.append(Spacer(1, 10))
    P('<font color="#E65100"><b>• Möglicherweise übersehen</b></font> — Engine GELB/GRAU oder '
      'ohne Ampel, aber eigene Rechnung ohne K.o. und mit RetDD über der Orientierungsschwelle:', text)
    if uebersehen:
        ue = [['Signal', 'Engine', 'Eigener RetDD/Jahr', 'Eigener DD %']]
        for r in uebersehen:
            e = roh[r]
            ue.append([Paragraph(esc(_name_ref(r)), text),
                       Paragraph(_ampel_inline((engine.get(r) or {}).get('ampel')), text),
                       de(e['retdd_jahr'], 2), de(e['max_dd_pct'], 1, 100)])
        story.append(_tabelle(ue, [70 * mm, 22 * mm, 40 * mm, 38 * mm], header=True))
    else:
        P('keine', klein)
    story.append(Spacer(1, 10))
    P('<b>H1-Abweichungen über 10 Prozentpunkte</b> (eigene H1-Messung vs. Engine-H1-Messung '
      '— beide inkl. offener Trades; Ursachen: andere Kapitalbasis, Teilmessung, '
      'Kursfenster):', text)
    if dd_abweichungen:
        da = [['Signal', 'Eigener Max-DD', 'Engine-DD', 'Differenz pp']]
        for r, edd, gdd in sorted(dd_abweichungen, key=lambda x: -abs(x[1] - x[2])):
            da.append([Paragraph(esc(_name_ref(r)), text), de(edd, 1), de(gdd, 1), de(edd - gdd, 1)])
        story.append(_tabelle(da, [70 * mm, 32 * mm, 30 * mm, 28 * mm], header=True))
    else:
        P('keine', klein)
    story.append(PageBreak())

    # ------------------------------------------------ 6. Datenqualität
    P('Datenqualität', h2)
    P(f'<b>Daten-/Analysefehler ({len(fehler)}):</b> nicht lesbare Dateien, fehlender '
      'USD-Waehrungsbeleg, SHA-Abweichungen oder andere unvollstaendige Daten — diese '
      'Signale sind in keiner Kennzahl dieses Berichts enthalten.', text)
    if fehler:
        fz = [['Signal', 'Fehler']]
        for r, meldung in list(fehler.items())[:25]:
            fz.append([Paragraph(esc(grund['meta'].get(r, {}).get('name') or f'ref {r}'), text),
                       Paragraph(esc(meldung), klein)])
        story.append(_tabelle(fz, [55 * mm, 115 * mm], header=True))
    story.append(Spacer(1, 8))
    beispiele = ', '.join((e['meta'].get('name') or str(e['ref'])) for e in
                          sorted(unbewertbar_basis,
                                 key=lambda x: -(x['meta'].get('abonnenten') or 0))[:12])
    P(f'<b>Kapitalbasis nicht verwendbar ({len(unbewertbar_basis)}):</b> beispielsweise '
      'nichtpositive bekannte Nettoanfangsbasis oder nichtpositive Basis nach '
      'Vorstartkosten. Fehlende Einzahlungszeilen allein werden durch einen klar '
      'gekennzeichneten Modellpfad behandelt. '
      f'Beispiele (nach Abonnenten): {esc(beispiele)}', text)
    story.append(Spacer(1, 8))
    P(f"<b>Kurze Historie unter 3 Monaten ohne K.o. ({len(kurz_liste)}):</b> "
      + esc(', '.join((e['meta'].get('name') or str(e['ref'])) for e in kurz_liste[:15])), text)
    story.append(Spacer(1, 8))
    P(f'<b>H1-Messung unvollständig ({len(h1_unvollstaendig)}):</b> Kapitalbasis und Trades '
      'reichen für die Prüfung, aber der Max-DD inkl. offener Trades ist mit den '
      'vorhandenen Cache-Kursen nicht belastbar messbar (Status unvollständig/skipped — '
      'Kurslücken, fehlende Symbole, FX-Lücke oder Zeitbasis). Diese Signale sind '
      'bewusst NICHT bewertet: Ohne belastbaren Max-DD hat der RetDD keine Aussagekraft '
      '(Nutzer-Regel 21.10.). Nachmessen über die Equity-DD-Studie oder den '
      'Max-Risiko-Rechner (mit Terminal-Anbindung). '
      + esc(', '.join((e['meta'].get('name') or str(e['ref'])) for e in
                      sorted(h1_unvollstaendig, key=lambda x: -(x['retdd_jahr'] or 0))[:15])), text)
    story.append(Spacer(1, 8))
    n_inaktiv = sum(1 for e in roh.values() if any('inaktiv' in k for k in e['ko_kriterien']))
    n_mart = sum(1 for e in roh.values() if e.get('martingale_flag'))
    n_aus = sum(1 for e in roh.values() if any('Ausschlussliste' in k for k in e['ko_kriterien']))
    P(f'<b>K.o.-Zählung über alle ausgewerteten Signale:</b> Martingale-Signatur {n_mart} · '
      f'inaktiv {n_inaktiv} · Ausschlussliste {n_aus}.', text)
    story.append(PageBreak())

    # ------------------------------------------------ 7. Anhang
    P('Anhang: Formeln und Disclaimer', h2)
    P('<b>Monatsrendite (TWR):</b> Kontoflüsse teilen den Monat in Teilperioden; '
      'Teilrendite = Teilzeit-PnL / Basis am Teilperioden-Start; Monatsfaktor = Produkt '
      'der Teilfaktoren. Leermonate zählen mit Faktor 1 (nicht kürzen).')
    P('<b>Eigener Max-DD:</b> Kurve aus Startkapital + realisierten Netto-Trades + '
      'Kontoflüssen. Peak-Regel: Einzahlung hebt den Peak, Auszahlung senkt ihn mit — '
      'nie unter den Kontostand. DD in Prozent = max((Peak − Equity) / Peak).')
    P('<b>RetDD/Jahr = CAGR / Max-DD (H1-Reko inkl. offener Trades);</b> '
      'RetDD/Monat = geometrische Monatsrendite / Max-DD (H1-Reko). '
      'Jahr = 365,2425 Tage, Monat = Jahr/12. Der Drawdown der geschlossenen Kurve '
      'fließt in KEINE Kennzahl ein (Nutzer-Regel 21.10.: keine Aussagekraft).')
    P('<b>Disclaimer:</b> Dieser Bericht ist eine datengestützte Kontrollauswertung, '
      'keine Anlageberatung und keine Aufforderung zum Kauf oder Abonnement eines '
      'Signals. Historische Renditen sind keine Prognose. H1-Messungen erfassen '
      'Floating-PnL, aber keine vollstaendigen Intrabar-Tiefs. Modellkapital und darauf '
      'bezogene Rendite-/DD-/RetDD-Werte sind Hypothesen, keine nachgewiesenen Kontowerte. '
      'Kopiergebühren, Performance-Entgelte, Slippage und Spread-Differenzen sind nicht '
      'enthalten und können die Effizienz beim Kopieren deutlich mindern.')
    P('Quellen je Kennzahl sind in den Tabellen ausgewiesen: eigene Rechnung (Skript über '
      'Roh-Trades), Engine (Scanner-Forensik), Plattform (Katalog/Selbstauskunft).', klein)

    # ------------------------------------------------ Build
    doc = SimpleDocTemplate(
        str(pdf_pfad), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title='Unabhängiger Kontrollscan MqlKiScanner',
        author='Kontrollscan-Skript (scripts/kontrollscan_bericht.py)',
    )

    def fuss(cv, _doc):
        cv.saveState()
        cv.setFont(FONT, 7.5)
        cv.setFillColor(GRAU)
        cv.drawString(18 * mm, 9 * mm,
                      'Unabhängiger Kontrollscan — eigene Rechnung aus Roh-Trades · keine Anlageberatung')
        cv.drawRightString(A4[0] - 18 * mm, 9 * mm, f'Seite {_doc.page}')
        cv.restoreState()

    doc.build(story, onFirstPage=fuss, onLaterPages=fuss)
    return doc.page
