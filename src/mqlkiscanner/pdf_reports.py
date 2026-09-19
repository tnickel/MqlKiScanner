"""Deterministic, on-demand PDF rendering for stored analysis texts."""
from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from threading import Lock

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

REPORT_TITLES = {
    "trade_analyse": "Trade-Analyse",
    "risiko_analyse": "Risiko-Analyse",
    "gesamtbericht": "Gesamtbericht",
    "portfolio": "Portfolio-Gesamtbericht",
}
INTERMEDIATE_KINDS = {"trade_analyse", "risiko_analyse"}

DISCLAIMER = (
    "Forensische Auswertung historischer Daten; keine Anlageberatung. "
    "Fehlende Evidenz ist keine Entwarnung. Risiko hat Vorrang vor Ertrag."
)
INTERMEDIATE_NOTE = (
    "Zwischenanalyse: Dieser Text ist ein Baustein der Gesamtbewertung und "
    "kein abschließendes Signalurteil."
)

_FONT_REGULAR = "MKS-Vera"
_FONT_BOLD = "MKS-Vera-Bold"
_FONT_ITALIC = "MKS-Vera-Italic"
_FONT_BOLD_ITALIC = "MKS-Vera-BoldItalic"
_FONTS_REGISTERED = False
_FONT_LOCK = Lock()


class PdfRenderError(RuntimeError):
    """Raised when a real, valid report PDF cannot be produced."""


@dataclass(frozen=True)
class PdfReport:
    """All non-secret inputs needed to render one stored report."""

    kind: str
    body: str
    signal_id: int | None = None
    signal_name: str = ""
    created_at: str | None = None
    model: str | None = None


def _register_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    with _FONT_LOCK:
        if _FONTS_REGISTERED:
            return
        font_dir = Path(reportlab.__file__).resolve().parent / "fonts"
        files = {
            _FONT_REGULAR: "Vera.ttf",
            _FONT_BOLD: "VeraBd.ttf",
            _FONT_ITALIC: "VeraIt.ttf",
            _FONT_BOLD_ITALIC: "VeraBI.ttf",
        }
        try:
            for name, filename in files.items():
                path = font_dir / filename
                if not path.is_file():
                    raise FileNotFoundError(f"Unicode-Schrift fehlt: {path}")
                pdfmetrics.registerFont(TTFont(name, str(path)))
            pdfmetrics.registerFontFamily(
                "MKS-Vera",
                normal=_FONT_REGULAR,
                bold=_FONT_BOLD,
                italic=_FONT_ITALIC,
                boldItalic=_FONT_BOLD_ITALIC,
            )
        except Exception as exc:
            raise PdfRenderError(f"Unicode-Schrift konnte nicht geladen werden: {exc}") from exc
        _FONTS_REGISTERED = True


def _slug(value: str, fallback: str) -> str:
    value = value.translate(str.maketrans({
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
    }))
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return (cleaned[:48] or fallback).strip("-")


def snapshot_token(*identity_parts: object) -> str:
    """Return a stable short token so equal IDs from distinct snapshots stay distinct."""
    joined = "\x1f".join("" if part is None else str(part) for part in identity_parts)
    return sha256(joined.encode("utf-8")).hexdigest()[:10]


def report_filename(
    kind: str,
    *,
    signal_id: int | None = None,
    signal_name: str = "",
    snapshot: str = "",
) -> str:
    """Build a safe, descriptive filename for a report PDF."""
    if kind not in REPORT_TITLES:
        raise ValueError(f"Unbekannte Berichtsart: {kind}")
    kind_slug = _slug(REPORT_TITLES[kind], "bericht")
    if kind == "portfolio":
        return f"mqlki-{kind_slug}.pdf"
    signal_part = f"signal-{signal_id}" if signal_id is not None else "signal"
    name_part = f"-{_slug(signal_name, 'unbenannt')}" if signal_name else ""
    snapshot_part = f"-{_slug(snapshot, 'snapshot')[:16]}" if snapshot else ""
    return f"mqlki-{signal_part}{name_part}-{kind_slug}{snapshot_part}.pdf"


def _font_safe(text: str) -> str:
    replacements = {
        "🟢": "[GRÜN]", "🟡": "[GELB]", "🔴": "[ROT]", "⚪": "[OFFEN]",
        "⛔": "[AUSSCHLUSS]", "✅": "[OK]", "❌": "[FEHLER]", "⚠": "[WARNUNG]",
    }
    for symbol, replacement in replacements.items():
        text = text.replace(symbol, replacement)
    text = text.replace("\ufe0f", "")
    text = re.sub(r":material/([a-z0-9_]+):", lambda match: f"[{match.group(1)}]", text)
    glyphs = pdfmetrics.getFont(_FONT_REGULAR).face.charToGlyph
    return "".join(
        character if character in "\n\t" or ord(character) in glyphs else "?"
        for character in text
    )


def _inline(text: str) -> str:
    """Escape untrusted report text, then restore a small safe Markdown subset."""
    value = html.escape(_font_safe(text.strip()), quote=False)
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"__([^_]+)__", r"<b>\1</b>", value)
    value = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", value)
    value = re.sub(r"`([^`]+)`", r"<font name='MKS-Vera'>\1</font>", value)
    return value


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "MKSReportTitle", parent=sample["Title"], fontName=_FONT_BOLD,
            fontSize=22, leading=27, textColor=colors.HexColor("#183642"),
            alignment=TA_LEFT, spaceAfter=5 * mm,
        ),
        "label": ParagraphStyle(
            "MKSReportLabel", parent=sample["Normal"], fontName=_FONT_BOLD,
            fontSize=9, leading=12, textColor=colors.HexColor("#087E8B"),
            spaceAfter=2 * mm,
        ),
        "meta": ParagraphStyle(
            "MKSReportMeta", parent=sample["Normal"], fontName=_FONT_REGULAR,
            fontSize=9, leading=13, textColor=colors.HexColor("#455A64"),
        ),
        "notice": ParagraphStyle(
            "MKSReportNotice", parent=sample["Normal"], fontName=_FONT_REGULAR,
            fontSize=9, leading=13, leftIndent=4 * mm, rightIndent=4 * mm,
            borderColor=colors.HexColor("#D5A021"), borderWidth=0.6,
            borderPadding=7, backColor=colors.HexColor("#FFF8E7"),
            textColor=colors.HexColor("#493A16"),
        ),
        "h1": ParagraphStyle(
            "MKSReportH1", parent=sample["Heading1"], fontName=_FONT_BOLD,
            fontSize=16, leading=20, textColor=colors.HexColor("#183642"),
            spaceBefore=5 * mm, spaceAfter=2 * mm,
        ),
        "h2": ParagraphStyle(
            "MKSReportH2", parent=sample["Heading2"], fontName=_FONT_BOLD,
            fontSize=13, leading=17, textColor=colors.HexColor("#087E8B"),
            spaceBefore=4 * mm, spaceAfter=1.5 * mm,
        ),
        "h3": ParagraphStyle(
            "MKSReportH3", parent=sample["Heading3"], fontName=_FONT_BOLD,
            fontSize=11, leading=15, textColor=colors.HexColor("#183642"),
            spaceBefore=3 * mm, spaceAfter=1 * mm,
        ),
        "body": ParagraphStyle(
            "MKSReportBody", parent=sample["BodyText"], fontName=_FONT_REGULAR,
            fontSize=9.5, leading=14, textColor=colors.HexColor("#263238"),
            spaceAfter=2.5 * mm,
        ),
        "quote": ParagraphStyle(
            "MKSReportQuote", parent=sample["BodyText"], fontName=_FONT_ITALIC,
            fontSize=9.5, leading=14, leftIndent=5 * mm,
            borderColor=colors.HexColor("#80CBC4"), borderWidth=0,
            borderLeftWidth=2, borderPadding=5, textColor=colors.HexColor("#37474F"),
        ),
        "code": ParagraphStyle(
            "MKSReportCode", parent=sample["Code"], fontName=_FONT_REGULAR,
            fontSize=8, leading=11, leftIndent=3 * mm, rightIndent=3 * mm,
            borderPadding=5, backColor=colors.HexColor("#F1F5F6"),
            textColor=colors.HexColor("#263238"),
        ),
        "table": ParagraphStyle(
            "MKSReportTable", parent=sample["BodyText"], fontName=_FONT_REGULAR,
            fontSize=7.5, leading=10, textColor=colors.HexColor("#263238"),
        ),
        "table_head": ParagraphStyle(
            "MKSReportTableHead", parent=sample["BodyText"], fontName=_FONT_BOLD,
            fontSize=7.5, leading=10, textColor=colors.white, alignment=TA_CENTER,
        ),
    }


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_table_separator(line: str) -> bool:
    cells = _table_cells(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _markdown_story(body: str, styles: dict[str, ParagraphStyle], width: float) -> list:
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    story: list = []
    paragraph: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            story.append(Paragraph(_inline(" ".join(paragraph)), styles["body"]))
            paragraph.clear()

    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            index += 1
            continue
        if stripped.startswith("```"):
            flush_paragraph()
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            code = "<br/>".join(
                html.escape(_font_safe(item), quote=False) or " " for item in code_lines)
            story.append(Paragraph(code, styles["code"]))
            index += 1
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            level = min(len(heading.group(1)), 3)
            story.append(Paragraph(_inline(heading.group(2)), styles[f"h{level}"]))
            index += 1
            continue
        if "|" in stripped and index + 1 < len(lines) and _is_table_separator(lines[index + 1]):
            flush_paragraph()
            raw_rows = [_table_cells(stripped)]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                raw_rows.append(_table_cells(lines[index]))
                index += 1
            column_count = max(len(row) for row in raw_rows)
            data = []
            for row_number, row in enumerate(raw_rows):
                style = styles["table_head"] if row_number == 0 else styles["table"]
                padded = row + [""] * (column_count - len(row))
                data.append([Paragraph(_inline(cell), style) for cell in padded])
            table = Table(data, colWidths=[width / column_count] * column_count, repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#087E8B")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B0BEC5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#F5F8F9")]),
            ]))
            story.extend([table, Spacer(1, 3 * mm)])
            continue
        bullet = re.match(r"^[-*+]\s+(.+)$", stripped)
        numbered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if bullet or numbered:
            flush_paragraph()
            items: list[ListItem] = []
            ordered = bool(numbered)
            pattern = r"^\d+[.)]\s+(.+)$" if ordered else r"^[-*+]\s+(.+)$"
            while index < len(lines):
                match = re.match(pattern, lines[index].strip())
                if not match:
                    break
                items.append(ListItem(Paragraph(_inline(match.group(1)), styles["body"])))
                index += 1
            story.append(ListFlowable(
                items, bulletType="1" if ordered else "bullet",
                start="1", leftIndent=5 * mm, bulletFontName=_FONT_REGULAR,
                bulletFontSize=8,
            ))
            story.append(Spacer(1, 1.5 * mm))
            continue
        if stripped.startswith(">"):
            flush_paragraph()
            story.append(Paragraph(_inline(stripped.lstrip("> ")), styles["quote"]))
            index += 1
            continue
        if re.fullmatch(r"[-*_]{3,}", stripped):
            flush_paragraph()
            story.append(HRFlowable(width="100%", thickness=0.5,
                                    color=colors.HexColor("#B0BEC5")))
            index += 1
            continue
        if stripped == r"\pagebreak":
            flush_paragraph()
            story.append(PageBreak())
            index += 1
            continue
        paragraph.append(stripped)
        index += 1
    flush_paragraph()
    return story


def _canvas(*args, **kwargs) -> Canvas:
    """Invariant mode keeps equivalent inputs byte-for-byte reproducible."""
    kwargs["invariant"] = 1
    return Canvas(*args, **kwargs)


def render_report_pdf(report: PdfReport) -> bytes:
    """Render a stored report as a valid PDF without any LLM or network call."""
    if report.kind not in REPORT_TITLES:
        raise PdfRenderError(f"Unbekannte Berichtsart: {report.kind}")
    if not isinstance(report.body, str) or not report.body.strip():
        raise PdfRenderError("Ein leerer Bericht kann nicht als PDF erzeugt werden.")
    _register_fonts()
    styles = _styles()
    title = REPORT_TITLES[report.kind]
    final = report.kind not in INTERMEDIATE_KINDS
    classification = "Finalbericht" if final else "Zwischenanalyse"
    identity = (
        f"{report.signal_name or 'Signal'} (#{report.signal_id})"
        if report.signal_id is not None else "Gesamtes Portfolio"
    )
    metadata = [
        ["Berichtstyp", f"{classification} · {title}"],
        ["Bezug", identity],
        ["Erstellt", report.created_at or "nicht verfügbar"],
        ["Modell", report.model or "nicht verfügbar"],
    ]
    buffer = BytesIO()
    page_width, _ = A4
    left = right = 19 * mm
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{title} – {identity}",
        author="MqlKiScanner",
        subject=f"{classification}: forensische MQL5-Auswertung",
    )
    usable_width = page_width - left - right
    meta_table = Table(
        [[Paragraph(f"<b>{html.escape(label)}</b>", styles["meta"]),
          Paragraph(html.escape(_font_safe(str(value))), styles["meta"])]
         for label, value in metadata],
        colWidths=[28 * mm, usable_width - 28 * mm],
    )
    meta_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.HexColor("#CFD8DC")),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story = [
        Paragraph(classification.upper(), styles["label"]),
        Paragraph(html.escape(title), styles["title"]),
        meta_table,
        Spacer(1, 5 * mm),
        Paragraph(INTERMEDIATE_NOTE if not final else DISCLAIMER, styles["notice"]),
        Spacer(1, 5 * mm),
    ]
    if not final:
        story.append(Paragraph(DISCLAIMER, styles["meta"]))
        story.append(Spacer(1, 3 * mm))
    story.extend(_markdown_story(report.body, styles, usable_width))

    def footer(canvas: Canvas, document) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#CFD8DC"))
        canvas.line(left, 12 * mm, page_width - right, 12 * mm)
        canvas.setFillColor(colors.HexColor("#607D8B"))
        canvas.setFont(_FONT_REGULAR, 7.5)
        canvas.drawString(left, 8 * mm, "MqlKiScanner · Forensische Risiko-Analyse")
        canvas.drawRightString(page_width - right, 8 * mm, f"Seite {document.page}")
        canvas.restoreState()

    try:
        doc.build(story, onFirstPage=footer, onLaterPages=footer, canvasmaker=_canvas)
        payload = buffer.getvalue()
    except PdfRenderError:
        raise
    except Exception as exc:
        raise PdfRenderError(f"PDF-Erzeugung fehlgeschlagen: {exc}") from exc
    if not payload.startswith(b"%PDF-") or b"%%EOF" not in payload[-1024:]:
        raise PdfRenderError("PDF-Erzeugung lieferte kein gültiges PDF-Dokument.")
    return payload
