"""Fresh schema publication must be atomic across independent connections."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import sqlite3
import threading

import pytest

from mqlkiscanner import db


def test_concurrent_initializers_never_observe_partial_identity_schema(monkeypatch):
    arrived, release = threading.Event(), threading.Event()
    original_schema, connect = db._SCHEMA, db._connect

    def pause():
        arrived.set()
        if not release.wait(10):
            raise RuntimeError("test initializer did not release")
        return 1

    @contextmanager
    def instrumented():
        with connect() as conn:
            conn.create_function("pause_schema_publication", 0, pause)
            yield conn

    marker = "CREATE TABLE IF NOT EXISTS signals ("
    assert marker in original_schema
    monkeypatch.setattr(db, "_SCHEMA", original_schema.replace(
        marker, "SELECT pause_schema_publication();\n" + marker, 1))
    monkeypatch.setattr(db, "_connect", instrumented)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(db.init_db)
        assert arrived.wait(10)
        second = pool.submit(db.init_db)
        try:
            with sqlite3.connect(db.DB_PATH.resolve().as_uri() + "?mode=ro", uri=True) as reader:
                assert reader.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
                assert reader.execute("PRAGMA user_version").fetchone()[0] == 0
        finally:
            release.set()
        first.result(timeout=10)
        second.result(timeout=10)
    monkeypatch.setattr(db, "_SCHEMA", original_schema)
    db.init_db()
    with sqlite3.connect(db.DB_PATH) as reader:
        assert reader.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
        assert reader.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_failed_fresh_initialization_rolls_back_every_table(monkeypatch):
    schema = db._SCHEMA
    monkeypatch.setattr(db, "_SCHEMA", schema + "\nSELECT missing_schema_function();")
    with pytest.raises(sqlite3.OperationalError, match="missing_schema_function"):
        db.init_db()
    with sqlite3.connect(db.DB_PATH) as reader:
        assert reader.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
        assert reader.execute("PRAGMA user_version").fetchone()[0] == 0
    monkeypatch.setattr(db, "_SCHEMA", schema)
    db.init_db()
