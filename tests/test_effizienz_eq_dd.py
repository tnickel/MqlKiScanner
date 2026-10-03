# -*- coding: utf-8 -*-
"""Gewinn pro realem Laufzeitmonat; RetDD mit EQ-DD ohne Vor-Rundung."""
import datetime as dt
import math

import pytest

from mqlkiscanner import portfolio_statistik as ps


HEADER = "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit"


def _csv(tmp_path, trades, balances=()):
    zeilen = [HEADER]
    for open_, close, profit, commission, swap in trades:
        zeilen.append(f"{open_:%Y.%m.%d %H:%M:%S};Buy;0.1;XAUUSD;2000;0.1;"
                      f"{close:%Y.%m.%d %H:%M:%S};2001;{commission:.17g};"
                      f"{swap:.17g};{profit:.17g}")
    for zeit, amount in balances:
        zeilen.append(f"{zeit:%Y.%m.%d %H:%M:%S};Balance;;;;;;;;;{amount:.17g}")
    pfad = tmp_path / "eff.csv"
    pfad.write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return str(pfad)


BEGIN = dt.datetime(2025, 1, 1)
END = dt.datetime(2026, 1, 1)


def _jahres_csv(tmp_path, profit=100, commission=0, swap=0):
    return _csv(tmp_path, [(BEGIN, END, profit, commission, swap)])


def test_leermonate_und_erster_open_gehoeren_zur_monatskurve(tmp_path):
    p = _csv(tmp_path, [(BEGIN, dt.datetime(2025, 1, 31), 10, 0, 0),
                       (dt.datetime(2025, 3, 1), dt.datetime(2025, 3, 31), 11, 0, 0)])
    kurve = ps.monatsrenditen(p, 100)
    assert kurve == {"2025-01": 10, "2025-02": 0, "2025-03": 10}
    eff = ps.effizienz_kennzahlen(p, 100, 10)
    monate = 89 / (365.2425 / 12)
    assert eff["dauer_monate"] == pytest.approx(monate)
    assert eff["ertrag_monat_geom_pct"] == pytest.approx(math.expm1(math.log(1.21) / monate) * 100)
    assert eff["ertrag_monat_geom_pct"] < 10


def test_lange_offene_position_keine_aktivmonat_annualisierung(tmp_path):
    p = _csv(tmp_path, [(BEGIN, dt.datetime(2025, 4, 1), 10, 0, 0)])
    assert ps.monatsrenditen(p, 100) == {
        "2025-01": 0, "2025-02": 0, "2025-03": 0, "2025-04": 10}
    eff = ps.effizienz_kennzahlen(p, 100, 10)
    assert eff["dauer_monate"] == pytest.approx(90 / (365.2425 / 12))
    assert eff["ertrag_monat_geom_pct"] < 4


def test_echte_zeitbasis_geometrischer_gewinn_und_cagr(tmp_path):
    p = _jahres_csv(tmp_path)
    eff = ps.effizienz_kennzahlen(p, 1000, 20)
    jahre = 365 / 365.2425
    gain = math.expm1(math.log(1.1) / (jahre * 12)) * 100
    cagr = math.expm1(math.log(1.1) / jahre) * 100
    assert eff["ertrag_monat_geom_pct"] == pytest.approx(gain)
    assert eff["cagr_jahr_pct"] == pytest.approx(cagr)
    assert eff["retdd_monat"] == pytest.approx(gain / 20)
    assert eff["zeit_von"] == BEGIN.isoformat()
    assert eff["zeit_bis"] == END.isoformat()
    assert eff["rendite_basis"] == "virtuelle_trade_netto_kurve"
    assert eff["retdd_basis"] == "uebergebener_max_equity_dd_pct"


@pytest.mark.parametrize("dd", [None, 0, -1, float("nan"), float("inf")])
def test_gewinn_bleibt_auch_ohne_belastbaren_equity_dd(tmp_path, dd):
    eff = ps.effizienz_kennzahlen(_jahres_csv(tmp_path), 1000, dd)
    assert eff["ertrag_monat_geom_pct"] is not None
    assert eff["cagr_jahr_pct"] is not None
    assert eff["retdd_monat"] is None
    assert eff["retdd_jahr"] is None
    assert eff["effizienz_status"] == "ohne_equity_dd"


@pytest.mark.parametrize("gain,dd", [(9.995, 10), (10.001, 10.004), (4.9995, 5)])
def test_vor_rundung_darf_retdd_minimum_nicht_passieren(tmp_path, gain, dd):
    monate = 365 / (365.2425 / 12)
    profit = 1000 * math.expm1(math.log1p(gain / 100) * monate)
    eff = ps.effizienz_kennzahlen(_jahres_csv(tmp_path, profit), 1000, dd)
    assert eff["ertrag_monat_geom_pct"] == pytest.approx(gain, abs=1e-10)
    assert eff["retdd_monat"] == pytest.approx(gain / dd, abs=1e-10)
    assert eff["retdd_monat"] < 1
    assert round(eff["retdd_monat"], 2) == 1


def test_kleine_monatsrendite_wird_nicht_zu_null_vorgerundet(tmp_path):
    p = _jahres_csv(tmp_path, .004)
    assert ps.monatsrenditen(p, 1000)["2026-01"] == pytest.approx(.0004)
    eff = ps.effizienz_kennzahlen(p, 1000, 10)
    assert eff["ertrag_monat_geom_pct"] > 0


def test_netto_inkl_gebuehren_kapitalfluesse_als_basisgrenze(tmp_path):
    p = _csv(tmp_path, [(BEGIN, END, 100, -2, -3)],
             [(BEGIN - dt.timedelta(days=1), 1000),
              (BEGIN + dt.timedelta(days=1), 10000)])
    eff = ps.effizienz_kennzahlen(p, 1000, 10)
    assert eff["netto_gesamt_usd"] == 95
    assert eff["endkapital_virtuell_usd"] == 1095
    assert eff["kapitalfluesse_nach_start"] == 1
    assert "andere Bezugsbasis" in eff["basis_hinweis"]


@pytest.mark.parametrize("profit", [-1000, -1100])
def test_nichtpositive_endbasis_ist_unbekannt(tmp_path, profit):
    eff = ps.effizienz_kennzahlen(_jahres_csv(tmp_path, profit), 1000, 50)
    assert eff["ertrag_monat_geom_pct"] is None
    assert eff["cagr_jahr_pct"] is None
    assert eff["retdd_monat"] is None
    assert eff["effizienz_status"] == "rendite_nicht_berechenbar"


def test_null_zeitspanne_ist_unbekannt_ohne_fake_monat(tmp_path):
    p = _csv(tmp_path, [(BEGIN, BEGIN, 100, 0, 0)])
    eff = ps.effizienz_kennzahlen(p, 1000, 10)
    assert eff["dauer_monate"] == 0
    assert eff["ertrag_monat_geom_pct"] is None


@pytest.mark.parametrize("basis", [float("nan"), float("inf"), 0, -100])
def test_unbrauchbare_startbasis_keine_kennzahl(tmp_path, basis):
    assert ps.effizienz_kennzahlen(_jahres_csv(tmp_path), basis, 10) is None
    assert ps.monatsrenditen(_jahres_csv(tmp_path), basis) == {}
