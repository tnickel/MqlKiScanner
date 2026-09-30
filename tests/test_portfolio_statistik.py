# -*- coding: utf-8 -*-
"""Tests für die Portfolio-Statistik (B20/B21, Intensiv-Review-Nachtrag).

B20: Verlustmonat-Cluster + Historie-Tiefe/gemeinsames Fenster als
     Code-Befund im Portfolio-Prompt (gemeinsame Schocks statt nur
     paarweiser Korrelation).
B21: Instrument-Overlap als eigenes Klumpenrisiko-Merkmal.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.mqlkiscanner import pipeline, portfolio_statistik
from src.mqlkiscanner.llm import prompt_fill

KOPF = ("Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;"
        "Swap;Profit")


def _csv(tmp_path, name, zeilen):
    p = tmp_path / name
    p.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return str(p)


def _monats_csv(tmp_path, name, basis, monate):
    """Positions-CSV: Einzahlung `basis`, je Monat ein Trade mit PnL."""
    zeilen = [KOPF,
              "2025.10.31 00:00:00;Balance;;;;;;;;;" + f"{basis:g}"]
    for monat, pnl in monate:
        tag = monat.replace("-", ".") + ".15"
        zeilen.append(f"{tag} 10:00:00;Buy;0.10;XAUUSD;4000;0.10;"
                      f"{tag} 12:00:00;4050;0;0;{pnl:g}")
    return _csv(tmp_path, name, zeilen)


# ------------------------------------------------------------ Monatsrenditen

def test_monatsrenditen_virtuelle_kurve_und_verlustmonat(tmp_path):
    p = _monats_csv(tmp_path, "a.csv", 1000,
                    [("2025-11", 100.0), ("2025-12", -50.0), ("2026-01", 30.0)])
    r = portfolio_statistik.monatsrenditen(p, 1000.0)
    assert r["2025-11"] == pytest.approx(10.0)
    assert r["2025-12"] == pytest.approx(-50.0 / 1100.0 * 100, abs=0.01)
    assert r["2026-01"] == pytest.approx(30.0 / 1050.0 * 100, abs=0.01)


def test_monatsrenditen_ohne_datei_oder_basis_bleibt_leer(tmp_path):
    assert portfolio_statistik.monatsrenditen(str(tmp_path / "gibt.es"), 100.0) == {}
    p = _monats_csv(tmp_path, "b.csv", 1000, [("2025-11", 10.0)])
    assert portfolio_statistik.monatsrenditen(p, None) == {}
    assert portfolio_statistik.monatsrenditen(p, 0.0) == {}


# ---------------------------------------------------------------- Statistik

class _R:
    """Minimaler ScanResult-Doppel für die Statistik."""
    def __init__(self, sid, name, pfad, basis, symbole, live=True):
        self.id, self.name = sid, name
        self.source_kind = "live" if live else "demo"
        self.trades_path = pfad
        self.kapitalbasis_verwendet_usd = basis
        self.symbole = symbole


def test_cluster_und_fenster(tmp_path):
    a = _monats_csv(tmp_path, "a.csv", 1000,
                    [("2025-11", 100.0), ("2025-12", -20.0), ("2026-01", 50.0)])
    b = _monats_csv(tmp_path, "b.csv", 2000,
                    [("2025-11", 40.0), ("2025-12", -30.0), ("2026-01", -10.0)])
    ergebnis = portfolio_statistik.statistik([
        _R(1, "Alpha", a, 1000.0, "XAUUSD, EURUSD"),
        _R(2, "Beta", b, 2000.0, "XAUUSD, AUDCAD")])
    cluster = ergebnis["verlustmonate_cluster"]
    # Nur 2025-12 hat ZWEI Verlierer (Alpha -1,82 %, Beta -1,47 %);
    # 2026-01 verliert nur Beta (Alpha +2,78 %) -> kein Cluster.
    assert set(cluster) == {"2025-12"}
    namen_dez = [s["name"] for s in cluster["2025-12"]["signale"]]
    assert namen_dez == ["Alpha", "Beta"]
    f = ergebnis["gemeinsames_fenster"]
    assert (f["von"], f["bis"], f["monate"], f["signale_mit_kurve"]) == \
        ("2025-11", "2026-01", 3, 2)
    zeilen = {z["name"]: z for z in ergebnis["signale"]}
    assert zeilen["Alpha"]["monate"] == 3
    assert zeilen["Alpha"]["schlechtester_monat"] == "2025-12"
    assert zeilen["Beta"]["schlechtester_wert_pct"] == pytest.approx(
        -30.0 / 2040.0 * 100, abs=0.01)


def test_instrument_overlap_nur_relevante_paare(tmp_path):
    a = _monats_csv(tmp_path, "a.csv", 1000, [("2025-11", 10.0)])
    b = _monats_csv(tmp_path, "b.csv", 1000, [("2025-11", 10.0)])
    c = _monats_csv(tmp_path, "c.csv", 1000, [("2025-11", 10.0)])
    ergebnis = portfolio_statistik.statistik([
        _R(1, "H4-1", a, 1000.0,
           "EURUSD, GBPUSD, USDJPY, XAUUSD, AUDCAD, EURGBP, NZDUSD"),
        _R(2, "H4-2", b, 1000.0,
           "EURUSD, GBPUSD, USDJPY, XAUUSD, AUDCAD, EURGBP, USDCAD"),
        _R(3, "GoldOnly", c, 1000.0, "XAUUSD")])
    paare = ergebnis["instrument_overlap"]
    assert paare, "H4-1/H4-2 mit 6 gemeinsamen Symbolen muss erscheinen"
    top = paare[0]
    assert {top["a"], top["b"]} == {"H4-1", "H4-2"}
    assert top["n_gemeinsam"] == 6
    assert top["jaccard"] >= 0.3
    # GoldOnly (1 Symbol) darf in keinem Paar stehen (Filter >= 3 gemeinsam)
    for paar in paare:
        assert "GoldOnly" not in (paar["a"], paar["b"])


def test_demo_ergebnisse_bleiben_draussen(tmp_path):
    a = _monats_csv(tmp_path, "a.csv", 1000, [("2025-11", 10.0)])
    ergebnis = portfolio_statistik.statistik(
        [_R(1, "Demo", a, 1000.0, "XAUUSD", live=False)])
    assert ergebnis["signale"] == []


# ------------------------------------------------------- Prompt-Integration

def test_portfolio_prompt_enthaelt_statistik_block():
    pstat = {"verlustmonate_cluster": {"2026-07": {"n": 7, "signale": []}},
             "hinweis": "Test-Hinweis"}
    prompt = prompt_fill.build_portfolio_prompt(
        "[]", "Kriterien", statistik_json=json.dumps(pstat, ensure_ascii=False))
    assert "{portfolio_statistik}" not in prompt
    assert "Portfolio-Statistik" in prompt
    assert "Test-Hinweis" in prompt
    assert "2026-07" in prompt


def test_portfolio_prompt_leerer_default_fuellt_platzhalter():
    prompt = prompt_fill.build_portfolio_prompt("[]", "Kriterien")
    assert "{portfolio_statistik}" not in prompt  # ersetzt (leer), nicht roh


def test_defaults_bleiben_mit_datei_synchron():
    basis = Path(prompt_fill.__file__).resolve().parents[3] / "config" / "prompts"
    from src.mqlkiscanner.llm import prompts as P
    assert P.DEFAULT_PORTFOLIO == (basis / "portfolio.md").read_text(encoding="utf-8")


def test_run_portfolio_reicht_statistik_an_prompt(tmp_path, monkeypatch):
    """Ende-zu-Ende: run_portfolio ruft die Statistik und füllt den Prompt."""
    a = _monats_csv(tmp_path, "a.csv", 1000, [("2025-11", 10.0)])
    from types import SimpleNamespace
    from unittest.mock import Mock
    gefangen = {}
    monkeypatch.setattr(
        pipeline.prompt_fill, "build_portfolio_prompt",
        lambda e, k, statistik_json="": gefangen.update(
            {"stat": statistik_json}) or "Kurzfassung: ok")
    pipe = pipeline.ScanPipeline()
    pipe.llm = SimpleNamespace(
        has_key=True, usage=SimpleNamespace(total_tokens=0),
        chat=Mock(return_value="Portfolio ok"))
    res = pipeline.ScanResult(
        id=1, name="Alpha", quelle="mql5", platform="MT5", ampel="🟢",
        source_kind="live", forensik_vorhanden=True, score=3.0,
        trades_path=a, kapitalbasis_verwendet_usd=1000.0,
        symbole="XAUUSD, EURUSD, GBPUSD", ertrag_monat_pct=8.0,
        ertrag_monat_pct_forensik=8.0, martingale_flag=False,
        stop_evidence="none")
    ergebnis = pipe.run_portfolio([res], lambda _: None)
    assert ergebnis["text"] == "Portfolio ok"
    assert "verlustmonate_cluster" in gefangen["stat"]
    assert "instrument_overlap" in gefangen["stat"]
