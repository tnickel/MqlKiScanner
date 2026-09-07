"""Globale Portfolios haben keinen Signal-Fremdschlüssel, auch bei striktem SQLite."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mqlkiscanner import db, pipeline


def enforce_foreign_keys(monkeypatch):
    connect = db._connect

    @contextmanager
    def strict_connect():
        with connect() as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            yield conn

    monkeypatch.setattr(db, "_connect", strict_connect)


@pytest.mark.parametrize("signal_id", [None, 0])
def test_global_portfolio_has_no_dangling_signal_reference(monkeypatch, signal_id):
    enforce_foreign_keys(monkeypatch)
    db.init_db()
    db.store_analysis(signal_id, "portfolio", "test", 10, "Portfolio")
    with db._connect() as conn:
        assert conn.execute("SELECT signal_id FROM analyses").fetchone()[0] is None
        assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.get_latest_analysis(None, "portfolio")["text"] == "Portfolio"
    assert db.get_latest_analysis(0, "portfolio")["text"] == "Portfolio"


def test_existing_portfolio_migration_preserves_history_and_latest_lookup(monkeypatch):
    db.init_db()
    db.upsert_signal(123, name="Real signal")
    db.store_analysis(123, "gesamtbericht", "test", 3, "Signal-Bericht")
    with db._connect() as conn:
        conn.execute("PRAGMA foreign_keys=OFF")  # Ausschließlich Legacy-0-Datensätze nachstellen.
        for text, timestamp in (("Alt", "2026-09-01 12:00:00"), ("Neu", "2026-09-02 12:00:00")):
            conn.execute(
                "INSERT INTO analyses (signal_id,kind,model,tokens,text,created_at) "
                "VALUES(0,'portfolio','legacy',5,?,?)", (text, timestamp))
        before = [tuple(r) for r in conn.execute(
            "SELECT id,kind,model,tokens,text,created_at FROM analyses ORDER BY id")]
        assert len(conn.execute("PRAGMA foreign_key_check").fetchall()) == 2
    # Lesen funktioniert auch bevor init_db die Altbestände angepasst hat.
    assert db.get_latest_analysis(None, "portfolio")["text"] == "Neu"
    enforce_foreign_keys(monkeypatch)
    db.init_db()
    db.init_db()  # Wiederholte App-Initialisierung bleibt idempotent.
    with db._connect() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert [tuple(r) for r in conn.execute(
            "SELECT id,kind,model,tokens,text,created_at FROM analyses ORDER BY id")] == before
        assert conn.execute("SELECT signal_id FROM analyses WHERE kind='gesamtbericht'").fetchone()[0] == 123
    assert db.get_latest_analysis(None, "portfolio")["text"] == "Neu"
    assert db.get_latest_analysis(123, "gesamtbericht")["text"] == "Signal-Bericht"
    db.store_analysis(None, "portfolio", "current", 7, "Aktuell")
    assert db.get_latest_analysis(0, "portfolio")["text"] == "Aktuell"


def test_pipeline_portfolio_saves_with_enforced_foreign_keys(monkeypatch):
    enforce_foreign_keys(monkeypatch)
    db.init_db()
    db.upsert_signal(123)
    pipe = pipeline.ScanPipeline()
    pipe.llm = SimpleNamespace(has_key=True, usage=SimpleNamespace(total_tokens=10),
                               chat=Mock(return_value="Portfolio ohne Elternsignal"))
    result = pipeline.ScanResult(id=123, forensik_vorhanden=True)
    summary = pipe.run_portfolio([result], lambda _: None)
    assert summary["storage_error"] == summary["reason"] == ""
    assert db.get_latest_analysis(None, "portfolio")["text"] == summary["text"]
    with db._connect() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
