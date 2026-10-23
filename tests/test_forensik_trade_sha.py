"""A forensic measurement belongs to its immutable CSV, not latest signal ID."""
import json

import pytest

from mqlkiscanner import db, pipeline
from mqlkiscanner.analysis_version import FORENSICS_VERSION
from mqlkiscanner.alle_signale_ui import tabellen_zeile


def _report():
    return {"version": FORENSICS_VERSION, "vollstaendig": True, "score": 5,
            "peak_exposure": {"shock_pct_max": 1},
            "equity_rekonstruktion": {"equity_dd_pct": 10, "verlaesslich": True}}


def _signal():
    return {"name": "Generic", "platform": "MT5", "quelle": "mql5", "stats": {
        "forensik_ok": True, "forensik_version": FORENSICS_VERSION}}


def _load():
    return pipeline.results_from_db(settings={}, materialize_pdfs=False, studien={})[0]


def test_separate_trade_snapshot_replacement_invalidates_old_forensics(tmp_path):
    db.init_db()
    path = tmp_path / "export.csv"
    path.write_text("old snapshot")
    db.store_scan_result(55, _signal(), str(path), _report())
    old = db.list_catalog()[0]
    assert old['forensik']['trades_sha256'] == old['trades_sha256']
    assert not _load().forensik_stale
    assert _load().max_drawdown_equity_pct == 10
    path.write_text("new trades")
    db.store_trade_file(55, str(path), quelle="mql5")
    new = db.list_catalog()[0]
    assert new['forensik']['trades_sha256'] == old['trades_sha256']
    assert new['trades_sha256'] != old['trades_sha256']
    loaded = _load()
    assert loaded.forensik_stale and not loaded.forensik_vorhanden
    assert loaded.max_drawdown_equity_pct is None
    row = tabellen_zeile(loaded, {}, fix_ids=set())
    assert row['True-DD %'] is None and row['True-DD ≈'] is None
    assert row['True-DD USD'] is None
    assert "Trade-SHA" in row['Messstatus']
    assert "Trade-Export" in loaded.urteil


def test_same_bytes_new_source_path_preserve_current_forensics(tmp_path):
    db.init_db()
    one, two = tmp_path / "one.csv", tmp_path / "two.csv"
    one.write_text("same data")
    two.write_bytes(one.read_bytes())
    db.store_scan_result(55, _signal(), str(one), _report())
    db.store_trade_file(55, str(two), quelle="mql5")
    assert not _load().forensik_stale


def test_atomic_complete_scan_binds_new_report_to_new_snapshot(tmp_path):
    db.init_db()
    path = tmp_path / "export.csv"
    path.write_text("first")
    report = _report()
    db.store_scan_result(55, _signal(), str(path), report)
    path.write_text("second")
    db.store_scan_result(55, _signal(), str(path), report)
    row = db.list_catalog()[0]
    assert row['forensik']['trades_sha256'] == row['trades_sha256']
    assert 'trades_sha256' not in report  # caller's reusable report is unchanged
    assert not _load().forensik_stale


def test_legacy_missing_binding_is_not_assumed_current(tmp_path):
    db.init_db()
    path = tmp_path / "export.csv"
    path.write_text("legacy")
    db.store_scan_result(55, _signal(), str(path), _report())
    with db._connect() as conn:
        # Simulate an existing database written before SHA binding existed.
        conn.execute("UPDATE forensik SET json=? WHERE signal_ref=(SELECT signal_ref FROM signal_identitaeten WHERE externe_id=55)", (json.dumps(_report()),))
    assert _load().forensik_stale


def test_explicit_conflicting_report_sha_is_not_silently_rebound(tmp_path):
    db.init_db()
    path = tmp_path / "export.csv"
    path.write_text("actual")
    report = {**_report(), "trades_sha256": "different"}
    db.store_scan_result(55, _signal(), str(path), report)
    assert _load().forensik_stale


def test_atomic_rollback_restores_both_bound_report_and_trade_snapshot(tmp_path, monkeypatch):
    db.init_db()
    path = tmp_path / "export.csv"
    path.write_text("first")
    db.store_scan_result(55, _signal(), str(path), _report())
    old = db.list_catalog()
    original = db.store_forensik
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("write failed")
    monkeypatch.setattr(db, "store_forensik", fail)
    path.write_text("second")
    with pytest.raises(RuntimeError):
        db.store_scan_result(55, _signal(), str(path), _report())
    assert db.list_catalog() == old
    assert not _load().forensik_stale
