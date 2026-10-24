"""Data-only measurements do not inherit the research ranking material gate."""
from copy import deepcopy
from pathlib import Path

import pytest

from test_abonnenten_analyse_daten import csv_bytes, service_env  # noqa: F401
from mqlkiscanner import abonnenten_analyse_daten as data, db
from mqlkiscanner.llm.client import GlmClient


DATA_SETTINGS = {"abonnenten_daten_ohne_ki": True}


def measure(env, settings=None):
    entry, _, _, _, _ = env
    with data.AnalyseDaten(DATA_SETTINGS if settings is None else settings) as provider:
        return provider.berechne(entry)


def set_export(env, count=50, days=65, **options):
    _, client, _, equity, _ = env
    client.raw = csv_bytes(trades=count, days=days, **options)
    client.answer["metrics"]["Balance"] = 1000+count*10
    equity.update(trades_total=count, trades_mit_kurs_und_kontrakt=count)


@pytest.mark.parametrize("count,days", [(49, 65), (50, 15), (3, 4), (1, 65)])
def test_below_material_gate_still_measures_all_trades_h1_and_returns(service_env, monkeypatch, count, days):
    entry, client, created, equity, _ = service_env
    set_export(service_env, count, days)
    seen = []

    def reconstruct(parsed, provider, capital, broker):
        seen.append(len(parsed.trades))
        return deepcopy(equity)

    monkeypatch.setattr(data, "_rekonstruiere_mit_feed_fallback", reconstruct)
    monkeypatch.setattr(GlmClient, "__init__", lambda *a, **k: pytest.fail("No KI client in data-only measurements"))
    result = measure(service_env)
    assert seen == [count]
    assert created[0].starts == created[0].closes == 1
    assert result["trades"] == count and result["data_complete"] is True
    assert result["equity_dd_pct"] == equity["equity_dd_pct_raw"]
    assert result["rendite_zeitraum_pct"] == pytest.approx(count)
    assert result["cagr_jahr_pct"] is not None and result["retdd_jahr"] is not None
    assert result["eligible"] is False and result["mindestmaterial_erfuellt"] is False
    assert result["rang_pruefhinweis"] and "50-Trade" in result["annualisierung_hinweis"]
    assert result["trade_history_complete"] is True
    assert result["trade_history_status"] == "vollstaendig"
    db.verify_trade_file(result["trades_path"], result["trades_sha256"])


def test_legacy_short_history_still_stops_before_terminal(service_env):
    set_export(service_env, 49, 65)
    result = measure(service_env, settings={})
    assert result["data_complete"] is True and result["eligible"] is False
    assert result["equity_dd_pct"] is None and not service_env[2]
    assert "Weniger als 50" in result["grund"]


@pytest.mark.parametrize("currency", ["EUR", "AUD", None])
def test_native_foreign_or_unknown_currency_snapshot_is_saved_before_usd_gate(service_env, monkeypatch, currency):
    _, client, created, _, _ = service_env
    client.answer["metrics"]["Currency"] = currency
    monkeypatch.setattr(data.engine, "analyze", lambda *a, **k: pytest.fail("No USD forensics without USD proof"))
    result = measure(service_env)
    assert result["trades"] == 50 and result["zeit_von"] and result["zeit_bis"]
    assert result["trades_path"] and result["trades_sha256"]
    assert result["trade_history_complete"] is True
    assert result["trade_money_currency"] == currency
    assert result["netto_quellwaehrung"] == 500
    assert result["account_currency"] == currency
    assert result["forensik"] == result["equity"] == {} and not created
    assert result["equity_dd_pct"] is result["cagr_jahr_pct"] is result["retdd_jahr"] is None
    assert not result["data_complete"] and not result["eligible"]
    assert "keine USD-Forensik" in result["grund"]
    db.verify_trade_file(result["trades_path"], result["trades_sha256"])


@pytest.mark.parametrize("field,value", [("TradesTruncated", True), ("TradesHistoryComplete", False),
                                        ("TradeHistoryComplete", False)])
def test_reported_partial_export_is_saved_but_not_promoted_to_full_history(service_env, monkeypatch, field, value):
    _, client, created, _, _ = service_env
    client.answer["metrics"][field] = value
    monkeypatch.setattr(data.engine, "analyze", lambda *a, **k: pytest.fail("Partial history cannot establish USD forensics"))
    result = measure(service_env)
    assert Path(result["trades_path"]).read_bytes() == client.raw
    assert result["trades"] == 50 and result["netto_quellwaehrung"] == 500
    assert result["trade_history_complete"] is False and result["trade_history_status"] == "teilweise"
    assert not result["data_complete"] and result["equity_dd_pct"] is None
    assert "Teillieferung" in result["grund"] and not created


def test_missing_actual_capital_uses_model_without_overwriting_measured_fields(service_env, monkeypatch):
    from mqlkiscanner import abonnenten_modellrechnung
    seen = []
    def calculate(entry, capital, **kwargs):
        seen.append((entry["trades"], entry["trades_sha256"], capital["kapital"]))
        return {"startkapital_usd": capital["kapital"], "equity_dd_pct": 12,
                "retdd_jahr": 3, "status": "berechnet", "grund": "Synthetisches H1-Modell"}
    monkeypatch.setattr(abonnenten_modellrechnung, "berechne_modell", calculate)
    service_env[1].answer["metrics"]["InitialDeposit"] = None
    result = measure(service_env)
    assert result["trades_path"] and result["trades"] == 50 and result["netto_quellwaehrung"] == 500
    assert result["kapitalbasis_usd"] is result["equity_dd_pct"] is result["cagr_jahr_pct"] is None
    assert not result["data_complete"] and not result["eligible"]
    assert seen == [(50, result["trades_sha256"], 10000)]
    assert result["modell"]["equity_dd_pct"] == 12 and result["modell"]["retdd_jahr"] == 3
    assert result["kapitalbasis_modell"] is True
    assert service_env[2][0].starts == service_env[2][0].closes == 1


@pytest.mark.parametrize("patch", [{"status": "ok_teilmessung", "teilmessung": True},
                                  {"fx_luecke": True}, {"verlaesslich": False}])
def test_usd_returns_can_be_measured_while_h1_dd_remains_unknown(service_env, patch):
    service_env[3].update(patch)
    result = measure(service_env)
    assert result["equity"] and result["equity_dd_pct"] is None
    assert result["rendite_zeitraum_pct"] == pytest.approx(50)
    assert result["rendite_status"] == "gemessen" and result["cagr_jahr_pct"] is not None
    assert result["retdd_jahr"] is result["retdd_zeitraum"] is None
    assert not result["eligible"] and not result["data_complete"]


def test_true_measured_zero_dd_is_displayable_but_retdd_division_stays_unknown(service_env):
    service_env[3].update(equity_dd_pct_raw=0, equity_dd_pct=0)
    result = measure(service_env)
    assert result["equity_dd_pct"] == 0 and result["data_complete"] is True
    assert result["rendite_zeitraum_pct"] == pytest.approx(50)
    assert result["retdd_jahr"] is result["retdd_zeitraum"] is None
    assert result["retdd_status"] == "nicht_definiert_dd_null"
    assert "Division durch null" in result["retdd_grund"]
    assert not result["eligible"]
    legacy = measure(service_env, settings={})
    assert legacy["equity_dd_pct"] is None and not legacy["data_complete"]


def test_incomplete_contract_proof_still_blocks_dd_but_preserves_native_profit(service_env):
    service_env[4]["contract_complete"] = False
    result = measure(service_env)
    assert result["equity_dd_pct"] is None and not result["data_complete"]
    assert result["netto_quellwaehrung"] == 500 and result["trade_money_currency"] == "USD"
    assert result["rendite_zeitraum_pct"] == pytest.approx(50)
    assert "Kontraktbelege" in result["grund"]


def test_cashflow_at_open_position_keeps_h1_measurement_but_not_fabricated_twr(service_env):
    set_export(service_env, 50, 65, deposits=True, flow=True)
    result = measure(service_env)
    assert result["equity_dd_pct"] == service_env[3]["equity_dd_pct_raw"]
    assert result["netto_quellwaehrung"] == 500
    assert result["cagr_jahr_pct"] is result["rendite_zeitraum_pct"] is result["retdd_jahr"] is None
    assert not result["data_complete"] and not result["eligible"]
    assert "kapitalfluss_equity_unbelegt" in result["grund"]


def test_full_export_is_not_shortened_to_material_or_prompt_limits(service_env, monkeypatch):
    count = 517
    set_export(service_env, count, 120)
    seen = []
    monkeypatch.setattr(data, "_rekonstruiere_mit_feed_fallback", lambda parsed, *args:
                        (seen.append(len(parsed.trades)) or deepcopy(service_env[3])))
    monkeypatch.setattr(GlmClient, "__init__", lambda *a, **k: pytest.fail("No prompt processing in data-only mode"))
    result = measure(service_env)
    assert seen == [count] and result["trades"] == count and result["data_complete"]
    assert Path(result["trades_path"]).read_bytes() == service_env[1].raw
    assert result["netto_quellwaehrung"] == count*10


def test_short_window_can_keep_observed_return_when_annualisation_overflows(service_env):
    _, client, _, equity, _ = service_env
    client.raw = ("Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
                  "2026.01.05 10:00:00;Buy;0.01;XAUUSD;2000;0.01;2026.01.05 10:00:01;2010;0;0;10\n").encode()
    client.answer["metrics"]["Balance"] = 1010
    equity.update(trades_total=1, trades_mit_kurs_und_kontrakt=1)
    result = measure(service_env)
    assert result["equity_dd_pct"] == equity["equity_dd_pct_raw"]
    assert result["rendite_zeitraum_pct"] == pytest.approx(1)
    assert result["cagr_jahr_pct"] is result["retdd_jahr"] is None
    assert result["retdd_zeitraum"] == pytest.approx(1/equity["equity_dd_pct_raw"])
    assert result["mindestmaterial_erfuellt"] is False and not result["eligible"]
