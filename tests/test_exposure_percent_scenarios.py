"""Prozent-Szenarien benutzen offene Entries des jeweiligen Signals."""
from datetime import datetime
from pathlib import Path

import pytest

from mqlkiscanner import config
from mqlkiscanner.forensics import exposure
from mqlkiscanner.models import BalanceRow, ParsedExport, Trade


@pytest.fixture(autouse=True)
def echte_specs(monkeypatch):
    monkeypatch.setattr(config, "CONTRACT_SPECS_FILE",
                        Path(__file__).resolve().parents[1] / "data" / "contract_specs.json")


def trade(price, lots=1, direction="Buy", opened=10, closed=11, symbol="CRVUSD"):
    return Trade(datetime(2026, 1, 5, opened), datetime(2026, 1, 5, closed),
                 direction, lots, symbol, price, price, 0)


def parsed(signal_id, *trades):
    result = ParsedExport(f"signal-{signal_id}.csv", "positions", trades=list(trades),
                          balances=[BalanceRow(datetime(2026, 1, 5, 9), 100000)])
    return result


@pytest.mark.parametrize("signal_id,price,direction", [
    (901234, 10, "Buy"), (901235, 30, "Sell"),
])
def test_andere_signal_ids_und_preise_bestimmen_ihr_eigenes_szenario(signal_id, price, direction):
    result = exposure.run(parsed(signal_id, trade(price, direction=direction)), broker="Vantage")
    scenario = result["per_symbol_scenarios"]["CRVUSD"]
    assert result["shock_usd"] == pytest.approx(price * .1 * 1000)
    assert result["stress_move"] == scenario["stress_move"] == pytest.approx(price * .1)
    assert scenario["reference_price"] == price
    assert scenario["stress_move_pct"] == 10
    assert scenario["stress_quote_per_lot"] == pytest.approx(price * .1 * 1000)


def test_volumengewichteter_entry_offener_positionen_und_expliziter_override():
    data = parsed(901236, trade(10), trade(30, lots=3))
    result = exposure.run(data, broker="Vantage")
    scenario = result["per_symbol_scenarios"]["CRVUSD"]
    assert scenario["reference_price"] == 25
    assert result["stress_move"] == scenario["stress_move"] == 2.5
    assert result["shock_usd"] == 10000
    absolute = exposure.run(data, stress_move=5, broker="Vantage")
    assert absolute["shock_usd"] == 20000
    assert absolute["stress_move"] == 5
    assert absolute["per_symbol_scenarios"]["CRVUSD"]["stress_move_pct"] is None


def test_spaetere_entries_veraendern_frueheren_schockpeak_nicht():
    result = exposure.run(parsed(901237, trade(10),
        trade(100000, lots=.000001, opened=12, closed=13)), broker="Vantage")
    assert result["shock_usd"] == 1000
    assert result["per_symbol_scenarios"]["CRVUSD"]["reference_price"] == 10
    assert result["stress_move"] == 1


def test_gleichzeitiger_hedge_bleibt_netto_null_ohne_formatierungsfehler():
    result = exposure.run(parsed(901238, trade(10), trade(30, direction="Sell")), broker="Vantage")
    assert result["shock_usd"] == 0
    assert result["peak_open_positions"] == 2
    assert result["per_symbol_scenarios"]["CRVUSD"]["reference_price"] == 20
    assert result["stress_move"] == 2


def test_teilhedge_verwendet_bruttovolumen_fuer_entry_und_nettovolumen_fuer_schock():
    result = exposure.run(parsed(901243, trade(10), trade(20, lots=.5, direction="Sell")),
                          broker="Vantage")
    scenario = result["per_symbol_scenarios"]["CRVUSD"]
    assert scenario["reference_price"] == pytest.approx(20 / 1.5)
    assert result["shock_usd"] == pytest.approx(666.67)
    assert result["stress_move"] == pytest.approx(scenario["reference_price"] * .1)


def test_entfernte_position_gehoert_nicht_zum_relativen_peak_entry():
    data = parsed(901244, trade(10, closed=11), trade(30, closed=12))
    data.balances.append(BalanceRow(datetime(2026, 1, 5, 11, 30), -99000))
    result = exposure.run(data, broker="Vantage")
    assert result["shock_usd"] == 4000
    assert result["per_symbol_scenarios"]["CRVUSD"]["reference_price"] == 20
    assert result["shock_pct_peak_usd"] == 3000
    assert result["shock_pct_peak_reference_prices"] == {"CRVUSD": 30}
    assert result["shock_pct_max"] == 300


def test_fremder_broker_erhaelt_keine_vantage_prozentspec():
    with pytest.raises(ValueError, match="cross_broker=false"):
        exposure.run(parsed(901239, trade(10)), broker="Tickmill")


def test_native_jpy_umrechnung_bleibt_zeitpunktbezogen(monkeypatch):
    monkeypatch.setattr(exposure.fx_rates, "usd_per", lambda quote, day:
                        {"rate": .01, "date": day.isoformat()} if quote == "JPY" else None)
    monkeypatch.setattr(exposure.fx_rates, "can_convert", lambda q: q == "JPY")
    result = exposure.run(parsed(901240, trade(10000, lots=2, symbol="BTCJPY")), broker="Vantage")
    assert result["shock_usd"] == 20
    scenario = result["per_symbol_scenarios"]["BTCJPY"]
    assert scenario["quote_currency"] == "JPY"
    assert scenario["stress_quote_per_lot"] == 1000


def test_eth_quote_ohne_umrechnung_bleibt_unbekannt(monkeypatch):
    monkeypatch.setattr(exposure.fx_rates, "usd_per", lambda *_: None)
    monkeypatch.setattr(exposure.fx_rates, "can_convert", lambda *_: False)
    result = exposure.run(parsed(901241, trade(30, symbol="BTCETH")), broker="Vantage")
    assert result["shock_usd"] is None
    assert result["conversion_complete"] is False
    assert result["per_symbol_scenarios"]["BTCETH"]["stress_quote_per_lot"] == 3


@pytest.mark.parametrize("price", [None, 0, -1, float("nan"), float("inf")])
def test_unbelegter_entry_erzeugt_keinen_nullschock(price):
    with pytest.raises(ValueError, match="Einstandspreise"):
        exposure.run(parsed(901242, trade(price)), broker="Vantage")
