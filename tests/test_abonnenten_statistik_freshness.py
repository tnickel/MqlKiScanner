"""A catalog read is no dated counter acquisition; native history is primary."""
from datetime import datetime, timedelta
from time import monotonic, sleep

import pytest

from mqlkiscanner import abonnenten_statistik as abo, client_updates, db, downloader_client, quellen


class NativeHistory:
    def __init__(self, version, count=2):
        self.version = version
        self.old = (datetime.now()-timedelta(days=7)).isoformat(timespec="seconds")
        self.rows = [dict(signalId=str(sid), version=version, signalName=f"Provider {sid}", subscribers=10)
                     for sid in range(1, count+1)]
        self.histories = {sid: [dict(timestamp=self.old, subscribers=10, change=0)]
                          for sid in range(1, count+1)}
        self.scopes = []

    def katalog(self, *, limit, offset, min_subscribers, catalog_scope):
        self.scopes.append(catalog_scope)
        assert catalog_scope == "full", "History mirroring must not infer new points from an overlay"
        return dict(items=self.rows[offset:offset+limit], total=len(self.rows), offset=offset, catalogScope="full")

    def history(self, sid, version):
        assert version == self.version
        if sid not in self.histories:
            raise downloader_client.DownloaderNotFound("No native dated history")
        return self.histories[sid]


def wire(monkeypatch, source_name="pelik", version="pelican", count=2):
    source = db.get_quelle(db.add_quelle(source_name, "Fixture", "http://native-history.invalid"))
    client = NativeHistory(version, count)
    monkeypatch.setattr(quellen, "_ensure", lambda: None)
    monkeypatch.setattr(quellen, "client_fuer_quelle", lambda *a, **kw: client)
    return source, client


def history(source, sid, version):
    return [(row["ts"], row["subscribers"], row["change"])
            for row in db.get_history(sid, version, quelle=source["kuerzel"])]


def wait_for_refresh():
    deadline = monotonic()+15
    while monotonic() < deadline:
        state = abo.refresh_zustand()
        if state.get("fertig") and not state.get("laeuft"):
            return state
        sleep(.01)
    pytest.fail("Fixture refresh did not finish")


@pytest.mark.parametrize("source_name,version", [
    ("mql5", "mql5"), ("pelik", "pelican"), ("vant", "vantage"), ("robo", "rst"), ("zulu", "zulu")])
def test_repeated_reads_keep_all_five_native_histories_without_today_points(monkeypatch, source_name, version):
    source, client = wire(monkeypatch, source_name, version)
    # A cache counter may change due to a GUI/detail action without any dated
    # native observation. Neither the cache value nor a caller flag dates it.
    client.rows[0]["subscribers"] = 999
    first = abo.sync_quelle(source)
    before = history(source, 1, version)
    second = abo.sync_quelle(source, eigene_messpunkte=True)
    assert first["messpunkte"] == second["messpunkte"] == 0
    assert first["history_punkte"] == second["history_punkte"] == 2
    assert history(source, 1, version) == before == [(client.old, 10, 0)]
    assert history(source, 2, version) == [(client.old, 10, 0)]
    assert len(db.katalog_list()) == 2


def test_native_404_never_fabricates_a_replacement_point_from_catalog(monkeypatch):
    source, client = wire(monkeypatch)
    client.histories.pop(1)
    result = abo.sync_quelle(source, eigene_messpunkte=True)
    assert result["messpunkte"] == 0 and history(source, 1, "pelican") == []
    assert history(source, 2, "pelican") == [(client.old, 10, 0)]


def test_explicit_refresh_adds_only_200_actual_native_points_to_300_provider_catalog(monkeypatch):
    source, client = wire(monkeypatch, count=300)
    abo.sync_quelle(source)
    outside_before = {sid: history(source, sid, "pelican") for sid in range(201, 301)}
    measured_at = (datetime.now()-timedelta(minutes=5)).isoformat(timespec="seconds")
    updates = []

    def native_refresh(settings, **kwargs):
        assert kwargs["modus"] == "abonnenten" and kwargs["tradelisten"] is False
        updates.append(1)
        # The native job itself records its genuine selected observations.
        for sid in range(1, 201):
            client.histories[sid].append(dict(timestamp=measured_at, subscribers=20, change=10))
            client.rows[sid-1]["subscribers"] = 20
        # A later GUI-only counter change has no date binding to that job.
        client.rows[0]["subscribers"] = 777
        return {"pelik": dict(status=client_updates.FERTIG, job_id="native-own", modus="abonnenten",
                              datenstand=measured_at, signale_geliefert=200)}

    monkeypatch.setattr(client_updates, "starte_alle_updates", native_refresh)
    assert abo.starte_refresh(messen=True, kuerzels=["pelik"])
    state = wait_for_refresh()
    assert state["fehler"] == "" and updates == [1]
    assert len(db.katalog_list()) == 300
    assert state["summary"]["quellen"]["pelik"]["messpunkte"] == 0
    assert len(db.subscriber_history_alle()) == 500  # 300 old + exactly 200 actual new native points.
    for sid in range(1, 201):
        assert history(source, sid, "pelican")[-1] == (measured_at, 20, 10)
    for sid in range(201, 301):
        assert history(source, sid, "pelican") == outside_before[sid]
    assert all(row["ts"] in {client.old, measured_at} for row in db.subscriber_history_alle())
    assert client.scopes == ["full", "full"]


def test_read_only_refresh_does_not_create_daily_freshness_or_start_source_jobs(monkeypatch):
    source, client = wire(monkeypatch)
    monkeypatch.setattr(client_updates, "starte_alle_updates", lambda *a, **kw: pytest.fail("Read-only refresh started a job"))
    assert abo.starte_refresh(messen=False)
    state = wait_for_refresh()
    assert state["summary"]["quellen"]["pelik"]["messpunkte"] == 0
    assert history(source, 1, "pelican") == [(client.old, 10, 0)]


def test_old_completed_job_and_changed_overlay_cannot_backdate_counts(monkeypatch):
    source, client = wire(monkeypatch)
    client.rows[0]["subscribers"] = 888
    # A stable old global job says nothing about later GUI-mutated catalog
    # values. Without a native history point, even explicit refresh adds none.
    monkeypatch.setattr(client_updates, "starte_alle_updates", lambda *a, **kw: {
        "pelik": dict(status=client_updates.FERTIG, job_id="old-but-still-current",
                      datenstand=client.old, signale_geliefert=2, modus="abonnenten")})
    assert abo.starte_refresh(messen=True, kuerzels=["pelik"])
    state = wait_for_refresh()
    assert state["summary"]["quellen"]["pelik"]["messpunkte"] == 0
    assert history(source, 1, "pelican") == [(client.old, 10, 0)]
