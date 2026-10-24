"""One capital decision reaches both forensic kernels without flow/fee drift."""
from datetime import datetime, timedelta
import json

import pytest

from mqlkiscanner import config, engine, kapitalbasis, parser
from mqlkiscanner.forensics import drawdown, exposure


def history(tmp_path, *, dynamic=True, costs=False, withdrawals=False, deposits=False):
    start = datetime(2024, 1, 2)
    rows = [";".join(parser.POSITION_HEADER)]
    if deposits:
        rows.extend(["2024.01.01 00:00:00;Balance;;;;;;;;;100",
                     "2024.01.01 01:00:00;Balance;;;;;;;;;-200"])
    elif withdrawals:
        rows.append("2024.01.01 01:00:00;Balance;;;;;;;;;-50")
    if costs:
        rows.append("2024.01.01 02:00:00;Commission;;;;;;;;;-10")
    for i in range(60 if dynamic else 3):
        opened = start + timedelta(days=i)
        pnl = 10 * i - (10 if costs else 0)
        lot = .1 + .0001 * pnl if dynamic else .2
        rows.append(";".join((opened.strftime(parser.TIME_FMT), "Buy", str(lot), "XAUUSD", "2000", str(lot),
                              (opened + timedelta(hours=1)).strftime(parser.TIME_FMT), str(2000+10/(lot*100)),
                              "0", "0", "10")))
    path = tmp_path / "capital-input.csv"
    path.write_text("\n".join(rows)+"\n", encoding="utf-8")
    return path


def assert_shared(report, source, amount):
    fx = report["forensics"]
    decision = fx["kapitalbasis"]
    assert decision["quelle"] == source
    assert fx["drawdown"]["startkapital_raw"] == pytest.approx(amount)
    assert fx["exposure"]["startkapital"] == pytest.approx(amount)
    assert fx["drawdown"]["kapitalbasis_details"] == fx["exposure"]["kapitalbasis_details"] == decision
    assert json.loads(json.dumps(report))["forensics"]["kapitalbasis"] == decision


def test_engine_uses_stable_sizing_instead_of_legacy_virtual_amount(tmp_path):
    path = history(tmp_path)
    report = engine.analyze(str(path), kapitalbasis_usd=90000, kapitalbasis_quelle="virtuelle_annahme")
    assert_shared(report, "modell_lot_pnl", 1000)
    assert report["forensics"]["exposure"]["capital_history_complete"] is False
    assert report["forensics"]["exposure"]["model_capital_available"] is True


def test_model_prestart_withdrawal_and_fee_are_accounted_exactly_once(tmp_path):
    path = history(tmp_path, costs=True, withdrawals=True)
    report = engine.analyze(str(path))
    assert_shared(report, "modell_lot_pnl", 990)
    decision = report["forensics"]["kapitalbasis"]
    assert decision["kapital"] == pytest.approx(1000)
    assert decision["injektion_usd"] == pytest.approx(1050)
    assert report["forensics"]["drawdown"]["kontokosten_vor_start_usd"] == -10


def test_known_nonpositive_csv_anchor_is_not_replaced_by_a_model(tmp_path):
    path = history(tmp_path, deposits=True)
    report = engine.analyze(str(path), kapitalbasis_usd=10000, kapitalbasis_quelle="manuell_eingabe")
    assert_shared(report, "csv_einzahlungen", -100)
    assert report["forensics"]["kapitalbasis"]["modell"] is False
    assert report["forensics"]["kapitalbasis"]["gueltig"] is False
    assert report["forensics"]["exposure"]["temporal_risk_available"] is False


def test_engine_and_direct_kernels_use_same_shared_reference_snapshot(tmp_path):
    rows = [{"quellen_uid": "native-source", "id": str(i), "kapital_usd": 2000,
             "median_lot": .1, "usd_je_lot": 20000} for i in range(5)]
    pool = {"version": 1, "basis": "ausschliesslich_belegte_usd_startkapitalien", "referenzen_n": 5,
            "gruppen": [{"kontraktgruppe": ["XAUUSD", "USD", 100.0], "n": 5, "referenzen": rows}]}
    target = config.DATA_DIR / "kapitalbasis" / "kalibrierung.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"kalibrierung": pool, "sha256": kapitalbasis.kalibrierung_sha256(pool)}), encoding="utf-8")
    path = history(tmp_path, dynamic=False)
    report = engine.analyze(str(path))
    assert_shared(report, "modell_lots_kalibriert", 4000)
    parsed = parser.load_export(path)
    assert drawdown.run(parsed)["startkapital_raw"] == 4000
    assert exposure.run(parsed)["startkapital"] == 4000


def test_explicit_foreign_trade_money_cannot_become_usd_from_capital_fallback(tmp_path):
    path = history(tmp_path)
    with pytest.raises(ValueError, match="Fremdwaehrung"):
        engine.analyze(str(path), quellen_stats={"account_currency": "EUR"})
