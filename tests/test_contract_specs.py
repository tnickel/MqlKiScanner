# -*- coding: utf-8 -*-
"""Kontraktspecs aus data/contract_specs.json: belegte Groessen statt Raten.

Die Spec-Datei ist im Test isolated (conftest): Jeder Test schreibt seine
eigenen Eintraege in tmp_path. Produktionswerte (Tickmill-Recherche) leben
in der echten Datei und werden hier nicht eingelesen — nur das Verhalten
der Engine gegenueber Spec-Eintraegen wird geprueft.
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from mqlkiscanner import symbols
from mqlkiscanner.forensics import exposure
from mqlkiscanner.models import BalanceRow, ParsedExport, Trade


def schreibe_specs(tmp_path: object, symbole: dict) -> None:
    """Schreibt contract_specs.json in den isolierten Datenordner."""
    path = tmp_path / "data" / "contract_specs.json"
    path.write_text(json.dumps({"symbols": symbole}, ensure_ascii=False),
                    encoding="utf-8")


def export_mit(symbol: str, lots: float = 1.0) -> ParsedExport:
    """Ein Trade + Startkapital, damit die Kapitalhistorie vollstaendig ist."""
    trade = Trade(open_time=datetime(2024, 1, 2, 10, 0),
                  close_time=datetime(2024, 1, 2, 11, 0),
                  direction="Buy", volume=lots, symbol=symbol,
                  entry_price=100.0, exit_price=101.0, profit=5.0)
    return ParsedExport(source_path="test", source_format="positions",
                        trades=[trade],
                        balances=[BalanceRow(time=datetime(2024, 1, 1, 9, 0),
                                             amount=1000.0)])


BTC_SPEC = {"contract_size": 1.0, "quote_currency": "USD", "class": "CRYPTO",
            "stress_move": 5000.0, "cross_broker": True,
            "source": "tickmill.com/instruments/btcusd"}


# ------------------------------------------------------------- Grundpfad
def test_spec_resolves_contract_and_shock(tmp_path):
    schreibe_specs(tmp_path, {"BTCUSD": BTC_SPEC})
    result = exposure.run(export_mit("BTCUSD", lots=2.0))
    assert result["contract_complete"] is True
    assert result["shock_usd"] == pytest.approx(2.0 * 5000.0 * 1.0)
    assert result["stress_move"] == 5000.0
    scenario = result["per_symbol_scenarios"]["BTCUSD"]
    assert scenario["contract_source"] == BTC_SPEC["source"]
    assert scenario["usd_conversion_available"] is True
    assert BTC_SPEC["source"] in result["spec_sources"]


def test_alias_and_broker_suffix_resolve(tmp_path):
    schreibe_specs(tmp_path, {"BTCUSD": {**BTC_SPEC, "aliases": ["BITCOIN"]}})
    result = exposure.run(export_mit("BITCOIN", lots=1.0))
    assert result["shock_usd"] == pytest.approx(5000.0)
    result = exposure.run(export_mit("BTCUSD.x", lots=1.0))
    assert result["shock_usd"] == pytest.approx(5000.0)
    assert symbols.normalize_symbol("BTCUSD.x") == "BTCUSD"


def test_cross_broker_false_needs_matching_broker(tmp_path):
    oel = {"contract_size": 1.0, "quote_currency": "USD", "stress_move": 10.0,
           "cross_broker": False, "brokers": ["tickmill"],
           "source": "tickmill.com/instruments/xtiusd"}
    schreibe_specs(tmp_path, {"XTIUSD": {**oel, "aliases": ["USOUSD"]}})
    # Passender Broker: Spec greift (Tickmill-Konvention 1 Barrel je Lot).
    ok = exposure.run(export_mit("USOUSD-ECN", lots=3.0), broker="Tickmill-EU-Live1")
    assert ok["shock_usd"] == pytest.approx(3.0 * 10.0 * 1.0)
    # Anderer Broker: Spec darf NICHT stillschweigend gelten (Faktor-100-Falle).
    with pytest.raises(ValueError, match="cross_broker=false"):
        exposure.run(export_mit("USOUSD-ECN"), broker="ICMarketsSC-Live23")
    # Kein Broker bekannt: ebenfalls verweigern.
    with pytest.raises(ValueError, match="cross_broker=false"):
        exposure.run(export_mit("USOUSD-ECN"))


def test_same_oil_alias_selects_matching_broker_variant(tmp_path):
    schreibe_specs(tmp_path, {
        "XTIUSD": {
            "contract_size": 1.0, "quote_currency": "USD", "stress_move": 10.0,
            "cross_broker": False, "brokers": ["tickmill"], "aliases": ["USOUSD"],
        },
        "USOUSD_VTMARKETS": {
            "contract_size": 1000.0, "quote_currency": "USD", "stress_move": 10.0,
            "cross_broker": False, "brokers": ["vtmarkets"], "aliases": ["USOUSD"],
        },
    })
    result = exposure.run(
        export_mit("USOUSD-ECN", lots=3.0), broker="VTMarkets-Live 2")
    assert result["shock_usd"] == pytest.approx(3.0 * 10.0 * 1000.0)
    assert result["per_symbol_scenarios"]["USOUSD"]["contract_source"] == \
        "contract_specs.json"


def test_non_usd_quote_stays_soft_refused(tmp_path):
    schreibe_specs(tmp_path, {"XAUEUR": {"contract_size": 100.0,
                                         "quote_currency": "EUR",
                                         "stress_move": 50.0,
                                         "unit_label": "EUR Kursbewegung"}})
    result = exposure.run(export_mit("XAUEUR", lots=1.0))
    # Kontrakt belegt, aber EUR-Quote: kein USD-Schock, nativer Betrag sichtbar.
    assert result["contract_complete"] is True
    assert result["conversion_complete"] is False
    assert result["shock_usd"] is None
    assert "EUR" in result["warnings"][0]
    scenario = result["per_symbol_scenarios"]["XAUEUR"]
    assert scenario["stress_quote_per_lot"] == pytest.approx(50.0 * 100.0)
    assert scenario["usd_conversion_available"] is False


def test_china50_index_convention_via_spec(tmp_path):
    schreibe_specs(tmp_path, {"CHINA50": {"contract_size": 1.0,
                                          "quote_currency": "USD",
                                          "stress_move": 500.0}})
    result = exposure.run(export_mit("CHINA50", lots=4.0))
    assert result["contract_complete"] is True
    assert result["shock_usd"] == pytest.approx(4.0 * 500.0 * 1.0)
    assert result["shock_formula"].endswith("= 2,000.00 USD")


# ----------------------------------------------------- Verweigerungsfaelle
def test_missing_spec_file_keeps_unknown_error(tmp_path):
    with pytest.raises(ValueError, match="Unbekannte Instrumente"):
        exposure.run(export_mit("BTCUSD"))


def test_spec_without_contract_size_is_ignored(tmp_path):
    schreibe_specs(tmp_path, {"BTCUSD": {"quote_currency": "USD"}})
    with pytest.raises(ValueError, match="Unbekannte Instrumente"):
        exposure.run(export_mit("BTCUSD"))


def test_broken_spec_json_counts_as_no_specs(tmp_path):
    path = tmp_path / "data" / "contract_specs.json"
    path.write_text("{kaputt", encoding="utf-8")
    with pytest.raises(ValueError, match="Unbekannte Instrumente"):
        exposure.run(export_mit("BTCUSD"))


# ------------------------------------------------------------ Einheiten
def test_spec_for_matching_rules(tmp_path):
    schreibe_specs(tmp_path, {"XTIUSD": {"contract_size": 1.0, "cross_broker": False,
                                         "brokers": ["tickmill"],
                                         "aliases": ["USOUSD"]}})
    # Suffix-Bereinigung + Broker-Match.
    assert symbols.spec_for("USOUSD-ECN", broker="Pepperstone-MT5") is None
    entry = symbols.spec_for("USOUSD-ECN", broker="tickmill global live")
    assert entry is not None and entry["contract_size"] == 1.0
    # Direktname ohne Broker: cross_broker=false verlangt immer einen Match.
    assert symbols.spec_for("XTIUSD") is None
    assert symbols.spec_for("XTIUSD", broker="Tickmill-EU") is not None
    # Diagnose-Probe ohne Broker-Pruefung findet den Eintrag trotzdem.
    assert symbols.spec_for("USOUSD-ECN", ignore_broker=True) is not None


def test_class_convention_still_wins_for_known_symbols(tmp_path):
    # XAUUSD hat Klassenkonvention 100; ein fehlender Spec-Eintrag aendert nichts.
    result = exposure.run(export_mit("XAUUSD", lots=1.0))
    assert result["shock_usd"] == pytest.approx(1.0 * 50.0 * 100.0)
    assert result["per_symbol_scenarios"]["XAUUSD"]["contract_source"] == "klassenkonvention"
