"""Fremdschlüssel werden bei jedem regulären Datenbankzugriff durchgesetzt."""
import sqlite3

import pytest

from mqlkiscanner import db


@pytest.mark.parametrize("table", ["forensik", "trade_files", "analyses"])
def test_missing_parent_is_rejected_without_changing_existing_signal(table, tmp_path):
    db.init_db()
    db.upsert_signal(123, name="Existing signal")
    before = db.get_signal(123)
    source = tmp_path / "input.csv"
    source.write_text("Time;Profit\n", encoding="utf-8")
    operations = {
        "forensik": lambda: db.store_forensik(999, {"score": 1}),
        "trade_files": lambda: db.store_trade_file(999, str(source)),
        "analyses": lambda: db.store_analysis(999, "gesamtbericht", "test", 1, "orphan"),
    }
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        operations[table]()
    assert db.get_signal(123) == before
    with db._connect() as conn:
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_valid_scan_transaction_and_global_portfolio_remain_supported(tmp_path):
    db.init_db()
    source = tmp_path / "input.csv"
    source.write_text("Time;Profit\n", encoding="utf-8")
    stored = db.store_scan_result(123, {"name": "Signal", "platform": "MT5"},
                                  str(source), {"score": 1})
    assert stored
    db.store_analysis(123, "gesamtbericht", "test", 1, "Signal report")
    db.store_analysis(None, "portfolio", "test", 1, "Global report")
    with db._connect() as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM forensik").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM trade_files").fetchone()[0] == 1
    assert db.get_latest_analysis(None, "portfolio")["text"] == "Global report"


def test_enabling_constraints_does_not_delete_unrelated_legacy_rows():
    db.init_db()
    with db._connect() as conn:
        conn.execute("PRAGMA foreign_keys=OFF")  # Explicitly reproduce a legacy database.
        conn.execute("INSERT INTO forensik (signal_id,json) VALUES (999,'{}')")
    db.init_db()
    with db._connect() as conn:
        assert conn.execute("SELECT signal_id FROM forensik").fetchone()[0] == 999
        assert len(conn.execute("PRAGMA foreign_key_check").fetchall()) == 1
