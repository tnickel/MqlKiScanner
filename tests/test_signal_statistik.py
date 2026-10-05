# -*- coding: utf-8 -*-
"""signal_statistik: unabhängige Vorstufen-Kennzahlen aus dem Trade-Cache.

Kernabsicherungen:
- Monatsrenditen/geom. Ertrag identisch mit den kanonischen Produzenten
  (portfolio_statistik) — keine zweite Rechnung, nur Weiterreichen.
- Kapitalbasis-Kaskade wie pipeline.analyze_candidate (Seite → implizit →
  virtuell), CSV-Einzahlungen schlagen die Injektion.
- Trading-DD aus GESCHLOSSENEN Trades (Benennungsregel: nie „Max-Drawdown“).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mqlkiscanner import portfolio_statistik, signal_statistik

KOPF = "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"


def _csv(pfad: Path, zeilen: list[str]) -> str:
    pfad.write_text(KOPF + "\n".join(zeilen) + "\n", encoding="utf-8-sig")
    return str(pfad)


def _trade(start: str, dauer_min: int, symbol: str, eintritt: float,
           austritt: float, profit: float, lots: float = 0.10) -> str:
    von = datetime.strptime(start, "%Y.%m.%d %H:%M")
    bis = von + timedelta(minutes=dauer_min)
    return (f"{von:%Y.%m.%d %H:%M:%S};Buy;{lots};{symbol};{eintritt};{lots};"
            f"{bis:%Y.%m.%d %H:%M:%S};{austritt};0;;{profit}")


# ----------------------------------------------------------------- Grundpfad
def test_monate_geom_pf_winrate_konsistent(tmp_path):
    pfad = _csv(tmp_path / "trades.csv", [
        _trade("2026.01.05 10:00", 10, "EURUSD", 1.1000, 1.1010, 100.0),
        _trade("2026.01.20 11:00", 10, "EURUSD", 1.1000, 1.1005, 50.0),
        _trade("2026.02.10 10:00", 10, "EURUSD", 1.1000, 1.0990, -60.0),
        _trade("2026.03.15 10:00", 10, "EURUSD", 1.1000, 1.1012, 120.0),
    ])
    erg = signal_statistik.berechne(pfad, {"balance_usd": 10_000.0})
    assert erg["fehler"] is None
    # Implizite Basis: Web-Balance − Netto = 10.000 − 210
    assert erg["kapitalbasis_usd"] == pytest.approx(9_790.0)
    assert erg["kapitalbasis_quelle"] == "implizit_aus_balance"
    # Kanonische Produzenten liefern dieselben Werte (keine Zweitrechnung).
    monate = portfolio_statistik.monatsrenditen(pfad, erg["kapitalbasis_usd"])
    assert erg["monate_pct"] == pytest.approx(monate)
    eff = portfolio_statistik.effizienz_kennzahlen(pfad, erg["kapitalbasis_usd"], None)
    assert erg["ertrag_monat_geom_pct"] == pytest.approx(eff["ertrag_monat_geom_pct"])
    assert erg["cagr_jahr_pct"] == pytest.approx(eff["cagr_jahr_pct"])
    # Grundwerte
    assert erg["trades"] == 4
    assert erg["wins"] == 3 and erg["losses"] == 1
    assert erg["winrate_pct"] == 75.0
    assert erg["profit_faktor"] == pytest.approx(270.0 / 60.0, abs=0.01)
    assert erg["monate_usd"]["2026-02"] == pytest.approx(-60.0)
    assert erg["kurve"][-1][1] == pytest.approx(10_000.0)  # Basis + 210 Netto


def test_trading_dd_aus_geschlossenen_trades(tmp_path):
    # +300 → −250 → +50: tiefster Rückgang vom Peak 300 auf 50 = 250 USD.
    pfad = _csv(tmp_path / "trades.csv", [
        _trade("2026.01.05 10:00", 10, "XAUUSD", 2000.0, 2003.0, 300.0),
        _trade("2026.02.05 10:00", 10, "XAUUSD", 2000.0, 1997.5, -250.0),
        _trade("2026.03.05 10:00", 10, "XAUUSD", 2000.0, 2000.5, 50.0),
    ])
    erg = signal_statistik.berechne(pfad, {"balance_usd": 10_000.0})
    basis = erg["kapitalbasis_usd"]  # 10.000 − 100 = 9.900
    assert erg["trading_dd_usd"] == pytest.approx(250.0)
    # Prozent auf den Peak (Basis + 300), nicht auf die Basis
    # (drawdown rundet auf 2 Nachkommastellen).
    assert erg["trading_dd_pct"] == pytest.approx(
        250.0 / (basis + 300.0) * 100.0, abs=0.01)


# ---------------------------------------------------------- Kapitalbasisfall
def test_kapitalbasis_kaskade_seite_vor_implizit_vor_virtuell(tmp_path):
    pfad = _csv(tmp_path / "t.csv", [_trade("2026.01.05 10:00", 10, "EURUSD", 1.1, 1.11, 50.0)])
    # 1) Signalseite schlägt implizit UND virtuell.
    basis, quelle = signal_statistik.kapitalbasis_kaskade(
        pfad, {"initial_deposit_usd": 500.0, "balance_usd": 9950.0,
               "kapitalbasis_virtual_usd": 10_000.0})
    assert (basis, quelle) == (500.0, "signalseite_initial_deposit")
    # 2) Implizit schlägt virtuell.
    basis, quelle = signal_statistik.kapitalbasis_kaskade(
        pfad, {"balance_usd": 9950.0, "kapitalbasis_virtual_usd": 10_000.0})
    assert basis == pytest.approx(9_900.0)
    assert quelle == "implizit_aus_balance"
    # 3) Virtuell als letzte Stufe (Quellen-Annahme).
    basis, quelle = signal_statistik.kapitalbasis_kaskade(
        pfad, {"kapitalbasis_virtual_usd": 10_000.0})
    assert (basis, quelle) == (10_000.0, "virtuelle_annahme")
    # 4) Gar nichts: keine Basis, ehrlich None.
    assert signal_statistik.kapitalbasis_kaskade(pfad, {}) == (None, "signalseite_initial_deposit")


def test_ohne_kapitalbasis_keine_prozentwerte_aber_usd(tmp_path):
    pfad = _csv(tmp_path / "t.csv", [_trade("2026.01.05 10:00", 10, "EURUSD", 1.1, 1.11, 50.0)])
    erg = signal_statistik.berechne(pfad, {})
    assert erg["fehler"] is None
    assert erg["kapitalbasis_ok"] is False
    assert erg["ertrag_monat_geom_pct"] is None
    assert erg["monate_pct"] == {}
    assert erg["kurve"] == []
    assert erg["monate_usd"]["2026-01"] == pytest.approx(50.0)  # USD bleibt messbar
    assert erg["trades"] == 1


def test_unlesbare_und_fehlende_datei(tmp_path):
    assert signal_statistik.berechne(str(tmp_path / "gibt_es_nicht.csv"), {}) is None
    kaputt = tmp_path / "kaputt.csv"
    kaputt.write_text("Time;Type;Volume\n2026.01.05 10:00:00;Buy\n", encoding="utf-8-sig")
    erg = signal_statistik.berechne(str(kaputt), {})
    assert erg is not None and erg["fehler"]


# -------------------------------------------------------------- Vererbungen
def test_ertrag_je_close_dd_ist_vorbewertung_nicht_retdd(tmp_path):
    pfad = _csv(tmp_path / "t.csv", [
        _trade("2026.01.05 10:00", 10, "EURUSD", 1.1, 1.11, 200.0),
        _trade("2026.02.05 10:00", 10, "EURUSD", 1.1, 1.10, -100.0),
    ])
    erg = signal_statistik.berechne(pfad, {"balance_usd": 10_000.0})
    erwartet = erg["ertrag_monat_geom_pct"] / erg["trading_dd_pct"]
    assert erg["ertrag_je_close_dd"] == pytest.approx(erwartet)
    assert math.isfinite(erg["ertrag_je_close_dd"])


def test_martingale_flag_durchgereicht(tmp_path):
    # Nach Verlust (0.01) doppelt nachgelegt (0.03) → Flag。
    pfad = _csv(tmp_path / "t.csv", [
        _trade("2026.01.05 10:00", 10, "EURUSD", 1.1000, 1.0990, -10.0, lots=0.01),
        _trade("2026.01.05 11:00", 10, "EURUSD", 1.0995, 1.1015, 30.0, lots=0.03),
    ])
    erg = signal_statistik.berechne(pfad, {"balance_usd": 1_000.0})
    assert erg["martingale_flag"] is True
    assert "Martingale" in (erg["martingale_text"] or "")
