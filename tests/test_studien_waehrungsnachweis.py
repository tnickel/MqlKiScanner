"""Legacy-MQL-Metadaten vor der USD-Studie erneuern, ohne Einheiten zu raten."""
import hashlib
from unittest.mock import Mock

import pytest

from mqlkiscanner import db, downloader_client, ingest, katalog, kursdaten, pipeline, quellen, studien_batch


@pytest.fixture
def native_source(tmp_path, monkeypatch):
    db.init_db()
    qid = db.add_quelle("mql5", "Synthetic native source", "http://127.0.0.1:1")
    db.katalog_upsert_many("mql5", [dict(signal_id=123, version="mql5", platform="mt5")])
    csv = tmp_path / "native.csv"
    csv.write_text(
        "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"
        "2026.01.05 10:00:00;Buy;0.10;EURUSD;1.1000;0.10;2026.01.05 11:00:00;1.1100;0;0;100\n",
        encoding="utf-8")
    res = pipeline.ScanResult(id=123, name="Legacy USD", quelle="mql5", platform="MT5",
                              trades_path=str(csv), trades_sha256=hashlib.sha256(csv.read_bytes()).hexdigest())
    response = dict(signalId=123, version="mql5", metrics={"Currency": "USD", "InitialDeposit": 1000})
    client = Mock()
    client.metrics.return_value = response
    monkeypatch.setattr(quellen, "client_fuer_quelle", lambda _: client)
    return res, db.get_quelle(qid), client, response


def test_missing_currency_refreshes_metadata_even_with_cached_trades(native_source):
    res, source, client, _ = native_source
    katalog.require_studienwaehrung(res)
    assert res.account_currency == "USD"
    assert res.quelle_id == source["id"] and res.quelle_version == "mql5"
    client.metrics.assert_called_once_with(123, "mql5")
    client.trades_csv.assert_not_called()
    assert katalog.metrics_stats(res)["account_currency"] == "USD"


def test_batch_refreshes_before_terminal_and_persists_usd_study(native_source, monkeypatch):
    res, _, client, _ = native_source
    provider = Mock(terminal_idx=0)
    provider.starten.return_value = (True, "synthetic")

    def provider_factory(_):
        assert client.metrics.call_count == 1
        assert res.account_currency == "USD"
        return provider

    monkeypatch.setattr(kursdaten, "KursDaten", provider_factory)
    reconstruct = Mock(return_value=dict(verlaesslich=True, equity_dd_pct=10.0,
                                         equity_dd_usd=100.0, account_currency="USD"))
    monkeypatch.setattr(studien_batch, "_rekonstruiere_mit_feed_fallback", reconstruct)
    control = dict(abbruch=False, aktuell=0, gerechnet=0, uebersprungen=0, fehler=[], summary="")
    studien_batch._laufe([res], control, {}, True)
    assert control["fertig"] and control["gerechnet"] == 1 and not control["fehler"]
    reconstruct.assert_called_once()
    assert reconstruct.call_args.args[2] == 1000
    stored = db.get_equity_studie(123)
    assert stored["report"]["account_currency"] == "USD"
    assert stored["trades_sha"] == res.trades_sha256
    assert not stored["virtuell"]


@pytest.mark.parametrize("currency", [None, "unknown", "EUR", "USC"])
def test_unproved_or_foreign_fresh_currency_never_starts_terminal(native_source, monkeypatch, currency):
    res, _, _, response = native_source
    if currency is None:
        response["metrics"].pop("Currency")
    else:
        response["metrics"]["Currency"] = currency
    factory = Mock()
    monkeypatch.setattr(kursdaten, "KursDaten", factory)
    control = dict(abbruch=False, aktuell=0, gerechnet=0, uebersprungen=0, fehler=[], summary="")
    studien_batch._laufe([res], control, {}, True)
    factory.assert_not_called()
    assert control["gerechnet"] == 0 and len(control["fehler"]) == 1
    assert "Kontowährung" in control["fehler"][0]
    assert db.get_equity_studie(123) is None


def test_offline_refresh_does_not_reuse_an_old_usd_cache(native_source):
    res, source, client, _ = native_source
    ingest.hole_metrics(source, 123, "mql5", client=client)
    client.metrics.side_effect = downloader_client.DownloaderConnectionError("synthetic offline")
    with pytest.raises(ValueError, match="Währungsnachweis konnte nicht"):
        katalog.require_studienwaehrung(res)
    assert res.account_currency is None
    # Der normale Import behält seinen ausdrücklich erlaubten Offlinepfad.
    assert ingest.hole_metrics(source, 123, "mql5", client=client)["metrics"]["Currency"] == "USD"


@pytest.mark.parametrize("field,value", [("signalId", 456), ("version", "mql4")])
def test_foreign_response_cannot_prove_currency(native_source, field, value):
    res, _, _, response = native_source
    response[field] = value
    with pytest.raises(ValueError, match="anderen Signal|anderen Plattform"):
        katalog.require_studienwaehrung(res)
    assert res.account_currency is None


@pytest.mark.parametrize("field,value", [("quelle", "different"), ("platform", "MT4"),
                                        ("quelle_version", "mql4")])
def test_conflicting_source_assignment_is_rejected_before_fetch(native_source, field, value):
    res, source, client, _ = native_source
    res.quelle_id, res.quelle_version = source["id"], "mql5"
    setattr(res, field, value)
    with pytest.raises(ValueError, match="Zuordnung|zuordnung|Kontowährung|widersprechen sich"):
        katalog.require_studienwaehrung(res)
    client.metrics.assert_not_called()


@pytest.mark.parametrize("currency", ["EUR", "USC"])
def test_explicit_foreign_currency_is_not_replaced_with_usd(native_source, currency):
    res, _, client, _ = native_source
    res.account_currency = currency
    with pytest.raises(ValueError, match=f"Kontowährung {currency}"):
        katalog.require_studienwaehrung(res)
    client.metrics.assert_not_called()


def test_already_proved_usd_does_not_require_an_extra_request(native_source):
    res, _, client, _ = native_source
    res.account_currency = "USD"
    katalog.require_studienwaehrung(res)
    client.metrics.assert_not_called()


def test_single_study_refreshes_currency_before_terminal(native_source, monkeypatch):
    from mqlkiscanner import equity_studie_ui
    res, _, client, _ = native_source
    provider = Mock()
    provider.starten.return_value = (False, "synthetic terminal reached")
    factory = Mock(return_value=provider)
    monkeypatch.setattr(kursdaten, "KursDaten", factory)
    with pytest.raises(RuntimeError, match="synthetic terminal reached"):
        equity_studie_ui.berechne(res, lambda *_: None)
    assert client.metrics.call_count == 1
    assert res.account_currency == "USD" and factory.call_count == 1


def test_single_study_uses_fresh_initial_deposit(native_source, monkeypatch):
    from mqlkiscanner import equity_studie_ui
    res, _, _, _ = native_source
    provider = Mock()
    provider.starten.return_value = (True, "synthetic")
    monkeypatch.setattr(kursdaten, "KursDaten", lambda _: provider)
    study = Mock(return_value={"status": "ok"})
    monkeypatch.setattr(equity_studie_ui, "studie", study)
    equity_studie_ui.berechne(res, lambda *_: None)
    assert study.call_args.args[2] == 1000
    provider.beenden.assert_called_once()


@pytest.mark.parametrize("has_trades", [False, True])
def test_trade_reload_must_not_bypass_failed_currency_proof(native_source, monkeypatch, has_trades):
    res, source, _, _ = native_source
    res.account_currency = "USD"
    res.quelle_id, res.quelle_version = source["id"], "mql5"
    if has_trades:
        # Header-Cache mit belegter Historie löst den zweiten Nachladepfad aus.
        from pathlib import Path
        Path(res.trades_path).write_text(
            "Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n",
            encoding="utf-8")
        monkeypatch.setattr(katalog, "metrics_stats", lambda _: {"quelle_trades_anzahl": 10})
    else:
        res.trades_path = ""

    def reload_without_proof(result):
        result.account_currency = None
        return "new-native.csv", True

    reload = Mock(side_effect=reload_without_proof)
    monkeypatch.setattr(katalog, "lade_signal_daten", reload)
    reconstruct = Mock()
    monkeypatch.setattr(studien_batch, "_rekonstruiere_mit_feed_fallback", reconstruct)
    with pytest.raises(ValueError, match="Kontowährung"):
        studien_batch._rechne_ein_signal(res, {}, Mock(), True)
    reload.assert_called_once()
    reconstruct.assert_not_called()
    assert db.get_equity_studie(123) is None
