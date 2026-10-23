"""Remaining exact Vantage contracts and non-ECB exposure fail-closed rules."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from mqlkiscanner import config, fx_rates, symbols
from mqlkiscanner.forensics import exposure
from mqlkiscanner.forensics.exposure_fx import ExposureUsdUmrechnung
from mqlkiscanner.models import BalanceRow, ParsedExport, Trade

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("symbol,exact,factor,quote", [
    ("NIKKEI225", "Nikkei225", 1, "JPY"), ("SOYBEAN-C", "Soybean-C", 500, "USD")])
def test_new_contracts_match_exact_terminal_proof(monkeypatch, symbol, exact, factor, quote):
    monkeypatch.setattr(config, "CONTRACT_SPECS_FILE", ROOT / "data/contract_specs.json")
    evidence = json.loads((ROOT / "doc/reviews/2026-10-18_tradeserver_v2_liveabschluss/contracts_terminal_spec.json").read_text())
    assert evidence["ok"] and not evidence["terminal_running_after_cleanup"]
    assert evidence["terminal"]["broker_server"] == "VantageMarkets-Live 10"
    contract = symbols.spec_for(symbol, broker="Vantage")
    assert contract["contract_size"] == evidence["symbols"][symbol]["trade_contract_size"] == factor
    assert contract["quote_currency"] == evidence["symbols"][symbol]["currency_profit"] == quote
    assert contract["terminal_symbol"] == evidence["symbols"][symbol]["name"] == exact
    assert symbols.alias_fuer_symbol(symbol, r"C:\Forex\Mt5\Vantage\terminal64.exe") == exact
    assert contract["cross_broker"] is False
    for broker in (None, "", "Tickmill", "RoboForex"):
        assert symbols.spec_for(symbol, broker=broker) is None


def sample(symbol="USDCNH", quote="CNH", *, offset_h=0, flat=False, bad_feed=False,
           missing_prior=False, server_unknown=False, wrong_close=False):
    day = datetime(2024, 1, 3)
    def price(hour):
        return 11.0 if flat else 1.0 + hour
    def bar(hour, close):
        return {"time": int((day + timedelta(hours=hour)).replace(tzinfo=timezone.utc).timestamp()),
                "open": close, "high": close + .001, "low": close - .001, "close": close}
    own = [bar(h, price(h)) for h in range(24)]
    conversion = [bar(h, 2000 + h) for h in range(24) if not (missing_prior and h == 9)]
    if missing_prior and quote == "CNH":
        own = [b for b in own if b["time"] != bar(9, 1)["time"]]
    trade = Trade(open_time=day + timedelta(hours=10-offset_h, minutes=15),
                  close_time=day + timedelta(hours=12-offset_h, minutes=15),
                  direction="Buy", volume=1, symbol=symbol,
                  entry_price=price(10), exit_price=1000 if wrong_close else price(12), profit=1)
    parsed = ParsedExport("test", "positions", [trade], balances=[BalanceRow(day, 10000)])
    class Provider:
        terminal_idx = 0
        changed = False
        def _feed_identitaet(self):
            return "installation", (None if server_unknown else
                                    '["terminal-A","server-B"]' if self.changed else '["terminal-A","server-A"]')
        def hole_h1(self, requested, low, high):
            if requested == symbol:
                return own
            if requested == quote + "USD":
                self.changed = bad_feed
                return conversion
            return None
    resolutions = {symbol: {"quote": quote}}
    return parsed, Provider(), resolutions


@pytest.mark.parametrize("offset_h", [-3, 0, 2])
def test_cnh_uses_own_inverse_prior_close_with_price_proven_offset(offset_h):
    parsed, provider, resolved = sample(offset_h=offset_h)
    converter = ExposureUsdUmrechnung(parsed, provider, resolved)
    result = converter.rate("CNH", parsed.trades[0].open_time, "USDCNH")
    assert result["rate"] == pytest.approx(1 / 10)
    assert result["time_basis_gmt_h"] == offset_h
    assert result["bar_end_utc"] == "2024-01-03T10:00:00+00:00"
    assert "server-A" in result["feed"]


def test_eth_uses_direct_usd_close_of_same_serverfeed():
    parsed, provider, resolved = sample("BTCETH", "ETH")
    converter = ExposureUsdUmrechnung(parsed, provider, resolved)
    result = converter.rate("ETH", parsed.trades[0].open_time, "BTCETH")
    assert result["rate"] == 2009  # bar09 closes10; bar10 close2010 is still future
    assert result["conversion_symbol"] == "ETHUSD"


@pytest.mark.parametrize("options", [
    {"flat": True}, {"bad_feed": True}, {"missing_prior": True},
    {"server_unknown": True}, {"wrong_close": True}])
def test_missing_ambiguous_cross_server_or_unproven_rates_stay_unknown(options):
    parsed, provider, resolved = sample("BTCETH", "ETH", **options)
    converter = ExposureUsdUmrechnung(parsed, provider, resolved)
    assert converter.rate("ETH", parsed.trades[0].open_time, "BTCETH") is None


def test_cnh_missing_prior_close_never_uses_future_or_cny_rate():
    parsed, provider, resolved = sample(missing_prior=True)
    converter = ExposureUsdUmrechnung(parsed, provider, resolved)
    assert converter.rate("CNH", parsed.trades[0].open_time, "USDCNH") is None
    assert converter.rate("CNY", parsed.trades[0].open_time, "USDCNH") is None
    assert converter.rate("CNH", parsed.trades[0].open_time, "EURCNH") is None


def test_quiet_cnh_can_use_common_clock_proved_by_same_export_feed():
    parsed, provider, resolved = sample(flat=True)
    day = datetime(2024, 1, 3)
    parsed.trades.append(Trade(open_time=day + timedelta(hours=10, minutes=15),
        close_time=day + timedelta(hours=12, minutes=15), direction="Buy", volume=1,
        symbol="XAUUSD", entry_price=2000, exit_price=2200, profit=1))
    original_loader = provider.hole_h1
    def loader(name, low, high):
        if name == "XAUUSD":
            return [{"time": int((day + timedelta(hours=h)).replace(tzinfo=timezone.utc).timestamp()),
                "open": 1000 + h * 100, "close": 1000 + h * 100,
                "low": 1000 + h * 100 - .1, "high": 1000 + h * 100 + .1}
                for h in range(24)]
        return original_loader(name, low, high)
    provider.hole_h1 = loader
    converter = ExposureUsdUmrechnung(parsed, provider, resolved)
    result = converter.rate("CNH", parsed.trades[0].open_time, "USDCNH")
    assert result["rate"] == pytest.approx(1 / 11)
    assert result["time_basis_gmt_h"] == 0


def test_provider_path_without_broker_server_is_no_feed_proof():
    parsed, provider, resolved = sample()
    provider._feed_identitaet = None
    converter = ExposureUsdUmrechnung(parsed, provider, resolved)
    assert converter.rate("CNH", parsed.trades[0].open_time, "USDCNH") is None


@pytest.mark.parametrize("bad_close", [0, -1, float("nan"), float("inf"), True])
def test_invalid_conversion_close_stays_unknown(bad_close):
    parsed, provider, resolved = sample("BTCETH", "ETH")
    original_loader = provider.hole_h1
    def loader(symbol, low, high):
        bars = original_loader(symbol, low, high)
        if symbol == "ETHUSD":
            for bar in bars:
                bar["close"] = bad_close
        return bars
    provider.hole_h1 = loader
    converter = ExposureUsdUmrechnung(parsed, provider, resolved)
    assert converter.rate("ETH", parsed.trades[0].open_time, "BTCETH") is None


def test_exposure_accepts_complete_h1_cnh_and_emits_h1_provenance(monkeypatch):
    monkeypatch.setattr(fx_rates, "_DOWNLOAD_TRIED", True)
    parsed, provider, _ = sample()
    result = exposure.run(parsed, kursanbieter=provider)
    assert result["conversion_complete"] is True
    assert result["shock_usd"] == 500
    assert result["per_symbol_scenarios"]["USDCNH"]["usd_conversion_available"] is True
    provenance = result["fx_conversion"]["kurse_am_flag_peak"]["USDCNH"]
    assert provenance["ezb_kursdatum"] is None
    assert provenance["conversion_symbol"] == "USDCNH"
    assert provenance["bar_end_utc"] == "2024-01-03T10:00:00+00:00"
    assert result["fx_conversion"]["h1_umrechnung"]["verwendete_ereignisse"] == 1


def test_no_provider_keeps_cnh_unknown_even_with_cny_ecb(monkeypatch):
    monkeypatch.setattr(fx_rates, "load", lambda: {"USD": (["2024-01-03"], [1.1]),
                                                 "CNY": (["2024-01-03"], [7.8])})
    parsed, _, _ = sample()
    result = exposure.run(parsed)
    assert result["shock_usd"] is None and result["conversion_complete"] is False


def test_engine_forwards_its_provider_to_exposure(monkeypatch):
    from mqlkiscanner import engine
    parsed, provider, _ = sample()
    monkeypatch.setattr(engine.parser, "load_export", lambda *a, **k: parsed)
    observed = []
    def calculate(p, **kwargs):
        observed.append(kwargs.get("kursanbieter"))
        return {"conversion_complete": False, "per_symbol_scenarios": {"USDCNH": {"quote_currency": "CNH"}}}
    monkeypatch.setattr(engine.exposure, "run", calculate)
    monkeypatch.setattr(engine.equity_rekonstruktion, "rekonstruiere", lambda *a, **k: observed.append("equity") or {})
    engine.analyze("test", kursanbieter=provider)
    assert observed == [None, "equity", provider]


def test_unproven_contract_is_rejected_before_course_access(monkeypatch):
    from mqlkiscanner import engine
    parsed, provider, _ = sample("NO_SUCH_INSTRUMENT", "CNH")
    monkeypatch.setattr(engine.parser, "load_export", lambda *a, **k: parsed)
    def forbidden(*args, **kwargs):
        raise AssertionError("No course access before contract validation")
    provider.hole_h1 = forbidden
    monkeypatch.setattr(engine.equity_rekonstruktion, "rekonstruiere", forbidden)
    with pytest.raises(ValueError, match="Unbekannte Instrumente"):
        engine.analyze("test", kursanbieter=provider)
