"""Independent integration regressions for source ownership and evidence basis."""
import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from mqlkiscanner import config, db, fix_signale, ingest, katalog, pipeline


def source(label="vant"):
    sid = db.add_quelle(label, label, "http://localhost:1")
    return db.get_quelle(sid)


def test_new_zero_subscriber_catalog_pin_is_added_without_workflow_head():
    q = source()
    db.katalog_upsert_many("vant", [{"signal_id": 42, "name": "Pinned Future", "platform": "vantage",
                                    "version": "vantage", "url": "", "abonnenten": 0, "wochen": None}])
    db.set_signal_fix(42, quelle="vant")
    assert db.get_signal(42, quelle="vant") is None
    pipe = pipeline.ScanPipeline({"listen_modus": "quellen", "min_abonnenten": 1, "min_wochen": 26})
    candidates = []
    pipe._ergaenze_fix_ids(candidates, log=lambda _: None)
    assert len(candidates) == 1
    assert candidates[0]["quelle_kuerzel"] == "vant" and candidates[0]["quelle_id"] == q["id"]
    assert candidates[0]["quellen_uid"] == q["quellen_uid"]
    assert candidates[0]["url"] == ""  # never invent an MQL URL for this provider
    assert pipe.build_candidates(candidates, lambda _: None) == candidates
    assert db.get_signal(42, quelle="vant") is None


@pytest.mark.parametrize("versions", [("mql4", "mql5"), ("mql5", "mql4")])
def test_platform_conflict_cannot_be_hidden_by_ingest_dedup(monkeypatch, versions):
    source("mql5")
    rows = [{"signalId": "42", "version": version, "signalName": version,
             "weeks": 52, "subscribers": 5} for version in versions]
    monkeypatch.setattr(ingest, "hole_katalog", lambda *a, **kw: ingest.KatalogListe(rows, catalog_scope="full"))
    candidates = ingest.kandidaten_aus_quellen()
    selected = pipeline.ScanPipeline({"min_abonnenten": 1, "min_wochen": 26}).build_candidates(candidates, lambda _: None)
    assert selected == [], "Same source+ID with MT4/MT5 conflict must fail closed, not take the first page item"


def test_two_sources_with_equal_ids_keep_both_regular_candidates(monkeypatch):
    source("vant")
    source("pelik")
    monkeypatch.setattr(ingest, "hole_katalog", lambda *a, **kw: ingest.KatalogListe([
        {"signalId": "42", "version": "vantage", "weeks": 52, "subscribers": 5}], catalog_scope="full"))
    candidates = ingest.kandidaten_aus_quellen()
    selected = pipeline.ScanPipeline({"min_abonnenten": 1, "min_wochen": 26}).build_candidates(candidates, lambda _: None)
    assert {c["quelle_kuerzel"] for c in selected} == {"vant", "pelik"}


def test_legacy_ambiguous_pin_cannot_select_any_source_until_explicit_assignment():
    db.init_db()
    for label in ("mql5", "vant"):
        db.resolve_identity(42, quelle=label, create=True)
    assert fix_signale.fix_keys({"fix_signal_ids": [42]}) == set()
    db.set_signal_fix(42, quelle="vant")
    assert fix_signale.fix_keys({"fix_signal_ids": [42]}) == {("vant", 42)}


def test_reports_cannot_share_basis_across_owners_and_source_rename_keeps_basis(monkeypatch):
    q = source("vant")
    other = source("pelik")
    monkeypatch.setattr(config, "load_known_signals", lambda: {"ausgeschlossen": []})
    def result(label, uid):
        return pipeline.ScanResult(id=42, quelle=label, quellen_uid=uid,
                                   trades_sha256="a" * 64, forensik_vorhanden=True,
                                   forensik_version=pipeline.FORENSICS_VERSION)
    own = result("vant", q["quellen_uid"])
    foreign = result("pelik", other["quellen_uid"])
    basis = pipeline.report_basis_for(own, {})
    assert basis != pipeline.report_basis_for(foreign, {})
    db.update_quelle(q["id"], kuerzel="vantage_neu")
    renamed = result("vantage_neu", q["quellen_uid"])
    assert pipeline.report_basis_for(renamed, {}) == basis


def test_candidate_wrong_connection_is_rejected_before_metrics_and_not_persisted(monkeypatch):
    q = source("vant")
    def forbidden(*args, **kwargs):
        raise AssertionError("A mismatched source connection must never fetch metrics")
    monkeypatch.setattr(ingest, "hole_metrics", forbidden)
    result = pipeline.ScanPipeline()._analyze_candidate_once(None, {
        "id": 42, "name": "Wrong owner", "platform": "vantage", "quelle_id": q["id"],
        "quelle_kuerzel": "pelik", "quellen_uid": q["quellen_uid"]}, lambda _: None)
    assert result.fehler and not result.persisted_this_run
    assert db.get_signal(42, quelle="vant") is None and db.get_signal(42, quelle="pelik") is None


def test_mixed_crawl_cannot_hide_conflicting_platform_of_same_identity(monkeypatch):
    source("mql5")
    common = {"id": 42, "abonnenten": 5, "wochen": 52}
    monkeypatch.setattr(pipeline.crawler, "crawl_lists", lambda *a, **kw: [dict(common, platform="MT4")])
    monkeypatch.setattr(ingest, "kandidaten_aus_quellen", lambda *a, **kw: [
        dict(common, platform="mt5", quelle_kuerzel="mql5")])
    pipe = pipeline.ScanPipeline({"listen_modus": "beides", "min_abonnenten": 1, "min_wochen": 26})
    signals = pipe.crawl(lambda *_: None, lambda _: None)
    assert pipe.build_candidates(signals, lambda _: None) == []


def test_llm_does_not_mix_changed_snapshot_payload_with_original_forensic_hash(tmp_path):
    source("mql5")
    path = tmp_path / "history.csv"
    header = "Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;Profit;Comment\n"
    original = "2024.01.01 01:00:00;Buy;0.01;XAUUSD;2000;;;2024.01.02 01:00:00;2001;0;0;1;\n"
    path.write_text(header + original, encoding="utf-8")
    snapshot, measured_sha = db.snapshot_trade_file(str(path))
    # Simulate a damaged evidence file after the in-memory forensic result was built.
    from pathlib import Path
    Path(snapshot).write_text(header + original.replace(";2001;0;0;1;", ";2010;0;0;10;"), encoding="utf-8")
    result = pipeline.ScanResult(id=42, quelle="mql5", trades_path=snapshot,
                                 trades_sha256=measured_sha, forensik_vorhanden=True,
                                 forensik_version=pipeline.FORENSICS_VERSION)
    fake = SimpleNamespace(has_key=True, usage=SimpleNamespace(total_tokens=0),
                           chat=Mock(return_value="Fake response. Kurzfassung: test."))
    pipe = pipeline.ScanPipeline()
    pipe.llm = fake
    outcome = pipe.run_llm([result], lambda _: None)
    assert fake.chat.call_count == 0, "Changed bytes must not become a prompt bound to the old forensic CSV hash"
    assert outcome["failed"] >= 1


def test_catalog_sync_conflicting_platform_identity_preserves_previous_catalog(monkeypatch):
    source("mql5")
    db.katalog_upsert_many("mql5", [{"signal_id": 99, "name": "Old known catalog", "platform": "mt5"}])
    before = db.katalog_list()
    monkeypatch.setattr(ingest, "hole_katalog", lambda *a, **kw: [
        {"signalId": "42", "version": "mql4", "signalName": "MT4 owner", "weeks": 52, "subscribers": 5},
        {"signalId": "42", "version": "mql5", "signalName": "MT5 owner", "weeks": 52, "subscribers": 5}])
    outcome = katalog.sync()
    assert outcome["quellen"]["mql5"]["fehler"], "An ambiguous identity is not a replacement catalog"
    assert db.katalog_list() == before
