"""One rate lookup, with explicit read-only loading for model calculations."""
from datetime import date
import math

import pytest

from mqlkiscanner import config, fx_rates


CSV = "Date,USD,CAD,JPY\n2024-01-04,1.095,1.465,145.1\n2024-01-03,1.096,1.47,144.65\n"


@pytest.fixture
def local_table(monkeypatch):
    config.FX_RATES_DIR.mkdir(parents=True, exist_ok=True)
    path = config.FX_RATES_DIR / fx_rates.CSV_NAME
    path.write_text(CSV, encoding="utf-8")

    def forbid_refresh(*args, **kwargs):
        raise AssertionError("Offline loading must not attempt refresh")

    monkeypatch.setattr(fx_rates, "_refresh", forbid_refresh)
    return path


def test_offline_loader_is_read_only_without_refresh(local_table):
    before = local_table.read_bytes(), local_table.stat().st_mtime_ns
    table = fx_rates.load(offline=True)
    assert table["USD"] == (["2024-01-03", "2024-01-04"], [1.096, 1.095])
    assert fx_rates.usd_per("CAD", date(2024, 1, 6), offline=True) == {
        "rate": 1.095 / 1.465, "date": "2024-01-04"}
    assert (local_table.read_bytes(), local_table.stat().st_mtime_ns) == before


@pytest.mark.parametrize("currency", ["USD", "EUR", "CAD", "JPY", "CHF"])
@pytest.mark.parametrize("day", [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 6),
                                  date(2024, 1, 14), date(2024, 1, 15)])
def test_online_and_offline_use_identical_historical_rates(local_table, monkeypatch, currency, day):
    table = fx_rates.load(offline=True)
    monkeypatch.setattr(fx_rates, "load", lambda **kwargs: table)
    assert fx_rates.usd_per(currency, day) == fx_rates.usd_per(currency, day, offline=True)
    assert fx_rates.usd_per_table(currency, day, table) == fx_rates.usd_per(currency, day)


def test_offline_usd_identity_and_historical_online_empty_table_contract(monkeypatch):
    monkeypatch.setattr(fx_rates, "load", lambda **kwargs: {})
    day = date(2024, 1, 6)
    assert fx_rates.usd_per_table("USD", day, {}) == {"rate": 1.0, "date": day.isoformat()}
    assert fx_rates.usd_per("USD", day, offline=True) == {"rate": 1.0, "date": day.isoformat()}
    assert fx_rates.usd_per("USD", day) is None
    assert fx_rates.usd_per("EUR", day, offline=True) is None


@pytest.mark.parametrize("rate", [0, -1, math.nan, math.inf])
def test_invalid_injected_rate_is_never_a_conversion(rate):
    table = {"USD": (["2024-01-03"], [1.1]), "CAD": (["2024-01-03"], [rate])}
    assert fx_rates.usd_per_table("CAD", date(2024, 1, 3), table) is None


def test_cross_rate_requires_both_quotes_from_the_same_day():
    table = {"USD": (["2024-01-02"], [1.1]), "CAD": (["2024-01-03"], [1.47])}
    assert fx_rates.usd_per_table("CAD", date(2024, 1, 3), table) is None


def test_missing_offline_cache_is_not_created_or_downloaded(monkeypatch):
    def forbid_refresh(*args, **kwargs):
        raise AssertionError("Offline loading must not refresh")

    monkeypatch.setattr(fx_rates, "_refresh", forbid_refresh)
    assert fx_rates.load(offline=True) == {}
    assert fx_rates.usd_per("CAD", date(2024, 1, 3), offline=True) is None
    assert not config.FX_RATES_DIR.exists()
