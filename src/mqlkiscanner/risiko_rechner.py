# -*- coding: utf-8 -*-
"""Max-Risiko-Rechner — maximaler Drawdown inkl. offener Trades für
beliebige Trade-CSVs (Nutzer-Wunsch 21.10.2026).

Eigener App-Punkt: Trades importieren (oder Signal aus der DB wählen),
„maximale Risikoberechnung" anstoßen und nach dem Lauf ein ausführliches
PDF erhalten. Misst mit derselben Produktionsmesstechnik wie die
Equity-DD-Studie (equity_studie.studie: Equity-Kurve auf H1-Raster mit
realisiertem UND offenem floating PnL, Auto-GMT je Symbol, Kursdaten über
das gemeinsame Lauf-Lock und die konfigurierten MetaTrader-Terminals).
Bewertet nichts, schreibt nichts in die Datenbank.
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from . import config, kursdaten, parser
from .equity_studie import studie
from .forensics import drawdown
from .forensics.drawdown_core import max_drawdown_aus_kurve
from . import kapitalbasis
from .studien_anzeigezeit import als_anzeigezeit, zeitachsen_label

JAHR_TAGE = 365.2425
MONAT_TAGE = JAHR_TAGE / 12.0
CLOSED_DD_VERSION = 2  # Prozentvertrag und gemeinsame Flow-/Zeitgruppenregel.

# ------------------------------------------------------------ eigene Zahlen


def statistik(parsed) -> dict:
    """Kompakte Kennzahlen aus den Roh-Trades (ohne Kurse): Netto, Spanne,
    längste Verlustserie, Winrate, Monats-Netto in USD."""
    trades = sorted(parsed.trades, key=lambda t: (t.close_time, t.open_time))
    if not trades:
        return {}
    erster = trades[0].open_time
    letzter = max(t.close_time for t in trades)
    serie = maxi = 0
    gewinne, verluste = [], []
    for t in trades:
        if t.net < 0:
            serie += 1
            maxi = max(maxi, serie)
            verluste.append(t.net)
        else:
            serie = 0
            gewinne.append(t.net)
    monats_netto: dict[str, float] = {}
    for t in trades:
        key = t.close_time.strftime("%Y-%m")
        monats_netto[key] = monats_netto.get(key, 0.0) + float(t.net)
    return {
        "n_trades": len(trades),
        "netto_gesamt": math.fsum(float(t.net) for t in trades),
        "spanne_monate": (letzter - erster).total_seconds() / 86400.0 / MONAT_TAGE,
        "max_verlustserie": maxi,
        "winrate": len(gewinne) / len(trades),
        "avg_gewinn": statistics.fmean(gewinne) if gewinne else None,
        "avg_verlust": statistics.fmean(verluste) if verluste else None,
        "monats_netto": monats_netto,
        "erster_trade": erster.isoformat(),
        "letzter_trade": letzter.isoformat(),
        "symbole": sorted({t.symbol for t in trades if t.symbol}),
    }


def closed_dd(parsed, startkapital: float) -> float | None:
    """Maximaler relativer Closing-DD in PROZENT, nicht als Anteil.

    startkapital kommt bereits vom Kapitalbasis-Löser (drawdown.run) und
    enthält die Kontobewegungen BIS zum ersten Trade-Open — hier laufen nur
    noch die SPÄTEREN Kontoflüsse als Ereignisse durch die Kurve (sonst
    wären Einzahlungen doppelt gezählt). Separate Kosten VOR dem ersten
    Open stecken bereits im Startsaldo; ab dem Open sind sie Ergebnis,
    niemals zu neutralisierende Kapitalflüsse."""
    if startkapital is None or startkapital <= 0 or not parsed.trades:
        return None
    return drawdown.konto_drawdown(parsed, startkapital)["dd_pct_max_rel_raw"]


def closed_dd_prozent(daten: dict) -> float | None:
    """Read current percent values or explicitly adapt pre-v2 session results.

    New outputs always carry percent units. Only old, untagged in-memory
    results used fractions; their conversion lives at this one boundary.
    This does not recalculate or upgrade their historical DD methodology.
    """
    value = daten.get("closed_dd_pct")
    if value is None:
        return None
    unit = daten.get("closed_dd_unit")
    if unit == "percent":
        return value
    if unit is None and daten.get("closed_dd_version", 1) == 1:
        return value * 100.0
    raise ValueError(f"Unbekannte Closing-DD-Einheit: {unit}")


# ------------------------------------------------------------- Berechnung


def berechne_csv(pfad, *, startkapital_manuell: float | None = None,
                 name: str = "", broker: str | None = None,
                 progress=None) -> dict:
    """Max-Risiko für eine Trade-CSV (MT5-Positions- oder MT4-Orderbuch-
    Export). Beträge müssen USD sein (Forensik-Basis).
    startkapital_manuell=None wählt die automatische Kapitalauflösung;
    eine explizite manuelle Eingabe muss positiv und endlich sein.

    Wirft RuntimeError mit klarem Text (Datei unlesbar, keine Kapitalbasis,
    Kurs-Terminal nicht verfügbar bzw. Lauf bereits belegt). Die gemeinsame
    Lauf-Sperre bleibt bis nach dem Terminal-Aufräumen gehalten.
    """
    from .agenten.lock import LockBesetzt, lauf_lock

    def p(anteil, text):
        if progress is not None:
            progress(anteil, text)

    pfad = Path(pfad)
    try:
        with lauf_lock(config.DATA_DIR):
            return _berechne_exklusiv(pfad, startkapital_manuell, name, broker, p)
    except LockBesetzt as exc:
        raise RuntimeError(
            "Ein Scan, eine Studie oder ein Verbindungstest ist bereits aktiv. "
            "Bitte dessen Abschluss abwarten und die Berechnung erneut starten.") from exc


def _berechne_exklusiv(pfad, startkapital_manuell, name, broker, p) -> dict:
    p(0.02, "Trade-Liste laden …")
    parsed = parser.load_export(pfad)
    if not parsed.trades:
        raise RuntimeError("Die Datei enthält keine Trade-Zeilen.")
    p(0.08, "Kapitalbasis ermitteln …")
    entscheid = kapitalbasis.aufloesen(parsed,
        kapitalbasis_usd=startkapital_manuell,
        kapitalbasis_quelle="manuell_eingabe" if startkapital_manuell is not None else None,
        broker=broker or None, kontext={"quelle": "import", "trades_path": str(pfad),
            "trades_sha256": sha256(pfad.read_bytes()).hexdigest()})
    dd = drawdown.run(parsed, kapitalentscheidung=entscheid)
    startkapital = float(dd.get("startkapital_raw", dd.get("startkapital")) or 0.0)
    if not entscheid.get("gueltig") or startkapital <= 0:
        raise RuntimeError(
            "Kapitalbasis nicht verwendbar: " + str(entscheid.get("grund") or "kein positives Startkapital"))
    quelle = dd.get("startkapital_quelle") or (
        "manuell_eingabe" if startkapital_manuell is not None else "unbekannt")
    p(0.10, "Kurs-Terminal verbinden (kann einige Sekunden dauern) …")
    anbieter = kursdaten.KursDaten(config.load_settings())
    try:
        ok, grund = anbieter.starten()
        if not ok:
            raise RuntimeError(f"Kursdaten nicht verfügbar: {grund}")
        daten = studie(
            parsed, anbieter, startkapital, broker=broker or None,
            progress=lambda a, t: p(0.10 + 0.88 * a, t))
    finally:
        anbieter.beenden()
    daten["meta"] = {
        "name": name or pfad.stem,
        "quelle": "import",
        "trades_pfad": str(pfad),
        "datei_sha256": sha256(pfad.read_bytes()).hexdigest(),
        "startkapital_quelle": quelle,
        "broker": broker or None,
        "kapitalbasis_details": dd.get("kapitalbasis_details") or entscheid,
        "kapitalbasis_modell": kapitalbasis.ist_modellquelle(entscheid),
    }
    daten["kapitalbasis_details"] = daten["meta"]["kapitalbasis_details"]
    daten["kapitalbasis_modell"] = daten["meta"]["kapitalbasis_modell"]
    if daten["kapitalbasis_modell"]:
        daten["methodik"] = ("Modellkurve mit geschätztem Startkapital und vorhandenen Kapitalflüssen: "
                             "realisiertes Netto + gelieferte spätere Ein-/Auszahlungen + Floating "
                             "an H1-Bar-Schlüssen; keine belegte Kontokurve")
    daten["statistik"] = statistik(parsed)
    daten["closed_dd_pct"] = dd["trading_dd"]["dd_pct_max_rel_raw"]
    daten["closed_dd_unit"] = "percent"
    daten["closed_dd_version"] = CLOSED_DD_VERSION
    return daten


def berechne_signal(result, progress=None) -> dict:
    """Max-Risiko für ein Signal aus der Datenbank — derselbe Messpfad wie
    die Equity-DD-Studie (inclusive Währungs-/Basis-Prüfung)."""
    from .equity_studie_ui import berechne as studie_berechne

    daten = studie_berechne(result, progress)
    pfad = (daten.get("meta") or {}).get("trades_pfad", "")
    if pfad and Path(pfad).exists():
        parsed = parser.load_export(
            pfad, plattform_positions=getattr(result, "plattform_trades", None))
        daten["statistik"] = statistik(parsed)
        basis = float((daten.get("kennzahlen") or {}).get("startkapital") or 0.0)
        daten["closed_dd_pct"] = closed_dd(parsed, basis)
    else:
        daten["statistik"] = {}
        daten["closed_dd_pct"] = None
    daten["closed_dd_unit"] = "percent"
    daten["closed_dd_version"] = CLOSED_DD_VERSION
    return daten


# ------------------------------------------------------------------ PDF


def _fonts():
    from .pdf_reports import _register_fonts

    _register_fonts()


def _pil_font(size: int, bold: bool = False):
    import reportlab
    from PIL import ImageFont

    d = Path(reportlab.__file__).resolve().parent / "fonts"
    return ImageFont.truetype(str(d / ("VeraBd.ttf" if bold else "Vera.ttf")), size)


def _de(v, nd=2, faktor=1.0, suffix=""):
    if v is None:
        return "—"
    return f"{v * faktor:.{nd}f}".replace(".", ",") + suffix


def _epoch_text(epoch) -> str:
    if not epoch:
        return "—"
    return als_anzeigezeit(epoch).strftime("%d.%m.%Y %H:%M")


def _gitter_stufe(v_min: float, v_max: float, ziel: int) -> float:
    """Runde Achsen-Stufe (1/2/5 × 10^n) mit ~ziel Teilstrichen."""
    roh = ((v_max - v_min) / ziel) if v_max > v_min else 1.0
    mag = 10.0 ** math.floor(math.log10(roh))
    for m in (1, 2, 5, 10):
        if roh <= m * mag:
            return m * mag
    return 10 * mag


def kurve_png(pfad: Path, punkte: list, startkapital: float, *, zeitbasis: dict | None = None) -> None:
    """Equity/realisiert oben, Unterwasser-Prozent unten (Pillow).

    Beschriftete Achsen: oben USD-Stufen, unten Rückgang in Prozent,
    unten Zeit-Ticks im gespeicherten Anzeigeraum. Die Report-Metadaten
    unterscheiden CSV-/Brokerzeit und normalisierte Referenzkurszeit.
    """
    from PIL import Image as PImage
    from PIL import ImageDraw

    w, h = 1400, 760
    basis = PImage.new("RGB", (w, h), "white")
    img = ImageDraw.Draw(basis)
    fk = _pil_font(21)
    f = _pil_font(24, bold=True)
    mess = [p for p in punkte if p.get("messpunkt") and p.get("equity") is not None]
    alle_werte = [p["realisiert"] for p in punkte if p.get("realisiert") is not None]
    alle_werte += [p["equity"] for p in mess]
    if not alle_werte:
        img.text((20, 20), "keine Kurvenpunkte messbar", font=f, fill=(120, 120, 120))
        pfad.parent.mkdir(parents=True, exist_ok=True)
        basis.save(pfad)
        return
    skalenwerte = alle_werte + ([startkapital] if startkapital else [])
    y_min, y_max = min(skalenwerte), max(skalenwerte)
    spanne = (y_max - y_min) or 1.0
    ml, mr, mt = 150, 30, 64
    ho = 510                # Unterkante Oberpanel
    uw_top, uw_hoch = 555, 130  # Unterwasser: 0-%-Linie, Tiefe in px
    uw_bottom = uw_top + uw_hoch

    def X(p):
        t0, t1 = punkte[0]["t"], punkte[-1]["t"]
        return ml + (w - ml - mr) * ((p - t0) / (t1 - t0) if t1 > t0 else 0.5)

    def Y_oben(v):
        return mt + (ho - mt - 20) * (1 - (v - y_min) / spanne)

    def rechts(text, y, farbe=(120, 120, 120)):
        img.text((ml - 10 - img.textlength(text, font=fk), y - 10), text,
                 font=fk, fill=farbe)

    def achse_usd(v):
        if abs(v) >= 1_000_000:
            return _de(v / 1_000_000, 1, 1, " Mio")
        return f"{v:,.0f}".replace(",", ".")

    # ── Oberpanel: Rahmen + USD-Gitter mit Beschriftung ─────────────────
    img.line([(ml, mt - 8), (ml, ho), (w - mr, ho)], fill=(90, 90, 90), width=2)
    step = _gitter_stufe(y_min, y_max, 4)
    stufen = [step * i for i in range(math.floor(y_min / step) + 1,
                                      math.floor(y_max / step) + 1)]
    if len(stufen) < 2:  # winzige Spanne: gleichmässige Fallback-Stufen
        stufen = [y_min + spanne * i / 3 for i in range(4)]
    for i, wert in enumerate(stufen):
        y = Y_oben(wert)
        if i:
            img.line([(ml, y), (w - mr, y)], fill=(228, 228, 228), width=1)
        rechts(achse_usd(wert), y)
    img.text((ml - 10 - img.textlength("USD", font=fk), mt - 34), "USD",
             font=fk, fill=(120, 120, 120))
    # Startkapital-Linie
    if startkapital and startkapital > 0:
        y0 = Y_oben(startkapital)
        img.line([(ml, y0), (w - mr, y0)], fill=(158, 158, 158), width=1)
        text = f"Startkapital {achse_usd(startkapital)}"
        tw = img.textlength(text, font=fk)
        x0 = w - mr - tw - 10
        img.rectangle([x0 - 4, y0 - 28, x0 + tw + 4, y0 - 2], fill="white")
        img.text((x0, y0 - 26), text, font=fk, fill=(120, 120, 120))
    def zeichne_segmente(werte, farbe, breite):
        # None ist eine unbekannte Strecke, kein interpolierter Messwert.
        segment = []

        def zeichne():
            if len(segment) > 1:
                img.line(segment, fill=farbe, width=breite)
            elif segment:
                x, y = segment[0]
                radius = breite / 2
                img.ellipse((x - radius, y - radius, x + radius, y + radius), fill=farbe)

        for wert in werte:
            if wert is None:
                zeichne()
                segment = []
            else:
                segment.append(wert)
        zeichne()

    # Die realisierte Kurve bleibt auch bei fehlenden Floatingkursen bekannt.
    zeichne_segmente(
        [(X(p["t"]), Y_oben(p["realisiert"]))
         if p.get("realisiert") is not None else None for p in punkte],
        (176, 190, 197), 2)
    zeichne_segmente(
        [(X(p["t"]), Y_oben(p["equity"]))
         if p.get("messpunkt") and p.get("equity") is not None else None for p in punkte],
        (46, 125, 50), 3)
    # Derselbe Flow-/Peak-Vertrag wie die ausgewiesenen Studienkennzahlen;
    # fehlende Messpunkte bleiben None. Eingabepunkte werden nicht verändert.
    verlauf = max_drawdown_aus_kurve(
        ((p["t"], p.get("equity"), bool(p.get("messpunkt")), p.get("flow_delta", 0.0))
         for p in punkte), verlauf=True)["verlauf"]
    unterwasser = [wert["dd_pct"] / 100.0 if wert is not None else None for wert in verlauf]
    u_wirklich = max((wert for wert in unterwasser if wert is not None), default=0.0)
    u_max = u_wirklich or 1.0  # nur Divisions-Basis, falls nie unter Wasser

    def Y_unten(v):
        return uw_top + uw_hoch * (v / u_max)

    # ── Unterpanel: 0-%-Linie, Tiefpunkt, Rahmen ────────────────────────
    img.line([(ml, uw_top), (w - mr, uw_top)], fill=(228, 228, 228), width=1)
    img.line([(ml, uw_top), (ml, uw_bottom), (w - mr, uw_bottom)],
             fill=(90, 90, 90), width=2)
    rechts("0 %", uw_top)
    if u_wirklich > 0:
        rechts(f"\u2212{_de(u_max * 100, 1, 1, ' %')}", uw_bottom)
    zeichne_segmente(
        [(X(p["t"]), Y_unten(wert)) if wert is not None else None
         for p, wert in zip(punkte, unterwasser)],
        (198, 40, 40), 2)
    img.text((ml, 8), "H1-Equity (grün), realisiert (grau); unten: Rückgang vom Hochpunkt",
             font=f, fill=(30, 30, 30))
    # X-Achse im Report-Zeitraum, ohne nachtraegliche Zeitverschiebung.
    t0, t1 = punkte[0]["t"], punkte[-1]["t"]
    tage = (t1 - t0) / 86400 if t1 > t0 else 0.0
    fmt = "%m.%Y" if tage >= 730 else ("%d.%m.%Y" if tage >= 90 else "%d.%m. %H:%M")
    ticks = [t0 + (t1 - t0) * i / 4 for i in range(5)] if t1 > t0 else [t0]
    for i, t in enumerate(ticks):
        x = X(t)
        img.line([(x, uw_bottom), (x, uw_bottom + 6)], fill=(90, 90, 90), width=1)
        text = als_anzeigezeit(t).strftime(fmt)
        links, _, rechts_rand, _ = img.textbbox((0, 0), text, font=fk)
        text_x = max(4 - links, min(w - 4 - rechts_rand,
                                   x - img.textlength(text, font=fk) / 2))
        img.text((text_x, uw_bottom + 12), text,
                 font=fk, fill=(90, 90, 90))
    img.text((ml, uw_bottom + 47), zeitachsen_label({"zeitbasis": zeitbasis}),
             font=fk, fill=(90, 90, 90))
    pfad.parent.mkdir(parents=True, exist_ok=True)
    basis.save(pfad)


def monate_png(pfad: Path, monats_netto: dict) -> None:
    from PIL import Image as PImage
    from PIL import ImageDraw

    w, h = 1200, 330
    basis = PImage.new("RGB", (w, h), "white")
    img = ImageDraw.Draw(basis)
    fk = _pil_font(20)
    if not monats_netto:
        img.text((10, 10), "keine Monatswerte", font=fk, fill=(120, 120, 120))
        pfad.parent.mkdir(parents=True, exist_ok=True)
        basis.save(pfad)
        return
    ymax = max([abs(v) for v in monats_netto.values()] + [1.0])
    bw = (w - 40) / len(monats_netto)
    null = h / 2
    img.line([(20, null), (w - 10, null)], fill=(150, 150, 150), width=2)
    for i, (key, v) in enumerate(sorted(monats_netto.items())):
        bh = (h / 2 - 36) * abs(v) / ymax
        x0 = 25 + i * bw
        if v >= 0:
            img.rectangle([x0, null - bh, x0 + bw - 3, null], fill=(46, 125, 50))
        else:
            img.rectangle([x0, null, x0 + bw - 3, null + bh], fill=(198, 40, 40))
    img.text((25, 4), f"Monats-Netto USD — {min(monats_netto)} bis {max(monats_netto)}",
             font=fk, fill=(60, 60, 60))
    img.text((25, h - 26), f"Skala ±{_de(ymax, 0, 1, ' USD')}", font=fk, fill=(120, 120, 120))
    pfad.parent.mkdir(parents=True, exist_ok=True)
    basis.save(pfad)


def baue_pdf(daten: dict, ziel: Path | None = None) -> tuple[Path, int]:
    """Ausführlichen PDF-Bericht erzeugen. Rückgabe (Pfad, Seitenzahl)."""
    import html
    closing_pct = closed_dd_prozent(daten)

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    _fonts()
    FONT, FONT_BOLD = "MKS-Vera", "MKS-Vera-Bold"
    GRAU = colors.HexColor("#616161")
    text = ParagraphStyle("p", fontName=FONT, fontSize=9.5, leading=13.5)
    klein = ParagraphStyle("k", fontName=FONT, fontSize=8.3, leading=11.5, textColor=GRAU)
    h2 = ParagraphStyle("h2", fontName=FONT_BOLD, fontSize=13, leading=17,
                        spaceBefore=10, spaceAfter=4)
    titel = ParagraphStyle("t", fontName=FONT_BOLD, fontSize=20, leading=25)

    meta = daten.get("meta") or {}
    k = daten.get("kennzahlen") or {}
    st = daten.get("statistik") or {}
    esc = lambda s: html.escape(str(s), quote=False)  # noqa: E731
    heute = datetime.now()
    ziel = ziel or (config.DATA_DIR / "reports" /
                    f"max_risiko_{heute.date().isoformat()}_"
                    f"{(meta.get('name') or 'bericht').replace(' ', '_')[:40]}.pdf")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(config.DATA_DIR).resolve().parent / ".tmp"
    story = []

    def P(s, stil=None):
        story.append(Paragraph(s, stil or text))

    def tabelle(zeilen, breiten, font=8.6):
        t = Table(zeilen, colWidths=breiten, repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT),
            ("FONTSIZE", (0, 0), (-1, -1), font),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BDBDBD")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ECEFF1")),
        ]))
        return t

    # 1. Deckblatt
    P("Maximale Risikoberechnung", titel)
    P("Maximaler Drawdown inklusive offener (floating) Trades — aus echten H1-Kursen nachgemessen",
      ParagraphStyle("u", fontName=FONT, fontSize=11, leading=15, textColor=GRAU))
    story.append(Spacer(1, 8))
    deck = [
        ["Bezeichnung", meta.get("name") or "—"],
        ["Quelle", "importierte Trade-CSV" if meta.get("quelle") == "import" else "Signal aus der Datenbank"],
        ["Trade-Datei", Path(meta.get("trades_pfad") or "—").name],
        ["Datei-SHA256", (meta.get("datei_sha256") or "—")[:32] + " …"],
        ["Erstellt", heute.strftime("%d.%m.%Y %H:%M")],
        ["Kurs-/Zeitbasis", f"{daten.get('status')} · "
                       + ("belastbar" if k.get("verlaesslich") else "mit Vorbehalten (Abdeckung/Zeitbasis)")],
        ["Zeitbasis der Kurve", zeitachsen_label(daten)],
        ["Startkapital", f"{_de(k.get('startkapital'), 2, 1, ' USD')} "
                         f"({kapitalbasis.beschreibung(meta.get('kapitalbasis_details') or meta.get('startkapital_quelle'))})"],
        ["Trades / Symbole", f"{st.get('n_trades', k.get('trades_total'))} / "
                             f"{len(st.get('symbole') or daten.get('symbole_mit_kursen') or [])}"],
    ]
    capital_details = meta.get("kapitalbasis_details") or daten.get("kapitalbasis_details") or {}
    if kapitalbasis.ist_modellquelle(capital_details or meta.get("startkapital_quelle")):
        deck.append(["Kapitalmodell", "Virtuelle Modellstudie: Prozent-DD und Renditen beruhen auf "
                     "geschätztem Startkapital; keine nachgewiesenen Kontokennzahlen."])
    if capital_details:
        deck.append(["Unsicherheit", str(capital_details.get("unsicherheit") or "nicht angegeben")])
        deck.append(["Kapitalbeleg", str(capital_details.get("beleg") or "nicht angegeben")])
    story.append(tabelle([[a, Paragraph(esc(b), text)] for a, b in deck], [55 * mm, 115 * mm]))
    story.append(PageBreak())

    # 2. Ergebnis
    P("Ergebnis — der maximale Drawdown", h2)
    kenn = [
        ["Kennzahl", "Wert"],
        ["Max-DD inkl. offener Trades", _de(k.get("equity_dd_pct"), 2, 1, " %")],
        ["Max-DD in USD", _de(k.get("equity_dd_usd"), 2, 1, " USD")],
        ["Rückfallzeitraum (USD-Maximum)", f"{_epoch_text(k.get('dd_von'))} bis {_epoch_text(k.get('dd_bis'))}"],
        ["Relatives Maximum", _de(k.get("dd_pct_max_rel"), 2, 1, " %")
         + f" (ab {_epoch_text(k.get('dd_rel_von'))})"],
        ["Stärkster offener Verlust (floating)", _de(k.get("floating_min_usd"), 2, 1, " USD")
         + f" · {_epoch_text(k.get('floating_min_t'))}"],
        ["Größter offener Gewinn (floating)", _de(k.get("floating_max_usd"), 2, 1, " USD")],
        ["Längste Unterwasser-Phase", _de(k.get("unterwasser_tage_max"), 1, 1, " Tage")],
        ["Kurs-Abdeckung der aktiven Stunden", _de(k.get("abdeckung_pct"), 1, 1, " %")],
        ["Eigener Closed-DD (nur geschlossene Trades)",
         _de(closing_pct, 2, 1, " %") + " — Untergrenze"],
    ]
    story.append(tabelle(kenn, [95 * mm, 75 * mm]))
    if closing_pct is not None and daten.get("closed_dd_version", 1) < CLOSED_DD_VERSION:
        P("Closed-DD aus einer älteren Berechnung; neue Berechnungen verwenden die gemeinsame Drawdown-Methodik.", text)
    if (closing_pct is not None and k.get("equity_dd_pct") is not None
            and k["equity_dd_pct"] - closing_pct > 10.0):
        story.append(Spacer(1, 6))
        P('<font color="#C62828"><b>Wichtiger Befund:</b> Die geschlossene Kurve unterschätzt '
          f"das Risiko massiv — Closed-DD {_de(closing_pct, 1, 1, ' %')} gegenüber "
          f"Max-DD {_de(k.get('equity_dd_pct'), 1, 1, ' %')} inklusive offener Trades.</font>", text)
    story.append(Spacer(1, 6))
    p1 = tmp / "mrr_kurve.png"
    kurve_png(p1, daten.get("punkte") or [], float(k.get("startkapital") or 0.0),
              zeitbasis=daten.get("zeitbasis"))
    story.append(Image(str(p1), width=170 * mm, height=92 * mm))
    story.append(Spacer(1, 8))
    p2 = tmp / "mrr_monate.png"
    monate_png(p2, st.get("monats_netto") or {})
    story.append(Image(str(p2), width=150 * mm, height=41 * mm))
    story.append(PageBreak())

    # 3. eigene Statistik
    P("Trade-Statistik (eigene Rechnung aus der CSV)", h2)
    if st:
        stat = [
            ["Kennzahl", "Wert"],
            ["Netto-PnL gesamt", _de(st.get("netto_gesamt"), 2, 1, " USD")],
            ["Zeitspanne", f"{_de(st.get('spanne_monate'), 1, 1, ' Monate')} · "
                           f"{st.get('erster_trade', '—')[:10]} bis {st.get('letzter_trade', '—')[:10]}"],
            ["Anzahl Trades", str(st.get("n_trades"))],
            ["Winrate", _de(st.get("winrate"), 1, 100, " %")],
            ["längste Verlustserie", f"{st.get('max_verlustserie')} Trades"],
            ["Ø Gewinn / Ø Verlust", f"{_de(st.get('avg_gewinn'), 2, 1, ' USD')} / "
                                      f"{_de(st.get('avg_verlust'), 2, 1, ' USD')}"],
            ["Symbole", ", ".join((st.get("symbole") or [])[:12])]
        ]
        story.append(tabelle(stat, [70 * mm, 100 * mm]))
    else:
        P("—", klein)
    story.append(Spacer(1, 10))

    # 4. Symbol-Diagnose
    P("Symbol-Diagnose — GMT-Versatz und Kursqualität", h2)
    befunde = daten.get("symbole") or []
    if befunde:
        zeilen = [["Symbol", "GMT-Versatz", "Trefferquote", "Status"]]
        for b in befunde:
            zeilen.append([
                Paragraph(esc(b.get("symbol")), text),
                _de(b.get("gmt_h"), 0, 1, " h"),
                _de(b.get("trefferquote"), 0, 100, " %") if b.get("trefferquote") is not None else "—",
                esc(b.get("status") or "—"),
            ])
        story.append(tabelle(zeilen, [45 * mm, 30 * mm, 35 * mm, 60 * mm]))
    else:
        P("keine Symbol-Befunde", klein)
    ohne_kurse = daten.get("symbole_ohne_kurse") or []
    ohne_kontrakt = daten.get("symbole_ohne_kontrakt") or []
    if ohne_kurse or ohne_kontrakt:
        story.append(Spacer(1, 6))
        if ohne_kurse:
            P("<b>Ohne Kurse</b> (floating dieser Symbole bleibt unbekannt, DD kann unterschätzt "
              f"sein): {esc(', '.join(map(str, ohne_kurse)))}", text)
        if ohne_kontrakt:
            P(f"<b>Ohne belegte Kontraktgröße</b>: {esc(', '.join(map(str, ohne_kontrakt)))}", text)
    if k.get("fx_luecke"):
        P('<font color="#C62828">FX-Umrechnungslücke — Messung gilt als unvollständig.</font>', text)
    story.append(PageBreak())

    # 5. Methodik + Disclaimer
    P("Methodik, Grenzen, Disclaimer", h2)
    P("<b>Messung:</b> Für jede Stunde der Export-Historie wird eine virtuelle Trading-Equity "
      "nachgebaut: Startkapital + realisierte Netto-Ergebnisse (geschlossene Trades) "
      "+ gelieferte spätere Ein-/Auszahlungen + offener "
      "Betrag (floating) aller damals offenen Exportpositionen, bewertet zum echten H1-Bar-Schluss "
      "am Bar-Ende je Symbol. Der maximale Rückfall dieser Kurve ist der berichtete Max-DD — im "
      "Gegensatz zum Closed-DD schließt er Verluste ein, die Positionen zwischendurch hatten. "
      "GMT-Versatz je Symbol durch Preisabgleich (Open/Close in der High-Low-Spanne der "
      "getroffenen Bar). Kapitalbasis: belegte Einzahlungen oder explizite Basis, sonst gemeinsame "
      "Lotschätzung, grobe Lotschätzung oder gekennzeichneter 10.000-USD-Fallback. "
      "Bekannte spätere Ein-/Auszahlungen bleiben in der Kontokurve erhalten.")
    P("<b>Grenzen:</b> H1-Schlusskurse — Verluste INNERHALB einer Stunde (Intrabar-Tiefs) bleiben "
      "unbekannt, der echte DD kann höher sein. Aktuell offene Positionen fehlen im Export. "
      "Eine geschätzte Kapitalbasis bleibt eine Modellannahme. Beträge müssen USD sein. "
      "Kopiergebühren, Slippage und Spread-Differenzen sind nicht enthalten. Diese Berechnung "
      "bewertet nichts — Ampel und Urteil der Engine bleiben unberührt.")
    P("<b>Disclaimer:</b> Datengestützte Kontrollauswertung, keine Anlageberatung. Historische "
      "Werte sind keine Prognose.", klein)

    doc = SimpleDocTemplate(
        str(ziel), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title="Maximale Risikoberechnung", author="MqlKiScanner Max-Risiko-Rechner")

    def fuss(cv, d):
        cv.saveState()
        cv.setFont(FONT, 7.5)
        cv.setFillColor(GRAU)
        cv.drawString(18 * mm, 9 * mm, "Max-Risiko-Rechner — H1-Messung inkl. offener Trades · keine Anlageberatung")
        cv.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Seite {d.page}")
        cv.restoreState()

    doc.build(story, onFirstPage=fuss, onLaterPages=fuss)
    return ziel, doc.page
