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
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from . import config, kursdaten, parser
from .equity_studie import studie
from .forensics import drawdown

JAHR_TAGE = 365.2425
MONAT_TAGE = JAHR_TAGE / 12.0

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
    """Eigener DD der geschlossenen Kurve (Nutzer-Regel: Auszahlung senkt den
    Peak, nie unter den Kontostand). Untergrenze — floating fehlt.

    startkapital kommt bereits vom Kapitalbasis-Löser (drawdown.run) und
    enthält die Kontobewegungen BIS zum ersten Trade-Open — hier laufen nur
    noch die SPÄTEREN Kontoflüsse als Ereignisse durch die Kurve (sonst
    wären Einzahlungen doppelt gezählt)."""
    if startkapital is None or startkapital <= 0 or not parsed.trades:
        return None
    erster_open = min(t.open_time for t in parsed.trades)
    events = [(t.close_time, float(t.net), "trade") for t in parsed.trades]
    for b in (getattr(parsed, "balances", None) or []):
        if b.time > erster_open:
            events.append((b.time, float(b.amount), "flow"))
    for c in (getattr(parsed, "costs", None) or []):
        if c.time > erster_open:
            events.append((c.time, float(c.amount), "flow"))
    events.sort(key=lambda e: e[0])
    equity = peak = float(startkapital)
    dd = 0.0
    for _z, delta, art in events:
        if art == "flow":
            equity += delta
            peak = max(equity, peak + delta)
        else:
            equity += delta
            peak = max(peak, equity)
        if peak > 0:
            dd = max(dd, (peak - equity) / peak)
    return dd


# ------------------------------------------------------------- Berechnung


def berechne_csv(pfad, *, startkapital_manuell: float | None = None,
                 name: str = "", broker: str | None = None,
                 progress=None) -> dict:
    """Max-Risiko für eine Trade-CSV (MT5-Positions- oder MT4-Orderbuch-
    Export). Beträge müssen USD sein (Forensik-Basis).

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
    dd = drawdown.run(
        parsed,
        kapitalbasis_usd=float(startkapital_manuell) if startkapital_manuell else None,
        kapitalbasis_quelle="manuell_eingabe" if startkapital_manuell else None,
    )
    startkapital = float(dd.get("startkapital") or 0.0)
    if startkapital <= 0:
        raise RuntimeError(
            "Keine Kapitalbasis belegt: Die CSV enthält keine Einzahlungs-/"
            "Kontobewegungs-Zeilen. Bitte das Startkapital im Formular manuell "
            "eingeben (Forensik-Regel: kein 10.000-USD-Modell).")
    quelle = dd.get("startkapital_quelle") or (
        "manuell_eingabe" if startkapital_manuell else "unbekannt")
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
    }
    daten["statistik"] = statistik(parsed)
    daten["closed_dd_pct"] = closed_dd(parsed, startkapital)
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
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%d.%m.%Y %H:%M")


def kurve_png(pfad: Path, punkte: list, startkapital: float) -> None:
    """Equity/realisiert oben, Unterwasser-Prozent unten (Pillow)."""
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
    y_min = min(alle_werte + [startkapital] if startkapital else alle_werte)
    y_max = max(alle_werte)
    spanne = (y_max - y_min) or 1.0
    ml, mr, mt, mb = 110, 30, 60, 200
    ho = h - mb - 40  # Höhe Oberpanel

    def X(p):
        t0, t1 = punkte[0]["t"], punkte[-1]["t"]
        return ml + (w - ml - mr) * ((p - t0) / (t1 - t0) if t1 > t0 else 0.5)

    def Y_oben(v):
        return mt + (ho - mt - 20) * (1 - (v - y_min) / spanne)

    def Y_unten(v):
        u_max = max([(p.get("_uw") or 0.0) for p in punkte] + [1.0])
        return ho + 40 + 130 * (v / u_max)

    img.line([(ml, mt - 8), (ml, ho), (w - mr, ho)], fill=(90, 90, 90), width=2)
    img.line([(ml, ho + 40), (ml, h - mb + 40), (w - mr, h - mb + 40)], fill=(90, 90, 90), width=2)
    # Startkapital-Linie
    if startkapital and startkapital > 0:
        y0 = Y_oben(startkapital)
        img.line([(ml, y0), (w - mr, y0)], fill=(158, 158, 158), width=1)
        img.text((w - mr - 150, y0 - 22), "Startkapital", font=fk, fill=(120, 120, 120))
    # realisiert (immer vorhanden)
    rl = [(X(p["t"]), Y_oben(p["realisiert"])) for p in punkte if p.get("realisiert") is not None]
    if len(rl) > 1:
        img.line(rl, fill=(176, 190, 197), width=2)
    # Equity (Messpunkte)
    eq = [(X(p["t"]), Y_oben(p["equity"])) for p in mess]
    if len(eq) > 1:
        img.line(eq, fill=(46, 125, 50), width=3)
    # Unterwasser: laufender Peak über Equity-Messpunkte
    peak = None
    for p in punkte:
        uw = 0.0
        if p.get("messpunkt") and p.get("equity") is not None:
            e = p["equity"]
            peak = e if peak is None else max(peak, e)
            if peak > 0:
                uw = (peak - e) / peak
        p["_uw"] = uw
    for p in punkte:
        p["_uw"] = p.get("_uw") or 0.0
    uwp = [(X(p["t"]), Y_unten(p["_uw"])) for p in punkte]
    if len(uwp) > 1:
        img.line(uwp, fill=(198, 40, 40), width=2)
    img.text((ml, 8), "Equity (grün, H1-Messpunkte) und realisiert (grau) · "
                      "unten: Unterwasser-Anteil am laufenden Peak", font=f, fill=(30, 30, 30))
    t0 = _epoch_text(punkte[0]["t"]) if punkte else "—"
    t1 = _epoch_text(punkte[-1]["t"]) if punkte else "—"
    img.text((ml, h - mb + 48), f"{t0} (UTC)  …  {t1} (UTC)", font=fk, fill=(90, 90, 90))
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
        ["Messstatus", f"{daten.get('status')} · "
                       + ("belastbar" if k.get("verlaesslich") else "mit Vorbehalten (Abdeckung/Zeitbasis)")],
        ["Startkapital", f"{_de(k.get('startkapital'), 2, 1, ' USD')} "
                         f"(Quelle: {meta.get('startkapital_quelle') or '—'})"],
        ["Trades / Symbole", f"{st.get('n_trades', k.get('trades_total'))} / "
                             f"{len(st.get('symbole') or daten.get('symbole_mit_kursen') or [])}"],
    ]
    story.append(tabelle([[a, Paragraph(esc(b), text)] for a, b in deck], [55 * mm, 115 * mm]))
    story.append(PageBreak())

    # 2. Ergebnis
    P("Ergebnis — der maximale Drawdown", h2)
    kenn = [
        ["Kennzahl", "Wert"],
        ["Max-DD inkl. offener Trades", _de(k.get("equity_dd_pct"), 2, 1, " %")],
        ["Max-DD in USD", _de(k.get("equity_dd_usd"), 2, 1, " USD")],
        ["Rückfallzeitraum (USD-Maximum)", f"{_epoch_text(k.get('dd_von'))} → {_epoch_text(k.get('dd_bis'))}"],
        ["Relatives Maximum", _de(k.get("dd_pct_max_rel"), 2, 1, " %")
         + f" (ab {_epoch_text(k.get('dd_rel_von'))})"],
        ["Stärkster offener Verlust (floating)", _de(k.get("floating_min_usd"), 2, 1, " USD")
         + f" · {_epoch_text(k.get('floating_min_t'))}"],
        ["Größter offener Gewinn (floating)", _de(k.get("floating_max_usd"), 2, 1, " USD")],
        ["Längste Unterwasser-Phase", _de(k.get("unterwasser_tage_max"), 1, 1, " Tage")],
        ["Kurs-Abdeckung der aktiven Stunden", _de(k.get("abdeckung_pct"), 1, 1, " %")],
        ["Eigener Closed-DD (nur geschlossene Trades)",
         _de(daten.get("closed_dd_pct"), 2, 100, " %") + " — Untergrenze"],
    ]
    story.append(tabelle(kenn, [95 * mm, 75 * mm]))
    if (daten.get("closed_dd_pct") is not None and k.get("equity_dd_pct") is not None
            and k["equity_dd_pct"] - daten["closed_dd_pct"] * 100.0 > 10.0):
        story.append(Spacer(1, 6))
        P('<font color="#C62828"><b>Wichtiger Befund:</b> Die geschlossene Kurve unterschätzt '
          f"das Risiko massiv — Closed-DD {_de(daten['closed_dd_pct'], 1, 100, ' %')} gegenüber "
          f"Max-DD {_de(k.get('equity_dd_pct'), 1, 1, ' %')} inklusive offener Trades.</font>", text)
    story.append(Spacer(1, 6))
    p1 = tmp / "mrr_kurve.png"
    kurve_png(p1, daten.get("punkte") or [], float(k.get("startkapital") or 0.0))
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
                           f"{st.get('erster_trade', '—')[:10]} → {st.get('letzter_trade', '—')[:10]}"],
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
      "nachgebaut: Startkapital + realisierte Netto-Ergebnisse (geschlossene Trades) + offener "
      "Betrag (floating) aller damals offenen Exportpositionen, bewertet zum echten H1-Bar-Schluss "
      "am Bar-Ende je Symbol. Der maximale Rückfall dieser Kurve ist der berichtete Max-DD — im "
      "Gegensatz zum Closed-DD schließt er Verluste ein, die Positionen zwischendurch hatten. "
      "GMT-Versatz je Symbol durch Preisabgleich (Open/Close in der High-Low-Spanne der "
      "getroffenen Bar). Kapitalbasis: Einzahlungs-Zeilen der CSV oder manuelle Eingabe.")
    P("<b>Grenzen:</b> H1-Schlusskurse — Verluste INNERHALB einer Stunde (Intrabar-Tiefs) bleiben "
      "unbekannt, der echte DD kann höher sein. Aktuell offene Positionen fehlen im Export. "
      "Spätere Ein-/Auszahlungen fehlen in der virtuellen Trading-Kurve. Beträge müssen USD sein. "
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
