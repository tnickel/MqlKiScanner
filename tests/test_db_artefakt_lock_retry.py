"""Artefakt-Schreiblocks: echte TempDB, keine Downloads oder Produktdaten."""
from __future__ import annotations

import contextlib
import sqlite3
import threading

import pytest

from mqlkiscanner import db


def _error(code):
    error = sqlite3.OperationalError("synthetischer SQLite-Fehler")
    error.sqlite_errorcode = code
    return error


@pytest.fixture
def source():
    return db.add_quelle("lockprobe", "Isolierte Lockprobe", "http://example.invalid")


def _observe_connections(monkeypatch, *, on_execute=None, timeout_ms=None):
    original = db._connect
    statements = []

    class Observed:
        def __init__(self, conn):
            self.conn = conn

        def __getattr__(self, name):
            return getattr(self.conn, name)

        def execute(self, sql, *args):
            statements.append(sql)
            if on_execute:
                return on_execute(self.conn, sql, args)
            return self.conn.execute(sql, *args)

    @contextlib.contextmanager
    def connect():
        with original() as conn:
            if timeout_ms is not None:
                conn.execute(f"PRAGMA busy_timeout={int(timeout_ms)}")
            yield Observed(conn)

    monkeypatch.setattr(db, "_connect", connect)
    return statements


def test_real_wal_lock_beyond_default_timeout_is_retried_without_repeating_writes(source, monkeypatch):
    """Der erste BEGIN scheitert wirklich nach busy_timeout=5000, kein Mock-Lock."""
    acquired = threading.Event()
    busy_seen = threading.Event()
    released = threading.Event()
    errors = []

    def holder():
        try:
            with contextlib.closing(sqlite3.connect(db.DB_PATH)) as conn:
                conn.execute("BEGIN IMMEDIATE")
                acquired.set()
                if not busy_seen.wait(12):
                    raise AssertionError("Der echte erste Lock-Timeout wurde nicht beobachtet")
                conn.rollback()
        except BaseException as exc:
            errors.append(exc)
        finally:
            released.set()

    thread = threading.Thread(target=holder)
    thread.start()
    assert acquired.wait(3)

    def execute(conn, sql, args):
        try:
            return conn.execute(sql, *args)
        except sqlite3.OperationalError as exc:
            if sql == "BEGIN IMMEDIATE" and exc.sqlite_errorcode == sqlite3.SQLITE_BUSY:
                busy_seen.set()
                assert released.wait(3)
            raise

    statements = _observe_connections(monkeypatch, on_execute=execute)
    try:
        db.store_quellen_artefakt(source, 42, "mql5", "trades", "new-sha", "synthetic.csv")
    finally:
        busy_seen.set()
        thread.join(4)
    assert not thread.is_alive()
    assert not errors
    assert busy_seen.is_set()
    assert statements.count("BEGIN IMMEDIATE") == 2
    assert sum("INSERT INTO signal_identitaeten" in sql for sql in statements) == 1
    assert sum("INSERT INTO quellen_artefakte" in sql for sql in statements) == 1
    assert db.get_quellen_artefakt(source, 42, "mql5", "trades")["sha256"] == "new-sha"


def test_persistent_real_lock_has_bounded_attempts_and_keeps_old_artifact(source, monkeypatch):
    db.store_quellen_artefakt(source, 42, "mql5", "trades", "old-sha", "old.csv")
    with contextlib.closing(sqlite3.connect(db.DB_PATH)) as holder:
        holder.execute("BEGIN IMMEDIATE")
        statements = _observe_connections(monkeypatch, timeout_ms=10)
        with pytest.raises(sqlite3.OperationalError) as caught:
            db.store_quellen_artefakt(source, 42, "mql5", "trades", "new-sha", "new.csv")
        assert caught.value.sqlite_errorcode == sqlite3.SQLITE_BUSY
        assert statements.count("BEGIN IMMEDIATE") == 3
        assert not any("INSERT INTO" in sql for sql in statements)
        holder.rollback()
    assert db.get_quellen_artefakt(source, 42, "mql5", "trades")["sha256"] == "old-sha"


@pytest.mark.parametrize("code", [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_BUSY_RECOVERY,
                                 sqlite3.SQLITE_BUSY_SNAPSHOT])
def test_busy_extended_codes_retry_acquisition_only(source, monkeypatch, code):
    attempts = 0

    def execute(conn, sql, args):
        nonlocal attempts
        if sql == "BEGIN IMMEDIATE":
            attempts += 1
            if attempts == 1:
                raise _error(code)
        return conn.execute(sql, *args)

    _observe_connections(monkeypatch, on_execute=execute)
    db.store_quellen_artefakt(source, 42, "mql5", "trades", "sha", "synthetic.csv")
    assert attempts == 2
    assert db.get_quellen_artefakt(source, 42, "mql5", "trades")["sha256"] == "sha"


@pytest.mark.parametrize("code", [sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_LOCKED_SHAREDCACHE,
                                 sqlite3.SQLITE_ERROR, sqlite3.SQLITE_IOERR, None])
def test_nonbusy_acquisition_errors_are_not_retried(source, monkeypatch, code):
    error = _error(code)

    def execute(conn, sql, args):
        if sql == "BEGIN IMMEDIATE":
            raise error
        return conn.execute(sql, *args)

    statements = _observe_connections(monkeypatch, on_execute=execute)
    with pytest.raises(sqlite3.OperationalError) as caught:
        db.store_quellen_artefakt(source, 42, "mql5", "trades", "sha", "synthetic.csv")
    assert caught.value is error
    assert statements.count("BEGIN IMMEDIATE") == 1


def test_busy_after_identity_mutation_is_not_replayed_and_rolls_back(source, monkeypatch):
    error = _error(sqlite3.SQLITE_BUSY)

    def execute(conn, sql, args):
        if "INSERT INTO quellen_artefakte" in sql:
            assert conn.in_transaction
            assert conn.execute("SELECT COUNT(*) FROM signal_identitaeten").fetchone()[0] == 1
            raise error
        return conn.execute(sql, *args)

    statements = _observe_connections(monkeypatch, on_execute=execute)
    with pytest.raises(sqlite3.OperationalError) as caught:
        db.store_quellen_artefakt(source, 42, "mql5", "trades", "sha", "synthetic.csv")
    assert caught.value is error
    assert statements.count("BEGIN IMMEDIATE") == 1
    with sqlite3.connect(db.DB_PATH) as conn:
        assert conn.execute("SELECT COUNT(*) FROM signal_identitaeten").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM quellen_artefakte").fetchone()[0] == 0


def test_busy_with_already_active_transaction_is_not_retried():
    class ActiveConnection:
        in_transaction = True
        calls = 0

        def execute(self, sql):
            self.calls += 1
            raise _error(sqlite3.SQLITE_BUSY)

    conn = ActiveConnection()
    with pytest.raises(sqlite3.OperationalError):
        db._begin_artefakt_write(conn)
    assert conn.calls == 1


def test_error_after_successful_commit_is_never_replayed(source, monkeypatch):
    original = db._connect
    connections = 0
    error = _error(sqlite3.SQLITE_BUSY)

    @contextlib.contextmanager
    def connect():
        nonlocal connections
        connections += 1
        with original() as conn:
            yield conn
        # Fehler nach bereits bestaetigtem Commit darf nie den Body wiederholen.
        raise error

    monkeypatch.setattr(db, "_connect", connect)
    with pytest.raises(sqlite3.OperationalError) as caught:
        db.store_quellen_artefakt(source, 42, "mql5", "trades", "sha", "synthetic.csv")
    assert caught.value is error
    assert connections == 1
    with sqlite3.connect(db.DB_PATH) as conn:
        assert conn.execute("SELECT COUNT(*) FROM signal_identitaeten").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM quellen_artefakte").fetchone()[0] == 1
