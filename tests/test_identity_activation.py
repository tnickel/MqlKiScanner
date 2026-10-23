"""Activation is explicit and safe-or-closed; all files are private TempDBs."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import sqlite3

import pytest

from mqlkiscanner import db, identity_activation as activation
from mqlkiscanner.agenten import lock, rollen

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows handle contract")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def pair(tmp_path):
    live, candidate = tmp_path / "live.db", tmp_path / "candidate.db"
    with closing(sqlite3.connect(live)) as conn:
        conn.execute("CREATE TABLE original(value TEXT)")
        conn.execute("INSERT INTO original VALUES('keep original')")
        conn.commit()
    with closing(sqlite3.connect(candidate)) as conn:
        conn.executescript(db._SCHEMA)
        conn.execute("PRAGMA user_version=2")
        conn.commit()
    rollback = candidate.with_name(candidate.name + ".legacy-backup.sqlite")
    rollback.write_bytes(live.read_bytes())
    return live, candidate, rollback


def activate(pair, **overrides):
    live, candidate, _ = pair
    args = {"expected_live_sha256": sha(live), "expected_candidate_sha256": sha(candidate),
            "lock_basis": live.parent}
    args.update(overrides)
    return activation.activate_candidate(live, candidate, **args)


def unchanged(pair, before):
    assert [path.read_bytes() for path in pair] == before
    assert not list(pair[0].parent.glob("*.lock"))


@pytest.mark.parametrize("mode", ["DELETE", "WAL"])
def test_atomic_backup_activates_schema_and_preserves_candidate_and_rollback(pair, mode):
    with closing(sqlite3.connect(pair[0])) as conn:
        conn.execute("PRAGMA journal_mode=" + mode)
    before = [p.read_bytes() for p in pair]
    result = activate(pair)
    assert result["activated"] is True and result["method"] == "sqlite_backup_exclusive"
    assert pair[1].read_bytes() == before[1] and pair[2].read_bytes() == before[2]
    assert sha(pair[0]) == result["activated_sha256"]
    # Backup is a transactional logical copy; page-1 counters/journal-mode bytes
    # need not have the candidate's physical SHA. Verify the actual contents.
    with closing(sqlite3.connect(pair[0])) as live, closing(sqlite3.connect(pair[1])) as source:
        assert list(live.iterdump()) == list(source.iterdump())
        assert live.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db._check_schema(live)
        assert live.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert live.execute("PRAGMA foreign_key_check").fetchall() == []
    assert not list(pair[0].parent.glob("*-wal"))
    assert not list(pair[0].parent.glob("*-shm"))
    assert not list(pair[0].parent.glob("*-journal"))
    assert not list(pair[0].parent.glob("*.lock"))


@pytest.mark.parametrize("mode", ["DELETE", "WAL"])
def test_guards_cover_hash_to_backup_and_concurrent_sqlite_access(pair, monkeypatch, mode):
    with closing(sqlite3.connect(pair[0])) as conn:
        conn.execute("PRAGMA journal_mode=" + mode)
    before = [p.read_bytes() for p in pair]
    phases = []
    real_copy = activation._copy_candidate
    real_progress = activation._backup_progress

    def attempt(sql):
        with closing(sqlite3.connect(pair[0], timeout=0)) as conn:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                conn.execute(sql).fetchall()
        return sql

    def guarded(phase):
        expected = {"agenten_lauff.lock", *(lock.rolle_lock_name(r.key) + ".lock" for r in rollen.ROLLEN)}
        assert {p.name for p in pair[0].parent.glob("*.lock")} == expected
        for file_mode in ("rb", "r+b"):
            with pytest.raises(PermissionError):
                pair[1].open(file_mode)
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert len(list(pool.map(attempt, ("SELECT name FROM sqlite_master", "BEGIN IMMEDIATE")))) == 2
        phases.append(phase)

    def copy(source, destination, state):
        guarded("after_hash_before_backup")
        real_copy(source, destination, state)
        guarded("backup_done_still_locked")
    def progress(status, remaining, total):
        guarded("during_backup")
        real_progress(status, remaining, total)
    monkeypatch.setattr(activation, "_copy_candidate", copy)
    monkeypatch.setattr(activation, "_backup_progress", progress)
    assert activate(pair)["activated"]
    assert set(phases) == {"after_hash_before_backup", "during_backup", "backup_done_still_locked"}
    assert pair[1].read_bytes() == before[1] and pair[2].read_bytes() == before[2]


@pytest.mark.parametrize("target", [0, 1])
def test_existing_sqlite_reader_prevents_activation(pair, target):
    before = [p.read_bytes() for p in pair]
    with closing(sqlite3.connect(pair[target])) as conn:
        conn.execute("BEGIN")
        conn.execute("SELECT name FROM sqlite_master").fetchall()
        with pytest.raises(activation.IdentityActivationError, match="sperrbar|aktive SQLite"):
            activate(pair)
    unchanged(pair, before)


@pytest.mark.parametrize("which", [0, 1])
@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
@pytest.mark.parametrize("contents", [b"", b"new pages"])
def test_any_sidecar_even_empty_blocks_without_deleting_it(pair, which, suffix, contents):
    sidecar = Path(str(pair[which]) + suffix)
    sidecar.write_bytes(contents)
    before = [p.read_bytes() for p in pair]
    with pytest.raises(activation.IdentityActivationError, match="Seitendatei"):
        activate(pair)
    assert sidecar.read_bytes() == contents
    unchanged(pair, before)


def test_sidecar_appearing_after_validation_blocks_before_replace(pair, monkeypatch):
    before = [p.read_bytes() for p in pair]
    real_validate = activation._validate_candidate_image
    sidecar = Path(str(pair[0]) + "-wal")
    def validate(image):
        real_validate(image)
        sidecar.write_bytes(b"late pages")
    monkeypatch.setattr(activation, "_validate_candidate_image", validate)
    with pytest.raises(activation.IdentityActivationError, match="Seitendatei"):
        activate(pair)
    assert sidecar.read_bytes() == b"late pages"
    unchanged(pair, before)


@pytest.mark.parametrize("field", ["expected_live_sha256", "expected_candidate_sha256"])
def test_changed_expected_hash_blocks_without_changing_files(pair, field):
    before = [p.read_bytes() for p in pair]
    with pytest.raises(activation.IdentityActivationError, match="SHA hat sich geaendert"):
        activate(pair, **{field: "0" * 64})
    unchanged(pair, before)


@pytest.mark.parametrize("mode", ["DELETE", "WAL"])
def test_partial_backup_progress_error_rolls_back_original_database(pair, monkeypatch, mode):
    with closing(sqlite3.connect(pair[0])) as conn:
        conn.execute("PRAGMA journal_mode=" + mode)
    before = [p.read_bytes() for p in pair]
    calls = []
    def fail(status, remaining, total):
        assert remaining > 0 and status == sqlite3.SQLITE_OK
        calls.append(remaining)
        raise RuntimeError("controlled partial backup failure")
    monkeypatch.setattr(activation, "_backup_progress", fail)
    with pytest.raises(RuntimeError, match="controlled partial backup failure"):
        activate(pair)
    assert calls
    unchanged(pair, before)
    with closing(sqlite3.connect(pair[0])) as conn:
        assert conn.execute("SELECT value FROM original").fetchall() == [("keep original",)]
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_live_hash_mismatch_never_calls_backup(pair, monkeypatch):
    before = [p.read_bytes() for p in pair]
    def forbidden(*args):
        pytest.fail("A changed live DB must never be overwritten")
    monkeypatch.setattr(activation, "_copy_candidate", forbidden)
    with pytest.raises(activation.IdentityActivationError, match="Live-SHA"):
        activate(pair, expected_live_sha256="0" * 64)
    unchanged(pair, before)


def test_error_after_committed_backup_is_explicit_and_never_restores_legacy(pair, monkeypatch):
    before_candidate, before_backup = pair[1].read_bytes(), pair[2].read_bytes()
    real_check = db._check_schema
    def check(conn):
        if conn.execute("PRAGMA database_list").fetchone()[2]:
            return False  # deterministic post-commit verification failure
        return real_check(conn)
    monkeypatch.setattr(db, "_check_schema", check)
    with pytest.raises(activation.IdentityActivationCommittedError) as error:
        activate(pair)
    assert error.value.activated is True
    with closing(sqlite3.connect(pair[0])) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='original'").fetchone() is None
    assert pair[1].read_bytes() == before_candidate and pair[2].read_bytes() == before_backup


@pytest.mark.parametrize("bad", [None, "", "a" * 63, "g" * 64, True])
def test_invalid_expected_hash_never_starts_activation(pair, bad):
    before = [p.read_bytes() for p in pair]
    with pytest.raises(activation.IdentityActivationError, match="SHA-256"):
        activate(pair, expected_live_sha256=bad)
    unchanged(pair, before)


@pytest.mark.parametrize("version", [0, 1, 3])
def test_wrong_candidate_schema_version_blocks(pair, version):
    with closing(sqlite3.connect(pair[1])) as conn:
        conn.execute(f"PRAGMA user_version={version}")
        conn.commit()
    before = [p.read_bytes() for p in pair]
    with pytest.raises(activation.IdentityActivationError, match="user_version=2"):
        activate(pair)
    unchanged(pair, before)


def test_legacy_child_schema_is_rejected_even_with_user_version_two(pair):
    with closing(sqlite3.connect(pair[1])) as conn:
        conn.execute("CREATE TABLE legacy_child(signal_id INTEGER)")
        conn.commit()
    before = [p.read_bytes() for p in pair]
    with pytest.raises(activation.IdentityActivationError, match="Schema"):
        activate(pair)
    unchanged(pair, before)


def test_missing_required_v2_table_is_rejected(pair):
    with closing(sqlite3.connect(pair[1])) as conn:
        conn.execute("DROP TABLE signal_fixierungen")
        conn.commit()
    before = [p.read_bytes() for p in pair]
    with pytest.raises(activation.IdentityActivationError, match="Schema"):
        activate(pair)
    unchanged(pair, before)


def test_foreign_key_violation_blocks(pair):
    with closing(sqlite3.connect(pair[1])) as conn:
        conn.executescript("CREATE TABLE activation_parent(id INTEGER PRIMARY KEY); "
                           "CREATE TABLE activation_child(pid INTEGER REFERENCES activation_parent(id)); "
                           "INSERT INTO activation_child VALUES(99);")
        conn.commit()
    before = [p.read_bytes() for p in pair]
    with pytest.raises(activation.IdentityActivationError, match="Fremdschluessel"):
        activate(pair)
    unchanged(pair, before)


def test_non_sqlite_candidate_blocks(pair):
    pair[1].write_bytes(b"invalid image")
    before = [p.read_bytes() for p in pair]
    with pytest.raises(activation.IdentityActivationError, match="SQLite-Datenbankabbild"):
        activate(pair)
    unchanged(pair, before)


def test_candidate_wal_header_without_sidecars_still_blocks(pair):
    with closing(sqlite3.connect(pair[1])) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert not Path(str(pair[1]) + "-wal").exists()
    before = [p.read_bytes() for p in pair]
    with pytest.raises(activation.IdentityActivationError, match="WAL-Modus"):
        activate(pair)
    unchanged(pair, before)


@pytest.mark.parametrize("name", ["agenten_lauff", *(lock.rolle_lock_name(r.key) for r in rollen.ROLLEN)])
def test_busy_global_or_role_lock_blocks(pair, name):
    before = [p.read_bytes() for p in pair]
    with lock.lauf_lock(pair[0].parent, name):
        with pytest.raises(lock.LockBesetzt):
            activate(pair)
        assert (pair[0].parent / (name + ".lock")).exists()
    unchanged(pair, before)


def test_relative_path_is_rejected(pair):
    with pytest.raises(activation.IdentityActivationError, match="Absoluter"):
        activation.activate_candidate("live.db", pair[1], expected_live_sha256=sha(pair[0]),
            expected_candidate_sha256=sha(pair[1]), lock_basis=pair[0].parent)


def test_same_file_and_hardlink_alias_are_rejected(pair):
    for alias in (pair[0], pair[0].with_name("hardlink.db")):
        if alias != pair[0]:
            os.link(pair[0], alias)
        with pytest.raises(activation.IdentityActivationError, match="dieselbe Datei"):
            activation.activate_candidate(pair[0], alias, expected_live_sha256=sha(pair[0]),
                expected_candidate_sha256=sha(alias), lock_basis=pair[0].parent)


def test_symlink_is_rejected_without_following_target(pair):
    link = pair[1].with_name("linked.db")
    try:
        link.symlink_to(pair[1])
    except OSError as error:
        pytest.skip(f"No local symlink privilege: {error.winerror}")
    before = [p.read_bytes() for p in pair]
    with pytest.raises(activation.IdentityActivationError, match="Reparse"):
        activation.activate_candidate(pair[0], link, expected_live_sha256=sha(pair[0]),
            expected_candidate_sha256=sha(pair[1]), lock_basis=pair[0].parent)
    unchanged(pair, before)


def test_retained_rollback_is_never_accepted_as_target(pair):
    before = [p.read_bytes() for p in pair]
    with pytest.raises(activation.IdentityActivationError, match="Rollback"):
        activation.activate_candidate(pair[2], pair[1], expected_live_sha256=sha(pair[2]),
            expected_candidate_sha256=sha(pair[1]), lock_basis=pair[0].parent)
    unchanged(pair, before)
