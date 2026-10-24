"""Shared capital precedence, provenance and immutable calibration snapshots."""
from copy import deepcopy
from datetime import datetime, timedelta
import json

import pytest

from mqlkiscanner import abonnenten_modellkapital as model
from mqlkiscanner import kapitalbasis as capital
from mqlkiscanner import config
from mqlkiscanner.forensics import drawdown
from mqlkiscanner.models import AccountCostRow, BalanceRow, ParsedExport, Trade

START = datetime(2026, 1, 1, 12)


def export(profits=(10,), lots=None, balances=(), costs=()):
    lots = lots or [.01] * len(profits)
    trades = [Trade(START + timedelta(days=i), START + timedelta(days=i, hours=1),
                    "Buy", lot, "XAUUSD", 2000, 2001, pnl)
              for i, (lot, pnl) in enumerate(zip(lots, profits))]
    return ParsedExport("source.csv", "positions", trades=trades,
                        balances=list(balances), costs=list(costs))


def context(ref=1, sha=None):
    return {"quelle": "mql5", "quellen_uid": "mql", "id": ref,
            "signal_ref": ref, "trades_sha256": sha or f"sha-{ref}", "account_currency": "USD",
            "forensik": {"forensics": {"exposure": {"per_symbol_scenarios": {
                "XAUUSD": {"quote_currency": "USD", "contract_factor_in_quote": 100}}}}}}


def pool(n=6):
    return model.kalibriere((context(ref), export(balances=[BalanceRow(START, 1000)]))
                           for ref in range(10, 10 + n))


def write_envelope(path, calibration, digest=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"kalibrierung": calibration,
                               "sha256": digest or capital.kalibrierung_sha256(calibration)},
                              ensure_ascii=False, allow_nan=False), encoding="utf-8")


def test_positive_csv_deposit_has_priority_and_costs_are_counted_once():
    parsed = export(balances=[BalanceRow(START - timedelta(days=1), 1000)],
                    costs=[AccountCostRow(START - timedelta(hours=1), -10, "fee")])
    before = deepcopy(parsed)
    result = capital.aufloesen(parsed, kapitalbasis_usd=50_000, kapitalbasis_quelle="manuell")
    assert result["quelle"] == "csv_einzahlungen"
    assert result["kapital"] == 1000 and result["injektion_usd"] == 0
    assert result["modell"] is False and result["gueltig"] is True
    dd = drawdown.run(parsed, kapitalentscheidung=result)
    assert dd["startkapital_raw"] == 990 and dd["end_balance_real"] == 1000
    assert dd["kontokosten_usd"] == -10
    assert parsed == before


@pytest.mark.parametrize("withdrawal", [-1000, -1500])
def test_known_nonpositive_net_csv_anchor_is_not_replaced_or_made_solvent(withdrawal):
    parsed = export(balances=[BalanceRow(START - timedelta(days=1), 1000), BalanceRow(START, withdrawal)])
    result = capital.aufloesen(parsed, kapitalbasis_usd=10_000, kapitalbasis_quelle="manuell")
    assert result["kapital"] == 1000 + withdrawal and result["injektion_usd"] == 0
    assert result["quelle"] == "csv_einzahlungen" and not result["modell"] and not result["gueltig"]
    assert drawdown.run(parsed, kapitalentscheidung=result)["startkapital_raw"] == 1000 + withdrawal


@pytest.mark.parametrize("source", ["manuell", "manuell_eingabe", "signalseite_initial_deposit", "extern", "web"])
def test_external_anchor_supplements_recorded_flows_and_preserves_later_flows(source):
    parsed = export([20, 10], balances=[BalanceRow(START, -50), BalanceRow(START + timedelta(hours=2), 200)],
                    costs=[AccountCostRow(START - timedelta(hours=1), -10, "fee")])
    result = capital.aufloesen(parsed, kapitalbasis_usd=1000, kapitalbasis_quelle=source)
    assert result["kapital"] == 950 and result["injektion_usd"] == 1000
    assert result["quelle"] == source
    dd = drawdown.run(parsed, kapitalentscheidung=result)
    assert dd["startkapital_raw"] == 940
    assert dd["end_balance_real"] == 1170
    assert dd["kurve"] == "real_mit_flows"


def test_native_initial_deposit_is_used_before_models_and_without_relabelling_currency():
    parsed = export()
    result = capital.aufloesen(parsed, stats={"initial_deposit_usd": 750, "account_currency": " usd "})
    assert result["kapital"] == result["injektion_usd"] == 750
    assert result["quelle"] == "signalseite_initial_deposit" and not result["modell"]
    assert result["beleg"]["waehrungsangaben"] == {"stats.account_currency": "USD"}


@pytest.mark.parametrize("invalid", [0, -1000, float("nan"), True, "1000"])
def test_invalid_source_initial_value_goes_to_model_with_diagnostic(invalid):
    result = capital.aufloesen(export(), stats={"initial_deposit_usd": invalid, "account_currency": "USD"})
    assert result["quelle"] == "modell_fallback_10000" and result["kapital"] == 10_000
    assert "initial_deposit_usd" in result["beleg"]["ignorierte_angaben"][0]["feld"]
    assert result["beleg"]["ignorierte_angaben"][0]["originalwert"] == ("nan" if isinstance(invalid, float) else invalid)
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("invalid", [0, -1, float("inf"), float("nan"), True, "1000"])
def test_invalid_explicit_manual_input_is_rejected(invalid):
    with pytest.raises(ValueError, match="manuell"):
        capital.aufloesen(export(), kapitalbasis_usd=invalid, kapitalbasis_quelle="manuell_eingabe")


def test_invalid_explicit_source_value_is_no_positive_evidence():
    result = capital.aufloesen(export(), kapitalbasis_usd=-25, kapitalbasis_quelle="signalseite_initial_deposit")
    assert result["quelle"] == "modell_fallback_10000"


def test_historical_virtual_fixed_values_do_not_preempt_current_regression():
    parsed = export([10] * 100, [(1000 + index * 10) * .0001 for index in range(100)])
    result = capital.aufloesen(parsed, kapitalbasis_usd=10_000, kapitalbasis_quelle="virtuelle_annahme",
                              stats={"kapitalbasis_virtual_usd": 10_000}, kontext=context())
    assert result["quelle"] == "modell_lot_pnl" and result["kapital"] == pytest.approx(1000)
    assert result["modell"] and result["basis_typ"] == "modell"
    assert len(result["beleg"]["ignorierte_angaben"]) == 2
    assert result["schaetzung"]["fitdiagnostik"]["lot_pnl_regression"]["status"] == "modell_fit"


def test_model_anchor_compensates_prestart_withdrawal_without_double_costs():
    parsed = export([10] * 100, [(1000 - 10 + index * 10) * .0001 for index in range(100)],
                    balances=[BalanceRow(START - timedelta(hours=2), -100)],
                    costs=[AccountCostRow(START - timedelta(hours=1), -10, "fee")])
    result = capital.aufloesen(parsed, kontext=context())
    assert result["kapital"] == pytest.approx(1000)
    assert result["injektion_usd"] == pytest.approx(1100)
    assert drawdown.run(parsed, kapitalentscheidung=result)["startkapital_raw"] == pytest.approx(990)


@pytest.mark.parametrize("stats,ctx", [
    ({"account_currency": "EUR"}, {}),
    ({"account_currency": "USD"}, {"trade_money_currency": "EUR"}),
    ({"account_currency": "USD"}, {"account_currency": "USD", "quellen_stats": {"account_currency": "JPY"}}),
    ({}, {"native_account_currency": "GBP"}),
])
def test_explicit_foreign_or_contradictory_money_blocks_even_csv_deposits(stats, ctx):
    with pytest.raises(ValueError, match="waehrung|waehrungs"):
        capital.aufloesen(export(balances=[BalanceRow(START, 1000)]), stats=stats, kontext=ctx)


def test_case_normalized_currency_claims_agree_and_generic_input_is_an_explicit_assumption():
    result = capital.aufloesen(export(), stats={"account_currency": " usd "},
                              kontext={"account_currency": "usd", "trade_money_currency": "USD"})
    assert result["beleg"]["usd_basis"] == "explizite_uebereinstimmende_waehrungsangaben"
    assumed = capital.aufloesen(export())
    assert assumed["beleg"]["usd_basis"] == "generischer_usd_inputvertrag_ohne_nativen_waehrungsbeleg"
    assert assumed["quelle"] == "modell_fallback_10000" and assumed["modell"]


@pytest.mark.parametrize("parsed", [None, ParsedExport("empty.csv", "positions")])
def test_missing_trades_still_get_explicit_fallback_without_io(parsed):
    result = capital.aufloesen(parsed)
    assert result["kapital"] == result["injektion_usd"] == 10_000
    assert result["beleg"]["erster_trade"] is None and result["modell"]
    json.dumps(result, allow_nan=False)


def test_explicit_calibration_is_frozen_and_own_anonymous_export_excluded():
    calibration = pool(5)
    before = deepcopy(calibration)
    anonymous = context(999, sha="sha-10")
    result = capital.aufloesen(export(), kontext=anonymous, calibration=calibration)
    # Five references minus the anonymised reimport leaves fewer than five.
    assert result["quelle"] == "modell_fallback_10000"
    assert calibration == before
    result = capital.aufloesen(export(), kontext=context(999), calibration=calibration)
    assert result["quelle"] == "modell_lots_kalibriert" and result["kapital"] == 1000
    assert result["beleg"]["kalibrierung"]["sha256"] == capital.kalibrierung_sha256(calibration)
    assert '"referenzen":' not in json.dumps(result["beleg"])


def test_calibration_does_not_double_count_same_export_under_another_identity():
    first = context(1, "same-export")
    second = context(2, "same-export")
    calibration = model.kalibriere([(first, export(balances=[BalanceRow(START, 1000)])),
                                  (second, export(balances=[BalanceRow(START, 5000)]))])
    assert calibration["referenzen_n"] == 1
    assert calibration["abgelehnt"]["doppelter_export"] == 1


def test_common_envelope_is_hash_checked_and_returned_by_copy(tmp_path):
    path = tmp_path / "kalibrierung.json"
    original = pool()
    write_envelope(path, original)
    loaded, proof = capital.lade_kalibrierung_mit_beleg(path)
    assert loaded == original and proof["status"] == "geprueft"
    loaded["gruppen"].clear()
    assert capital.lade_kalibrierung(path) == original
    modified = pool(7)
    write_envelope(path, modified)
    assert capital.lade_kalibrierung(path) == modified


def test_common_loader_uses_config_data_directory_and_binds_decision_to_sha():
    path = config.DATA_DIR / "kapitalbasis" / "kalibrierung.json"
    original = pool()
    write_envelope(path, original)
    result = capital.aufloesen(export(), kontext=context(999))
    assert result["quelle"] == "modell_lots_kalibriert" and result["kapital"] == 1000
    assert result["beleg"]["kalibrierung"]["sha256"] == capital.kalibrierung_sha256(original)


def test_raw_pool_requires_sidecar_digest_and_reloads_when_sidecar_changes(tmp_path):
    path = tmp_path / "kalibrierung.json"
    original = pool()
    path.write_text(json.dumps(original), encoding="utf-8")
    assert capital.lade_kalibrierung(path) is None
    sidecar = path.with_suffix(".sha256")
    sidecar.write_text(capital.kalibrierung_sha256(original) + "  kalibrierung.json\n", encoding="utf-8")
    assert capital.lade_kalibrierung(path) == original
    sidecar.write_text("0" * 64, encoding="utf-8")
    assert capital.lade_kalibrierung(path) is None


@pytest.mark.parametrize("fault", ["digest", "version_bool", "count", "ratio", "duplicate_identity"])
def test_invalid_snapshot_is_not_repaired_or_used(tmp_path, fault):
    path = tmp_path / "kalibrierung.json"
    original = pool()
    if fault == "version_bool": original["version"] = True
    if fault == "count": original["referenzen_n"] += 1
    if fault == "ratio": original["gruppen"][0]["referenzen"][0]["usd_je_lot"] *= 2
    if fault == "duplicate_identity": original["gruppen"][0]["referenzen"][1]["id"] = "10"
    write_envelope(path, original, "0" * 64 if fault == "digest" else None)
    before = path.read_bytes()
    loaded, proof = capital.lade_kalibrierung_mit_beleg(path)
    assert loaded is None and proof["status"] == "fehler"
    assert path.read_bytes() == before


def test_missing_calibration_is_diagnostic_and_creates_no_directories(tmp_path):
    path = tmp_path / "not-created" / "kalibrierung.json"
    loaded, proof = capital.lade_kalibrierung_mit_beleg(path)
    assert loaded is None and proof["status"] == "fehlt"
    assert not path.parent.exists()


@pytest.mark.parametrize("source", ["modell_lot_pnl", "modell_lots_kalibriert", "modell_fallback_10000",
                                     "modell_closing_dd_anker", "virtuelle_annahme", "fallback_10000",
                                     "komplex_lot_pnl_regression", "grobe_lot_kalibrierung"])
def test_helpers_preserve_model_status_for_old_and_new_sources(source):
    assert capital.ist_modellquelle(source)
    assert capital.ist_modellquelle({"quelle": source})
    assert "belegte Kontogroesse" in capital.beschreibung(source) or "Modell" in capital.beschreibung(source)


def test_model_marker_cannot_be_hidden_by_actual_sounding_source():
    assert capital.ist_modellquelle({"quelle": "manuell", "modell": True})
    assert "Modellannahme" in capital.beschreibung({"quelle": "manuell", "modell": True})
    assert not capital.ist_modellquelle("csv_einzahlungen")
    assert not capital.ist_modellquelle("signalseite_initial_deposit")


def test_central_api_preserves_inputs_and_delegates_sizing_once(monkeypatch):
    parsed, ctx, stats = export(), context(), {"account_currency": "USD"}
    original = deepcopy((parsed, ctx, stats))
    calls = []
    real = model.schaetze_kapital

    def record(subject, parsed_arg, calibration):
        calls.append((subject, parsed_arg))
        return real(subject, parsed_arg, calibration)

    monkeypatch.setattr(model, "schaetze_kapital", record)
    result = capital.aufloesen(parsed, stats=stats, kontext=ctx)
    assert len(calls) == 1 and calls[0][1] is parsed
    assert (parsed, ctx, stats) == original
    json.dumps(result, allow_nan=False)


def test_global_model_metadata_describes_retained_flows_and_subscriber_scenario_stays_separate():
    parsed = export(balances=[BalanceRow(START + timedelta(hours=2), 500)])
    global_result = capital.aufloesen(parsed)
    assert global_result["beleg"]["spaetere_flows_n"] == 1
    assert any("Ein-/Auszahlungen bleiben" in line for line in global_result["annahmen"])
    assert "Keine Ein-/Auszahlungen innerhalb des modellierten Tradefensters" not in global_result["schaetzung"]["annahmen"]
    scenario = model.schaetze_kapital(context(), parsed)
    assert "Keine Ein-/Auszahlungen innerhalb des modellierten Tradefensters" in scenario["annahmen"]


def test_no_flow_dd_anchor_rejects_known_later_flows_but_explicit_scenario_copy_can_use_it():
    parsed = export([100, -50], balances=[BalanceRow(START + timedelta(hours=2), 500)])
    subject = context()
    subject["modellkapital_closing_dd_anker"] = {
        "unabhaengig": True, "scope_bestaetigt": True, "selbst_berechnet": False,
        "definition": "max_rel_closing_netto_ohne_flows", "trades_sha256": subject["trades_sha256"],
        "quelle": "Unabhaengiger nativer Closing-DD mit geprueftem Exportfenster",
        "zeit_von": parsed.trades[0].open_time.isoformat(),
        "zeit_bis": parsed.trades[-1].close_time.isoformat(), "dd_pct_max_rel": 50 / 1100 * 100,
    }
    actual = model.schaetze_kapital(subject, parsed)
    assert actual["herkunft"] == "fallback_10000"
    assert "Kapitalfluesse" in actual["fitdiagnostik"]["closing_dd_anker"]["grund"]
    scenario = deepcopy(parsed)
    scenario.balances = []
    estimated = model.schaetze_kapital(subject, scenario)
    assert estimated["herkunft"] == "komplex_closing_dd_anker"
    assert estimated["kapital"] == pytest.approx(1000)
    assert len(parsed.balances) == 1
