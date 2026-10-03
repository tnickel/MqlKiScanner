# -*- coding: utf-8 -*-
"""Fehlende Kursdaten sichtbar machen (Nutzer-Wunsch 03.10.: „sollte im
Bericht erscheinen, damit ich weiß, wo ich dran arbeiten kann").

Deckt ab: strukturiertes fehlende_kursdaten-Feld im Forensik-JSON der KI,
PDF-Zeile, aggregierte Arbeitsliste (inkl. Forensik-scheitert-am-Kontrakt-
Fall aus dem Fehler-Feld).
"""
from __future__ import annotations

import json

from mqlkiscanner import pipeline
from mqlkiscanner.app_ui import fehlende_kursdaten_arbeitsliste


def _result(**kwargs):
    basis = dict(id=1, name="Testsignal", ampel="🟡", forensik_vorhanden=True)
    basis.update(kwargs)
    return pipeline.ScanResult(**basis)


def test_forensik_json_nennt_fehlende_kursdaten_strukturiert():
    r = _result(equity_rekon_ohne_kurse=["US100"],
                equity_rekon_ohne_kontrakt=["XCUUSDM"])
    payload = json.loads(pipeline._forensik_json(r))
    feld = payload["fehlende_kursdaten"]
    assert feld["ohne_kurse"] == ["US100"]
    assert feld["ohne_kontrakt"] == ["XCUUSDM"]
    assert "zu NIEDRIG" in feld["folge"]
    assert "contract_specs.json" in feld["handlung"]


def test_forensik_json_ohne_fehlende_kursdaten_ohne_feld():
    r = _result()
    payload = json.loads(pipeline._forensik_json(r))
    assert "fehlende_kursdaten" not in payload


def test_arbeitsliste_aggregiert_symbole_ueber_signale():
    eintraege = fehlende_kursdaten_arbeitsliste([
        _result(id=1, name="KiraCat", equity_rekon_ohne_kurse=["US100"]),
        _result(id=2, name="Zweites", equity_rekon_ohne_kurse=["US100", "DE30"]),
        _result(id=3, name="Drittes", equity_rekon_ohne_kontrakt=["DE30M"]),
        _result(id=4, name="Kaputt", fehler="ValueError: Unbekannte Instrumente "
                "ohne belegte Kontraktgroesse: DE30M, XCUUSDM — in data/contract_specs.json "
                "eintragen (Kontraktgroesse, Gewinnwaehrung, Quelle), dann erneut pruefen."),
    ])
    nach_symbol = {e["symbol"]: e for e in eintraege}
    assert set(nach_symbol["US100"]["signale"]) == {"KiraCat", "Zweites"}
    assert "kein Kurs" in nach_symbol["US100"]["grund"]
    assert nach_symbol["DE30M"]["signale"] == ["Drittes", "Kaputt"]
    assert set(nach_symbol["XCUUSDM"]["signale"]) == {"Kaputt"}
    assert "Kontraktgröße nicht belegt" in nach_symbol["XCUUSDM"]["grund"]


def test_arbeitsliste_leer_ohne_befunde():
    assert fehlende_kursdaten_arbeitsliste([_result(), _result(id=2)]) == []


def test_pdf_anhang_nennt_fehlende_kursdaten_zeile():
    """Der Portfolio-PDF-Anhang führt je Strategie die Engine-Kennzahlen —
    die Zeile 'Fehlende Kursdaten' muss darin auftauchen (die einzelnen
    KI-Berichts-PDFs erhalten die Nennung über die Prompt-Pflicht)."""
    from mqlkiscanner.pdf_reports import _anhang_markdown
    r = _result(id=42, name="PDF-Fall", ampel="🟢", equity_rekon_ohne_kurse=["US100"],
                equity_rekon_ohne_kontrakt=["XCUUSDM"], score=4.0,
                gesamtbericht="Text.")
    portfolio = ("## 3. Portfolio-Vorschlag\n\n- PDF-Fall — 100 % — Ertragsträger\n")
    md = _anhang_markdown([r], portfolio)
    assert "Fehlende Kursdaten" in md
    assert "US100" in md and "XCUUSDM" in md
