"""Native FT contracts stay broker scoped and need dated USD conversion."""
from datetime import datetime
import json
from pathlib import Path

import pytest

from mqlkiscanner import config, symbols
from mqlkiscanner.forensics import exposure

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "doc/reviews/2026-10-18_identitaet_kontrakte_umsetzung/ft_terminal_spec.json"


@pytest.fixture(autouse=True)
def actual_contracts(monkeypatch):
    monkeypatch.setattr(config, "CONTRACT_SPECS_FILE", ROOT / "data/contract_specs.json")


@pytest.mark.parametrize("symbol,exact,quote,stress", [
    ("GER40FT", "GER40ft", "EUR", 500), ("UK100FT", "UK100ft", "GBP", 200)])
def test_native_ft_matches_exact_evidence_with_one_broker_authority(symbol, exact, quote, stress):
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    live = evidence["symbols"][exact]
    assert evidence["ok"] and not evidence["aliases_used"]
    assert evidence["terminal"]["broker_server"] == "VantageMarkets-Live 10"
    for broker in ("vantage", "VantageMarkets-Live 10", "Vantage International Group Limited"):
        spec = symbols.spec_for(symbol, broker=broker)
        assert spec["contract_size"] == live["trade_contract_size"] == 1
        assert spec["quote_currency"] == live["currency_profit"] == quote
        assert spec["stress_move"] == stress  # existing scenarios, not broker metadata
        assert spec["cross_broker"] is False and spec["brokers"] == ["vantage"]
        assert spec["aliases"] == [symbol]
        assert spec["terminal_symbol"] == exact
    # An unbound duplicate would silently make the foreign-broker path available.
    assert symbol not in symbols.load_specs()
    assert [key for key, spec in symbols.load_specs().items()
            if symbol in spec.get("aliases", [])] == [symbol + "_VANTAGE"]


@pytest.mark.parametrize("symbol", ["GER40FT", "UK100FT"])
@pytest.mark.parametrize("broker", [None, "", "Tickmill", "ActivTrades", "RoboForex", "Zulu"])
def test_missing_or_foreign_broker_never_gets_vantage_ft(symbol, broker):
    assert symbols.spec_for(symbol, broker=broker) is None
    assert exposure._resolve_symbol(symbol, broker=broker) is None


@pytest.mark.parametrize("symbol,currency,move", [("GER40FT", "EUR", 500), ("UK100FT", "GBP", 200)])
def test_ft_shock_uses_dated_fx_instead_of_fixed_usd_median(monkeypatch, symbol, currency, move):
    calls = []
    def dated_rate(quote, day):
        calls.append((quote, day))
        return {"rate": 1.1 if day.year == 2024 else 1.3}
    monkeypatch.setattr(exposure.fx_rates, "usd_per", dated_rate)
    for year, rate in ((2024, 1.1), (2025, 1.3)):
        day = datetime(year, 2, 5)
        state = {"complete": True, "missing": set()}
        amount, dominant = exposure._portfolio_shock({symbol: -2}, broker="vantage", when=day, fx_state=state)
        assert amount == pytest.approx(2 * move * rate)
        assert dominant == symbol and state["complete"]
    assert calls == [(currency, datetime(year, 2, 5).date()) for year in (2024, 2025)]
    assert exposure.shock_usd(1, move, symbol, broker="vantage") is None


@pytest.mark.parametrize("symbol,currency", [("GER40FT", "EUR"), ("UK100FT", "GBP")])
def test_ft_missing_fx_keeps_risk_unknown(monkeypatch, symbol, currency):
    monkeypatch.setattr(exposure.fx_rates, "usd_per", lambda *_: None)
    state = {"complete": True, "missing": set()}
    amount, _ = exposure._portfolio_shock({symbol: 1}, broker="vantage", when=datetime(2024, 2, 5), fx_state=state)
    assert amount is None
    assert state == {"complete": False, "missing": {f"{symbol} ({currency})"}}


def test_exact_ft_aliases_are_already_available_and_cash_remains_separate():
    terminal = r"C:\Forex\Mt5\Vantage\terminal64.exe"
    assert symbols.alias_fuer_symbol("GER40FT", terminal) == "GER40ft"
    assert symbols.alias_fuer_symbol("UK100FT", terminal) == "UK100ft"
    cash = symbols.spec_for("UK100", broker="Vantage")
    future = symbols.spec_for("UK100FT", broker="Vantage")
    assert cash is not future and cash["aliases"] == ["UK100"]
    assert "UK100FT" not in cash["aliases"]
