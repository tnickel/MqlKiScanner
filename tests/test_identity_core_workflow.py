"""Same external ID must stay independent through actual workflow decisions."""
import json

import pytest

from mqlkiscanner import ampel_verlauf, db, fix_signale, pipeline, regelwerk
from mqlkiscanner.signal_identity import AmbiguousSignalIdentity


def candidate(source, sid=123, platform="MT5"):
    return {"id": sid, "quelle_kuerzel": source, "platform": platform,
            "wochen": 40, "abonnenten": 10}


def test_three_sources_with_equal_ids_survive_filter_and_per_source_slots():
    pipe = pipeline.ScanPipeline({"min_wochen": 26, "min_abonnenten": 1})
    entries = [candidate(source) for source in ("mql5", "vant", "robo")]
    filtered = pipe.build_candidates(entries, lambda _: None)
    selected, _ = fix_signale.waehle_fuer_export(filtered, 1, pipe.settings)
    assert {(c["quelle_kuerzel"], c["id"]) for c in selected} == {
        ("mql5", 123), ("vant", 123), ("robo", 123)}


def test_conflicting_platforms_block_only_their_source_identity():
    pipe = pipeline.ScanPipeline({"min_wochen": 0, "min_abonnenten": 0})
    entries = [candidate("mql5", platform="MT4"), candidate("mql5"), candidate("vant")]
    filtered = pipe.build_candidates(entries, lambda _: None)
    assert [c["quelle_kuerzel"] for c in filtered] == ["vant"]


def test_curated_mql_exclusion_never_applies_to_foreign_equal_id(monkeypatch):
    monkeypatch.setattr(pipeline.config, "load_known_signals", lambda: {
        "ausgeschlossen": [{"id": 123, "grund": "MQL-only finding"}]})
    assert pipeline.ampel_for(pipeline.ScanResult(id=123, quelle="mql5"), {})[0] == "⛔"
    assert pipeline.ampel_for(pipeline.ScanResult(id=123, quelle="vant"), {})[0] != "⛔"
    assert regelwerk.ausgeschlossen_eintrag(123, quelle="vant") is None
    from mqlkiscanner.ampel_matrix import _listen_zelle
    assert _listen_zelle(pipeline.ScanResult(id=123, quelle="vant")).kurz == "nicht gelistet"


def test_equal_trade_hashes_cannot_reuse_other_sources_report():
    settings = {"schranke_eq_dd_pct": 50, "min_calmar_jahr": 3}
    first = pipeline.ScanResult(id=123, quelle="mql5", trades_sha256="a" * 64)
    second = pipeline.ScanResult(id=123, quelle="vant", trades_sha256="a" * 64)
    for result in (first, second):
        identity = db.resolve_identity(result.id, quelle=result.quelle, create=True)
        result.signal_ref, result.quellen_uid = identity.signal_ref, identity.quellen_uid
    basis_a = pipeline.report_basis_for(first, settings)
    basis_b = pipeline.report_basis_for(second, settings)
    assert basis_a != basis_b
    db.store_analysis(123, "gesamtbericht", "offline", 0, "Only MQL", basis=basis_a, quelle="mql5")
    pipeline.restore_current_reports(second, settings)
    assert not second.gesamtbericht
    assert json.loads(pipeline._kandidat_json(second))["quelle"] == "vant"
    with pytest.raises(AmbiguousSignalIdentity):
        db.get_latest_analysis(123, "gesamtbericht")


def test_pin_and_partial_scan_do_not_promote_equal_id_of_other_source():
    db.resolve_identity(123, quelle="mql5", create=True)
    db.resolve_identity(123, quelle="vant", create=True)
    fix_signale.setzen(123, quelle="vant")
    assert fix_signale.fix_keys({}) == {("vant", 123)}
    results = [pipeline.ScanResult(id=123, quelle="mql5", ampel="🔴"),
               pipeline.ScanResult(id=123, quelle="vant", ampel="⚪")]
    assert fix_signale.teilscan_ziel_keys(results, {}) == {("vant", 123)}


def test_colour_history_uses_source_and_preserves_run_trigger():
    a = pipeline.ScanResult(id=123, quelle="mql5", ampel="🟢")
    b = pipeline.ScanResult(id=123, quelle="vant", ampel="🔴")
    assert ampel_verlauf.erfasse_bewertung(a, {}, quelle="full") is None
    assert ampel_verlauf.erfasse_bewertung(b, {}, quelle="gelbgruen") is None
    assert db.get_last_ampel_verlauf(123, quelle="mql5")["ampel"] == "🟢"
    row = db.get_last_ampel_verlauf(123, quelle="vant")
    assert row["ampel"] == "🔴" and row["quelle"] == "gelbgruen"
    assert row["signal_quelle"] == "vant"


def test_stable_uid_keeps_report_basis_and_pin_after_source_rename():
    qid = db.add_quelle("vant", "Vantage", "http://localhost:8092")
    identity = db.resolve_identity(123, quelle="vant", create=True)
    result = pipeline.ScanResult(id=123, quelle="vant", quellen_uid=identity.quellen_uid)
    fix_signale.setzen(123, quelle="vant")
    before = pipeline.report_basis_for(result, {})
    db.update_quelle(qid, kuerzel="vantage-new", base_url="http://localhost:9999")
    renamed = db.resolve_identity(123, quelle="vantage-new")
    assert renamed.signal_ref == identity.signal_ref
    result.quelle = "vantage-new"
    assert pipeline.report_basis_for(result, {}) == before
    assert fix_signale.fix_keys({}) == {("vantage-new", 123)}


def test_direct_betreuer_call_skips_foreign_identity_before_session(monkeypatch):
    from mqlkiscanner.agenten import betreuer
    def forbidden(*args, **kwargs):
        pytest.fail("Foreign identity reached the direct MQL5 path")
    monkeypatch.setattr(betreuer, "Mql5Session", forbidden)
    monkeypatch.setattr(betreuer, "_signal_pruefen_inner", forbidden)
    result = betreuer.signal_pruefen({"id": 123, "quelle": "vant", "name": "Foreign"}, {})
    assert result["status"] == "skipped"
    with pytest.raises(ValueError, match="ausschließlich für MQL5"):
        betreuer.export_holen(None, {"id": 123, "quelle": "vant"}, {})


def test_unowned_or_ambiguous_legacy_pins_are_never_assigned_by_guessing():
    assert fix_signale.fix_keys({"fix_signal_ids": [123]}) == set()
    logs = []
    pipeline.ScanPipeline({"fix_signal_ids": [123]})._ergaenze_fix_ids([], logs.append)
    assert any("Quellenbesitzer nicht eindeutig" in line for line in logs)
    db.resolve_identity(123, quelle="mql5", create=True)
    db.resolve_identity(123, quelle="vant", create=True)
    assert fix_signale.fix_keys({"fix_signal_ids": [123]}) == set()


def test_catalogue_pin_uses_explicit_same_uid_mirror_after_primary_archived():
    primary = db.add_quelle("primary", "Primary", "http://primary.invalid")
    identity = db.resolve_identity(42, quelle="primary", create=True)
    mirror = db.add_quelle("mirror", "Explicit mirror", "http://mirror.invalid",
                           quellen_uid=identity.quellen_uid)
    db.katalog_upsert_many("primary", [{"signal_id": 42, "name": "Pinned",
        "platform": "Vantage", "version": "vantage", "abonnenten": 0}])
    fix_signale.setzen(42, quelle="primary")
    db.delete_quelle(primary)
    signals = []
    pipeline.ScanPipeline({})._ergaenze_fix_ids(signals, lambda _: None)
    assert len(signals) == 1 and signals[0]["quelle_id"] == mirror
    assert signals[0]["quellen_uid"] == identity.quellen_uid
