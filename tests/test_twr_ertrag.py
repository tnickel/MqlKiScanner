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
    # Zähler beim TWR-Wert: erster Monat 10 %, danach 3 % je Monat —
    # verteilt auf die EXAKTE Spanne (10.01.–10.12. ≈ 11 Monate), nicht auf
    # 12 angebrochene Kalendermonate (Copilot-Review 05.10. spät, Mittel 3).
    # rel=1e-5: die Gewinne stehen auf Cent gerundet in der CSV.
    assert eff["ertrag_monat_geom_pct"] == pytest.approx(
        ((1.10 * 1.03 ** 11) ** (1 / eff["dauer_monate"]) - 1) * 100.0, rel=1e-5)
    # Kern des Befunds: KEIN falsches Grün mehr — ~3,9 %/M ÷ 6 % DD < 1.
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


# ------- Zeitgenauer TWR (Copilot-Review 05.10. spaet, Hoch 2) ----------
def _trade_am(datum: str, gewinn: float) -> str:
    return (f"{datum} 10:00:00;Buy;0.10;XAUUSD;4000.00;0.10;"
            f"{datum} 12:00:00;4050.00;0;0;{gewinn:.2f}\n")


def _fluss_am(datum: str, betrag: float) -> str:
    return f"{datum} 18:00:00;Balance;;;;;;;;;{betrag:.2f}\n"


def _halbjahr(fluesse: list[str]) -> list[str]:
    """Basis 1.000 (übergeben), ~1.000 USD Gewinn je Monat (10 Trades à
    100 USD). Keine Start-Balance-Zeile: sie läge nach dem ersten Open."""
    zeilen = []
    for monat in range(1, 7):
        for tag in range(1, 28, 3):
            zeilen.append(_trade_am(f"2026.{monat:02d}.{tag:02d}", 100.0))
        zeilen.append(_trade_am(f"2026.{monat:02d}.27", 100.0))
    return zeilen + fluesse


def test_gewinnauszahlung_am_monatsende_blaeht_nicht_auf(tmp_path):
    """Vorher: 900 USD Auszahlung am 28. wirkte zum Monatsanfang — Jan
    1000 PnL ÷ 100 Stand = 1100 % → Calmar riesig → falsches Grün."""
    fluesse = [_fluss_am(f"2026.{m:02d}.28", -900.0) for m in range(1, 7)]
    serie = _monatsserie(load_export(_csv_pfad(tmp_path, _halbjahr(fluesse))), 1000.0)
    assert serie["2026-01"] == pytest.approx(100.0)
    # Feb: Start 1.100 nach Auszahlung → 1000/1100.
    assert serie["2026-02"] == pytest.approx(1000.0 / 1100.0 * 100.0)
    assert max(serie.values()) < 150.0


def test_vollauszahlung_des_gewinns_verliert_die_rendite_nicht(tmp_path):
    """Vorher: Stand am Monatsanfang ≤ 0 → leere Serie → Rendite fehlte."""
    fluesse = [_fluss_am(f"2026.{m:02d}.28", -1000.0) for m in range(1, 7)]
    serie = _monatsserie(load_export(_csv_pfad(tmp_path, _halbjahr(fluesse))), 1000.0)
    assert len(serie) == 6
    assert all(v == pytest.approx(100.0) for v in serie.values())


def test_einzahlung_wirkt_ab_ihrem_zeitpunkt_nicht_ab_monatsanfang(tmp_path):
    """Einzahlung 9.000 am 28.01.: Januar-Gewinn entstand auf 1.000
    (≈ 100 %), nicht auf 10.000 (vorher 10 % — wie Einzahlung am 1.)."""
    spaet = _monatsserie(load_export(_csv_pfad(
        tmp_path, _halbjahr([_fluss_am("2026.01.28", 9000.0)]))), 1000.0)
    assert spaet["2026-01"] == pytest.approx(100.0)
    assert spaet["2026-02"] == pytest.approx(1000.0 / 11000.0 * 100.0)
    frueh = _monatsserie(load_export(_csv_pfad(
        tmp_path, _halbjahr([_fluss_am("2026.01.01", 9000.0)]))), 1000.0)
    # Einzahlung am 01.01. abends: nur der erste Trade lag auf 1.000.
    assert frueh["2026-01"] == pytest.approx((1.1 * 11000.0 / 10100.0 - 1.0) * 100.0)
    assert frueh["2026-01"] < 25.0


def test_flusszweig_nutzt_exakte_spanne_wie_zweig_ohne_fluss(tmp_path):
    """Mittel 3: Ein Nullfluss erzwingt den TWR-Zweig; das Ergebnis muss
    dem Zweig ohne Fluss gleichen (vorher Kalendermonate statt Spanne)."""
    ohne = effizienz_kennzahlen(_csv_pfad(tmp_path, _halbjahr([])), 1000.0, 20.0)
    mit = effizienz_kennzahlen(_csv_pfad(
        tmp_path, _halbjahr([_fluss_am("2026.03.15", 0.0)])), 1000.0, 20.0)
    assert ohne["rendite_basis"] == "virtuelle_trade_netto_kurve"
    assert mit["rendite_basis"] == "twr_reale_kurve_monatsverkettung"
    assert mit["ertrag_monat_geom_pct"] == pytest.approx(ohne["ertrag_monat_geom_pct"], rel=1e-9)
    assert mit["cagr_jahr_pct"] == pytest.approx(ohne["cagr_jahr_pct"], rel=1e-9)


def test_forensik_version_entwertet_bestand_vor_calmar_gate():
    """Hoch 1: Bestand vor TWR-Fix/Mindesthistorie trägt keinen Status
    historie_zu_kurz — Version 13 erzwingt den Neu-Scan."""
    from mqlkiscanner.analysis_version import FORENSICS_VERSION
    assert FORENSICS_VERSION >= 13


# ------- Calmar-Schwelle einheitlich (Copilot-Review 05.10. spaet) -------
def test_min_calmar_schwelle_null_bleibt_ueberall_null():
    from mqlkiscanner import ampel_matrix, config, pipeline as pl
    assert config.min_calmar_jahr({"min_calmar_jahr": 0}) == 0.0
    assert config.min_calmar_jahr({}) == 3.0
    assert config.min_calmar_jahr(None) == 3.0
    assert config.min_calmar_jahr({"min_calmar_jahr": "x"}) == 3.0
    assert config.min_calmar_jahr({"min_calmar_jahr": float("nan")}) == 3.0
    assert config.min_calmar_jahr({"min_calmar_jahr": -2}) == 0.0
    settings = {"min_calmar_jahr": 0}
    assert "Mindest-Calmar (Grün-Gate): 0 pro Jahr" in pl._kriterien_text(settings)
    r = pl.ScanResult(id=1, name="Null", forensik_vorhanden=True)
    assert ampel_matrix.matrix_payload(r, settings)["grenzen"]["min_calmar_jahr"] == 0.0


