# -*- coding: utf-8 -*-
"""Beweisbasierte Duplikat-Entfernung im Parser (Nutzer-Entscheidung
03.10.2026): Identische CSV-Zeilen werden NUR entfernt, wenn die Plattform-
Anzahl (Signalseite „Trades:") die Doppellieferung belegt.

Zwei reale Konstellationen als Belege:
- Night Scalper: Plattform zählt ALLE Rohzeilen (299 = 299) → alles echt,
  nichts darf entfernt werden (die alte Massen-Heuristik löschte 17 echte).
- The Holy Grail: Plattform zählt erst ohne die Mehrfachzeilen →
  Doppellieferung bewiesen, jedes erste Vorkommen bleibt.
"""
from __future__ import annotations

from pathlib import Path

from mqlkiscanner import parser

HEADER = ("Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n")
ZEILEN = [
    "2026.09.01 22:39:54;Sell;0.01;XAUUSD;4324.98;0.01;2026.09.02 04:13:01;4319.66;-0.18;;5.32\n",
    "2026.09.01 16:12:05;Sell;0.01;XAUUSD;4326.38;0.01;2026.09.01 16:31:23;4349.51;-0.18;;-23.13\n",
    "2026.09.02 08:00:00;Buy;0.01;XAUUSD;4330.00;0.01;2026.09.02 09:00:00;4340.00;-0.18;;9.82\n",
    "2026.09.02 10:00:00;Buy;0.01;XAUUSD;4340.00;0.01;2026.09.02 11:00:00;4335.00;-0.18;;-4.18\n",
]


def _csv(tmp_path: Path, zeilen: list[str]) -> Path:
    pfad = tmp_path / "export.csv"
    pfad.write_text(HEADER + "".join(zeilen), encoding="utf-8")
    return pfad


def _mit_duplikaten() -> list[str]:
    # 6 Rohzeilen: 2 Zeilen doppelt geliefert (Z. 1 und Z. 3) → 4 eindeutige.
    return ZEILEN + [ZEILEN[0], ZEILEN[2]]


def test_plattform_beweist_doppellieferung_entfernt(tmp_path):
    """THG-Konstellation: Plattform zählt 4, Roh-Export hat 6 Zeilen mit
    2 exakten Mehrfachvorkommen → Doppellieferung bewiesen, erstes
    Vorkommen bleibt."""
    pfad = _csv(tmp_path, _mit_duplikaten())
    erg = parser.load_export(str(pfad), plattform_positions=4)
    assert len(erg.trades) == 4
    assert erg.identische_tradezeilen == 2
    assert erg.duplikate_entfernt == 2
    # Netto zählt jede doppelt gelieferte Zeile nur EINMAL (inkl.
    # Commission -0,18 je Trade: Profit - 4 x 0,18).
    netto = sum(t.net for t in erg.trades)
    assert abs(netto - (5.32 - 23.13 + 9.82 - 4.18 - 4 * 0.18)) < 1e-6


def test_plattform_zaehlt_alle_zeilen_nachts_scalper(tmp_path):
    """Night-Scalper-Konstellation: Plattform zählt alle 6 Rohzeilen →
    identische Zeilen sind ECHT (Zwillings-Grid-Legs), nichts wird
    entfernt — trotz Mehrfachvorkommen."""
    pfad = _csv(tmp_path, _mit_duplikaten())
    erg = parser.load_export(str(pfad), plattform_positions=6)
    assert len(erg.trades) == 6
    assert erg.identische_tradezeilen == 2
    assert erg.duplikate_entfernt == 0
    # Beide Mehrfachvorkommen zählen je zweimal (echt): Z. 1 (+5,32) und
    # Z. 3 (+9,82) doppelt, Commission 6 x -0,18.
    netto = sum(t.net for t in erg.trades)
    assert abs(netto - (2 * 5.32 - 23.13 + 2 * 9.82 - 4.18 - 6 * 0.18)) < 1e-6


def test_ohne_beweiszahl_bleibt_alles_erhalten(tmp_path):
    """Keine Plattform-Angabe (None, z. B. Datenquellen ohne Positionszahl
    oder Signalseite ohne Wert): kein Beweis, keine Entfernung."""
    pfad = _csv(tmp_path, _mit_duplikaten())
    erg = parser.load_export(str(pfad))
    assert len(erg.trades) == 6
    assert erg.identische_tradezeilen == 2
    assert erg.duplikate_entfernt == 0


def test_beweis_passt_zu_keiner_zaehlung_bleibt_alles_erhalten(tmp_path):
    """Deckt sich die Plattformzahl weder mit der Rohzahl noch mit der
    Zahl ohne Mehrfachvorkommen (5), beweist sie nichts — alles bleibt."""
    pfad = _csv(tmp_path, _mit_duplikaten())
    erg = parser.load_export(str(pfad), plattform_positions=5)
    assert len(erg.trades) == 6
    assert erg.duplikate_entfernt == 0


def test_nicht_ganzzahlige_oder_negative_beweiszahl_ignoriert(tmp_path):
    pfad = _csv(tmp_path, _mit_duplikaten())
    assert len(parser.load_export(str(pfad), plattform_positions=4.5).trades) == 6
    assert len(parser.load_export(str(pfad), plattform_positions=-4).trades) == 6
    assert len(parser.load_export(str(pfad), plattform_positions="4").trades) == 6


def test_ohne_duplikate_ist_die_beweiszahl_wirkungslos(tmp_path):
    pfad = _csv(tmp_path, list(ZEILEN))
    erg = parser.load_export(str(pfad), plattform_positions=4)
    assert len(erg.trades) == 4
    assert erg.identische_tradezeilen == 0
    assert erg.duplikate_entfernt == 0


def test_einzelzwilling_mit_beweis_wird_entfernt(tmp_path):
    """Selbst EIN Zwillingspaar wird mit passendem Plattform-Beweis
    entfernt — der Beweis entscheidet, nicht die Masse (Umkehrung der
    alten 10-Zeilen-Heuristik)."""
    zeilen = list(ZEILEN) + [ZEILEN[1]]
    pfad = _csv(tmp_path, zeilen)
    erg = parser.load_export(str(pfad), plattform_positions=4)
    assert len(erg.trades) == 4
    assert erg.duplikate_entfernt == 1
    # Und mit Plattform-Beweis für alle 5: derselbe Zwilling bleibt echt.
    erg2 = parser.load_export(str(pfad), plattform_positions=5)
    assert len(erg2.trades) == 5
    assert erg2.duplikate_entfernt == 0


def test_engine_reicht_beweis_durch(tmp_path):
    """engine.analyze(plattform_positions=...) → Parser; die Forensik läuft
    auf der bereinigten Trade-Menge."""
    from mqlkiscanner import engine
    pfad = _csv(tmp_path, _mit_duplikaten())
    report = engine.analyze(str(pfad), plattform_positions=4)
    assert report["stats"]["trades_anzahl"] == 4
    assert report["stats"]["duplikate_entfernt"] == 2
    assert report["stats"]["identische_tradezeilen"] == 2
    report_ohne = engine.analyze(str(pfad))
    assert report_ohne["stats"]["trades_anzahl"] == 6
