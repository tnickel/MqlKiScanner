# -*- coding: utf-8 -*-
"""EZB-Referenzkurse: belegte USD-Umrechnung zum Handelstag.

Die Tests schreiben eigene kleine ECB-CSVs (gleiches Format wie
eurofxref-hist.csv: ISO-Datum, Punkte-Dezimaltrenner, EUR-Basis) in den
isolierten Datenordner. Kein Netz: Der Download-Versuch wird abgefangen
(conftest) oder per Flag uebersprungen.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from mqlkiscanner import fx_rates, scoring
from mqlkiscanner.forensics import exposure
from mqlkiscanner.models import BalanceRow, ParsedExport, Trade

# 2024-01-03 ist ein Mittwoch (Handelstag); 06./07. = Wochenende.
ECB_CSV = """Date,USD,CAD,JPY
2024-01-02,1.0972,1.4523,144.20
2024-01-03,1.0960,1.4700,144.65
2024-01-04,1.0950,1.4650,145.10
"""


@pytest.fixture(autouse=True)
def ohne_download_versuch(monkeypatch):
    """Tests laden nie nach; die Tabelle kommt aus der Handgeschriebenen CSV."""
    monkeypatch.setattr(fx_rates, "_DOWNLOAD_TRIED", True)


def schreibe_kurse(tmp_path, text: str = ECB_CSV) -> None:
    ordner = tmp_path / "data" / "fx_rates"
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "eurofxref-hist.csv").write_text(text, encoding="utf-8")


def export_mit(symbol: str, lots: float = 1.0,
               tag: tuple = (2024, 1, 3)) -> ParsedExport:
    trade = Trade(open_time=datetime(*tag, 10, 0),
                  close_time=datetime(*tag, 11, 0),
                  direction="Buy", volume=lots, symbol=symbol,
                  entry_price=1.5000, exit_price=1.5020, profit=5.0)
    return ParsedExport(source_path="test", source_format="positions",
                        trades=[trade],
                        balances=[BalanceRow(datetime(2024, 1, 2, 9, 0),
                                             amount=1000.0)])


# ------------------------------------------------------------- Kurs-Modul
def test_cross_rate_is_derived_from_two_documented_ecb_rates(tmp_path):
    schreibe_kurse(tmp_path)
    fx = fx_rates.usd_per("CAD", date(2024, 1, 3))
    # 1 CAD = (EUR/USD) / (EUR/CAD) = 1.0960 / 1.4700 USD am selben Tag.
    assert fx["rate"] == pytest.approx(1.0960 / 1.4700)
    assert fx["date"] == "2024-01-03"


def test_weekend_walks_back_to_last_published_day(tmp_path):
    schreibe_kurse(tmp_path)
    fx = fx_rates.usd_per("CAD", date(2024, 1, 6))   # Samstag
    assert fx["date"] == "2024-01-04"
    assert fx["rate"] == pytest.approx(1.0950 / 1.4650)


def test_gaps_and_unknowns_stay_unknown(tmp_path):
    schreibe_kurse(tmp_path)
    assert fx_rates.usd_per("CHF", date(2024, 1, 3)) is None      # nicht in Datei
    assert fx_rates.usd_per("CAD", date(2024, 1, 20)) is None     # > 10 Tage Luecke
    assert fx_rates.usd_per("CAD", date(2023, 12, 1)) is None     # vor erstem Kurs
    assert fx_rates.usd_per("USD", date(2024, 1, 3))["rate"] == 1.0


def test_real_ecb_file_is_newest_first_and_gets_sorted(tmp_path):
    """Die offizielle eurofxref-hist.csv beginnt mit dem NEUESTEN Tag."""
    text = ("Date,USD,CAD\n"
            "2024-01-04,1.0950,1.4650\n"
            "2024-01-03,1.0960,1.4700\n"
            "2024-01-02,1.0972,1.4523\n")
    schreibe_kurse(tmp_path, text)
    fx = fx_rates.usd_per("CAD", date(2024, 1, 4))
    assert fx["date"] == "2024-01-04"
    assert fx["rate"] == pytest.approx(1.0950 / 1.4650)
    assert fx_rates.status()["letzte_kursdatum"] == "2024-01-04"


def test_eur_reads_directly_from_usd_column(tmp_path):
    """EUR ist die EZB-Basiswaehrung (keine eigene Spalte): 1 EUR = USD-Spalte."""
    schreibe_kurse(tmp_path)
    fx = fx_rates.usd_per("EUR", date(2024, 1, 3))
    assert fx == {"rate": 1.0960, "date": "2024-01-03"}
    assert fx_rates.usd_per("EUR", date(2024, 1, 6))["date"] == "2024-01-04"
    assert fx_rates.can_convert("EUR") is True
    assert fx_rates.can_convert("CHF") is False      # nicht in der Testdatei


def test_eur_quoted_spec_symbol_becomes_convertible(tmp_path):
    """XAUEUR/DE40 (EUR-Quote) duerfen mit Kursdatei nicht mehr gesperrt sein."""
    import json
    specs = tmp_path / "data" / "contract_specs.json"
    specs.write_text(json.dumps({"symbols": {"XAUEUR": {
        "contract_size": 100.0, "quote_currency": "EUR", "stress_move": 50.0}}}),
        encoding="utf-8")
    schreibe_kurse(tmp_path)
    result = exposure.run(export_mit("XAUEUR", lots=2.0))
    native = 2.0 * 50.0 * 100.0                      # 10.000 EUR
    assert result["conversion_complete"] is True
    assert result["shock_usd"] == pytest.approx(native * 1.0960)
    prov = result["fx_conversion"]["kurse_am_flag_peak"]["XAUEUR"]
    assert prov["ezb_kursdatum"] == "2024-01-03"
    scenario = result["per_symbol_scenarios"]["XAUEUR"]
    assert scenario["usd_conversion_available"] is True


# --------------------------------------------- Exposure-End-to-End-Umrechnung
def test_fx_cross_shock_is_converted_with_documented_rate(tmp_path):
    schreibe_kurse(tmp_path)
    result = exposure.run(export_mit("EURCAD", lots=1.0))
    native = 1.0 * 0.05 * 100_000          # 500 Pips Schock, 1 Lot -> 5.000 CAD
    assert result["conversion_complete"] is True
    assert result["shock_usd"] == pytest.approx(native * (1.0960 / 1.4700), rel=1e-6)
    prov = result["fx_conversion"]["kurse_am_flag_peak"]["EURCAD"]
    assert prov["ezb_kursdatum"] == "2024-01-03"
    assert result["fx_conversion"]["quelle"].startswith("EZB")
    assert result["warnings"] == []


def test_full_forensics_gate_opens_with_rates(tmp_path):
    schreibe_kurse(tmp_path)
    report = {"stats": {"trades": 1},
              "forensics": {"martingale": {"flag": False},
                            "exposure": exposure.run(export_mit("NZDCAD", lots=1.0)),
                            "stops": {"stop_evidence": "none"},
                            "drawdown": {"test": "drawdown"}}}
    assert scoring.evaluate(report)["forensics_complete"] is True


def test_mixed_portfolio_sums_converted_and_usd_symbols(tmp_path):
    schreibe_kurse(tmp_path)
    gold = Trade(open_time=datetime(2024, 1, 3, 10),
                 close_time=datetime(2024, 1, 3, 11),
                 direction="Sell", volume=1.0, symbol="XAUUSD",
                 entry_price=2050.0, exit_price=2051.0, profit=-100.0)
    parsed = ParsedExport(source_path="test", source_format="positions",
                          trades=[gold, export_mit("NZDCAD", lots=1.0).trades[0]],
                          balances=[BalanceRow(datetime(2024, 1, 2, 9, 0),
                                               amount=10000.0)])
    result = exposure.run(parsed)
    cad_in_usd = 1.0 * 0.05 * 100_000 * (1.0960 / 1.4700)
    gold_usd = 1.0 * 50.0 * 100.0
    assert result["shock_usd"] == pytest.approx(gold_usd + cad_in_usd, rel=1e-6)


# ------------------------------------------------------- Verweigerungsfaelle
def test_no_deposits_before_first_trade_names_the_reason(tmp_path, monkeypatch):
    """Belegfall Signal #2308093: Startkapital 0 -> konkrete Warnung."""
    trade = Trade(open_time=datetime(2024, 1, 3, 10),
                  close_time=datetime(2024, 1, 3, 11),
                  direction="Buy", volume=1.0, symbol="EURUSD",
                  entry_price=1.1, exit_price=1.1001, profit=5.0)
    parsed = ParsedExport(source_path="t", source_format="positions",
                          trades=[trade],
                          balances=[BalanceRow(datetime(2024, 2, 1), 500.0)])  # spaeter
    result = exposure.run(parsed)
    assert result["capital_history_complete"] is False
    assert result["temporal_risk_available"] is False
    assert any("Kapitalbasis unbekannt" in w for w in result["warnings"])


def test_withdrawal_during_trading_names_the_reason(tmp_path):
    """Belegfall Signal #1496203: Auszahlung treibt Konto unter 0."""
    trades = [Trade(open_time=datetime(2024, 1, 2, 10),
                    close_time=datetime(2024, 1, 5, 11),
                    direction="Buy", volume=1.0, symbol="EURUSD",
                    entry_price=1.1, exit_price=1.1001, profit=5.0)]
    parsed = ParsedExport(source_path="t", source_format="positions",
                          trades=trades,
                          balances=[BalanceRow(datetime(2024, 1, 1), 500.0),
                                    BalanceRow(datetime(2024, 1, 3), -1000.0)])
    result = exposure.run(parsed)
    assert result["capital_history_complete"] is True
    assert result["temporal_risk_available"] is False
    assert any("Kontostand war bei offenen Positionen <= 0" in w
               for w in result["warnings"])


def test_without_rates_file_fx_cross_stays_refused(tmp_path, monkeypatch):
    result = exposure.run(export_mit("EURCAD", lots=1.0))
    assert result["conversion_complete"] is False
    assert result["shock_usd"] is None
    assert "EZB" in result["warnings"][0]
    assert "nicht verfuegbar" in result["warnings"][0]


def test_broken_rates_file_counts_as_absent(tmp_path):
    ordner = tmp_path / "data" / "fx_rates"
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "eurofxref-hist.csv").write_text("kaputt", encoding="utf-8")
    result = exposure.run(export_mit("EURCAD", lots=1.0))
    assert result["conversion_complete"] is False
    assert result["shock_usd"] is None


def test_trade_day_before_history_stays_refused(tmp_path):
    schreibe_kurse(tmp_path)
    result = exposure.run(export_mit("EURCAD", lots=1.0,
                                     tag=(2023, 11, 15)))
    assert result["conversion_complete"] is False
    assert result["shock_usd"] is None


def test_usd_period_before_fx_addition_downgrades_flag_consistently(tmp_path):
    """Signal haendet zuerst Gold (USD), spaeter dazu EURCAD ohne Kurse:
    temporal_risk_available muss mit conversion_complete zusammen fallen —
    ein frueherer Gold-Schock darf nicht als verfuegbar durchrutschen."""
    gold = Trade(open_time=datetime(2024, 1, 3, 10),
                 close_time=datetime(2024, 1, 3, 11),
                 direction="Sell", volume=1.0, symbol="XAUUSD",
                 entry_price=2050.0, exit_price=2051.0, profit=-100.0)
    eurcad = Trade(open_time=datetime(2024, 2, 1, 10),   # nach Kurshistorie-Ende
                   close_time=datetime(2024, 2, 1, 11),
                   direction="Buy", volume=1.0, symbol="EURCAD",
                   entry_price=1.45, exit_price=1.448, profit=-8.0)
    parsed = ParsedExport(source_path="test", source_format="positions",
                          trades=[gold, eurcad],
                          balances=[BalanceRow(datetime(2024, 1, 2, 9, 0),
                                               amount=10000.0)])
    result = exposure.run(parsed)
    assert result["conversion_complete"] is False
    assert result["temporal_risk_available"] is False
    assert result["shock_pct_max"] is None


# ------------------------------------------------------------ Parser-Diagnose
def test_ecb_csv_with_na_and_trailing_columns_parses(tmp_path):
    text = ("Date,USD,CAD,XXXX,\n"
            "2024-01-03,1.0960,N/A,9.9,\n"
            ",,,,,,,,,,,\n")
    schreibe_kurse(tmp_path, text)
    assert fx_rates.usd_per("CAD", date(2024, 1, 3)) is None  # N/A -> kein Kurs
    assert fx_rates.usd_per("XXXX", date(2024, 1, 3))["rate"] == pytest.approx(1.0960 / 9.9)


# --------------------------------------------------- Inhaltsbasierte Auffrischung
def _zip_antwort(csv_text: str):
    """requests.get-Ersatz: echte ZIP-Antwort mit einer ECB-CSV."""
    import io as _io
    import zipfile as _zip

    buffer = _io.BytesIO()
    with _zip.ZipFile(buffer, "w") as archive:
        archive.writestr("eurofxref-hist.csv", csv_text)
    buffer.seek(0)

    class Antwort:
        content = buffer.getvalue()

        def raise_for_status(self):
            return None

    return Antwort()


def test_veraltete_datei_wird_nachgeladen(tmp_path, monkeypatch):
    """Belegfall 20.09.2026: Datei endet 2024, heutige Trades brauchen Kurse —
    die inhaltsbasierte Pruefung muss den Download ausloesen."""
    monkeypatch.setattr(fx_rates, "_DOWNLOAD_TRIED", False)
    schreibe_kurse(tmp_path)  # Kurse enden 2024-01-04
    frisch = ("Date,USD,CAD\n"
              f"{date.today().isoformat()},1.0900,1.4600\n")
    aufgerufen = []
    monkeypatch.setattr(fx_rates.requests, "get",
                        lambda url, timeout: aufgerufen.append(url)
                        or _zip_antwort(frisch))
    fx_rates.load()
    assert aufgerufen, "Veraltete Datei hat keinen Download ausgeloest"
    status = fx_rates.status()
    assert status["letzte_kursdatum"] == date.today().isoformat()
    fx = fx_rates.usd_per("CAD", date.today())
    assert fx is not None and fx["date"] == date.today().isoformat()


def test_frische_datei_loest_keinen_download_aus(tmp_path, monkeypatch):
    heutiger_kurs = ("Date,USD,CAD\n"
                     f"{date.today().isoformat()},1.0900,1.4600\n")
    schreibe_kurse(tmp_path, heutiger_kurs)

    def verweigert(*args, **kwargs):
        raise AssertionError("Download haette nicht ausgeloest werden duerfen")

    monkeypatch.setattr(fx_rates.requests, "get", verweigert)
    monkeypatch.setattr(fx_rates, "_DOWNLOAD_TRIED", False)
    fx = fx_rates.usd_per("CAD", date.today())
    assert fx is not None and fx["date"] == date.today().isoformat()


def test_download_fehler_laesst_alte_datei_und_tabelle_bestehen(tmp_path, monkeypatch):
    monkeypatch.setattr(fx_rates, "_DOWNLOAD_TRIED", False)
    schreibe_kurse(tmp_path)

    def scheitert(*args, **kwargs):
        raise ConnectionError("offline")

    monkeypatch.setattr(fx_rates.requests, "get", scheitert)
    fx = fx_rates.usd_per("CAD", date(2024, 1, 3))
    assert fx is not None and fx["date"] == "2024-01-03"
    assert fx_rates.status()["letzte_kursdatum"] == "2024-01-04"


def test_datei_letzter_kurstag_liest_erste_datenzeile(tmp_path):
    schreibe_kurse(tmp_path, "Date,USD\n2024-01-09,1.09\n2024-01-08,1.08\n")
    assert fx_rates._datei_letzter_kurstag(
        tmp_path / "data" / "fx_rates" / "eurofxref-hist.csv") == date(2024, 1, 9)
