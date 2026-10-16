"""The MQL source exports native money; a source transport does not prove USD."""
import json
import hashlib
from unittest.mock import Mock

import pytest

from mqlkiscanner import db, downloader_client, ingest, katalog, pipeline


@pytest.mark.parametrize("currency", [None, "unknown", "USC", "EUR", "USD"])
def test_source_adapter_preserves_native_money_without_implicit_usd(currency):
    metrics = {"Balance": 1100, "InitialDeposit": 1000}
    if currency is not None:
        metrics["Currency"] = currency
    stats = ingest.metrics_zu_stats({"version": "mql5", "metrics": metrics}, "mql5")
    assert stats["account_currency"] == (currency.upper() if currency else None)
    assert stats["balance_account"] == 1100
    assert stats["initial_deposit_account"] == 1000
    assert stats["balance_usd"] == (1100 if currency == "USD" else None)
    assert stats["initial_deposit_usd"] == (1000 if currency == "USD" else None)


@pytest.mark.parametrize("currency", [None, "unknown", "USC", "EUR", "USD"])
@pytest.mark.parametrize("alias", ["mql5", "mql_mirror", "robo", "pelican", "vantage", "vant", "zulu"])
def test_source_pipeline_currency_guard_precedes_fx_and_terminal(tmp_path, monkeypatch, currency, alias):
    db.init_db()
    qid = db.add_quelle(alias, "Synthetic MQL mirror", "http://127.0.0.1:1")
    csv = tmp_path / "native.csv"
    csv.write_text("synthetic native export", encoding="utf-8")
    metrics = {"Balance": 1100, "InitialDeposit": 1000}
    if currency is not None:
        metrics["Currency"] = currency
    monkeypatch.setattr(ingest, "hole_metrics", lambda *_: {"version": "mql5", "metrics": metrics})
    monkeypatch.setattr(ingest, "hole_trades", lambda *_: (str(csv), True))
    reached = Mock(side_effect=RuntimeError("USD validation passed; synthetic stop"))
    monkeypatch.setattr(pipeline.fx_rates, "status", reached)
    forbidden = Mock(side_effect=AssertionError("No native money may enter USD forensics"))
    monkeypatch.setattr(pipeline, "analyze_export", forbidden)
    result = pipeline.ScanPipeline({})._analyze_candidate_once(None,
        {"id": 123, "platform": "MT5", "quelle_id": qid,
         "quelle_kuerzel": alias, "quelle_version": "mql5"}, lambda _: None)
    assert not result.forensik_vorhanden
    assert reached.call_count == int(currency == "USD")
    assert ("synthetic stop" if currency == "USD" else "Kontowährung") in result.fehler
    forbidden.assert_not_called()
    stored = json.loads(db.get_signal(123)["stats_json"])
    assert stored["account_money"]["balance_account"] == 1100
    assert stored["balance_usd"] == (1100 if currency == "USD" else None)


@pytest.mark.parametrize("version,alias", [("pelican", "pelican"), ("vantage", "vant"),
                                         ("zulu", "zulu"), ("mql5", "robo")])
def test_documented_usd_normalizing_source_contract_is_preserved(version, alias):
    metrics = {"Balance": 1100}
    if alias == "robo":
        metrics["Currency"] = "USD"  # Actual Robo contract; its alias proves no unit.
    stats = ingest.metrics_zu_stats({"version": version, "metrics": metrics}, alias)
    assert stats["account_currency"] == "USD"
    assert stats["balance_usd"] == 1100


def test_pelican_currency_is_original_account_while_exported_money_is_usd():
    stats = ingest.metrics_zu_stats({"version": "pelican", "metrics": {
        "Currency": "EUR", "CurrencyConvertedToUsd": True, "Balance": 1100}}, "pelik")
    assert stats["account_currency"] == "USD"
    assert stats["balance_usd"] == 1100
    assert stats["balance_account"] is None


@pytest.mark.parametrize("currency", [None, "USC", "EUR", "USD"])
def test_catalogue_retains_verified_currency_before_study_guard(tmp_path, currency):
    db.init_db()
    qid = db.add_quelle("robo", "Synthetic MQL mirror", "http://127.0.0.1:1")
    db.katalog_upsert_many("robo", [{"signal_id": 123, "version": "mql5", "platform": "mt5"}])
    for kind, payload in (("trades", b"synthetic native export"),
            ("metrics", json.dumps({"signalId": 123, "version": "mql5", "metrics": {
                "Currency": currency, "Balance": 1100, "InitialDeposit": 1000}}).encode())):
        path = tmp_path / kind
        path.write_bytes(payload)
        db.store_quellen_artefakt(qid, 123, "mql5", kind, hashlib.sha256(payload).hexdigest(), str(path))
    results, stats = katalog.katalog_resultate(gescannt=set(), studien={})
    result = results[0]
    assert result.account_currency == currency
    if currency == "USD":
        pipeline.require_usd_account(result)
    else:
        with pytest.raises(ValueError, match="Kontowährung"):
            pipeline.require_usd_account(result)
    assert stats[123]["balance_usd"] == (1100 if currency == "USD" else None)


def test_catalogue_manual_reload_carries_currency_proof_to_result(tmp_path, monkeypatch):
    db.init_db()
    qid = db.add_quelle("mirror", "Synthetic MQL mirror", "http://127.0.0.1:1")
    result = pipeline.ScanResult(id=123, quelle="mirror", quelle_id=qid,
                                 platform="MT5", quelle_version="mql5")
    monkeypatch.setattr(ingest, "hole_metrics", lambda *_: {"metrics": {"Currency": "USD"}})
    monkeypatch.setattr(ingest, "hole_trades", lambda *_: (str(tmp_path / "trades"), True))
    katalog.lade_signal_daten(result)
    assert result.account_currency == "USD"
    pipeline.require_usd_account(result)


def test_failed_native_metrics_reload_invalidates_previous_usd_proof_for_new_csv(tmp_path, monkeypatch):
    db.init_db()
    qid = db.add_quelle("robo", "Synthetic native mirror", "http://127.0.0.1:1")
    result = pipeline.ScanResult(id=123, quelle="robo", quelle_id=qid, platform="MT5",
                                 quelle_version="mql5", account_currency="USD")
    monkeypatch.setattr(ingest, "hole_metrics", Mock(side_effect=downloader_client.DownloaderError("synthetic metadata error")))
    monkeypatch.setattr(ingest, "hole_trades", lambda *_: (str(tmp_path / "new_native.csv"), True))
    path, changed = katalog.lade_signal_daten(result)
    assert changed and path.endswith("new_native.csv")
    assert result.account_currency is None
    with pytest.raises(ValueError, match="Kontowährung"):
        pipeline.require_usd_account(result)


@pytest.mark.parametrize("evidence_version", [None, 18, 19])
def test_old_implicit_db_usd_does_not_authorize_a_fresh_native_study(evidence_version):
    db.init_db()
    stats = {"account_currency": "USD", "forensik_version": 18}
    if evidence_version is not None:
        stats["account_currency_evidence_version"] = evidence_version
    results = pipeline.results_from_db(catalog_rows=[{
        "signal_id": 123, "quelle": "robo", "platform": "MT5", "stats": stats,
    }], studien={}, materialize_pdfs=False)
    result = results[0]
    if evidence_version == 19:
        assert result.account_currency == "USD"
        pipeline.require_usd_account(result)
    else:
        assert result.account_currency is None
        with pytest.raises(ValueError, match="Kontowährung"):
            pipeline.require_usd_account(result)
