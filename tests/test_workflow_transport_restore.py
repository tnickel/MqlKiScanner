"""Schema-2 workflow persistence must preserve a proven source transport."""
from dataclasses import replace

import pytest

from mqlkiscanner import db, downloader_client, ingest, katalog, pipeline


def _workflow(source="vant", platform="vantage", sid=42):
    qid = db.add_quelle(source, source, f"http://{source}.invalid")
    db.upsert_signal(sid, name="Synthetic workflow", platform=platform, quelle=source)
    assert db.katalog_list() == []
    result = next(r for r in pipeline.results_from_db(materialize_pdfs=False)
                  if r.id == sid and r.quelle == source)
    assert result.signal_ref and result.quellen_uid
    assert result.quelle_id is None and result.quelle_version == ""
    return qid, result


@pytest.mark.parametrize("platform,version", [
    ("vantage", "vantage"), ("pelican", "pelican"), ("zulu", "zulu"),
    ("MT4", "mql4"), ("MT5", "mql5"),
])
def test_persisted_workflow_without_catalogue_restores_exact_registered_owner(platform, version):
    qid, result = _workflow(platform=platform)
    assert katalog.quellen_referenz(result) == (qid, version)
    assert result.quelle_id is None  # Resolver does not rewrite the workflow.


def test_equal_external_id_in_other_source_does_not_replace_transport():
    qid, result = _workflow()
    other_qid = db.add_quelle("pelik", "Other", "http://other.invalid")
    db.upsert_signal(42, platform="pelican", quelle="pelik")
    other = next(r for r in pipeline.results_from_db(materialize_pdfs=False) if r.quelle == "pelik")
    assert katalog.quellen_referenz(result) == (qid, "vantage")
    assert katalog.quellen_referenz(other) == (other_qid, "pelican")
    assert result.signal_ref != other.signal_ref


@pytest.mark.parametrize("conflict", ["uid", "alias", "reference", "id", "version"])
def test_conflicting_owner_evidence_stops_before_transport_fetch(monkeypatch, conflict):
    _, result = _workflow()
    db.add_quelle("foreign", "Other", "http://foreign.invalid")
    db.upsert_signal(42, platform="vantage", quelle="foreign")
    foreign = db.resolve_identity(42, quelle="foreign")
    if conflict == "uid":
        result.quellen_uid = foreign.quellen_uid
    elif conflict == "alias":
        result.quelle = "foreign"
    elif conflict == "reference":
        result.signal_ref = foreign.signal_ref
    elif conflict == "id":
        result.id = 43
    else:
        result.quelle_version = "mql5"
    monkeypatch.setattr(ingest, "hole_metrics", lambda *a, **k: pytest.fail("owner conflict"))
    monkeypatch.setattr(ingest, "hole_trades", lambda *a, **k: pytest.fail("owner conflict"))
    with pytest.raises(ValueError):
        katalog.quellen_referenz(result)
    with pytest.raises(downloader_client.DownloaderError):
        katalog.lade_signal_daten(result, allow_offline_cache=False)


@pytest.mark.parametrize("platform", ["", "unknown", "rst", "mql6"])
def test_unknown_platform_is_not_defaulted_from_source_or_old_version(platform):
    _, result = _workflow()
    result.platform = platform
    result.quelle_version = "vantage"
    assert katalog.quellen_referenz(result) is None


def test_unbound_legacy_owner_is_not_inferred_from_registry_or_numeric_id():
    _, proven = _workflow()
    legacy = pipeline.ScanResult(id=42, quelle="unproven", platform="vantage",
                                 quellen_uid=proven.quellen_uid)
    assert katalog.quellen_referenz(legacy) is None
    assert katalog.quellen_referenz(replace(legacy, quellen_uid="")) is None


def test_removed_or_inactive_transport_does_not_fall_back_to_foreign_owner():
    qid, result = _workflow()
    db.add_quelle("foreign", "Other", "http://foreign.invalid")
    db.upsert_signal(42, platform="vantage", quelle="foreign")
    db.update_quelle(qid, aktiv=False)
    assert katalog.quellen_referenz(result) is None
    db.delete_quelle(qid)
    assert katalog.quellen_referenz(result) is None


def test_explicit_same_uid_mirrors_keep_stable_active_transport_preference():
    qid, result = _workflow()
    mirror = db.add_quelle("mirror", "Mirror", "http://mirror.invalid",
                           quellen_uid=result.quellen_uid)
    db.add_quelle("mirror2", "Mirror 2", "http://mirror2.invalid",
                  quellen_uid=result.quellen_uid)
    assert katalog.quellen_referenz(result) == (qid, "vantage")
    db.update_quelle(qid, aktiv=False)
    assert katalog.quellen_referenz(result) == (mirror, "vantage")
    db.delete_quelle(qid)
    assert katalog.quellen_referenz(result) == (mirror, "vantage")
    db.update_quelle(mirror, kuerzel="renamed-mirror")
    assert katalog.quellen_referenz(result) == (mirror, "vantage")


def test_restored_workflow_runs_strict_on_demand_fetch_without_catalogue(tmp_path, monkeypatch):
    qid, result = _workflow()
    calls = []
    path = tmp_path / "synthetic.csv"
    path.write_bytes(b"synthetic cache")

    def metrics(q, sid, version, **kwargs):
        calls.append(("metrics", q["id"], sid, version, kwargs))
        return {"signalId": sid, "version": version, "metrics": {"Currency": "USD"}}

    def trades(q, sid, version, **kwargs):
        calls.append(("trades", q["id"], sid, version, kwargs))
        return str(path), True

    monkeypatch.setattr(ingest, "hole_metrics", metrics)
    monkeypatch.setattr(ingest, "hole_trades", trades)
    assert katalog.lade_signal_daten(result, allow_offline_cache=False) == (str(path), True)
    assert calls == [(kind, qid, 42, "vantage", {"allow_offline_cache": False})
                     for kind in ("metrics", "trades")]
    assert result.quelle_id == qid and result.quelle_version == "vantage"
