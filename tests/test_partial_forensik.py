# -*- coding: utf-8 -*-
"""Teilergebnisse unvollstaendiger Forensik: sichtbar, dauerhaft, nie Kandidat.

Belegfaelle: #2308093/#1496203 (Kapitalbasis unbekannt — Parser lief, Score
zu Recht verweigert, aber Winrate/DD/Martingale/Stop duerfen nicht verloren
gehen). Design-Regel bleibt: kein Gruen/Score ohne vollstaendige Batterie;
bewiesene Martingale-Signatur bleibt rot.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from mqlkiscanner import db, pipeline
from mqlkiscanner.pipeline import ScanResult, ampel_for

# Positions-Export OHNE Balance-Zeilen: Trading laeuft, Kapitalbasis fehlt.
CSV_NO_CAPITAL = (
    "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
    "2024.01.02 10:00:00;Buy;0.10;XAUUSD;2050;0.10;2024.01.02 11:00:00;2048;0;0;-20\n"
    "2024.01.03 10:00:00;Buy;0.10;XAUUSD;2048;0.10;2024.01.03 11:00:00;2055;0;0;70\n"
)


def _analyze_mit_cache(tmp_path, monkeypatch, csv_text: str):
    cache = tmp_path / "cache.csv"
    cache.write_text(csv_text, encoding="utf-8")
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats",
                        Mock(return_value={"dd_equity_pct": 12.0,
                                           "monthly_growth_pct": 9.0}))
    monkeypatch.setattr(pipeline.exporter, "export_positions",
                        Mock(return_value=(str(cache), False)))
    monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)
    pipe = pipeline.ScanPipeline()
    return pipe.analyze_candidate(None, {"id": 555001, "name": "Teil-Test"},
                                  lambda _: None)


def test_incomplete_run_persists_partial_findings(tmp_path, monkeypatch):
    res = _analyze_mit_cache(tmp_path, monkeypatch, CSV_NO_CAPITAL)
    # Der Lauf scheitert an der Kapitalbasis — mit konkretem Grund.
    assert res.fehler and "Kapitalbasis unbekannt" in res.fehler
    assert res.forensik_vorhanden is False
    # ... aber die berechneten Teilergebnisse bleiben am Objekt UND in der DB.
    assert res.winrate_pct == 50.0
    assert res.martingale_flag is False
    saved = db.list_catalog()[0]["forensik"]
    assert saved["vollstaendig"] is False
    assert saved["winrate_pct"] == 50.0
    assert saved["martingale_flag"] is False
    assert saved["score"] is None


def test_results_from_db_restores_partials_as_vorpruefung(tmp_path, monkeypatch):
    _analyze_mit_cache(tmp_path, monkeypatch, CSV_NO_CAPITAL)
    rows = pipeline.results_from_db()
    res = next(r for r in rows if r.id == 555001)
    assert res.forensik_vorhanden is False
    assert res.fehler and "Kapitalbasis unbekannt" in res.fehler
    assert res.winrate_pct == 50.0
    assert res.trading_dd_pct is not None
    assert res.score is None
    # Keine "Veraltet"-Verwechslung: Der Grund steht als Fehler, nicht als
    # Altersmeldung.
    assert "Veraltet" not in res.urteil and "veraltet" not in res.urteil
    assert res.ampel == "⚪"


def test_martingale_red_flag_survives_error_status():
    res = ScanResult(id=555002, name="Red-Flag-Test", source_kind="live",
                     forensik_vorhanden=False,
                     fehler="Forensik unvollständig: Kapitalbasis unbekannt",
                     martingale_flag=True)
    ampel, urteil = ampel_for(res, {"schranke_eq_dd_pct": 30.0})
    assert ampel == "🔴"
    assert "Martingale" in urteil


def test_error_without_red_flag_stays_white():
    res = ScanResult(id=555003, name="Weiss-Test", source_kind="live",
                     forensik_vorhanden=False,
                     fehler="Forensik unvollständig: Kapitalbasis unbekannt",
                     martingale_flag=False)
    ampel, urteil = ampel_for(res, {"schranke_eq_dd_pct": 30.0})
    assert ampel == "⚪"
    assert "Fehler" in urteil


def test_partial_never_becomes_candidate(tmp_path, monkeypatch):
    # Selbst mit Top-Plattformwerten bleibt unvollstaendige Forensik ⚪ —
    # kein Score < 5-Pfad, keine Gruen-Moeglichkeit.
    _analyze_mit_cache(tmp_path, monkeypatch, CSV_NO_CAPITAL)
    res = next(r for r in pipeline.results_from_db() if r.id == 555001)
    assert res.ampel != "🟢"
