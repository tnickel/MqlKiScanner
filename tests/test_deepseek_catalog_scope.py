"""The overview's full catalog must not broaden the scan/download scope."""
from types import SimpleNamespace

import pytest

from mqlkiscanner import db, downloader_client, ingest, katalog, quellen


class ProviderAPI:
    """Model the sources' default audience filter and bounded pages."""

    def __init__(self, *, change_total=False):
        self.calls = []
        self.change_total = change_total
        self.items = [
            {"signalId": str(sid), "version": "pelican", "subscribers": audience,
             "signalName": f"Signal {sid}", "weeks": 52}
            for sid, audience in ((1, 7), (2, 0), (3, 0), (4, 2), ("test_1", 0))
        ]

    def get(self, url, *, params=None, **kwargs):
        assert url.endswith("/api/v1/providers"), "Catalog sync must not fetch trades or history"
        params = dict(params or {})
        self.calls.append(params)
        minimum = params.get("minSubscribers", 1)
        rows = [row for row in self.items if row["subscribers"] >= minimum]
        offset = params.get("offset", 0)
        block = rows[offset:offset + min(params.get("limit", 500), 2)]
        total = len(rows) + int(self.change_total and offset > 0)
        data = {"items": block, "count": len(block), "total": total, "offset": offset}
        return SimpleNamespace(status_code=200, json=lambda: data)


def wire_source(monkeypatch, *, change_total=False):
    db.init_db()
    source = db.get_quelle(db.add_quelle("pelik", "Catalog test", "http://catalog.test:8090"))
    client = downloader_client.DownloaderClient(source["base_url"])
    api = ProviderAPI(change_total=change_total)
    monkeypatch.setattr(downloader_client.requests, "get", api.get)
    monkeypatch.setattr(quellen, "client_fuer_quelle", lambda source, **kwargs: client)
    return source, client, api


def test_client_default_keeps_existing_subscriber_scope(monkeypatch):
    _, client, api = wire_source(monkeypatch)
    page = client.katalog()
    assert page["total"] == 2
    assert api.calls == [{"limit": 500, "offset": 0, "minSubscribers": 1}]


@pytest.mark.parametrize("minimum", [0, 1, 7])
def test_client_exposes_subscriber_scope_without_losing_pagination_or_version(monkeypatch, minimum):
    _, client, api = wire_source(monkeypatch)
    client.katalog(limit=17, offset=2, version="pelican", min_subscribers=minimum)
    assert api.calls == [{"limit": 17, "offset": 2, "version": "pelican",
                          "minSubscribers": minimum}]


def test_full_catalog_sync_retains_zero_audience_through_database_and_display(monkeypatch):
    _, _, api = wire_source(monkeypatch)
    result = katalog.sync()
    assert result["gesamt"] == 4  # Five raw rows; the nonnumeric test ID is discarded only afterwards.
    assert result["quellen"]["pelik"]["fehler"] is None
    assert [call["offset"] for call in api.calls] == [0, 2, 4]
    assert all(call["minSubscribers"] == 0 for call in api.calls)
    rows = {row["signal_id"]: row for row in db.katalog_list()}
    assert set(rows) == {1, 2, 3, 4}
    assert rows[2]["abonnenten"] == rows[3]["abonnenten"] == 0
    displayed, _ = katalog.katalog_resultate()
    assert {row.id for row in displayed} == {1, 2, 3, 4}
    assert db.list_catalog() == []  # Catalog metadata does not create workflow findings.


def test_scan_candidate_fetch_preserves_previous_scope_after_full_catalog_sync(monkeypatch):
    _, _, api = wire_source(monkeypatch)
    katalog.sync()
    api.calls.clear()
    candidates = ingest.kandidaten_aus_quellen()
    assert [row["id"] for row in candidates] == [1, 4]
    assert all(call["minSubscribers"] == 1 for call in api.calls)
    assert len(db.katalog_list()) == 4


def test_incomplete_full_catalog_still_cannot_delete_previous_rows(monkeypatch):
    _, _, api = wire_source(monkeypatch, change_total=True)
    db.katalog_upsert_many("pelik", [{"signal_id": sid} for sid in (1, 2, 99)])
    result = katalog.sync()
    assert result["quellen"]["pelik"]["fehler"]
    assert result["quellen"]["pelik"]["geloescht"] == 0
    assert {row["signal_id"] for row in db.katalog_list()} == {1, 2, 99}
    assert all(call["minSubscribers"] == 0 for call in api.calls)
