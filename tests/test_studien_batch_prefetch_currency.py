"""B11: prepare native MQL currency and trades before any terminal access."""
from pathlib import Path
from unittest.mock import Mock

import pytest

from mqlkiscanner import db, downloader_client, katalog, kursdaten, pipeline, quellen, studien_batch

CSV = b"Time;Type;Volume;Symbol;Price;Volume;Time;Price;Commission;Swap;Profit\n"


def source_result(currency):
    qid = db.add_quelle("native", "Synthetic MQL source", "http://synthetic.invalid")
    db.katalog_upsert_many("native", [{"signal_id": 7, "version": "mql5", "platform": "mt5"}])
    return pipeline.ScanResult(id=7, quelle="native", quelle_id=qid,
                               quelle_version="mql5", platform="MT5", account_currency=currency)


def setup_client(monkeypatch, replies, *, trade_failure=False):
    trace = []
    remaining = list(replies)

    class Client:
        def metrics(self, sid, version):
            trace.append("metrics")
            value = remaining.pop(0) if len(remaining) > 1 else remaining[0]
            if isinstance(value, Exception):
                raise value
            return {"signalId": sid, "version": version, "metrics": {"Currency": value}}

        def trades_csv(self, sid, version):
            trace.append("trades")
            if trade_failure:
                raise downloader_client.DownloaderError("synthetic CSV unavailable")
            return CSV

    monkeypatch.setattr(quellen, "client_fuer_quelle", lambda source: Client())
    provider = Mock(terminal_idx=0)
    provider.starten.side_effect = lambda: (trace.append("terminal") or (True, "synthetic"))
    factory = Mock(return_value=provider)
    monkeypatch.setattr(kursdaten, "KursDaten", factory)
    return trace, factory


def control():
    return dict(abbruch=False, aktuell=0, gerechnet=0, uebersprungen=0, fehler=[], summary="")


@pytest.mark.parametrize("currency", [None, "unknown", "unbekannt"])
def test_unknown_mql_prepares_usd_and_trade_cache_before_terminal(monkeypatch, currency):
    result = source_result(currency)
    trace, factory = setup_client(monkeypatch, ["USD"])

    def calculate(res, *_):
        assert Path(res.trades_path).read_bytes() == CSV
        assert res.trades_sha256
        trace.append("calculate")
        return True

    monkeypatch.setattr(studien_batch, "_rechne_ein_signal", calculate)
    state = control()
    studien_batch._laufe([result], state, {}, True)
    assert state.get("vorladen_gesamt") == state.get("vorladen_fertig") == 1
    assert state["fehler"] == [] and state["gerechnet"] == 1
    assert trace.index("trades") < trace.index("terminal") < trace.index("calculate")
    factory.assert_called_once()


def test_unknown_mql_trade_failure_never_starts_terminal_or_retries(monkeypatch):
    result = source_result(None)
    trace, factory = setup_client(monkeypatch, ["USD"], trade_failure=True)
    state = control()
    studien_batch._laufe([result], state, {}, True)
    factory.assert_not_called()
    assert trace.count("trades") == 1
    assert state.get("vorladen_fertig") == 1 and len(state["fehler"]) == 1


@pytest.mark.parametrize("currency", ["EUR", "USC", "GBP"])
def test_known_non_usd_is_not_fetched_and_never_starts_terminal(monkeypatch, currency):
    result = source_result(currency)
    trace, factory = setup_client(monkeypatch, ["USD"])
    state = control()
    studien_batch._laufe([result], state, {}, True)
    assert trace == []
    factory.assert_not_called()
    assert state.get("vorladen_gesamt", 0) == 0
    assert len(state["fehler"]) == 1


@pytest.mark.parametrize("currency", [None, "unknown", "EUR", "USC"])
def test_new_metrics_cannot_reuse_previous_usd_proof_or_retry_into_usd(monkeypatch, currency):
    result = source_result("USD")
    # A later metrics retry would claim USD; the failed preparation must not
    # be revived by that second request in the serial computation loop.
    trace, factory = setup_client(monkeypatch, [currency, "USD"])
    state = control()
    studien_batch._laufe([result], state, {}, True)
    factory.assert_not_called()
    assert trace.count("metrics") == 1
    assert state["gerechnet"] == 0 and len(state["fehler"]) == 1


def test_old_usd_metrics_cache_does_not_authorize_new_native_csv(monkeypatch):
    result = source_result("USD")
    trace, factory = setup_client(monkeypatch, ["USD"])
    source = db.get_quelle(result.quelle_id)
    # Produce an intact old USD cache, then simulate a disconnected metrics
    # endpoint with an otherwise successful new CSV endpoint.
    from mqlkiscanner import ingest
    ingest.hole_metrics(source, result.id, result.quelle_version)
    trace.clear()
    trace2, factory2 = setup_client(monkeypatch, [
        downloader_client.DownloaderConnectionError("synthetic metrics offline")])
    state = control()
    studien_batch._laufe([result], state, {}, True)
    factory2.assert_not_called()
    assert trace2 == ["metrics"]
    assert state["gerechnet"] == 0 and len(state["fehler"]) == 1


def test_converting_source_preserves_verified_offline_metrics_contract(monkeypatch):
    qid = db.add_quelle("vant", "Synthetic converting source", "http://synthetic.invalid/vantage")
    db.katalog_upsert_many("vant", [{"signal_id": 7, "version": "vantage", "platform": "vantage"}])
    result = pipeline.ScanResult(id=7, quelle="vant", quelle_id=qid,
                                 quelle_version="vantage", platform="vantage", account_currency="USD")
    setup_client(monkeypatch, ["EUR"])
    from mqlkiscanner import ingest
    ingest.hole_metrics(db.get_quelle(qid), result.id, result.quelle_version)
    trace, factory = setup_client(monkeypatch, [
        downloader_client.DownloaderConnectionError("synthetic metrics offline")])

    def calculate(res, *_):
        assert res.account_currency == "USD"  # Original account EUR, export normalized USD.
        assert Path(res.trades_path).read_bytes() == CSV
        return True

    monkeypatch.setattr(studien_batch, "_rechne_ein_signal", calculate)
    state = control()
    studien_batch._laufe([result], state, {}, True)
    assert trace == ["metrics", "trades", "terminal"]
    factory.assert_called_once()
    assert state["gerechnet"] == 1 and state["fehler"] == []


def test_stop_after_currency_resolution_does_not_start_csv_fetch(monkeypatch):
    result = source_result(None)
    state = control()
    def resolve(res):
        res.account_currency = "USD"
        state["abbruch"] = True
    monkeypatch.setattr(katalog, "require_studienwaehrung", resolve)
    fetch = Mock()
    factory = Mock()
    monkeypatch.setattr(katalog, "lade_signal_daten", fetch)
    monkeypatch.setattr(kursdaten, "KursDaten", factory)
    studien_batch._laufe([result], state, {}, True)
    fetch.assert_not_called()
    factory.assert_not_called()
    assert state["phase"] == "abgebrochen" and state["fertig"] is True
