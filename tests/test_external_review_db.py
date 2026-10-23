"""Globale Portfolios haben keinen Signal-Fremdschlüssel, auch bei striktem SQLite."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from mqlkiscanner import db, pipeline, identity_migration


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
        assert conn.execute("SELECT signal_ref FROM analyses").fetchone()[0] is None
        assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.get_latest_analysis(None, "portfolio")["text"] == "Portfolio"
    assert db.get_latest_analysis(0, "portfolio")["text"] == "Portfolio"


def test_existing_portfolio_copy_migration_preserves_history_and_latest_lookup(monkeypatch,tmp_path):
    import sqlite3
    legacy,target=tmp_path/'legacy.db',tmp_path/'candidate.db'
    with sqlite3.connect(legacy) as conn:
        conn.execute('CREATE TABLE signals(signal_id INTEGER PRIMARY KEY,name TEXT,quelle TEXT)')
        conn.execute("INSERT INTO signals VALUES(123,'Real signal','mql5')")
        conn.execute('CREATE TABLE analyses(id INTEGER PRIMARY KEY,signal_id INTEGER,kind TEXT,model TEXT,tokens INTEGER,text TEXT,created_at TEXT)')
        conn.execute("INSERT INTO analyses VALUES(1,123,'gesamtbericht','test',3,'Signal-Bericht','2026-09-01')")
        for i,text,timestamp in ((2,'Alt','2026-09-01 12:00:00'),(3,'Neu','2026-09-02 12:00:00')):
            conn.execute("INSERT INTO analyses VALUES(?,0,'portfolio','legacy',5,?,?)",(i,text,timestamp))
        before=[tuple(r) for r in conn.execute('SELECT id,kind,model,tokens,text,created_at FROM analyses ORDER BY id')]
    report=identity_migration.migrate_copy(legacy,target,verify_files=False)
    assert report['tables']['analyses']=={'before':3,'migrated':3,'quarantined':0}
    monkeypatch.setattr(db,'DB_PATH',target)
    enforce_foreign_keys(monkeypatch)
    db.init_db()
    db.init_db()
    with db._connect() as conn:
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert [tuple(r) for r in conn.execute('SELECT id,kind,model,tokens,text,created_at FROM analyses ORDER BY id')]==before
        assert conn.execute("SELECT signal_ref FROM analyses WHERE kind='gesamtbericht'").fetchone()[0]==db.resolve_identity(123).signal_ref
    assert db.get_latest_analysis(None,'portfolio')['text']=='Neu'
    assert db.get_latest_analysis(123,'gesamtbericht')['text']=='Signal-Bericht'
    db.store_analysis(None,'portfolio','current',7,'Aktuell')
    assert db.get_latest_analysis(0,'portfolio')['text']=='Aktuell'


def test_pipeline_portfolio_saves_with_enforced_foreign_keys(monkeypatch):
    monkeypatch.setattr(pipeline, 'refresh_report_verdict', lambda *a: None)
    enforce_foreign_keys(monkeypatch)
    db.init_db()
    db.upsert_signal(123)
    pipe = pipeline.ScanPipeline()
    pipe.llm = SimpleNamespace(has_key=True, usage=SimpleNamespace(total_tokens=10),
                               chat=Mock(return_value="- [mql5:123] Alpha — 100 % — Kern"))
    result = pipeline.ScanResult(id=123, name='Alpha', forensik_vorhanden=True, ampel="🟢")
    summary = pipe.run_portfolio([result], lambda _: None)
    assert summary["storage_error"] == summary["reason"] == ""
    assert db.get_latest_analysis(None, "portfolio")["text"] == summary["text"]
    with db._connect() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
