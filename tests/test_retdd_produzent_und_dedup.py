# -*- coding: utf-8 -*-
"""B24/B25 (Lauf-Review 02.10.2026): Der RetDD-Produzent und das
Trade-Dedup.

B24: retdd_monat/retdd_jahr/ertrag_monat_geom_pct/cagr_jahr_pct waren seit
dem 01.10. deklariert und überall konsumiert (Ampel-Zelle, Prompts,
Portfolio, Tradeserver-Sync) — aber NIEMALS berechnet (0/97 Signale mit
Wert). Der Produzent (portfolio_statistik.effizienz_kennzahlen) rechnet auf
derselben Kurve wie die Forensik-Erträge; Nutzer-Regel 02.10.:
1,0 = Mindestqualität (Grün-Weg in ampel_for setzt das hart durch).

B25-Korrektur 03.10.: Ohne Ticket-ID beweisen identische Zeilen keine
Doppellieferung. Der Parser zählt sie und erhält sämtliche Positionen.
"""
from __future__ import annotations

import math
from pathlib import Path

from mqlkiscanner import portfolio_statistik
from mqlkiscanner.parser import load_export

KOPF = ("Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit")


def _csv(tmp_path: Path, zeilen: list[str], name: str = "export.csv") -> str:
    pfad = tmp_path / name
    pfad.write_text("\n".join([KOPF] + zeilen) + "\n", encoding="utf-8")
    return str(pfad)


def _trade(monat: str, profit: float, symbol="XAUUSD") -> str:
    return (f"2026.{monat}.01 10:00:00;Buy;0.10;{symbol};2400.00;0.10;"
            f"2026.{monat}.02 10:00:00;2410.00;0.00;0.00;{profit:.2f}")


# ------------------------------------------------------------------ B24 —

def test_effizienz_kennzahlen_geometrisch_und_calmar(tmp_path):
    """Drei Abschluesse +100/+110/+121 in 121 Tagen: Kalenderlabels sind
    keine Laufzeitmonate; Annualisierung nutzt die Zeitspanne (≥ 3 Monate
    Mindesthistorie, Nutzer-Regel 05.10.)."""
    pfad = _csv(tmp_path, [
        _trade("01", 100.0), _trade("02", 110.0), _trade("05", 121.0)])
    eff = portfolio_statistik.effizienz_kennzahlen(pfad, 1000.0, 10.0)
    assert eff is not None
    jahre = 121.0 / 365.2425
    geom = math.expm1(math.log(1.331) / (jahre * 12)) * 100
    cagr = math.expm1(math.log(1.331) / jahre) * 100
    assert abs(eff["ertrag_monat_geom_pct"] - geom) < 1e-10
    assert abs(eff["cagr_jahr_pct"] - cagr) < 1e-9
    assert abs(eff["retdd_monat"] - geom / 10) < 1e-10
    assert abs(eff["retdd_jahr"] - cagr / 10) < 1e-10


def test_effizienz_kennzahlen_ohne_basis_bleibt_none(tmp_path):
    pfad = _csv(tmp_path, [_trade("01", 100.0), _trade("05", 0.0)])
    assert portfolio_statistik.effizienz_kennzahlen(pfad, None, 10.0) is None
    ohne_dd = portfolio_statistik.effizienz_kennzahlen(pfad, 1000.0, None)
    assert ohne_dd["ertrag_monat_geom_pct"] is not None
    assert ohne_dd["retdd_monat"] is None
    assert ohne_dd["effizienz_status"] == "ohne_equity_dd"
    assert portfolio_statistik.effizienz_kennzahlen(pfad, 0.0, 10.0) is None
    assert portfolio_statistik.effizienz_kennzahlen(
        str(tmp_path / "fehlt.csv"), 1000.0, 10.0) is None


def test_effizienz_niedrigere_rendite_trotz_kontowachstum():
    """Zinseszins-Wahrheit: 3× +10 % auf wachsendem Konto ergibt 10 %/M
    GEOMETRISCH, nicht 10 % vom fixen Start (Fixbasislüge Combo-Profile-
    Fall 01.10.: 91,8 % linear vs 27,7 % geom)."""
    kurve = {"2026-01": 10.0, "2026-02": 10.0, "2026-03": 10.0}
    faktor = 1.0
    for m in sorted(kurve):
        faktor *= 1 + kurve[m] / 100
    assert abs((faktor ** (1 / 3) - 1) * 100 - 10.0) < 1e-9


# ------------------------------------------------------------------ B25 —

def test_parser_erhaelt_identische_positionen_unabhaengig_von_anzahl(tmp_path):
    """Auch zehn identische Zeilenpaare können echte Zwillingspositionen sein."""
    # Einzelfall: 3 Zeilen, 1 doppelt — bleibt unangetastet (Multiset, F-16)
    pfad_klein = _csv(tmp_path,
                      [_trade("01", 100.0), _trade("02", -50.0),
                       _trade("01", 100.0)], "klein.csv")
    klein = load_export(str(pfad_klein))
    assert len(klein.trades) == 3
    assert klein.duplikate_entfernt == 0
    assert klein.identische_tradezeilen == 1

    # Zehn Monate mit je zwei Positionen: Menge ist kein Identitätsbeweis.
    eindeutige = [_trade(f"{m:02d}", 10.0) for m in range(1, 11)]
    pfad_masse = _csv(tmp_path, eindeutige + eindeutige, "masse.csv")
    masse = load_export(str(pfad_masse))
    assert len(masse.trades) == 20
    assert masse.duplikate_entfernt == 0
    assert masse.identische_tradezeilen == 10
    assert sum(t.net for t in masse.trades) == 200.0


def test_parser_ohne_duplikate_zaehlt_null(tmp_path):
    pfad = _csv(tmp_path, [_trade("01", 100.0), _trade("02", -50.0)])
    parsed = load_export(pfad)
    assert len(parsed.trades) == 2
    assert parsed.duplikate_entfernt == 0
    assert parsed.identische_tradezeilen == 0


def test_ticketlose_lieferung_thg_wird_nicht_per_mengenheuristik_gekuerzt():
    """Ohne Ticketbeleg bleiben auch die 4.197 identischen THG-Zeilen erhalten."""
    pfad = str(Path(__file__).resolve().parents[1] / "data" / "trade_snapshots" /
               "c8c100a09a6b0a34c69f128d8dc29d868e59a187dd32d9d9a1a7e7249efceffe.csv")
    if not Path(pfad).exists():
        import pytest
        pytest.skip("Original-Lieferung nicht mehr im Cache")
    parsed = load_export(pfad)
    assert parsed.duplikate_entfernt == 0
    assert parsed.identische_tradezeilen == 4197
    assert len(parsed.trades) == 15340


def test_identische_positionen_erhoehen_offenes_risiko_und_realisierte_verluste(tmp_path):
    from mqlkiscanner.forensics import drawdown, exposure
    parsed = load_export(_csv(tmp_path, [_trade("01", -10.0)] * 20))
    dd = drawdown.run(parsed, kapitalbasis_usd=1000.0)
    risiko = exposure.run(parsed)
    assert dd["trading_dd"]["dd_pct_max_rel"] == 20.0
    assert risiko["peak_open_positions"] == 20
    assert abs(risiko["peak_net_lots"] - 2.0) < 1e-12


def test_night_scalper_realer_export_bleibt_299_positionen():
    pfad = Path(__file__).resolve().parents[1] / "data" / "trade_snapshots" / (
        "78dc2d20af837e3bf748a7bf08539b44baa02d86982decafe7e75cc1b404db78.csv")
    if not pfad.exists():
        import pytest
        pytest.skip("Realer Night-Scalper-Snapshot nicht vorhanden")
    parsed = load_export(str(pfad))
    assert len(parsed.trades) == 299
    assert parsed.identische_tradezeilen == 17
    assert abs(math.fsum(t.net for t in parsed.trades) - 2422.0) < 1e-9
