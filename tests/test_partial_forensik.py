# -*- coding: utf-8 -*-
"""Teilergebnisse unvollstaendiger Forensik: sichtbar, dauerhaft, nie Kandidat.

Eine bekannte nichtpositive CSV-Kapitalbasis darf nicht durch Modellkapital
ersetzt werden. Parser-Ergebnisse bleiben trotz unvollstaendiger Forensik
erhalten. Fehlende Kapitalbelege dagegen erlauben seit 24.10.2026 ein
getrennt gekennzeichnetes Modell, weiterhin ohne Gruen-Freigabe.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from mqlkiscanner import db, pipeline
from mqlkiscanner.pipeline import ScanResult, ampel_for

# Ohne Balance-Zeilen greift die ausdruecklich erlaubte Modellkapitalbasis.
CSV_NO_CAPITAL = (
    "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
    "2024.01.02 10:00:00;Buy;0.10;XAUUSD;2050;0.10;2024.01.02 11:00:00;2048;0;0;-20\n"
    "2024.01.03 10:00:00;Buy;0.10;XAUUSD;2048;0.10;2024.01.03 11:00:00;2055;0;0;70\n"
)

# Ein belegter Nullanker bleibt null; er darf kein 10k-Modell ausloesen.
CSV_NONPOSITIVE_CAPITAL = CSV_NO_CAPITAL.replace(
    "2024.01.02 10:00:00;Buy",
    "2024.01.01 10:00:00;Balance;;;;;;;;;100\n"
    "2024.01.01 11:00:00;Balance;;;;;;;;;-100\n"
    "2024.01.02 10:00:00;Buy",
)


def _analyze_mit_cache(tmp_path, monkeypatch, csv_text: str):
    cache = tmp_path / "cache.csv"
    cache.write_text(csv_text, encoding="utf-8")
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats",
                        Mock(return_value={"account_currency": "USD", "dd_equity_pct": 12.0,
                                           "monthly_growth_pct": 9.0}))
    monkeypatch.setattr(pipeline.exporter, "export_positions",
                        Mock(return_value=(str(cache), False)))
    monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)
    pipe = pipeline.ScanPipeline()
    return pipe.analyze_candidate(None, {"id": 555001, "name": "Teil-Test"},
                                  lambda _: None)


def test_incomplete_run_persists_partial_findings(tmp_path, monkeypatch):
    res = _analyze_mit_cache(tmp_path, monkeypatch, CSV_NONPOSITIVE_CAPITAL)
    # Die belegte Nullbasis verhindert vollstaendige Kontoforensik.
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


def test_results_from_db_preserves_partials_and_explicit_drawdown_breach(tmp_path, monkeypatch):
    _analyze_mit_cache(tmp_path, monkeypatch, CSV_NONPOSITIVE_CAPITAL)
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
    # Der Verlust nach belegter vollstaendiger Kapitalentnahme ist ein
    # messbarer 100-%-DD. Diese harte rote Flag gilt auch bei Teilforensik.
    assert res.trading_dd_pct == 100.0 and res.ampel == "🔴"


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
    # Top-Plattformwerte erlauben kein Gruen aus Teilforensik; eine bekannte
    # harte rote Flag bleibt trotzdem wirksam.
    _analyze_mit_cache(tmp_path, monkeypatch, CSV_NONPOSITIVE_CAPITAL)
    res = next(r for r in pipeline.results_from_db() if r.id == 555001)
    assert res.ampel != "🟢"


def test_missing_capital_preserves_a_separate_model_after_reload(tmp_path, monkeypatch):
    result = _analyze_mit_cache(tmp_path, monkeypatch, CSV_NO_CAPITAL)
    assert not result.fehler and not result.forensik_vorhanden
    assert result.modellpruefung_vorhanden and result.kapitalbasis_ist_modell
    assert result.kapitalbasis_verwendet_usd == 10000
    saved = db.list_catalog()[0]["forensik"]
    assert saved["vollstaendig"] is False
    assert saved["modellpruefung_vollstaendig"] is True
    restored = next(row for row in pipeline.results_from_db() if row.id == result.id)
    assert restored.kapitalbasis_ist_modell and restored.modellpruefung_vorhanden
    assert not restored.forensik_vorhanden and restored.ampel != "🟢"
    assert restored.winrate_pct == 50.0
