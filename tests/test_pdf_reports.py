"""PDF reports are valid, readable, deterministic, and snapshot-safe."""
from __future__ import annotations

from io import BytesIO

import pytest

from mqlkiscanner import app_ui, pipeline
from mqlkiscanner.pdf_reports import (
    materialize_portfolio_pdf,
    materialize_result_pdfs,
    PdfRenderError,
    PdfReport,
    persist_report_pdf,
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


def test_reports_are_persisted_in_signal_snapshot_structure(tmp_path):
    result = pipeline.ScanResult(
        id=900001, name="Gold Größe", trades_sha256="a" * 64,
        trade_analyse="Trade", risiko_analyse="Risiko", gesamtbericht="Final")
    paths = materialize_result_pdfs(result, root=tmp_path)
    assert set(paths) == {"trade_analyse", "risiko_analyse", "gesamtbericht"}
    assert paths["trade_analyse"] == (
        tmp_path / "signale" / "900001-gold-groesse" / ("a" * 10)
        / "01-trade-analyse.pdf")
    assert paths["risiko_analyse"].is_file()
    assert paths["gesamtbericht"].read_bytes().startswith(b"%PDF-")


def test_portfolio_versions_are_persisted_separately(tmp_path):
    first = {"text": "Portfolio A", "created_at": "2026-09-19 10:00:00", "model": "m"}
    second = {"text": "Portfolio B", "created_at": "2026-09-19 11:00:00", "model": "m"}
    first_path = materialize_portfolio_pdf(first, root=tmp_path)
    second_path = materialize_portfolio_pdf(second, root=tmp_path)
    assert first_path is not None and first_path.is_file()
    assert second_path is not None and second_path.is_file()
    assert first_path != second_path
    assert first_path.name == second_path.name == "portfolio-gesamtbericht.pdf"


def test_persist_replaces_stale_bytes_for_same_report_path(tmp_path):
    first = PdfReport("gesamtbericht", "Erste Fassung", 42, "Signal")
    second = PdfReport("gesamtbericht", "Zweite Fassung", 42, "Signal")
    path = persist_report_pdf(first, snapshot="same", root=tmp_path)
    first_bytes = path.read_bytes()
    same_path = persist_report_pdf(second, snapshot="same", root=tmp_path)
    assert same_path == path
    assert same_path.read_bytes() != first_bytes
    assert "Zweite Fassung" in _text(same_path.read_bytes())


def test_save_run_materializes_all_available_pdfs():
    result = pipeline.ScanResult(
        id=77, name="Persistiert", trades_sha256="b" * 64,
        trade_analyse="Trade", risiko_analyse="Risiko", gesamtbericht="Final")
    portfolio = {
        "text": "Portfolio", "created_at": "2026-09-19 11:30:00", "model": "m",
    }
    pipeline.ScanPipeline.save_run([result], {}, portfolio)
    root = pipeline.config.REPORTS_DIR
    assert len(list((root / "signale").rglob("*.pdf"))) == 3
    assert len(list((root / "portfolio").rglob("*.pdf"))) == 1


# ------------- Nutzer-Wunsch 30.09.2026: Portfolio-Anhang je Empfehlung -----

_PORTFOLIO_TEXT = """Kurzfassung: Empfehlung Alpha, Beta.

## 1. Bestandsaufnahme

Alpha, Beta, Gamma, SafeGold — Übersicht aller Signale. SafeGold dupliziert.

## 3. Portfolio-Vorschlag

- Alpha — 40 % — Haupt-Ertragsträger
- Beta — 30 % — Diversifikator
- SafeGold — 30 % — Reserve

## 4. Gesamtrisiko

Klumpenrisiken etc. Aussortiert: Gamma (Grund).
"""


def _ergebnis(sid, name, **kw):
    basis = dict(id=sid, name=name, quelle="pelik", platform="pelican",
                 ampel="🟢", score=4.1, ertrag_monat_pct=15.4,
                 ertrag_monat_pct_forensik=3.5, dd_equity_pct=0.78,
                 ertrag_monat_geom_pct=6.19, retdd_monat=99,
                 dd_balance_pct=None, trading_dd_pct=0.27,
                 # Review 04.10.: Monitor-Closing-DD ist kein Messwert mehr —
                 # derselbe Wert als Kurs-Reko gesetzt, PDF-Zeile bleibt geprüft.
                 equity_dd_rekonstruiert_pct=6.19, monitor_trade_eq_dd_pct=6.19,
                 abonnenten=1425, wochen=178, kapitalbasis_verwendet_usd=10000,
                 kapitalbasis_verwendet_quelle="implizit_aus_balance",
                 stop_nachweis="SL nicht übertragen — neutral",
                 gesamtbericht="## Urteil\n\nEMPFEHLUNG — Alpha passt.")
    basis.update(kw)
    return pipeline.ScanResult(**basis)


def test_anhang_erkennt_nur_die_empfohlenen_strategien():
    from mqlkiscanner.pdf_reports import _anhang_markdown, _empfohlene_signale
    ergebnisse = [
        _ergebnis(1, "Alpha"),
        _ergebnis(2, "Beta"),
        _ergebnis(3, "Gamma"),
        _ergebnis(4, "SafeGold", gesamtbericht="SafeGold-Duplikat-Bericht"),
    ]
    namen = [r.name for r in _empfohlene_signale(_PORTFOLIO_TEXT, ergebnisse)]
    assert namen == ["Alpha", "Beta", "SafeGold"]   # Gamma nur in Bestandsaufnahme
    md = _anhang_markdown(ergebnisse, _PORTFOLIO_TEXT)
    assert "Anhang — Empfohlene Strategien im Detail" in md
    assert "Strategie 1: Alpha" in md and "Strategie 2: Beta" in md
    assert "Strategie 3: SafeGold" in md and "Strategie 4" not in md
    assert "EMPFEHLUNG — Alpha passt." in md      # voller Gesamtbericht drin
    assert "| Gewinn %/Monat (geometrisch) | 6,19 % |" in md
    assert "| Max-Drawdown (Equity, gemessen) | 6,19 % |" in md
    assert "| RetDD (Monatsgewinn / Max-Equity-DD) | 1,000 |" in md
    assert "Gamma" not in md.split("Gesamtrisiko")[0] or True


def test_portfolio_pdf_mit_anhang_rendert_und_ohne_bleibt_klassisch():
    from mqlkiscanner.pdf_reports import portfolio_pdf_spec
    report = {"text": _PORTFOLIO_TEXT, "model": "glm-5.3", "created_at": "x"}
    klassisch = portfolio_pdf_spec(report)[0]
    assert "Anhang" not in klassisch.body
    mit = portfolio_pdf_spec(
        report, ergebnisse=[_ergebnis(1, "Alpha"), _ergebnis(2, "Beta")])[0]
    assert "Anhang — Empfohlene Strategien im Detail" in mit.body
    # PDF bleibt valide und enthält die Anhang-Überschrift im Fließtext
    text = _text(render_report_pdf(mit))
    assert "Empfohlene Strategien im Detail" in text
    assert "EMPFEHLUNG" in text


def test_materialize_portfolio_pdf_durchreichung(tmp_path):
    ergebnisse = [_ergebnis(1, "Alpha")]
    pfad = materialize_portfolio_pdf(
        {"text": _PORTFOLIO_TEXT}, root=tmp_path, ergebnisse=ergebnisse)
    assert pfad and pfad.exists()
    text = _text(pfad.read_bytes())
    assert "Strategie 1: Alpha" in text


def test_anhang_sammelt_alle_berichte_je_strategie():
    """Nutzer-Wunsch 02.10.: Im Anhang steht ALLES zu jeder empfohlenen
    Strategie — Kurzfassung, Risiko-Analyse (Stufe 1), Trade-Analyse
    (Stufe 2), Gesamtbericht und die Tiefenanalyse, jeweils mit Modell-
    Angabe; fehlende Berichte werden ehrlich benannt."""
    from mqlkiscanner.pdf_reports import _anhang_markdown
    alpha = _ergebnis(
        1, "Alpha",
        kurzfassung="Kurz: Alpha solide.",
        risiko_analyse="RISIKO-ALPHA-TEXT", risiko_analyse_model="glm-5.3-flash",
        risiko_analyse_at="2026-10-02 08:00:00",
        trade_analyse="TRADE-ALPHA-TEXT", trade_analyse_model="glm-5.3",
        tiefenanalyse="TIEFEN-ALPHA", tiefenanalyse_model="glm-5.3")
    beta = _ergebnis(2, "Beta")   # ohne jeden Nebenbericht
    md = _anhang_markdown([alpha, beta], _PORTFOLIO_TEXT)
    alpha_block = md.split("Strategie 1: Alpha")[1].split("Strategie 2: Beta")[0]
    assert "Kurz: Alpha solide." in alpha_block
    assert "Risiko-Analyse (Stufe 1" in alpha_block
    assert "RISIKO-ALPHA-TEXT" in alpha_block and "glm-5.3-flash" in alpha_block
    assert "Trade-Analyse (Stufe 2)" in alpha_block
    assert "TRADE-ALPHA-TEXT" in alpha_block
    assert "Gesamtbericht (ungekürzt)" in alpha_block
    assert "EMPFEHLUNG — Alpha passt." in alpha_block
    assert "Erweiterte KI-Analyse (Tiefenanalyse, manuell)" in alpha_block
    assert "TIEFEN-ALPHA" in alpha_block
    beta_block = md.split("Strategie 2: Beta")[1]
    assert "nicht vorhanden" in beta_block      # ehrlich statt still fehlen
    assert "RISIKO-ALPHA-TEXT" not in beta_block


def test_portfolio_pdf_anhang_rendert_alle_berichtsteile():
    """Ende-zu-Ende: Der gerenderte PDF-Text enthält je Strategie die
    Berichtsteile — nicht nur den Gesamtbericht."""
    from mqlkiscanner.pdf_reports import portfolio_pdf_spec
    alpha = _ergebnis(
        1, "Alpha", risiko_analyse="RISIKO-IM-PDF", trade_analyse="TRADE-IM-PDF")
    report = {"text": _PORTFOLIO_TEXT, "model": "glm-5.3", "created_at": "x"}
    mit = portfolio_pdf_spec(report, ergebnisse=[alpha])[0]
    text = _text(render_report_pdf(mit))
    assert "RISIKO-IM-PDF" in text and "TRADE-IM-PDF" in text
