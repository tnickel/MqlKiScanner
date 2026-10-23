"""Explicit Windows-only activation of a previously reviewed copy candidate.

Never called on import or app startup. The caller must first stop all writers
and approve the migration/quarantine report and retained rollback snapshot.
The exclusive SQLite destination lock spans hash verification and backup.
The candidate is held by a native read handle and copied from frozen RAM bytes.
This module neither stops processes nor restores an old DB after a failure.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager, closing
from datetime import datetime, timezone
import ctypes
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys

from . import db
from .agenten import lock, rollen

_WINDOWS = sys.platform == "win32"
_SIDECARS = ("-wal", "-shm", "-journal")


class IdentityActivationError(RuntimeError):
    """Preconditions failed; no automatic retry or legacy restore is allowed."""


class IdentityActivationCommittedError(IdentityActivationError):
    """The backup committed; final verification failed. Never restore blindly."""
    activated = True


def _absolute_plain_path(value, *, directory=False) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise IdentityActivationError("Absoluter, unverkuerzter Pfad erforderlich")
    if path.drive.startswith("\\") or str(path).startswith("\\\\"):
        raise IdentityActivationError("Aktivierung nur auf lokalem Windows-Dateisystem")
    if any(":" in part for part in path.parts[1:]):
        raise IdentityActivationError("Alternative Datenstroeme sind nicht erlaubt")
    # Do not resolve away a symlink/junction before checking every component.
    for component in (path, *path.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if directory and component == path:
                continue
            raise IdentityActivationError("Pfad oder Elternverzeichnis fehlt") from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise IdentityActivationError("Symlink/Junction/Reparse-Punkt ist nicht erlaubt")
    if directory:
        if path.exists() and not path.is_dir():
            raise IdentityActivationError("Lockbasis muss ein Verzeichnis sein")
    elif not path.is_file():
        raise IdentityActivationError("Datenbankpfad muss eine vorhandene regulaere Datei sein")
    if path.name.casefold().endswith(".legacy-backup.sqlite"):
        raise IdentityActivationError("Rollback-Snapshot darf nicht aktiviert oder ersetzt werden")
    return path


def _no_sidecars(*paths):
    for path in paths:
        for suffix in _SIDECARS:
            if os.path.lexists(str(path) + suffix):
                raise IdentityActivationError(f"SQLite-Seitendatei vorhanden ({path.name}{suffix}); Aktivierung gesperrt")


def _expected_hash(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise IdentityActivationError(f"Gueltiger erwarteter SHA-256 fuer {label} erforderlich")
    return value.lower()


@contextmanager
def _exclusive_read_delete(path):
    """Hold native GENERIC_READ / FILE_SHARE_DELETE, denying other R/W handles.

    FILE_SHARE_DELETE allows delete/rename operations, not database reads or
    writes. Activation itself uses SQLite backup, never native rename. Application locks
    coordinate cooperating callers; this is not a sandbox against a hostile
    process independently renaming paths. Metadata/path identity is rechecked.
    """
    if not _WINDOWS:
        raise IdentityActivationError("Aktivierung braucht die gepruefte Windows-Handle-Sperre")
    from ctypes import wintypes
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL
    # OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT: never create/truncate a DB.
    native = create(str(path), 0x80000000, 0x4, None, 3, 0x00200000, None)
    if native == ctypes.c_void_p(-1).value:
        error = ctypes.get_last_error()
        raise IdentityActivationError(f"Datei nicht exklusiv gegen Lese-/Schreibzugriffe sperrbar (WinError {error})")
    try:
        descriptor = msvcrt.open_osfhandle(native, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close(native)
        raise
    # open_osfhandle transfers ownership; closing this stream closes the HANDLE.
    with os.fdopen(descriptor, "rb") as stream:
        yield stream


def _hash_handle(stream, *, retain=False):
    stream.seek(0)
    hasher = hashlib.sha256()
    chunks = [] if retain else None
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        hasher.update(chunk)
        if retain:
            chunks.append(chunk)
    return hasher.hexdigest(), b"".join(chunks) if retain else None


def _same_path_handle(path, stream):
    named, held = path.stat(), os.fstat(stream.fileno())
    if (named.st_dev, named.st_ino) != (held.st_dev, held.st_ino):
        raise IdentityActivationError("Datenbankpfad wurde seit dem Sperrerwerb ersetzt")


def _validate_candidate_image(image):
    if len(image) < 100 or image[:16] != b"SQLite format 3\x00":
        raise IdentityActivationError("Kandidat ist kein SQLite-Datenbankabbild")
    if image[18:20] != b"\x01\x01":
        raise IdentityActivationError("Kandidat muss geschlossen und ohne WAL-Modus vorliegen")
    try:
        # Validate exactly the locked bytes, not a second unguarded path open.
        with closing(sqlite3.connect(":memory:")) as conn:
            conn.deserialize(image)
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA trusted_schema=OFF")
            conn.execute("PRAGMA temp_store=MEMORY")
            if conn.execute("PRAGMA user_version").fetchone()[0] != 2:
                raise IdentityActivationError("Kandidat benoetigt user_version=2")
            if not db._check_schema(conn):
                raise IdentityActivationError("Kandidat hat kein vollstaendiges Identitaetsschema")
            if conn.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise IdentityActivationError("Kandidat besteht integrity_check nicht")
            if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise IdentityActivationError("Kandidat hat verletzte Fremdschluessel")
    except (sqlite3.Error, db.IdentityMigrationRequired) as error:
        raise IdentityActivationError("Kandidat ist ungueltig oder sein Schema nicht aktivierbar") from error


def _backup_progress(status, remaining, total):
    # No retries on BUSY/LOCKED: all locks are already held, and the source is
    # private RAM. This hook is called only before DONE (also for fault tests).
    if status != sqlite3.SQLITE_OK:
        raise IdentityActivationError(f"SQLite-Backup vor Abschluss fehlgeschlagen ({status})")


def _copy_candidate(source, destination, state):
    def progress(status, remaining, total):
        if status == sqlite3.SQLITE_DONE:
            state["committed"] = True
            return  # Never call optional/fallible code after SQLite committed.
        _backup_progress(status, remaining, total)
    source.backup(destination, pages=16, progress=progress, sleep=0)
    if not state["committed"]:
        raise IdentityActivationError("SQLite-Backup lieferte keinen bestaetigten Abschluss")


def _no_foreign_sidecars_after_lock(live, journal_mode):
    # EXCLUSIVE must be set before the first WAL access: our private empty WAL
    # needs no SHM. Existing/nonempty WAL pages are never silently adopted.
    for suffix in ("-shm", "-journal"):
        if os.path.lexists(str(live) + suffix):
            raise IdentityActivationError("Fremde SQLite-Seitendatei nach Sperrerwerb")
    wal = Path(str(live) + "-wal")
    if os.path.lexists(wal) and (journal_mode != "wal" or wal.stat().st_size != 0):
        raise IdentityActivationError("Neue oder fremde WAL-Seiten nach Sperrerwerb")


def activate_candidate(live_path, candidate_path, *, expected_live_sha256,
                       expected_candidate_sha256, lock_basis):
    """Copy reviewed bytes in one SQLite backup transaction, without an unlock gap.

    Existing sidecars (even empty) block. SQLite EXCLUSIVE locking mode is set
    before first live access; BEGIN EXCLUSIVE/COMMIT retains that lock until
    connection close, including throughout SHA verification and backup. The
    native candidate guard remains held. Candidate and rollback are untouched.
    A pre-DONE backup error rolls back through SQLite, never through file copy.
    """
    if not _WINDOWS:
        raise IdentityActivationError("Aktivierung wird nur unter Windows unterstuetzt")
    live = _absolute_plain_path(live_path)
    candidate = _absolute_plain_path(candidate_path)
    basis = _absolute_plain_path(lock_basis, directory=True)
    expected_live = _expected_hash(expected_live_sha256, "Live-DB")
    expected_candidate = _expected_hash(expected_candidate_sha256, "Kandidat")
    if live.samefile(candidate):
        raise IdentityActivationError("Live-DB und Kandidat sind dieselbe Datei")
    _no_sidecars(live, candidate)
    with live.open("rb") as stream:
        header = stream.read(20)
    if len(header) != 20 or header[:16] != b"SQLite format 3\x00":
        raise IdentityActivationError("Live-Datei ist kein bestehendes SQLite-Datenbankabbild")
    with ExitStack() as held:
        held.enter_context(lock.lauf_lock(basis))
        for role in sorted(role.key for role in rollen.ROLLEN):
            held.enter_context(lock.lauf_lock(basis, lock.rolle_lock_name(role)))
        # Repeat path/sidecar checks after acquiring all cooperating writer locks.
        _absolute_plain_path(live)
        _absolute_plain_path(candidate)
        _absolute_plain_path(basis, directory=True)
        _no_sidecars(live, candidate)
        candidate_stream = held.enter_context(_exclusive_read_delete(candidate))
        _same_path_handle(candidate, candidate_stream)
        candidate_sha, image = _hash_handle(candidate_stream, retain=True)
        if candidate_sha != expected_candidate:
            raise IdentityActivationError("Kandidaten-SHA hat sich geaendert")
        _validate_candidate_image(image)
        _no_sidecars(live, candidate)
        source = held.enter_context(closing(sqlite3.connect(":memory:")))
        source.deserialize(image)
        source.execute("PRAGMA query_only=ON")
        live_id = (live.stat().st_dev, live.stat().st_ino)
        destination = held.enter_context(closing(sqlite3.connect(
            live.as_uri() + "?mode=rw&cache=private", uri=True, timeout=0)))
        destination.execute("PRAGMA busy_timeout=0")
        if destination.execute("PRAGMA locking_mode=EXCLUSIVE").fetchone()[0] != "exclusive":
            raise IdentityActivationError("SQLite-Exklusivmodus nicht bestaetigt")
        # No schema/journal query before setting EXCLUSIVE, especially for WAL.
        _no_sidecars(live, candidate)
        try:
            destination.execute("BEGIN EXCLUSIVE")
            destination.execute("COMMIT")
        except sqlite3.Error as error:
            raise IdentityActivationError("Live-DB hat aktive SQLite-Leser/Schreiber") from error
        destination.execute("PRAGMA synchronous=FULL")
        journal_mode = destination.execute("PRAGMA journal_mode").fetchone()[0]
        _no_foreign_sidecars_after_lock(live, journal_mode)
        _no_sidecars(candidate)
        _absolute_plain_path(live)
        _absolute_plain_path(candidate)
        if live_id != (live.stat().st_dev, live.stat().st_ino):
            raise IdentityActivationError("Live-Pfad wurde seit dem Oeffnen ersetzt")
        _same_path_handle(candidate, candidate_stream)
        with live.open("rb") as stream:
            live_sha, _ = _hash_handle(stream)
        if live_sha != expected_live:
            raise IdentityActivationError("Live-SHA hat sich geaendert; neuen Stillstand und Kandidatenstand pruefen")
        if (journal_mode == "wal" and destination.execute("PRAGMA page_size").fetchone()[0]
                != source.execute("PRAGMA page_size").fetchone()[0]):
            raise IdentityActivationError("WAL-Ziel und Kandidat brauchen dieselbe SQLite-Seitengroesse")
        state = {"committed": False}
        try:
            _copy_candidate(source, destination, state)
            if journal_mode == "wal":
                checkpoint = destination.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                if checkpoint[0] != 0 or checkpoint[1] != checkpoint[2]:
                    raise IdentityActivationError("Eigener WAL konnte nicht vollstaendig konsolidiert werden")
            if (destination.execute("PRAGMA user_version").fetchone()[0] != 2
                    or not db._check_schema(destination)
                    or destination.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
                    or destination.execute("PRAGMA foreign_key_check").fetchone() is not None):
                raise IdentityActivationError("Aktivierte Datenbank besteht die Abschlusspruefung nicht")
            with live.open("rb") as stream:
                activated_sha, _ = _hash_handle(stream)
        except BaseException as error:
            if state["committed"]:
                if not isinstance(error, Exception):
                    error.activation_committed = True
                    raise
                raise IdentityActivationCommittedError(
                    "Backup bereits committed; Abschlussfehler, kein automatischer Restore") from error
            raise
        return {"activated": True, "method": "sqlite_backup_exclusive", "live_path": str(live),
                "candidate_path": str(candidate), "candidate_sha256": candidate_sha,
                "previous_live_sha256": live_sha, "activated_sha256": activated_sha,
                "journal_mode": journal_mode, "schema_version": 2,
                "candidate_modified": False, "rollback_snapshot_modified": False,
                "activated_utc": datetime.now(timezone.utc).isoformat()}
