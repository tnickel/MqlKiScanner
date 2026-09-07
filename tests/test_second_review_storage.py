"""Database snapshots remain consistent when mutable CSV caches change."""
import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

import pytest

from mqlkiscanner import db, pipeline


CSV = (
    "Time;Type;Volume;Symbol;Price;S/L;T/P;Time;Price;Commission;Swap;Profit;Comment\n"
    "2023.12.31 10:00:00;Balance;;;;;;;;;;1000;\n"
    "2024.01.01 10:00:00;Buy;0.01;XAUUSD;2000;1990;2010;2024.01.01 11:00:00;2001;0;0;1;\n"
    "2024.01.02 10:00:00;Buy;0.01;XAUUSD;2000;1990;2010;2024.01.02 11:00:00;1999;0;0;-1;\n"
)


def trade_record(signal_id):
    with db._connect() as conn:
        return dict(conn.execute("SELECT * FROM trade_files WHERE signal_id=?",
                                 (signal_id,)).fetchone())


def test_database_owns_snapshot_with_hash_of_exact_bytes(tmp_path):
    inputs = tmp_path / "external_inputs"
    inputs.mkdir()
    source = inputs / "trades.csv"
    original = b"\xef\xbb\xbf" + CSV.encode("utf8")
    source.write_bytes(original)
    db.init_db()
    db.upsert_signal(123)
    stored = Path(db.store_trade_file(123, str(source)))
    row = trade_record(123)
    assert stored.parent == db.DB_PATH.parent / "trade_snapshots"
    assert stored.read_bytes() == original
    assert stored.stem == row["sha256"] == hashlib.sha256(original).hexdigest()
    assert row["path"] == str(stored)
    assert list(inputs.iterdir()) == [source]  # No snapshot beside input files.
    source.write_text("changed cache", encoding="utf8")
    assert stored.read_bytes() == original


def test_cache_refresh_and_sql_rollback_keep_old_snapshot_and_finding(tmp_path, monkeypatch):
    cache = tmp_path / "123_positions.csv"
    cache.write_text(CSV, encoding="utf8")
    monkeypatch.setattr(pipeline.signal_stats, "fetch_signal_stats",
                        Mock(return_value={"dd_equity_pct": 5, "monthly_growth_pct": 10}))
    monkeypatch.setattr(pipeline.exporter, "export_positions", Mock(return_value=(str(cache), False)))
    monkeypatch.setattr(pipeline.time, "sleep", lambda _: None)
    pipe = pipeline.ScanPipeline()
    first = pipe.analyze_candidate(None, {"id": 123}, lambda _: None)
    assert not first.fehler and first.forensik_vorhanden
    before = db.list_catalog()
    old_snapshot = Path(before[0]["trades_path"])
    assert first.trades_path == str(old_snapshot) and old_snapshot != cache
    old_bytes = old_snapshot.read_bytes()
    cache.write_text(CSV.replace(";0;0;1;", ";0;0;500;"), encoding="utf8")
    original_store = db.store_forensik

    def write_then_fail(*args, **kwargs):
        original_store(*args, **kwargs)
        raise sqlite3.OperationalError("simulated commit-path failure")

    monkeypatch.setattr(db, "store_forensik", write_then_fail)
    failed = pipe.analyze_candidate(None, {"id": 123}, lambda _: None)
    assert "Speichern fehlgeschlagen" in failed.fehler and failed.ampel == "⚪"
    assert db.list_catalog() == before
    assert old_snapshot.read_bytes() == old_bytes != cache.read_bytes()
    row = trade_record(123)
    assert row["sha256"] == db.file_sha256(row["path"])
    loaded = pipeline.results_from_db()[0]
    assert loaded.forensik_vorhanden and loaded.score == first.score
    assert loaded.trades_path == first.trades_path


def test_successful_refresh_returns_new_committed_snapshot(tmp_path):
    source = tmp_path / "cache.csv"
    source.write_text(CSV, encoding="utf8")
    db.init_db()
    first = db.store_scan_result(123, {"name": "first"}, str(source), {"score": 1})
    source.write_text(CSV.replace(";0;0;1;", ";0;0;500;"), encoding="utf8")
    second = db.store_scan_result(123, {"name": "second"}, str(source), {"score": 2})
    assert first != second
    assert Path(first).read_text(encoding="utf8") == CSV
    assert Path(second).read_bytes() == source.read_bytes()
    assert trade_record(123)["path"] == second
    assert db.list_catalog()[0]["forensik"]["score"] == 2


def test_identical_concurrent_snapshots_are_idempotent(tmp_path):
    source = tmp_path / "cache.csv"
    source.write_text(CSV, encoding="utf8")
    db.init_db()
    db.upsert_signal(1)
    db.upsert_signal(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        paths = list(pool.map(lambda sid: db.store_trade_file(sid, str(source)), [1, 2]))
    assert paths[0] == paths[1]
    assert Path(paths[0]).read_bytes() == source.read_bytes()
    assert list((db.DB_PATH.parent / "trade_snapshots").iterdir()) == [Path(paths[0])]
    assert trade_record(1)["sha256"] == trade_record(2)["sha256"]


def test_failed_snapshot_publication_leaves_no_partial_reference(tmp_path, monkeypatch):
    source = tmp_path / "cache.csv"
    source.write_text(CSV, encoding="utf8")
    db.init_db()
    monkeypatch.setattr(db.os, "replace", Mock(side_effect=OSError("disk failure")))
    with pytest.raises(OSError, match="disk failure"):
        db.store_scan_result(123, {"name": "new"}, str(source), {"score": 1})
    assert db.list_catalog() == []
    assert not list((db.DB_PATH.parent / "trade_snapshots").iterdir())
