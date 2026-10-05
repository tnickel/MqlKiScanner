# -*- coding: utf-8 -*-
"""TWR-Zähler bei Kapitalflüssen (Copilot-Review 05.10. abends, Hoch 1).

Vorher: ertrag_monat_geom_pct = (Start + Σ netto)/Start^(1/M) auf der
VIRTUELLEN Kurve, während der Max-DD-Nenner auf der REALEN Kurve (mit
Einzahlungen) stand. Gewinne auf EINGEZAHLTEM Geld zählten als Rendite auf
das kleine Startkapital — TrueRetDD konnte über 1,0 gehoben werden und
falsches Grün freischalten. Jetzt verkettet der Zähler die TWR-
Monatsrenditen der realen Kurve: Einzahlung = Nenner-Erhöhung, kein Gewinn.
"""
import math

import pytest

from mqlkiscanner.parser import load_export
from mqlkiscanner.portfolio_statistik import _monatsserie, effizienz_kennzahlen, monatsrenditen


def _csv_pfad(tmp_path, zeilen: list[str]) -> str:
    pfad = tmp_path / "twr.csv"
    pfad.write_text(
        "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
        + "".join(zeilen), encoding="utf-8")
    return str(pfad)


def _trade(monat: str, gewinn: float) -> str:
    return (f"2026.{monat}.10 10:00:00;Buy;0.10;XAUUSD;4000.00;0.10;"
            f"2026.{monat}.10 12:00:00;4050.00;0;0;{gewinn:.2f}\n")


def _balance(monat: str, betrag: float) -> str:
    # MT5-Positions-Format: Betrag in der Profit-Spalte (Index 10)
    return f"2026.{monat}.05 08:00:00;Balance;;;;;;;;;{betrag:.2f}\n"


def test_einzahlung_zaehlt_nicht_als_rendite_twrmuster(tmp_path):
    """Reviewer-Rechenbeispiel: Start 1.000, +9.000 Einzahlung, danach
    ~3 %/M auf dem großen Kapital, DD 6 %. Vorher ergab der virtuelle
    Zähler ~15 %/M → TrueRetDD ~2,5 → GRÜN. TWR ergibt ~3 %/M → 0,5."""
    zeilen = [_balance("01", 1000.0), _trade("01", 100.0)]   # +10 % auf 1.000
    stand = 1100.0
    for monat in ("02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"):
        if monat == "02":
            zeilen.append(_balance("02", 9000.0))            # Einzahlung
            stand += 9000.0
        gewinn = stand * 0.03
        zeilen.append(_trade(monat, gewinn))
        stand += gewinn
    pfad = _csv_pfad(tmp_path, zeilen)
    eff = effizienz_kennzahlen(pfad, 1000.0, dd_max_pct=6.0)
    assert eff is not None
    assert eff["kapitalfluesse_nach_start"] == 1
    assert eff["rendite_basis"] == "twr_reale_kurve_monatsverkettung"
    # Zähler beim TWR-Wert: erster Monat 10 %, danach 3 % je Monat.
    assert eff["ertrag_monat_geom_pct"] == pytest.approx(
        ((1.10 * 1.03 ** 11) ** (1 / 12) - 1) * 100.0, rel=0.01)
    # Kern des Befunds: KEIN falsches Grün mehr — ~3,2 %/M ÷ 6 % DD < 1.
    assert eff["retdd_monat"] == pytest.approx(
        eff["ertrag_monat_geom_pct"] / 6.0)
    assert eff["retdd_monat"] < 1.0


def test_monatsserie_bucht_flow_als_nenner_nicht_als_gewinn(tmp_path):
    zeilen = [_balance("01", 1000.0), _trade("01", 100.0),
              _balance("02", 9000.0), _trade("02", 330.0)]
    pfad = _csv_pfad(tmp_path, zeilen)
    parsed = load_export(pfad)
    serie = _monatsserie(parsed, 1000.0)
    assert serie["2026-01"] == pytest.approx(10.0)
    # 330 auf 10.100 (1.000 + 100 + 9.000): ~3,27 % — NICHT 330/1.100 = 30 %.
    assert serie["2026-02"] == pytest.approx(330.0 / 10100.0 * 100.0)
    assert not math.isclose(serie["2026-02"], 30.0, abs_tol=0.5)


def test_ohne_flows_bleibt_die_bisherige_rendite_exakt(tmp_path):
    """Kein Verhaltenbruch für die Mehrheit: ohne Balance-Rows rechnet der
    Zähler weiter wie bisher (virtuell == real). Spanne über 5 Monate —
    unter 3 Monaten gilt seit 05.10. historie_zu_kurz (kein RetDD)."""
    zeilen = [_balance("01", 1000.0), _trade("01", 100.0), _trade("02", 110.0),
              _trade("03", 121.0), _trade("04", 133.1), _trade("05", 146.41)]
    pfad = _csv_pfad(tmp_path, zeilen)
    eff = effizienz_kennzahlen(pfad, 1000.0, dd_max_pct=10.0)
    assert eff["rendite_basis"] == "virtuelle_trade_netto_kurve"
    netto = 100.0 + 110.0 + 121.0 + 133.1 + 146.41
    erwartet = ((1 + netto / 1000.0) ** (1 / eff["dauer_monate"]) - 1) * 100.0
    assert eff["ertrag_monat_geom_pct"] == pytest.approx(erwartet, rel=1e-6)
    assert eff["retdd_monat"] == pytest.approx(erwartet / 10.0, rel=1e-6)


def test_monatsrenditen_und_vorstufe_nutzen_dieselbe_serie(tmp_path):
    zeilen = [_balance("01", 1000.0), _trade("01", 100.0),
              _balance("02", 9000.0), _trade("02", 330.0)]
    pfad = _csv_pfad(tmp_path, zeilen)
    parsed = load_export(pfad)
    assert monatsrenditen(pfad, 1000.0) == _monatsserie(parsed, 1000.0)


# ---------------- Mindesthistorie (Nutzer-Regel 05.10., Übergabe) --------
def test_zehn_tage_historie_kein_retdd_kein_gruen(tmp_path):
    """Übergabe-Rechenbeispiel: 10 k Start, +400 USD in 10 Tagen, DD 2 % —
    vorher geom. ~12,7 %/M -> RetDD 6,3 -> GRÜN. Jetzt: historie_zu_kurz,
    Ertrag bleibt sichtbar, aber kein Gate-Wert."""
    zeilen = ["2026.01.05 10:00:00;Buy;0.10;XAUUSD;4000.00;0.10;"
              "2026.01.15 12:00:00;4050.00;0;0;400.00\n"]
    pfad = _csv_pfad(tmp_path, zeilen)
    eff = effizienz_kennzahlen(pfad, 10_000.0, dd_max_pct=2.0)
    assert eff["effizienz_status"] == "historie_zu_kurz"
    assert eff["ertrag_monat_geom_pct"] is not None   # Anzeige bleibt
    assert eff["retdd_monat"] is None and eff["retdd_jahr"] is None


def test_exakt_drei_monate_sind_berechenbar(tmp_path):
    """Grenze: ab 3 Monaten Trade-Spanne gibt es wieder einen Calmar."""
    zeilen = ["2026.01.05 10:00:00;Buy;0.10;XAUUSD;4000.00;0.10;"
              "2026.01.05 12:00:00;4050.00;0;0;100.00\n",
              "2026.04.07 10:00:00;Buy;0.10;XAUUSD;4000.00;0.10;"
              "2026.04.07 12:00:00;4050.00;0;0;100.00\n"]
    pfad = _csv_pfad(tmp_path, zeilen)
    eff = effizienz_kennzahlen(pfad, 1000.0, dd_max_pct=10.0)
    assert eff["effizienz_status"] != "historie_zu_kurz"
    assert eff["retdd_jahr"] is not None


def test_kurze_historie_sperrt_auch_den_vorbehalt():
    """Übergabe: kein retdd_*_vorbehalt bei historie_zu_kurz — auch nach
    DB-artigem Reload über refresh_efficiency nicht."""
    from mqlkiscanner import pipeline as pl
    r = pl.ScanResult(id=1, name="Kurz", forensik_vorhanden=True,
                      ertrag_monat_geom_pct=12.7, cagr_jahr_pct=800.0,
                      equity_dd_rekonstruiert_pct=None,
                      equity_dd_rekon_roh_pct=2.0,
                      equity_rekon_grund="duenne Daten",
                      effizienz_befund={"effizienz_status": "historie_zu_kurz"})
    row = r.to_row()
    assert row["TrueRetDD"] is None
    assert row["TrueRetDD (Vorbehalt)"] is None
    ampel, urteil = pl.ampel_for(r, {})
    assert ampel == "🟡"
    assert "unter 3 Monaten" in urteil


