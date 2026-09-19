"""PDF reports are valid, readable, deterministic, and snapshot-safe."""
from __future__ import annotations

from io import BytesIO

import pytest

from mqlkiscanner import app_ui, pipeline
from mqlkiscanner.pdf_reports import (
    PdfRenderError,
    PdfReport,
    render_report_pdf,
    report_filename,
)

pypdf = pytest.importorskip("pypdf")


def _text(payload: bytes) -> str:
    reader = pypdf.PdfReader(BytesIO(payload))
    assert len(reader.pages) >= 1
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_unicode_markdown_report_is_valid_readable_and_deterministic():
    report = PdfReport(
        kind="trade_analyse",
        signal_id=2342895,
        signal_name="Kira Ähre",
        created_at="2026-09-19 10:15:51",
        model="starkes-modell",
        body=(
            "# Überprüfung der Handelsweise\n\n"
            "Größe, Öl und Schutz müssen **belegt** sein.\n\n"
            "- Erster Befund\n- Zweiter Befund\n\n"
            "| Kennzahl | Wert |\n|---|---:|\n| Drawdown | 12,5 % |"
        ),
    )
    first = render_report_pdf(report)
    second = render_report_pdf(report)
    assert first == second
    assert first.startswith(b"%PDF-") and first.rstrip().endswith(b"%%EOF")
    text = _text(first)
    assert "Zwischenanalyse" in text
    assert "Überprüfung der Handelsweise" in text
    assert "Größe, Öl und Schutz müssen belegt sein." in text
    assert "Drawdown" in text and "12,5 %" in text
    assert "keine Anlageberatung" in text


def test_final_and_portfolio_reports_are_clearly_labeled():
    signal = render_report_pdf(PdfReport(
        "gesamtbericht", "Finaler Signaltext", 42, "Signal", "2026-09-19", "model-2"))
    portfolio = render_report_pdf(PdfReport(
        "portfolio", "Finaler Portfoliotext", created_at="2026-09-19", model="model-2"))
    assert "Finalbericht" in _text(signal)
    assert "Finaler Signaltext" in _text(signal)
    assert "Portfolio-Gesamtbericht" in _text(portfolio)
    assert "Gesamtes Portfolio" in _text(portfolio)
    assert "Finaler Portfoliotext" in _text(portfolio)


def test_empty_or_unknown_reports_fail_explicitly():
    with pytest.raises(PdfRenderError, match="leer"):
        render_report_pdf(PdfReport("gesamtbericht", "  "))
    with pytest.raises(PdfRenderError, match="Unbekannte"):
        render_report_pdf(PdfReport("nicht-vorhanden", "Text"))


def test_safe_filenames_include_kind_id_and_snapshot_identity():
    first = pipeline.ScanResult(
        id=900001, name="Gold / Größe", trades_path=r"C:\snapshots\first.csv",
        gesamtbericht="Erster Bericht")
    second = pipeline.ScanResult(
        id=900001, name="Gold / Größe", trades_path=r"C:\snapshots\second.csv",
        gesamtbericht="Zweiter Bericht")
    _, first_name = app_ui.result_pdf_spec(first, "gesamtbericht")
    _, second_name = app_ui.result_pdf_spec(second, "gesamtbericht")
    assert first_name != second_name
    for filename in (first_name, second_name):
        assert filename.startswith("mqlki-signal-900001-gold-groesse-gesamtbericht-")
        assert filename.endswith(".pdf")
        assert "\\" not in filename and "/" not in filename and " " not in filename
    assert report_filename("portfolio") == "mqlki-portfolio-gesamtbericht.pdf"


def test_portfolio_pdf_specs_do_not_mix_sources():
    archived, archived_name = app_ui.portfolio_pdf_spec({
        "text": "ARCHIVBERICHT", "created_at": "2025-01-01", "model": "alt",
    })
    current, current_name = app_ui.portfolio_pdf_spec({
        "text": "AKTUELLER BERICHT", "created_at": "2026-09-19", "model": "neu",
    })
    assert archived_name == current_name == "mqlki-portfolio-gesamtbericht.pdf"
    assert "ARCHIVBERICHT" in _text(render_report_pdf(archived))
    assert "AKTUELLER BERICHT" not in _text(render_report_pdf(archived))
    assert "AKTUELLER BERICHT" in _text(render_report_pdf(current))
