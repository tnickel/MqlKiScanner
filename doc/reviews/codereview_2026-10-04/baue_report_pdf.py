# -*- coding: utf-8 -*-
"""Baut den PDF-Endreport aus report.md (Report-Route, ReportLab).

Markdown-Teilmenge: #/##/###-Überschriften, Tabellen, Listen, **fett**,
`code`, --- Trenner, Absätze. Emojis/symbole werden typografisch ersetzt
(ReportLab-Standardfonts sind Latin-1). Cover wird separat via
cover_render.py (Template 02) erzeugt und mit pypdf vorangestellt.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (CondPageBreak, KeepTogether, PageBreak,
                                Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

HIER = Path(__file__).resolve().parent
MD = HIER / "report.md"
OUT = HIER / "_body.pdf"

# --- Fonts (Host: Windows; lokal zuerst) ------------------------------------
FONTS = Path("C:/Windows/Fonts")
try:
    pdfmetrics.registerFont(TTFont("Body", str(FONTS / "arial.ttf")))
    pdfmetrics.registerFont(TTFont("BodyB", str(FONTS / "arialbd.ttf")))
    pdfmetrics.registerFont(TTFont("BodyI", str(FONTS / "ariali.ttf")))
    BASE, BOLD, ITAL = "Body", "BodyB", "BodyI"
except Exception:
    BASE = BOLD = ITAL = "Helvetica"

# --- Cascade-Palette (palette.cascade, minimal) -----------------------------
PAGE_BG = colors.HexColor("#f3f3f2")
TABLE_STRIPE = colors.HexColor("#ececea")
HEADER_FILL = colors.HexColor("#574f38")
BORDER = colors.HexColor("#c2bcaa")
ACCENT = colors.HexColor("#26728b")
TEXT_PRIMARY = colors.HexColor("#171615")
TEXT_MUTED = colors.HexColor("#908e87")

# --- Zeichen-Ersatz (Latin-1-sicher) ----------------------------------------
ERSATZ = {
    "🟢": "[GRÜN]", "🟡": "[GELB]", "🔴": "[ROT]", "⚪": "[WEISS]",
    "✔": "OK", "✅": "[x]", "❌": "[ ]", "📌": "FIX ",
    "→": "->", "↔": "<->", "≤": "<=", "≥": ">=", "±": "+/-",
    "−": "-", "–": "-", "—": "-", "„": '"', "·": "-",
    "…": "...", "×": "x", "≈": "~", "Ê": "É", " ": " ",
    "✓": "v", "⚠": "!", "\u00a0": " ",
}


def saeubern(text: str) -> str:
    for k, v in ERSATZ.items():
        if not k:      # leerer Key wuerde JEDES Zeichen umschliessen
            continue
        text = text.replace(k, v)
    # alles, was nach dem Ersatz nicht Latin-1-kodierbar ist, hart ersetzen
    return text.encode("latin-1", "replace").decode("latin-1")


def inline(text: str) -> str:
    text = saeubern(text)
    text = re.sub(r"\*\*(.+?)\*\*", r'<font name="%s">\1</font>' % BOLD, text)
    text = re.sub(r"`(.+?)`", r'<font name="%s" color="#26728b">\1</font>' % ITAL, text)
    return text


STILE = {
    "h1": ParagraphStyle("h1", fontName=BOLD, fontSize=17, leading=22,
                         spaceBefore=14, spaceAfter=8, textColor=TEXT_PRIMARY),
    "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=13.5, leading=18,
                         spaceBefore=12, spaceAfter=6, textColor=HEADER_FILL),
    "h3": ParagraphStyle("h3", fontName=BOLD, fontSize=11.5, leading=15,
                         spaceBefore=10, spaceAfter=4, textColor=TEXT_PRIMARY),
    "p": ParagraphStyle("p", fontName=BASE, fontSize=9.5, leading=12.9,
                        spaceAfter=5, textColor=TEXT_PRIMARY),
    "li": ParagraphStyle("li", fontName=BASE, fontSize=9.5, leading=12.9,
                         leftIndent=14, spaceAfter=3, textColor=TEXT_PRIMARY),
    "td": ParagraphStyle("td", fontName=BASE, fontSize=8.2, leading=10.5,
                         textColor=TEXT_PRIMARY),
    "th": ParagraphStyle("th", fontName=BOLD, fontSize=8.4, leading=11,
                         textColor=colors.white),
    "meta": ParagraphStyle("meta", fontName=ITAL, fontSize=9, leading=12.5,
                           textColor=TEXT_MUTED, spaceAfter=6),
}


def fusszeile(canvas, doc):
    canvas.saveState()
    canvas.setFont(BASE, 7.5)
    canvas.setFillColor(TEXT_MUTED)
    canvas.drawString(20 * mm, 12 * mm,
                      "Gesamtbearbeitungs-Review SIGNALDOWNLOADER - 04.10.2026")
    canvas.drawRightString(190 * mm, 12 * mm, f"Seite {doc.page + 1}")
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.4)
    canvas.line(20 * mm, 15 * mm, 190 * mm, 15 * mm)
    canvas.restoreState()


def tabelle_bauen(zeilen: list[list[str]], verfuegbar: float) -> Table:
    n_spalten = max(len(z) for z in zeilen)
    # Spaltenbreiten nach laengstem Zellinhalt (gekappt), damit Namen wie
    # PelicanWinnerLooser nicht ohne Trennung in Einzelbuchstaben brechen.
    laengen = [max(min(len(z[i]) if i < len(z) else 0 for z in zeilen), 24)
               for i in range(n_spalten)]
    gesamt = sum(laengen) or 1
    colw = [l / gesamt for l in laengen]
    daten = [[Paragraph(inline(z), STILE["th"]) for z in zeilen[0]]]
    for z in zeilen[1:]:
        z = z + [""] * (n_spalten - len(z))
        daten.append([Paragraph(inline(z), STILE["td"]) for z in z])
    t = Table(daten, colWidths=[w * verfuegbar for w in colw],
              repeatRows=1, hAlign="CENTER")
    stil = [("BACKGROUND", (0, 0), (-1, 0), HEADER_FILL),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    for i in range(2, len(daten), 2):
        stil.append(("BACKGROUND", (0, i), (-1, i), TABLE_STRIPE))
    t.setStyle(TableStyle(stil))
    return t


def main() -> int:
    zeilen = MD.read_text(encoding="utf-8").splitlines()
    doc = SimpleDocTemplate(
        str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm,
        title="Gesamtbearbeitungs-Review SIGNALDOWNLOADER - Endreport",
        author="Z.ai")
    verfuegbar = A4[0] - 40 * mm
    story: list = []
    i = 0
    while i < len(zeilen):
        z = zeilen[i]
        if z.startswith("|") and i + 1 < len(zeilen) and set(zeilen[i + 1].replace("|", "").strip()) <= set("-: "):
            block = [z]
            i += 2
            while i < len(zeilen) and zeilen[i].startswith("|"):
                block.append(zeilen[i]); i += 1
            zellen = [[c.strip() for c in r.strip("|").split("|")] for r in block]
            story.append(Spacer(1, 3))
            story.append(tabelle_bauen(zellen, verfuegbar))
            story.append(Spacer(1, 6))
            continue
        if z.startswith("# "):
            story.append(CondPageBreak(80))
            story.append(Paragraph(inline(z[2:]), STILE["h1"]))
        elif z.startswith("## "):
            story.append(CondPageBreak(70))
            story.append(Paragraph(inline(z[3:]), STILE["h2"]))
        elif z.startswith("### "):
            story.append(CondPageBreak(58))
            story.append(Paragraph(inline(z[4:]), STILE["h3"]))
        elif z.strip() == "---":
            story.append(Spacer(1, 4))
        elif re.match(r"^\s*[-*] ", z):
            story.append(Paragraph("&bull; " + inline(re.sub(r"^\s*[-*] ", "", z)),
                                   STILE["li"]))
        elif re.match(r"^\s*\d+\. ", z):
            story.append(Paragraph(inline(z.strip()), STILE["li"]))
        elif z.startswith("**") and z.endswith("**") and z.count("**") == 2:
            story.append(Paragraph(inline(z), STILE["h3"]))
        elif z.startswith("*") and z.endswith("*") and len(z) > 2:
            story.append(Paragraph(inline(z.strip("*")), STILE["meta"]))
        elif z.strip():
            story.append(Paragraph(inline(z), STILE["p"]))
        i += 1
    doc.build(story, onFirstPage=fusszeile, onLaterPages=fusszeile)
    print("Body-PDF:", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
