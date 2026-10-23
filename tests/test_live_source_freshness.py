"""A strict live refresh must reject offline fallback even with intact caches."""
from types import SimpleNamespace

import pytest

from mqlkiscanner import db, downloader_client, ingest, katalog, pipeline, quellen


@pytest.fixture
def cached_source(monkeypatch):
    qid = db.add_quelle("fresh", "fresh", "http://synthetic.invalid")
    source = db.get_quelle(qid)
    class Online:
        def metrics(self, *args):
            return {"signalId": 77, "version": "mql5", "metrics": {"Currency": "USD"}}
        def trades_csv(self, *args):
            return b"Time;Type;Volume;Symbol;Price;Time;Price;Commission;Swap;Profit\n"
    path, _ = ingest.hole_trades(source, 77, "mql5", client=Online())
    ingest.hole_metrics(source, 77, "mql5", client=Online())
    class Offline:
        def metrics(self, *args):
            raise downloader_client.DownloaderConnectionError("offline")
        def trades_csv(self, *args):
            raise downloader_client.DownloaderConnectionError("offline")
    monkeypatch.setattr(quellen, "client_fuer_quelle", lambda q: Offline())
    return source, path


def test_default_offline_read_works_but_strict_trade_refresh_fails(cached_source):
    source, path = cached_source
    assert ingest.hole_trades(source, 77, "mql5") == (path, False)
    with pytest.raises(downloader_client.DownloaderConnectionError, match="offline"):
        ingest.hole_trades(source, 77, "mql5", allow_offline_cache=False)


def test_strict_catalog_refresh_does_not_retain_previous_currency_proof(cached_source):
    source, path = cached_source
    owner = db.resolve_identity(77, quelle="fresh")
    r = pipeline.ScanResult(id=77, quelle="fresh", platform="MT5", quelle_id=source["id"],
                           quelle_version="mql5", quellen_uid=source["quellen_uid"],
                           signal_ref=owner.signal_ref, account_currency="USD", trades_path=path)
    with pytest.raises(downloader_client.DownloaderConnectionError, match="offline"):
        katalog.lade_signal_daten(r, allow_offline_cache=False)
    assert r.account_currency is None


def test_strict_pipeline_rejects_offline_metrics_before_any_forensics(cached_source, monkeypatch):
    source, _ = cached_source
    from mqlkiscanner import engine
    monkeypatch.setattr(engine, "analyze", lambda *a, **kw: pytest.fail("No old source basis in a fresh run"))
    p = pipeline.ScanPipeline(allow_offline_source_cache=False)
    candidate = {"id": 77, "name": "synthetic", "platform": "MT5", "quelle_kuerzel": "fresh",
                 "quelle_id": source["id"], "quellen_uid": source["quellen_uid"], "quelle_version": "mql5"}
    # One attempt, to avoid exercising the unrelated five-second retry policy.
    result = p._analyze_candidate_once(None, candidate, log=lambda text: None)
    assert not result.forensik_vorhanden and "offline" in result.fehler
