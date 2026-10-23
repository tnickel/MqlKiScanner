"""Journal triggers are independent from stable source-owned signal references."""
import sqlite3

import pytest

from mqlkiscanner import db
from mqlkiscanner.agenten import journal


def test_equal_external_ids_are_separate_and_reads_return_external_identity():
    a = journal.lauf_starten("betreuer", "gui", 42, signal_quelle="mql5")
    b = journal.lauf_starten("betreuer", "daemon", 42, signal_quelle="vant")
    rows = {row["id"]: row for row in journal.list_laeufe()}
    assert rows[a]["signal_id"] == rows[b]["signal_id"] == 42
    assert rows[a]["signal_quelle"] == "mql5" and rows[a]["quelle"] == "gui"
    assert rows[b]["signal_quelle"] == "vant" and rows[b]["quelle"] == "daemon"
    assert rows[a]["signal_ref"] != rows[b]["signal_ref"]
    active = {row["id"]: row for row in journal.aktive_laeufe("betreuer")}
    for run in (a, b):
        assert active[run]["signal_id"] == rows[run]["signal_id"]
        assert active[run]["signal_ref"] == rows[run]["signal_ref"]
        assert active[run]["signal_quelle"] == rows[run]["signal_quelle"]
    with db._connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(agenten_laeufe)")}
        assert "signal_ref" in columns and "signal_id" not in columns
        assert [dict(row) for row in conn.execute("PRAGMA foreign_key_list(agenten_laeufe)")][0]["table"] == "signal_identitaeten"


def test_run_without_signal_keeps_null_identity_and_trigger():
    run = journal.lauf_starten("dirigent", "gui")
    row = journal.letzter_lauf()
    assert row["id"] == run and row["quelle"] == "gui"
    assert row["signal_id"] is row["signal_ref"] is row["signal_quelle"] is None
    assert journal.aktive_laeufe()[0]["signal_id"] is None


def test_reference_only_allows_catalog_identity_without_signal_header():
    db.init_db()
    identity = db.resolve_identity(77, quelle="vant", create=True)
    run = journal.lauf_starten("betreuer", "daemon", signal_ref=identity.signal_ref)
    row = journal.letzter_lauf()
    assert row["id"] == run and row["signal_id"] == 77 and row["signal_quelle"] == "vant"
    assert db.get_signal(77, quelle="vant") is None


@pytest.mark.parametrize("kwargs", [
    {"signal_id": 42}, {"signal_id": 42, "signal_quelle": ""},
    {"signal_quelle": "vant"}, {"signal_ref": 999999}])
def test_unqualified_or_incomplete_identity_cannot_create_run(kwargs):
    with pytest.raises(db.IdentityError):
        journal.lauf_starten("betreuer", "daemon", **kwargs)
    assert journal.list_laeufe() == []


def test_reference_conflicts_do_not_write_run():
    db.init_db()
    identity = db.resolve_identity(42, quelle="vant", create=True)
    for kwargs in ({"signal_id": 43}, {"signal_id": 42, "signal_quelle": "mql5"}):
        with pytest.raises(db.IdentityError):
            journal.lauf_starten("betreuer", "gui", signal_ref=identity.signal_ref, **kwargs)
    assert journal.list_laeufe() == []


def test_renaming_source_preserves_reference_and_returns_current_source():
    source = db.add_quelle("vant", "Vantage", "http://localhost:8092")
    journal.lauf_starten("betreuer", "gui", 42, signal_quelle="vant")
    before = journal.letzter_lauf()
    db.update_quelle(source, kuerzel="vantage_neu")
    after = journal.letzter_lauf()
    assert after["signal_ref"] == before["signal_ref"]
    assert after["quellen_uid"] == before["quellen_uid"]
    assert after["signal_quelle"] == "vantage_neu" and after["quelle"] == "gui"


def test_failed_run_insert_rolls_back_new_identity_and_source():
    journal.init_journal()
    with db._connect() as conn:
        conn.execute("CREATE TRIGGER reject_run BEFORE INSERT ON agenten_laeufe "
                     "BEGIN SELECT RAISE(ABORT, 'controlled insert failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match="controlled insert failure"):
        journal.lauf_starten("betreuer", "daemon", 42, signal_quelle="new_source")
    with db._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM agenten_laeufe").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM signal_identitaeten").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM quellen_identitaeten WHERE kuerzel='new_source'").fetchone()[0] == 0


def test_legacy_journal_needs_copy_migration_without_inplace_schema_change():
    with db._connect() as conn:
        conn.execute("CREATE TABLE agenten_laeufe(id INTEGER PRIMARY KEY, signal_id INTEGER)")
        conn.execute("INSERT INTO agenten_laeufe(id,signal_id) VALUES(1,42)")
    with pytest.raises(db.IdentityMigrationRequired):
        journal.init_journal()
    with db._connect() as conn:
        assert [row["name"] for row in conn.execute("PRAGMA table_info(agenten_laeufe)")] == ["id", "signal_id"]
        assert conn.execute("SELECT signal_id FROM agenten_laeufe").fetchone()[0] == 42
