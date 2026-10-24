"""Capital models remain explicit hypotheses, with no trading-risk formula."""
from copy import deepcopy
from datetime import datetime, timedelta
import json

import pytest

from mqlkiscanner import abonnenten_modellkapital as capital
from mqlkiscanner.models import ParsedExport, Trade, BalanceRow, AccountCostRow


START = datetime(2026, 1, 1, 12)


def parsed(profits, lots=None, balances=None, symbol="XAUUSD"):
    if lots is None:
        lots = [.01] * len(profits)
    trades = [Trade(START + timedelta(days=index), START + timedelta(days=index, hours=1),
                    "Buy", volume, symbol, 2000, 2001, profit)
              for index, (profit, volume) in enumerate(zip(profits, lots))]
    return ParsedExport("original.csv", "positions", trades=trades, balances=balances or [])


def entry(ref=1, currency="USD", **extra):
    return {"signal_ref": ref, "id": ref, "quellen_uid": "native-mql", "quelle": "mql5",
            "account_currency": currency, "trades_sha256": f"sha-{ref}",
            "forensik": {"forensics": {"exposure": {"per_symbol_scenarios": {
                "XAUUSD": {"quote_currency": "USD", "contract_factor_in_quote": 100}}}}}, **extra}


def reference(ref, value, volume=.01, **changes):
    return entry(ref, **changes), parsed([10] * 60, [volume] * 60,
                                        [BalanceRow(START - timedelta(days=1), value)])


def anchor(subject, export, pct):
    return {"unabhaengig": True, "scope_bestaetigt": True, "selbst_berechnet": False,
            "definition": "max_rel_closing_netto_ohne_flows", "trades_sha256": subject["trades_sha256"],
            "quelle": "Unabhängiger nativer Closing-DD mit geprüftem Exportfenster",
            "zeit_von": min(trade.open_time for trade in export.trades).isoformat(),
            "zeit_bis": max(trade.close_time for trade in export.trades).isoformat(), "dd_pct_max_rel": pct}


def test_proven_usd_start_precedes_models_and_actual_initial_deposit_is_not_ten_thousand():
    subject, export = reference(1, 250)
    before = deepcopy((subject, export))
    result = capital.schaetze_kapital(subject, export)
    assert result["kapital"] == 250 and result["basis_typ"] == "belegt" and not result["modell"]
    assert result["herkunft"] == "csv_einzahlungen_vor_handelsbeginn"
    assert (subject, export) == before


def test_native_initial_deposit_requires_explicit_native_usd_proof():
    subject = entry(quellen_stats={"account_currency": "USD", "initial_deposit_usd": 500})
    result = capital.schaetze_kapital(subject, parsed([10]))
    assert result["basis_typ"] == "belegt" and result["kapital"] == 500
    subject["quellen_stats"]["account_currency"] = "EUR"
    result = capital.schaetze_kapital(subject, parsed([10]))
    assert result["basis_typ"] == "modell" and result["kapital"] == 10_000


@pytest.mark.parametrize("subject,export", [(None, None), ({}, None), ({"quelle": "robo"}, None),
                                             ({}, ParsedExport("empty", "positions"))])
def test_missing_inputs_and_zero_trades_get_explicit_fallback(subject, export):
    result = capital.schaetze_kapital(subject, export)
    assert result["kapital"] == 10_000 and result["herkunft"] == "fallback_10000" and result["modell"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("currency", ["EUR", "JPY", None])
def test_real_non_usd_or_unknown_capital_is_never_relabelled_usd(currency):
    subject, export = reference(1, 50_000, currency=currency)
    result = capital.schaetze_kapital(subject, export)
    assert result["basis_typ"] == "modell" and result["kapital"] == 10_000
    assert result["quellwaehrung"] == currency and not result["waehrungsumrechnung"]
    assert not result["native_pnl_als_usd_belegt"]


def test_exact_proportional_sizing_can_identify_capital_under_explicit_no_flow_hypothesis():
    export = parsed([10] * 100, [(1000 + index * 10) * .0001 for index in range(100)])
    result = capital.schaetze_kapital(entry(), export)
    assert result["herkunft"] == "komplex_lot_pnl_regression"
    assert result["kapital"] == pytest.approx(1000)
    assert result["modell"] and result["basis_typ"] == "modell"
    assert result["fitdiagnostik"]["lot_pnl_regression"]["fit"]["r2"] == pytest.approx(1)


def test_explicit_later_cashflow_rejects_no_flow_sizing_identification():
    export = parsed([10] * 100, [(1000 + index * 10) * .0001 for index in range(100)],
                    [BalanceRow(START + timedelta(days=30), 100)])
    result = capital.schaetze_kapital(entry(), export)
    assert result["herkunft"] == "fallback_10000"
    assert "Kapitalfluesse" in result["fitdiagnostik"]["lot_pnl_regression"]["grund"]


def test_constant_lots_contain_no_identifiable_capital_scale():
    result = capital.schaetze_kapital(entry(), parsed([10] * 100))
    assert result["herkunft"] == "fallback_10000"
    assert "Konstante Lots" in result["fitdiagnostik"]["lot_pnl_regression"]["grund"]


def test_negative_regression_capital_remains_diagnostic_and_is_not_clamped():
    export = parsed([.5] * 100, [1 - .01 * index * .5 for index in range(100)])
    result = capital.schaetze_kapital(entry(), export)
    assert result["fitdiagnostik"]["lot_pnl_regression"]["fit"]["kapital"] == pytest.approx(-100)
    assert result["kapital"] == 10_000 and result["herkunft"] == "fallback_10000"


def test_fallback_is_never_increased_to_make_model_solvent():
    result = capital.schaetze_kapital(entry(), parsed([-12_000]))
    assert result["kapital"] == 10_000 and result["modell_min_closing_balance"] == -2000
    assert result["solvenz_anpassung"] is False and "kein Kapital" in result["modell_warnung"]


def test_independent_definition_bound_closing_dd_inverts_net_path_without_mixing_maxima():
    subject, export = entry(), parsed([100, -50, 1000, -60])
    # Largest relative DD is 50 / 1100; largest dollar DD is a different event.
    subject["modellkapital_closing_dd_anker"] = anchor(subject, export, 50 / 1100 * 100)
    result = capital.schaetze_kapital(subject, export)
    assert result["kapital"] == pytest.approx(1000)
    assert result["herkunft"] == "komplex_closing_dd_anker" and result["modell"]


@pytest.mark.parametrize("fault", ["own", "scope", "definition", "sha", "window"])
def test_own_circular_or_mismatched_dd_does_not_supply_capital_evidence(fault):
    subject, export = entry(), parsed([100, -50])
    an = anchor(subject, export, 5)
    if fault == "own": an["unabhaengig"] = False
    elif fault == "scope": an["scope_bestaetigt"] = False
    elif fault == "definition": an["definition"] = "platform_equity_dd"
    elif fault == "sha": an["trades_sha256"] = "other-export"
    else: an["zeit_bis"] = "another-window"
    subject["modellkapital_closing_dd_anker"] = an
    assert capital.schaetze_kapital(subject, export)["herkunft"] == "fallback_10000"


def test_rough_lot_model_uses_empirical_contract_matched_actual_capital_pool():
    references = [reference(index, value) for index, value in enumerate([1000, 1500, 2000, 2500, 3000], 1)]
    before = deepcopy(references)
    calibration = capital.kalibriere(references)
    result = capital.schaetze_kapital(entry(99), parsed([10] * 60, [.02] * 60), calibration)
    assert result["kapital"] == 4000 and result["herkunft"] == "grobe_lot_kalibrierung"
    assert result["kalibrierung_ref_n"] == 5 and result["modell"]
    assert result["kalibrierung"]["empirischer_modellbereich_p10_p90"] == [2400, 5600]
    assert references == before
    json.dumps(calibration, allow_nan=False)
    json.dumps(result, allow_nan=False)


def test_model_references_foreign_currency_and_duplicate_identities_never_enter_calibration():
    references = [reference(1, 1000), reference(1, 2000), reference(2, 3000, currency="EUR"),
                  reference(3, 4000, modellkapital={"basis_typ": "modell"}), ({}, None)]
    calibration = capital.kalibriere(references)
    assert calibration["referenzen_n"] == 1
    assert calibration["abgelehnt"]["fehlende_oder_doppelte_identitaet"] == 1
    assert calibration["abgelehnt"]["kein_belegtes_usd_startkapital"] == 3


def test_unknown_or_mismatched_contract_and_too_small_pool_fall_back_without_risk_percent_rule():
    calibration = capital.kalibriere([reference(index, 1000) for index in range(1, 6)])
    subject = entry(99)
    subject["forensik"]["forensics"]["exposure"]["per_symbol_scenarios"]["XAUUSD"]["contract_factor_in_quote"] = 1
    assert capital.schaetze_kapital(subject, parsed([10] * 60), calibration)["herkunft"] == "fallback_10000"
    assert capital.schaetze_kapital(entry(99), parsed([10] * 60), capital.kalibriere([reference(1, 1000)]))["herkunft"] == "fallback_10000"
    assert capital.schaetze_kapital(entry(99), parsed([10]), {"basis": "ausschliesslich_belegte_usd_startkapitalien", "gruppen": [None]})["herkunft"] == "fallback_10000"


def test_target_identity_is_excluded_from_its_own_rough_reference_model():
    calibration = capital.kalibriere([reference(index, 1000) for index in range(1, 7)])
    result = capital.schaetze_kapital(entry(1), parsed([10] * 60), calibration)
    assert result["herkunft"] == "grobe_lot_kalibrierung" and result["kalibrierung_ref_n"] == 5


def test_initial_deposit_is_before_pretrade_costs_and_all_costs_count_exactly_once():
    subject, export = reference(1, 1000)
    export.costs = [AccountCostRow(START - timedelta(hours=1), -10, "commission")]
    result = capital.schaetze_kapital(subject, export)
    assert result["kapital"] == 1000 and result["basis_typ"] == "belegt"
    times, amounts = capital._events(export)
    assert amounts[0] == -10 and 1000 + amounts[0] == 990


def test_forensic_trade_start_anchor_is_recovered_before_pretrade_costs():
    subject = entry()
    subject["forensik"]["forensics"]["drawdown"] = {
        "startkapital_raw": 990, "startkapital_quelle": "signalseite_initial_deposit", "kontokosten_vor_start_usd": -10}
    export = parsed([10] * 60)
    export.costs = [AccountCostRow(START - timedelta(hours=1), -10, "commission")]
    assert capital.schaetze_kapital(subject, export)["kapital"] == 1000
    subject["forensik"]["forensics"]["drawdown"]["kontokosten_vor_start_usd"] = -20
    assert capital.schaetze_kapital(subject, export)["basis_typ"] == "modell"


def test_explicit_eur_trade_money_excludes_five_otherwise_usd_references_from_calibration():
    references = [reference(index, 1000, quellen_stats={"account_currency": "USD"}, trade_money_currency="EUR")
                  for index in range(1, 6)]
    calibration = capital.kalibriere(references)
    assert calibration["referenzen_n"] == 0 and calibration["gruppen"] == []
    assert calibration["abgelehnt"]["kein_belegtes_usd_startkapital"] == 5


@pytest.mark.parametrize("claims", [
    {"account_currency": "USD", "quellen_stats": {"account_currency": "USD"}, "trade_money_currency": "EUR"},
    {"account_currency": "USD", "quellen_stats": {"account_currency": "EUR"}, "trade_money_currency": "USD"},
    {"account_currency": "EUR", "quellen_stats": {"account_currency": "USD"}, "trade_money_currency": "USD"},
])
def test_conflicting_currency_claims_disable_proven_capital_regression_and_rough_calibration(claims):
    calibration = capital.kalibriere([reference(index, 1000) for index in range(1, 6)])
    subject = entry(99, **claims)
    proportional = parsed([10] * 100, [(1000 + index * 10) * .0001 for index in range(100)])
    result = capital.schaetze_kapital(subject, proportional, calibration)
    assert result["herkunft"] == "fallback_10000" and result["basis_typ"] == "modell"
    assert result["quellwaehrung"] is None and not result["native_pnl_als_usd_belegt"]
    proportional.balances = [BalanceRow(START - timedelta(days=1), 1000)]
    assert capital.schaetze_kapital(subject, proportional, calibration)["basis_typ"] == "modell"


def test_all_three_currency_claims_are_case_and_whitespace_normalised_consistently():
    subject, export = reference(1, 1000, account_currency=" usd ",
                                quellen_stats={"account_currency": "uSd"}, trade_money_currency="UsD ")
    result = capital.schaetze_kapital(subject, export)
    assert result["basis_typ"] == "belegt" and result["kapital"] == 1000 and result["quellwaehrung"] == "USD"
    no_flow_export = parsed([10] * 60)
    subject["quellen_stats"]["initial_deposit_usd"] = 750
    assert capital.schaetze_kapital(subject, no_flow_export)["kapital"] == 750


def test_fresh_gold_csv_without_exposure_metadata_uses_existing_frozen_pool_without_recalibration(monkeypatch):
    pool = capital.kalibriere([reference(index, value) for index, value in enumerate([1000, 1500, 2000, 2500, 3000], 1)])
    before = deepcopy(pool)
    monkeypatch.setattr(capital, "kalibriere", lambda *args: pytest.fail("Frozen reference pool must be reused"))
    subject = entry(99, forensik={}, quellen_stats={"account_currency": "USD"})
    result = capital.schaetze_kapital(subject, parsed([10] * 60, [.02] * 60, symbol="XAUUSD+"), pool)
    assert result["herkunft"] == "grobe_lot_kalibrierung" and result["kapital"] == 4000
    assert result["kalibrierung"]["kontraktgruppe"] == ["XAUUSD", "USD", 100]
    assert pool == before


def test_fresh_fx_csv_uses_same_local_quote_and_factor_as_recorded_exposure_without_rates():
    references = []
    for index in range(1, 6):
        subject = entry(index)
        subject["forensik"]["forensics"]["exposure"]["per_symbol_scenarios"] = {
            "AUDCAD": {"quote_currency": "CAD", "contract_factor_in_quote": 100_000}}
        references.append((subject, parsed([10] * 60, balances=[BalanceRow(START - timedelta(days=1), 1000)], symbol="AUDCAD")))
    pool = capital.kalibriere(references)
    result = capital.schaetze_kapital(entry(99, forensik={}), parsed([10] * 60, [.02] * 60, symbol="AUDCAD.a"), pool)
    assert result["herkunft"] == "grobe_lot_kalibrierung" and result["kapital"] == 2000
    assert result["kalibrierung"]["kontraktgruppe"] == ["AUDCAD", "CAD", 100_000]


def test_local_contract_fallback_honours_broker_scoped_oil_specs_and_conflicting_broker_claims():
    from mqlkiscanner import config
    config.CONTRACT_SPECS_FILE.write_text(json.dumps({"symbols": {"USOIL": {
        "contract_size": 1, "quote_currency": "USD", "cross_broker": False,
        "brokers": ["Tickmill"], "stress_move": 10, "source": "Synthetic broker-specific fixture"}}}), encoding="utf-8")
    references = []
    for index in range(1, 6):
        subject = entry(index)
        subject["forensik"]["forensics"]["exposure"]["per_symbol_scenarios"] = {
            "USOIL": {"quote_currency": "USD", "contract_factor_in_quote": 1}}
        references.append((subject, parsed([10] * 60, balances=[BalanceRow(START - timedelta(days=1), 1000)], symbol="USOIL")))
    pool = capital.kalibriere(references)
    export = parsed([10] * 60, [.02] * 60, symbol="USOIL")
    allowed = entry(99, forensik={}, quellen_stats={"account_currency": "USD", "broker_server": "Tickmill-Live"})
    assert capital.schaetze_kapital(allowed, export, pool)["herkunft"] == "grobe_lot_kalibrierung"
    for stats, claims in [({"broker_server": "OtherBroker"}, {}), ({}, {}),
                          ({"broker_server": "Tickmill-Live"}, {"broker_server": "OtherBroker"})]:
        subject = entry(99, forensik={}, quellen_stats=stats, **claims)
        assert capital.schaetze_kapital(subject, export, pool)["herkunft"] == "fallback_10000"


def test_unknown_broker_with_a_specific_fx_contract_exception_is_not_generic_lot_evidence():
    from mqlkiscanner import config
    config.CONTRACT_SPECS_FILE.write_text(json.dumps({"symbols": {"EURUSD": {
        "contract_size": 1000, "quote_currency": "USD", "cross_broker": False,
        "brokers": ["MicroBroker"], "stress_move": .05, "source": "Synthetic micro contract"}}}), encoding="utf-8")
    references = []
    for index in range(1, 6):
        subject = entry(index)
        subject["forensik"]["forensics"]["exposure"]["per_symbol_scenarios"] = {
            "EURUSD": {"quote_currency": "USD", "contract_factor_in_quote": 100_000}}
        references.append((subject, parsed([10] * 60, balances=[BalanceRow(START - timedelta(days=1), 1000)], symbol="EURUSD")))
    pool, export = capital.kalibriere(references), parsed([10] * 60, [.02] * 60, symbol="EURUSD")
    assert capital.schaetze_kapital(entry(99, forensik={}), export, pool)["herkunft"] == "fallback_10000"
    special = entry(99, forensik={}, quellen_stats={"broker_server": "MicroBroker-Live"})
    assert capital.schaetze_kapital(special, export, pool)["herkunft"] == "fallback_10000", "1000-unit lots must not match frozen 100000-unit references"


@pytest.mark.parametrize("symbol", ["EURUSDT", "XAUUSD247", "UNKNOWN"])
def test_local_resolver_does_not_guess_unknown_or_ambiguous_contract_units(symbol):
    pool = capital.kalibriere([reference(index, 1000) for index in range(1, 6)])
    result = capital.schaetze_kapital(entry(99, forensik={}), parsed([10] * 60, [.02] * 60, symbol=symbol), pool)
    assert result["herkunft"] == "fallback_10000"


def test_currency_conflict_still_prevents_fresh_contract_fallback_and_pool_use(monkeypatch):
    pool = capital.kalibriere([reference(index, 1000) for index in range(1, 6)])
    subject = entry(99, forensik={}, quellen_stats={"account_currency": "USD"}, trade_money_currency="EUR")
    monkeypatch.setattr(capital, "_local_contract", lambda *args: pytest.fail("Conflicting money units must stop before local contract fallback"))
    assert capital.schaetze_kapital(subject, parsed([10] * 60), pool)["herkunft"] == "fallback_10000"
