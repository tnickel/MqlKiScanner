# -*- coding: utf-8 -*-
"""SQLite-Datenbank: alle Scan-Daten haltbar speichern (Nutzer-Prinzip).

"csv herunterladen, infos alle von mql5 herunterladen und alles in datenbank."

Tabellen:
- signals     : Signal-Kopfdaten + Kennzahlen-JSON (von der MQL5-Seite)
- trade_files : geladene Trade-CSVs je Signal (Pfad, Hash, Zeitpunkt)
- forensik    : Engine-Befund-JSON je Signal
- analyses    : LLM-Teilergebnisse (kind = trade_analyse | risiko_analyse |
                gesamtbericht), aktuelle Texte müssen zur Bewertungsbasis passen
- subscriber_history : Abonnenten-Verlauf je Signal+Version (MqlDownloader)
- downloader_reports : lokal gespiegelte Testreport-PDFs (MqlDownloader)
- ampel_verlauf : Farb-Chronik je Signal und Lauf (append-only; Ampel, Score,
                  Urteil, Kriterien-Matrix als Audit-Snapshot)
- ampel_wechsel : protokollierte Wechsel (Farbe und/oder Kriterien gekippt)
                  mit Begründungen — die Wechselliste der GUI

Pfad: data/mqlkiscanner.db (gitignored). sqlite3 aus der Stdlib — kein
Server noetig.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import tempfile
import uuid

from .signal_identity import (SignalIdentity, IdentityError, AmbiguousSignalIdentity,
                              IdentityMigrationRequired, source_label)
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR

DB_PATH = DATA_DIR / "mqlkiscanner.db"
_ALIAS_CACHE = {}
_SCHEMA_CHECK_CACHE = set()
_SCHEMA_CONTRACT = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS migration_quarantaene (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ursprung_tabelle TEXT NOT NULL, grund TEXT NOT NULL, datensatz_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agenten_budget_altkosten (
    schritt_id INTEGER PRIMARY KEY,
    quarantaene_id INTEGER NOT NULL UNIQUE REFERENCES migration_quarantaene(id),
    ts TEXT, tokens INTEGER, budget_ledger INTEGER DEFAULT 0,
    prompt_vorhanden INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_budget_altkosten_ts ON agenten_budget_altkosten(ts);
CREATE TABLE IF NOT EXISTS quellen_identitaeten (
    quellen_uid TEXT PRIMARY KEY, kuerzel TEXT NOT NULL UNIQUE,
    angelegt_am TEXT, archiviert INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS quellen_alias (
    kuerzel TEXT PRIMARY KEY,
    quellen_uid TEXT NOT NULL REFERENCES quellen_identitaeten(quellen_uid)
);
CREATE TABLE IF NOT EXISTS signal_identitaeten (
    signal_ref INTEGER PRIMARY KEY AUTOINCREMENT,
    quellen_uid TEXT NOT NULL REFERENCES quellen_identitaeten(quellen_uid),
    externe_id INTEGER NOT NULL,
    UNIQUE(quellen_uid, externe_id)
);
CREATE INDEX IF NOT EXISTS idx_identity_external ON signal_identitaeten(externe_id);
CREATE TABLE IF NOT EXISTS signal_fixierungen (
    signal_ref INT NOT NULL PRIMARY KEY REFERENCES signal_identitaeten(signal_ref),
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS signals (
    signal_ref   INT NOT NULL PRIMARY KEY REFERENCES signal_identitaeten(signal_ref),
    name        TEXT,
    platform    TEXT,
    url         TEXT,
    autor       TEXT,
    abo_preis   REAL,
    abonnenten  REAL,
    wochen      REAL,
    stats_json  TEXT,
    updated_at  TEXT,
    quelle TEXT NOT NULL DEFAULT 'mql5'
);
CREATE TABLE IF NOT EXISTS trade_files (
    signal_ref   INT NOT NULL PRIMARY KEY REFERENCES signals(signal_ref),
    path        TEXT,
    sha256      TEXT,
    fetched_at  TEXT
);
CREATE TABLE IF NOT EXISTS forensik (
    signal_ref   INT NOT NULL PRIMARY KEY REFERENCES signals(signal_ref),
    json        TEXT,
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS analyses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_ref   INTEGER REFERENCES signal_identitaeten(signal_ref),
    kind        TEXT,
    model       TEXT,
    tokens      INTEGER,
    text        TEXT,
    created_at  TEXT,
    basis       TEXT
);
CREATE INDEX IF NOT EXISTS idx_analyses_sig_kind ON analyses(signal_ref, kind, id DESC);
CREATE TABLE IF NOT EXISTS subscriber_history (
    signal_ref   INT NOT NULL REFERENCES signal_identitaeten(signal_ref),
    version     TEXT NOT NULL,
    ts          TEXT NOT NULL,
    subscribers INTEGER,
    change      INTEGER,
    fetched_at  TEXT,
    PRIMARY KEY (signal_ref, version, ts)
);
CREATE TABLE IF NOT EXISTS downloader_reports (
    signal_ref     INT NOT NULL REFERENCES signal_identitaeten(signal_ref),
    version       TEXT NOT NULL,
    name          TEXT NOT NULL,
    path          TEXT NOT NULL,
    size_bytes    INTEGER,
    last_modified TEXT,
    fetched_at    TEXT,
    PRIMARY KEY (signal_ref, version, name)
);
CREATE TABLE IF NOT EXISTS tradeserver_sync_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    base_url    TEXT,
    status      TEXT,
    summary_json TEXT
);
CREATE TABLE IF NOT EXISTS llm_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL, attempt INTEGER NOT NULL, created_at TEXT NOT NULL,
    model TEXT, prompt TEXT, content TEXT, response TEXT,
    usage_json TEXT, http_status INTEGER, finish_reason TEXT,
    UNIQUE(call_id,attempt)
);
CREATE TABLE IF NOT EXISTS ampel_verlauf (
    signal_ref  INT NOT NULL REFERENCES signal_identitaeten(signal_ref),
    ts         TEXT NOT NULL,
    quelle     TEXT NOT NULL,
    ampel      TEXT NOT NULL,
    score      REAL,
    urteil     TEXT,
    matrix     TEXT,
    PRIMARY KEY (signal_ref, ts)
);
CREATE TABLE IF NOT EXISTS ampel_wechsel (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_ref   INT NOT NULL REFERENCES signal_identitaeten(signal_ref),
    name        TEXT,
    ts          TEXT NOT NULL,
    quelle      TEXT NOT NULL,
    ampel_alt   TEXT,
    ampel_neu   TEXT NOT NULL,
    farbwechsel INTEGER NOT NULL,
    richtung    TEXT NOT NULL,
    gruende     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ampel_wechsel_ts ON ampel_wechsel(ts DESC);
CREATE TABLE IF NOT EXISTS datenquellen (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    kuerzel          TEXT NOT NULL UNIQUE,
    quellen_uid      TEXT NOT NULL REFERENCES quellen_identitaeten(quellen_uid),
    archiviert       INTEGER NOT NULL DEFAULT 0,
    name             TEXT,
    base_url         TEXT NOT NULL,
    typ              TEXT NOT NULL DEFAULT 'mql5-downloader-v1',
    aktiv            INTEGER NOT NULL DEFAULT 1,
    angelegt_am      TEXT,
    letzte_pruefung  TEXT
);
CREATE TABLE IF NOT EXISTS quellen_artefakte (
    quelle_id   INTEGER NOT NULL REFERENCES datenquellen(id),
    signal_ref   INT NOT NULL REFERENCES signal_identitaeten(signal_ref),
    version     TEXT NOT NULL,
    art         TEXT NOT NULL,
    sha256      TEXT,
    path        TEXT,
    fetched_at  TEXT,
    PRIMARY KEY (quelle_id, signal_ref, version, art)
);
CREATE TABLE IF NOT EXISTS client_updates (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                 TEXT NOT NULL,
    quelle_id          INTEGER,
    kuerzel            TEXT NOT NULL,
    base_url           TEXT,
    job_id             TEXT,
    status             TEXT NOT NULL,
    dauer_s            REAL,
    signale_geliefert  INTEGER,
    tradelisten_neu    INTEGER,
    tradelisten_aktualisiert INTEGER,
    datenstand         TEXT,
    fehler             TEXT,
    hinweise           TEXT
);
CREATE INDEX IF NOT EXISTS idx_client_updates_ts ON client_updates(ts DESC);
-- Vollkatalog der Clients (Nutzer 08.10.2026): ALLE gemeldeten Signale je
-- Quelle — bewusst GETRENNT von `signals`, damit der Workflow-Vorfilter
-- (Mindestalter/-abo) nur beim Scan greift und die Übersicht alles zeigt.
CREATE TABLE IF NOT EXISTS katalog_signale (
    quelle      TEXT NOT NULL,
    signal_ref   INT NOT NULL REFERENCES signal_identitaeten(signal_ref),
    name        TEXT,
    platform    TEXT,
    url         TEXT,
    version     TEXT,
    abonnenten  REAL,
    wochen      REAL,
    risiko      TEXT,
    updated_at  TEXT,
    PRIMARY KEY (signal_ref)
);
CREATE TABLE IF NOT EXISTS katalog_sync (
    quelle      TEXT PRIMARY KEY,
    gelaufen_am TEXT,
    anzahl      INTEGER,
    fehler      TEXT
);
-- Equity-Studien aus dem Batch „Lücken füllen" (Nutzer 08.10.2026): dieselbe
-- equity_rekonstruktion-Struktur wie im Workflow-Forensik-Snapshot, aber für
-- Signale OHNE Scan-Lauf persistent abgelegt. trades_sha macht den Datensatz
-- verfallbar: Neue Trade-Lieferung → Studie ist alt und wird neu gerechnet.
-- Manuelle Nutzer-Markierungen (Nutzer 08.10.2026): gruen/gelb/orange je
-- Signal, Filter über die Alle-Signale-Seite. Kein Eintrag = unmarkiert.
-- Freitext-Kommentar je Signal (Nutzer 09.10.2026): z. B. warum aufgenommen
-- und warum Fix-ID — langer Text, Bearbeitung über den Dialog der Seite.
CREATE TABLE IF NOT EXISTS signal_kommentare (
    signal_ref   INT NOT NULL PRIMARY KEY REFERENCES signal_identitaeten(signal_ref),
    kommentar   TEXT NOT NULL,
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS signal_markierungen (
    signal_ref   INT NOT NULL PRIMARY KEY REFERENCES signal_identitaeten(signal_ref),
    farbe       TEXT NOT NULL,
    updated_at  TEXT
);
-- Beobachtungsliste der Abonnentenstatistik (Nutzer-Wunsch 20.10.2026):
-- ausgewählte Signale dauerhaft beobachten — eigener Tab, unabhängig vom
-- Abonnenten-Filter (ein beobachtetes Signal bleibt bei 0 Abonnenten sichtbar).
CREATE TABLE IF NOT EXISTS beobachtungsliste (
    signal_ref  INT NOT NULL PRIMARY KEY REFERENCES signal_identitaeten(signal_ref),
    angelegt_am TEXT
);
CREATE TABLE IF NOT EXISTS equity_studien (
    signal_ref   INT NOT NULL PRIMARY KEY REFERENCES signal_identitaeten(signal_ref),
    trades_sha  TEXT,
    json        TEXT,
    cagr_jahr_pct REAL,
    ertrag_monat_geom_pct REAL,
    dd_usd      REAL,
    basislos    INTEGER,
    virtuell    INTEGER,
    forensics_version INTEGER NOT NULL DEFAULT 0,
    updated_at  TEXT
);
"""


@contextlib.contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # WAL + busy_timeout: Daemon-Prozess, GUI-Session und Scan-Thread
        # schreiben gleichzeitig — ohne beides sind „database is locked"
        # und daraus folgend halbe Läufe realistisch (Review 29.09.).
        # Reihenfolge wichtig: busy_timeout ZUERST — die journal_mode-
        # Umschaltung braucht die Datei kurz exklusiv und wirft sonst
        # sofort „database is locked". Schlägt sie trotzdem fehl, läuft
        # diese Verbindung im aktuellen Modus weiter (WAL ist persistent;
        # ein anderer Prozess hat es längst gesetzt oder es greift später).
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        conn.execute("PRAGMA foreign_keys=ON")
        with conn:
            yield conn
    finally:
        if conn.total_changes:
            _ALIAS_CACHE.clear()
        conn.close()


SCHEMA_VERSION = 2


def _unique_indexes(conn, table):
    indexes=set()
    for row in conn.execute('PRAGMA index_list("'+table.replace('"','""')+'")'):
        if row[2] and not row[4]: # only full UNIQUE indexes enforce the complete owner domain
            indexes.add(tuple(r[2] for r in conn.execute('PRAGMA index_info("'+row[1].replace('"','""')+'")')))
    return indexes


def _check_schema(conn):
    global _SCHEMA_CONTRACT
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    schema_version = conn.execute("PRAGMA schema_version").fetchone()[0]
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    inode = Path(path).stat().st_ino if path else None
    cache_key = (path,inode,schema_version,version)
    if path and cache_key in _SCHEMA_CHECK_CACHE:
        return True
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for name in names - {"sqlite_sequence"}:
        columns = {row[1] for row in conn.execute('PRAGMA table_info("'+name.replace('"','""')+'")')}
        if "signal_id" in columns and "signal_ref" not in columns:
            raise IdentityMigrationRequired("Identitaetsmigration erforderlich: Copy-Migration benutzen")
    if "signal_identitaeten" in names:
        if _SCHEMA_CONTRACT is None:
            with contextlib.closing(sqlite3.connect(":memory:")) as expected:
                expected.executescript(_SCHEMA)
                _SCHEMA_CONTRACT = {name: (
                    {r[1]:(r[5],r[3]) for r in expected.execute(f'PRAGMA table_info("{name}")')},
                    {(r[2],r[3],r[4]) for r in expected.execute(f'PRAGMA foreign_key_list("{name}")')},
                    _unique_indexes(expected,name))
                    for name, in expected.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if version != SCHEMA_VERSION or not _SCHEMA_CONTRACT.keys() <= names:
            raise IdentityMigrationRequired("Unvollstaendiges oder nicht unterstuetztes Identitaetsschema")
        for name,(columns,foreign_keys,unique_indexes) in _SCHEMA_CONTRACT.items():
            actual_columns = {r[1]:(r[5],r[3]) for r in conn.execute(f'PRAGMA table_info("{name}")')}
            actual_foreign_keys = {(r[2],r[3],r[4]) for r in conn.execute(f'PRAGMA foreign_key_list("{name}")')}
            if (any(actual_columns.get(key)!=value for key,value in columns.items())
                    or not foreign_keys <= actual_foreign_keys
                    or not unique_indexes <= _unique_indexes(conn,name)):
                raise IdentityMigrationRequired(f"Unvollstaendiges Identitaetsschema: {name}")
        if path:
            _SCHEMA_CHECK_CACHE.add(cache_key)
        return True
    if "signals" in names:
        raise IdentityMigrationRequired("Signalbestand ohne Identitaetsregister benoetigt Copy-Migration")
    return False


def init_db() -> None:
    """Initialize a new v2 DB; never silently migrate an existing legacy DB."""
    if DB_PATH.exists() and DB_PATH.stat().st_size:
        with contextlib.closing(sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=ro", uri=True)) as check:
            # Version, tables and constraints must belong to one snapshot
            # while another process may initialize a previously empty DB.
            check.execute("BEGIN")
            if _check_schema(check):
                return
    with _connect() as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "signals" in names and "signal_identitaeten" not in names:
            raise IdentityMigrationRequired(
                "Identitaetsmigration erforderlich: bestehende DB nur per Copy-Migration umstellen")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            raise IdentityMigrationRequired(f"Nicht unterstuetzte DB-Schemaversion {version}")
        # executescript commits a pending transaction before running. Start
        # the transaction inside the script so no reader sees half the
        # tables (or all tables before the user_version marker is committed).
        conn.executescript("BEGIN IMMEDIATE;\n" + _SCHEMA)
        if "quelle" not in {row["name"] for row in conn.execute("PRAGMA table_info(signals)")}:
            conn.execute("ALTER TABLE signals ADD COLUMN quelle TEXT NOT NULL DEFAULT 'mql5'")
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _source(conn, quelle, *, create=False):
    if quelle is not None and (not isinstance(quelle, str) or not quelle.strip()):
        raise IdentityError("Signalquelle muss ein nichtleeres Kuerzel sein")
    label = source_label(quelle)
    row = conn.execute(
        "SELECT q.* FROM quellen_identitaeten q JOIN quellen_alias a "
        "ON a.quellen_uid=q.quellen_uid WHERE a.kuerzel=?", (label,)).fetchone()
    if row is None and create:
        uid = str(uuid.uuid4())
        conn.execute("INSERT INTO quellen_identitaeten(quellen_uid,kuerzel,angelegt_am) VALUES(?,?,?)",
                     (uid, label, _now()))
        conn.execute("INSERT INTO quellen_alias(kuerzel,quellen_uid) VALUES(?,?)", (label, uid))
        row = conn.execute("SELECT * FROM quellen_identitaeten WHERE quellen_uid=?", (uid,)).fetchone()
    return row


def kanonische_quelle(quelle) -> str:
    """Resolve a retained alias without initializing or changing a database."""
    label = source_label(quelle)
    if not DB_PATH.exists():
        return label
    def state(path):
        try:
            value = path.stat()
            return value.st_mtime_ns, value.st_size
        except OSError:
            return None
    key = (str(DB_PATH.resolve()), state(DB_PATH), state(Path(str(DB_PATH) + "-wal")))
    cached = _ALIAS_CACHE.get(key)
    if cached is not None:
        return cached.get(label, label)
    with contextlib.closing(sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='quellen_alias'").fetchone():
            return label
        aliases = {row[0]: row[1] for row in conn.execute("SELECT a.kuerzel,q.kuerzel FROM quellen_alias a "
            "JOIN quellen_identitaeten q ON q.quellen_uid=a.quellen_uid")}
    _ALIAS_CACHE.clear()
    _ALIAS_CACHE[key] = aliases
    return aliases.get(label, label)


def source_identity(quelle) -> dict | None:
    init_db()
    with _connect() as conn:
        row = _source(conn,quelle)
    return dict(row) if row else None


def resolve_identity(signal_id: int | None = None, *, quelle=None, signal_ref=None,
                     create=False, _connection=None) -> SignalIdentity | None:
    """Resolve external identity explicitly; ambiguous ID-only reads fail closed."""
    if _connection is None:
        init_db()
    with (contextlib.nullcontext(_connection) if _connection is not None else _connect()) as conn:
        if create and not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        base = ("SELECT i.signal_ref,i.externe_id,q.quellen_uid,q.kuerzel FROM signal_identitaeten i "
                "JOIN quellen_identitaeten q ON q.quellen_uid=i.quellen_uid ")
        if signal_ref is not None:
            rows = conn.execute(base + "WHERE i.signal_ref=?", (int(signal_ref),)).fetchall()
            if rows and signal_id is not None and rows[0]["externe_id"] != int(signal_id):
                raise IdentityError("Signalreferenz und externe Signal-ID widersprechen sich")
            if rows and quelle is not None:
                source = _source(conn, quelle)
                if source is None or source["quellen_uid"] != rows[0]["quellen_uid"]:
                    raise IdentityError("Signalreferenz und behauptete Quelle widersprechen sich")
        elif quelle is not None:
            if signal_id is None:
                raise IdentityError("Externe Signal-ID fehlt")
            source = _source(conn, quelle, create=create)
            if source is None:
                return None
            if create:
                conn.execute("INSERT INTO signal_identitaeten(quellen_uid,externe_id) VALUES(?,?) "
                             "ON CONFLICT(quellen_uid,externe_id) DO NOTHING",
                             (source["quellen_uid"], int(signal_id)))
            rows = conn.execute(base + "WHERE i.quellen_uid=? AND i.externe_id=?",
                                (source["quellen_uid"], int(signal_id))).fetchall()
        else:
            if signal_id is None:
                raise IdentityError("Signal-ID oder interne Referenz fehlt")
            rows = conn.execute(base + "WHERE i.externe_id=?", (int(signal_id),)).fetchall()
            if len(rows) > 1:
                raise AmbiguousSignalIdentity(f"Signal-ID {signal_id} gehoert mehreren Quellen")
            if not rows and create:
                return resolve_identity(signal_id, quelle="mql5", create=True, _connection=conn)
        if not rows:
            return None
        row = rows[0]
        return SignalIdentity(row["kuerzel"], row["externe_id"], row["signal_ref"], row["quellen_uid"])


def _write_identity(conn, signal_id, *, quelle=None, signal_ref=None):
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    if quelle is not None and (not isinstance(quelle, str) or not quelle.strip()):
        raise IdentityError("ID-Kollision abgewehrt: Signalquelle muss ein nichtleeres Kuerzel sein")
    if quelle is None and signal_ref is None:
        existing = conn.execute("SELECT 1 FROM signal_identitaeten WHERE externe_id=?",
                                (int(signal_id),)).fetchone()
        if existing:
            raise IdentityError("ID-Kollision abgewehrt: vorhandene Identitaet benoetigt eine explizite Quelle oder signal_ref")
    identity = resolve_identity(signal_id, quelle=quelle, signal_ref=signal_ref,
                                create=True, _connection=conn)
    if identity is None:
        raise IdentityError("Interne Signalreferenz existiert nicht")
    return identity


def _identity_fields(identity):
    return {"signal_id": identity.signal_id, "signal_ref": identity.signal_ref,
            "quelle": identity.quelle, "quellen_uid": identity.quellen_uid}


def _bulk_identities(conn, values, *, quelle=None):
    """Resolve a whole mixed qualified batch with a fixed number of queries."""
    from .signal_identity import identity_key
    requests = []
    for value in values:
        if isinstance(value, tuple):
            source, external = value
        elif isinstance(value, SignalIdentity):
            source, external = value.quelle, value.signal_id
        else:
            source, external = quelle, int(value)
        requests.append((source, int(external)))
    if not requests:
        return {}
    aliases = {row[0]: row[1] for row in conn.execute("SELECT kuerzel,quellen_uid FROM quellen_alias")}
    ids = sorted({external for _, external in requests})
    rows = []
    for start in range(0, len(ids), 500):
        chunk = ids[start:start+500]
        rows.extend(conn.execute("SELECT i.signal_ref,i.externe_id,q.quellen_uid,q.kuerzel "
            "FROM signal_identitaeten i JOIN quellen_identitaeten q ON q.quellen_uid=i.quellen_uid "
            "WHERE i.externe_id IN ("+','.join('?' for _ in chunk)+")",chunk).fetchall())
    result = {}
    for source, external in requests:
        matches = [row for row in rows if row["externe_id"] == external and
                   (source is None or row["quellen_uid"] == aliases.get(source_label(source)))]
        if len(matches) > 1:
            raise AmbiguousSignalIdentity(f"Signal-ID {external} gehoert mehreren Quellen")
        if matches:
            row = matches[0]
            identity = SignalIdentity(row["kuerzel"],external,row["signal_ref"],row["quellen_uid"])
            key = (identity.quelle,external) if source is not None else external
            result[key] = identity
    return result


def _read_ref(signal_id, *, quelle=None, signal_ref=None):
    return resolve_identity(signal_id, quelle=quelle, signal_ref=signal_ref)


def _connection_identity(conn, quelle_id, signal_id, *, create=False):
    source = conn.execute("SELECT q.kuerzel FROM datenquellen d JOIN quellen_identitaeten q "
                          "ON q.quellen_uid=d.quellen_uid WHERE d.id=?", (int(quelle_id),)).fetchone()
    if source is None:
        raise IdentityError("Unbekannte Datenquellen-Verbindung")
    return resolve_identity(signal_id, quelle=source[0], create=create, _connection=conn)


def _list_user_state(table, field, *, quelle=None, identitaeten=False):
    init_db()
    with _connect() as conn:
        rows = conn.execute(f"SELECT s.{field},i.externe_id,q.kuerzel FROM {table} s "
            "JOIN signal_identitaeten i ON i.signal_ref=s.signal_ref JOIN quellen_identitaeten q "
            "ON q.quellen_uid=i.quellen_uid").fetchall()
        ambiguous = {row[0] for row in conn.execute("SELECT externe_id FROM signal_identitaeten "
                                                  "GROUP BY externe_id HAVING COUNT(*)>1")}
    source = kanonische_quelle(quelle) if quelle is not None else None
    return {((row["kuerzel"],row["externe_id"]) if identitaeten else row["externe_id"]):row[field]
            for row in rows if (source is None or row["kuerzel"]==source)
            and (identitaeten or source is not None or row["externe_id"] not in ambiguous)}


def set_signal_fix(signal_id: int, fix=True, *, quelle=None, signal_ref=None):
    init_db()
    with _connect() as conn:
        identity = _write_identity(conn, signal_id, quelle=quelle, signal_ref=signal_ref)
        if fix:
            conn.execute("INSERT INTO signal_fixierungen(signal_ref,updated_at) VALUES(?,?) "
                         "ON CONFLICT(signal_ref) DO UPDATE SET updated_at=excluded.updated_at",
                         (identity.signal_ref, _now()))
        else:
            conn.execute("DELETE FROM signal_fixierungen WHERE signal_ref=?", (identity.signal_ref,))


def list_signal_fixierungen(*, identitaeten=False):
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT i.externe_id,q.kuerzel FROM signal_fixierungen f "
            "JOIN signal_identitaeten i ON i.signal_ref=f.signal_ref "
            "JOIN quellen_identitaeten q ON q.quellen_uid=i.quellen_uid").fetchall()
    if identitaeten:
        return {(row["kuerzel"], row["externe_id"]) for row in rows}
    return {row["externe_id"] for row in rows if len(signal_quellen(row["externe_id"])) == 1}


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def upsert_signal(signal_id: int, name: str = "", platform: str = "", url: str = "",
                  autor: str = "", abo_preis=None, abonnenten=None, wochen=None,
                  stats: dict | None = None, quelle: str | None = None, *,
                  signal_ref=None, _connection=None) -> None:
    if _connection is None:
        init_db()
    with (contextlib.nullcontext(_connection) if _connection is not None else _connect()) as conn:
        identity = _write_identity(conn, signal_id, quelle=quelle, signal_ref=signal_ref)
        _guard_platform(conn, identity.signal_ref, platform)
        conn.execute("""INSERT INTO signals (signal_ref,name,platform,url,autor,abo_preis,
            abonnenten,wochen,stats_json,updated_at,quelle) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(signal_ref) DO UPDATE SET name=excluded.name,platform=excluded.platform,
            url=excluded.url,autor=excluded.autor,abo_preis=excluded.abo_preis,
            abonnenten=excluded.abonnenten,wochen=excluded.wochen,stats_json=excluded.stats_json,
            updated_at=excluded.updated_at,quelle=excluded.quelle""",
            (identity.signal_ref,name,platform,url,autor,abo_preis,abonnenten,wochen,
             json.dumps(stats or {},ensure_ascii=False),_now(),identity.quelle))


def _guard_platform(conn, signal_ref, platform, version=None):
    """An owner/external-ID pair cannot silently change trading platform."""
    from .downloader_client import platform_version
    def normalized(value):
        return platform_version(str(value or "")) or str(value or "").strip().lower()
    claims = {normalized(value) for value in (platform,version) if value}
    for table in ("signals", "katalog_signale"):
        row = conn.execute(f"SELECT platform FROM {table} WHERE signal_ref=?",(signal_ref,)).fetchone()
        if row and row[0]:
            claims.add(normalized(row[0]))
    row = conn.execute("SELECT version FROM katalog_signale WHERE signal_ref=?",(signal_ref,)).fetchone()
    if row and row[0]:
        claims.add(normalized(row[0]))
    if len(claims) > 1:
        raise IdentityError("Plattformwiderspruch innerhalb derselben Signalidentitaet")



def _snapshot_trade_file(path: str, *, expected_sha256: str | None = None) -> tuple[str, str]:
    """Keep the exact hashed bytes independently of the mutable download cache.

    A rolled-back SQL transaction may leave an unused snapshot, but cannot
    overwrite a previous version. Files belong to this database, never to the
    directory containing an input fixture or externally supplied CSV.
    """
    directory = DB_PATH.parent / "trade_snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    suffix = ".json" if Path(path).suffix.lower() == ".json" else ".csv"
    temporary = None
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as source:
            with tempfile.NamedTemporaryFile(mode="wb", dir=directory,
                                             suffix=".tmp", delete=False) as target:
                temporary = Path(target.name)
                for chunk in iter(lambda: source.read(65536), b""):
                    target.write(chunk)
                    digest.update(chunk)
                target.flush()
                os.fsync(target.fileno())
        sha256 = digest.hexdigest()
        if expected_sha256 is not None and sha256 != expected_sha256:
            raise ValueError("Trade-SHA stimmt nicht mit der geprüften Analyseeingabe überein")
        snapshot = directory / f"{sha256}{suffix}"
        # Concurrent identical content has the same destination and bytes.
        os.replace(temporary, snapshot)
        return str(snapshot), sha256
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def snapshot_trade_file(path: str) -> tuple[str, str]:
    """Freeze input bytes before analysis, independently of a SQL transaction."""
    return _snapshot_trade_file(path)


def verify_trade_file(path: str, expected_sha256: str) -> None:
    """Reject missing or changed evidence instead of trusting its metadata."""
    if not path or not expected_sha256:
        raise ValueError("Trade-Snapshot oder sein geprüfter SHA fehlt")
    if file_sha256(path) != expected_sha256:
        raise ValueError("Trade-Snapshot verändert: SHA stimmt nicht überein")


def store_trade_file(signal_id: int, path: str, *, expected_sha256=None,
                     quelle=None, signal_ref=None, _connection=None) -> str:
    if _connection is None:
        init_db()
    with (contextlib.nullcontext(_connection) if _connection is not None else _connect()) as conn:
        identity = _write_identity(conn, signal_id, quelle=quelle, signal_ref=signal_ref)
        snapshot, sha256 = _snapshot_trade_file(path, expected_sha256=expected_sha256)
        conn.execute("""INSERT INTO trade_files(signal_ref,path,sha256,fetched_at) VALUES(?,?,?,?)
            ON CONFLICT(signal_ref) DO UPDATE SET path=excluded.path,sha256=excluded.sha256,
            fetched_at=excluded.fetched_at""", (identity.signal_ref,snapshot,sha256,_now()))
    return snapshot



def store_forensik(signal_id: int, report: dict, *, quelle=None, signal_ref=None,
                   _connection=None) -> None:
    if _connection is None:
        init_db()
    with (contextlib.nullcontext(_connection) if _connection is not None else _connect()) as conn:
        identity = _write_identity(conn, signal_id, quelle=quelle, signal_ref=signal_ref)
        report = dict(report)
        trade = conn.execute("SELECT sha256 FROM trade_files WHERE signal_ref=?",
                             (identity.signal_ref,)).fetchone()
        report.setdefault("trades_sha256",trade["sha256"] if trade else "")
        conn.execute("""INSERT INTO forensik(signal_ref,json,updated_at) VALUES(?,?,?)
            ON CONFLICT(signal_ref) DO UPDATE SET json=excluded.json,updated_at=excluded.updated_at""",
            (identity.signal_ref,json.dumps(report,ensure_ascii=False),_now()))



def store_scan_result(signal_id: int, signal: dict, trades_path: str = "",
                      forensik: dict | None = None, *, expected_trades_sha256=None,
                      quelle=None, signal_ref=None) -> str:
    init_db()
    snapshot = ""
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        payload = dict(signal)
        incoming_source = payload.pop("quelle",quelle)
        incoming_ref = payload.pop("signal_ref",signal_ref)
        claimed_uid = payload.pop("quellen_uid",None)
        identity = _write_identity(conn,signal_id,quelle=incoming_source,signal_ref=incoming_ref)
        if claimed_uid is not None and claimed_uid != identity.quellen_uid:
            raise IdentityError("Behauptete Quellen-UID passt nicht zur Signalidentitaet")
        upsert_signal(signal_id,**payload,quelle=identity.quelle,signal_ref=identity.signal_ref,
                      _connection=conn)
        if expected_trades_sha256 is not None:
            if not trades_path:
                raise ValueError("Gepruefter Trade-SHA ohne Trade-Snapshot")
            if forensik is not None and forensik.get("trades_sha256") != expected_trades_sha256:
                raise ValueError("Befund-SHA stimmt nicht mit der geprueften Analyseeingabe ueberein")
        if trades_path:
            snapshot = store_trade_file(signal_id,trades_path,expected_sha256=expected_trades_sha256,
                                        signal_ref=identity.signal_ref,_connection=conn)
        if forensik is not None:
            store_forensik(signal_id,forensik,signal_ref=identity.signal_ref,_connection=conn)
    return snapshot



def store_analysis(signal_id: int | None, kind: str, model: str, tokens: int, text: str,
                   *, basis=None, quelle=None, signal_ref=None) -> str:
    init_db()
    if kind in {"portfolio", "portfolio_ungueltig"} and signal_id == 0:
        signal_id = None
    with _connect() as conn:
        ref = None
        if signal_id is not None or signal_ref is not None:
            ref = _write_identity(conn,signal_id,quelle=quelle,signal_ref=signal_ref).signal_ref
        elif kind not in {"portfolio", "portfolio_ungueltig"}:
            raise IdentityError("Signalbezogene Analyse ohne Signalidentitaet")
        stamp = _now()
        conn.execute("INSERT INTO analyses(signal_ref,kind,model,tokens,text,created_at,basis) VALUES(?,?,?,?,?,?,?)",
                     (ref,kind,model,tokens,text,stamp,basis))
    return stamp



def store_llm_attempt(call_id: str, attempt: int, *, model: str, prompt: str,
                      content: str, response: str, usage: dict, http_status=None,
                      finish_reason=None) -> None:
    """Full response audit, separate from billing and successful analysis history.

    Never stores HTTP headers/API keys. Agent budget rows remain the sole
    source of agent cost accounting; this table does not charge tokens.
    """
    init_db()
    with _connect() as conn:
        conn.execute("INSERT INTO llm_attempts "
            "(call_id,attempt,created_at,model,prompt,content,response,usage_json,http_status,finish_reason) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (call_id,attempt,_now(),model,prompt,content,response,
             json.dumps(usage,ensure_ascii=False),http_status,finish_reason))


def list_llm_attempts(call_id: str) -> list[dict]:
    init_db()
    with _connect() as conn:
        rows=conn.execute("SELECT * FROM llm_attempts WHERE call_id=? ORDER BY attempt",(call_id,)).fetchall()
    result=[]
    for row in rows:
        item=dict(row);item["usage"]=json.loads(item.pop("usage_json") or "{}");result.append(item)
    return result


def get_latest_analysis(signal_id: int | None, kind: str, *, basis=None,
                        quelle=None, signal_ref=None) -> dict | None:
    init_db()
    if kind in {"portfolio", "portfolio_ungueltig"} and signal_id == 0:
        signal_id = None
    identity = None
    if signal_id is not None or signal_ref is not None:
        identity = _read_ref(signal_id,quelle=quelle,signal_ref=signal_ref)
        if identity is None:
            return None
    elif kind not in {"portfolio", "portfolio_ungueltig"}:
        return None
    with _connect() as conn:
        row = conn.execute("SELECT * FROM analyses WHERE signal_ref IS ? AND kind=? "
            "AND (? IS NULL OR basis=?) ORDER BY id DESC LIMIT 1",
            (identity.signal_ref if identity else None,kind,basis,basis)).fetchone()
    return {**dict(row),**(_identity_fields(identity) if identity else {"signal_id":None})} if row else None



def list_catalog() -> list[dict]:
    """Alle Signale mit Forensik und neuesten KI-Texten (eine Zeile je Signal)."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT i.externe_id AS signal_id, s.signal_ref, q.quellen_uid, q.kuerzel AS quelle, s.name, s.platform, s.url, s.autor, s.abo_preis,
                   s.abonnenten, s.wochen,
                   s.stats_json, s.updated_at AS signal_updated,
                   t.path AS trades_path, t.sha256 AS trades_sha256, t.fetched_at AS trades_fetched,
                   f.json AS forensik_json, f.updated_at AS forensik_updated,
                   (SELECT text FROM analyses a WHERE a.signal_ref=s.signal_ref
                      AND a.kind='trade_analyse' ORDER BY a.id DESC LIMIT 1) AS trade_analyse,
                   (SELECT created_at FROM analyses a WHERE a.signal_ref=s.signal_ref
                      AND a.kind='trade_analyse' ORDER BY a.id DESC LIMIT 1) AS trade_at,
                   (SELECT model FROM analyses a WHERE a.signal_ref=s.signal_ref
                      AND a.kind='trade_analyse' ORDER BY a.id DESC LIMIT 1) AS trade_model,
                   (SELECT text FROM analyses a WHERE a.signal_ref=s.signal_ref
                      AND a.kind='risiko_analyse' ORDER BY a.id DESC LIMIT 1) AS risiko_analyse,
                   (SELECT created_at FROM analyses a WHERE a.signal_ref=s.signal_ref
                      AND a.kind='risiko_analyse' ORDER BY a.id DESC LIMIT 1) AS risiko_at,
                   (SELECT model FROM analyses a WHERE a.signal_ref=s.signal_ref
                      AND a.kind='risiko_analyse' ORDER BY a.id DESC LIMIT 1) AS risiko_model,
                   (SELECT text FROM analyses a WHERE a.signal_ref=s.signal_ref
                      AND a.kind='gesamtbericht' ORDER BY a.id DESC LIMIT 1) AS gesamtbericht,
                   (SELECT created_at FROM analyses a WHERE a.signal_ref=s.signal_ref
                      AND a.kind='gesamtbericht' ORDER BY a.id DESC LIMIT 1) AS gesamt_at,
                   (SELECT model FROM analyses a WHERE a.signal_ref=s.signal_ref
                      AND a.kind='gesamtbericht' ORDER BY a.id DESC LIMIT 1) AS gesamt_model,
                   (SELECT text FROM analyses a WHERE a.signal_ref=s.signal_ref
                      AND a.kind='tiefenanalyse' ORDER BY a.id DESC LIMIT 1) AS tiefenanalyse,
                   (SELECT created_at FROM analyses a WHERE a.signal_ref=s.signal_ref
                      AND a.kind='tiefenanalyse' ORDER BY a.id DESC LIMIT 1) AS tiefe_at,
                   (SELECT model FROM analyses a WHERE a.signal_ref=s.signal_ref
                      AND a.kind='tiefenanalyse' ORDER BY a.id DESC LIMIT 1) AS tiefe_model
            FROM signals s
             JOIN signal_identitaeten i ON i.signal_ref=s.signal_ref
             JOIN quellen_identitaeten q ON q.quellen_uid=i.quellen_uid
            LEFT JOIN trade_files t ON t.signal_ref = s.signal_ref
            LEFT JOIN forensik f ON f.signal_ref = s.signal_ref
            ORDER BY COALESCE(f.updated_at, s.updated_at) DESC, i.externe_id DESC
            """
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["stats"] = json.loads(item.pop("stats_json") or "{}")
        item["forensik"] = json.loads(item.pop("forensik_json") or "null")
        out.append(item)
    return out


def get_signal(signal_id: int | None = None, *, quelle=None, signal_ref=None) -> dict | None:
    identity = _read_ref(signal_id,quelle=quelle,signal_ref=signal_ref)
    if identity is None:
        return None
    with _connect() as conn:
        row = conn.execute("SELECT * FROM signals WHERE signal_ref=?",(identity.signal_ref,)).fetchone()
    return {**dict(row),**_identity_fields(identity)} if row else None



def _signal_quellen(conn, signal_id: int) -> set[str]:
    return {row[0] for row in conn.execute("SELECT q.kuerzel FROM signal_identitaeten i JOIN "
        "quellen_identitaeten q ON q.quellen_uid=i.quellen_uid WHERE i.externe_id=?",(int(signal_id),))}



def signal_quellen(signal_id: int) -> set[str]:
    """Known source claims for one numeric ID; no updates or schema changes."""
    if not DB_PATH.exists():
        return set()
    with contextlib.closing(sqlite3.connect(DB_PATH.resolve().as_uri()+"?mode=ro",uri=True)) as conn:
        if not _check_schema(conn):
            return set()
        return _signal_quellen(conn, signal_id)





def known_signal_ids(*, identitaeten=False):
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT i.externe_id,q.kuerzel FROM signals s JOIN signal_identitaeten i "
            "ON i.signal_ref=s.signal_ref JOIN quellen_identitaeten q ON q.quellen_uid=i.quellen_uid").fetchall()
        if identitaeten:
            return {(row["kuerzel"],row["externe_id"]) for row in rows}
        return {row["externe_id"] for row in rows if len(_signal_quellen(conn,row["externe_id"]))==1}



def store_history_points(signal_id: int, version: str, points: list[dict],
                         *, fetched_at: str | None = None, quelle=None, signal_ref=None) -> int:
    init_db()
    """Abonnenten-Punkte je Signal+Version ersetzen (Vollabgleich).

    Ein Punkt ohne Zeitstempel wäre ohne Bezug — er wird übersprungen.
    Rückgabe: Anzahl übernommener Punkte.
    """
    ts = fetched_at or _now()
    kept = 0
    with _connect() as conn:
        identity = _write_identity(conn, signal_id, quelle=quelle, signal_ref=signal_ref)
        signal_ref = identity.signal_ref
        for point in points:
            stamp = str(point.get("timestamp") or "").strip()
            if not stamp:
                continue
            conn.execute(
                """INSERT INTO subscriber_history
                   (signal_ref, version, ts, subscribers, change, fetched_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(signal_ref, version, ts) DO UPDATE SET
                     subscribers=excluded.subscribers, change=excluded.change,
                     fetched_at=excluded.fetched_at""",
                (signal_ref, version, stamp,
                 point.get("subscribers"), point.get("change"), ts))
            kept += 1
    return kept



def get_history(signal_id: int, version: str | None = None, *, quelle=None, signal_ref=None) -> list[dict]:
    """Abonnenten-Verlauf aufsteigend; ohne Version alle Versionen gemischt."""
    identity = _read_ref(signal_id, quelle=quelle, signal_ref=signal_ref)
    if identity is None:
        return []
    signal_ref = identity.signal_ref
    with _connect() as conn:
        rows = conn.execute(
            "SELECT signal_ref, version, ts, subscribers, change, fetched_at "
            "FROM subscriber_history WHERE signal_ref=? "
            "AND (? IS NULL OR version=?) ORDER BY version, ts",
            (signal_ref, version, version)).fetchall()
    return [{**dict(row), **_identity_fields(identity)} for row in rows]


def subscriber_history_alle() -> list[dict]:
    """ALLE Abonnenten-Messpunkte mit Identität (Abonnentenstatistik, doc/24).

    Eine Abfrage für die ganze Übersicht statt N Einzelabrufe; gruppiert
    wird beim Aufrufer. `subscribers` kann NULL sein (Punkt ohne Zahl).
    """
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT h.signal_ref, h.version, h.ts, h.subscribers, h.change, "
            "i.externe_id AS signal_id, q.kuerzel AS quelle, q.quellen_uid "
            "FROM subscriber_history h "
            "JOIN signal_identitaeten i ON i.signal_ref=h.signal_ref "
            "JOIN quellen_identitaeten q ON q.quellen_uid=i.quellen_uid "
            "ORDER BY h.signal_ref, h.version, h.ts").fetchall()
    return [dict(row) for row in rows]


def analyses_zaehler_alle(kinds=("trade_analyse", "risiko_analyse",
                                 "gesamtbericht", "tiefenanalyse")) -> dict[int, dict]:
    """Berichte-Zählung je Identität — UNABHÄNGIG von der signals-Zeile.

    Katalog-Signale ohne Scan haben keine signals-Zeile; über list_catalog
    wären ihre Analysen (z. B. Batch-Tiefenanalysen, 20.10.) unsichtbar.
    Rückgabe {signal_ref: {kind: True}}.
    """
    init_db()
    platzhalter = ",".join("?" * len(kinds))
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT signal_ref, kind FROM analyses WHERE kind IN ({platzhalter})",
            tuple(kinds)).fetchall()
    out: dict[int, dict] = {}
    for row in rows:
        out.setdefault(int(row["signal_ref"]), {})[row["kind"]] = True
    return out


def letzte_ampeln_je_signal() -> dict[int, dict]:
    """Neueste Ampel je Signal aus der Chronik (nur Anzeige, nie Neubewertung).

    ampel_verlauf ist append-only; der neueste Eintrag je signal_ref ist das
    letzte Engine-Ergebnis. Rückgabe {signal_ref: {"ampel", "ts", "urteil"}}.
    """
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT a.signal_ref, a.ts, a.ampel, a.urteil FROM ampel_verlauf a "
            "JOIN (SELECT signal_ref, MAX(ts) AS max_ts FROM ampel_verlauf "
            "      GROUP BY signal_ref) n "
            "ON a.signal_ref=n.signal_ref AND a.ts=n.max_ts").fetchall()
    return {int(r["signal_ref"]): {"ampel": r["ampel"], "ts": r["ts"],
                                   "urteil": r["urteil"]} for r in rows}



def store_downloader_report(signal_id: int, version: str, name: str, path: str,
                            size_bytes: int | None = None,
                            last_modified: str | None = None, *, quelle=None, signal_ref=None) -> None:
    init_db()
    with _connect() as conn:
        identity = _write_identity(conn, signal_id, quelle=quelle, signal_ref=signal_ref)
        signal_ref = identity.signal_ref
        conn.execute(
            """INSERT INTO downloader_reports
               (signal_ref, version, name, path, size_bytes, last_modified, fetched_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(signal_ref, version, name) DO UPDATE SET
                 path=excluded.path, size_bytes=excluded.size_bytes,
                 last_modified=excluded.last_modified, fetched_at=excluded.fetched_at""",
            (signal_ref, version, name, path, size_bytes, last_modified, _now()))



def list_downloader_reports(signal_id: int, *, quelle=None, signal_ref=None) -> list[dict]:
    """Lokal gespiegelte Downloader-PDFs je Signal (Version, Name sortiert)."""
    identity = _read_ref(signal_id, quelle=quelle, signal_ref=signal_ref)
    if identity is None:
        return []
    signal_ref = identity.signal_ref
    with _connect() as conn:
        rows = conn.execute(
            "SELECT version, name, path, size_bytes, last_modified, fetched_at "
            "FROM downloader_reports WHERE signal_ref=? ORDER BY version, name",
            (signal_ref,)).fetchall()
    return [{**dict(row), **_identity_fields(identity)} for row in rows]



def downloader_report_counts(signal_ids, *, quelle=None, identitaeten=False) -> dict:
    init_db()
    with _connect() as conn:
        identities = _bulk_identities(conn,signal_ids,quelle=quelle)
        counts = {row[0]:row[1] for row in conn.execute("SELECT signal_ref,COUNT(*) FROM downloader_reports GROUP BY signal_ref")}
    return {key:counts.get(identity.signal_ref,0) for key,identity in identities.items()}


def downloader_reports_liste_alle() -> dict[int, list[dict]]:
    """ALLE gespiegelten Testreport-PDFs mit Identität (Doku-Spalte, doc/24).

    Ein Abruf für die Übersicht: {signal_ref: [{version, name, path}, …]}.
    """
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT d.signal_ref, d.version, d.name, d.path "
            "FROM downloader_reports d ORDER BY d.signal_ref, d.version, d.name").fetchall()
    out: dict[int, list[dict]] = {}
    for row in rows:
        out.setdefault(int(row["signal_ref"]), []).append(
            {"version": row["version"], "name": row["name"], "path": row["path"]})
    return out



def store_tradeserver_sync_run(*, base_url: str, status: str,
                               summary: dict | None = None) -> int:
    """Lauf-Historie des Tradeserver-Syncs (append-only, nur Protokoll).

    Der Sync schreibt ausschließlich hierhin — Ampeln, Urteile, Scores
    und die Fachtabellen bleiben unberührt.
    """
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO tradeserver_sync_runs "
            "(started_at, finished_at, base_url, status, summary_json) "
            "VALUES (?,?,?,?,?)",
            (_now(), _now(), str(base_url or ""), str(status or ""),
             json.dumps(summary or {}, ensure_ascii=False)))
        return int(cursor.lastrowid or 0)


def list_tradeserver_sync_runs(limit: int = 10) -> list[dict]:
    """Die letzten Sync-Läufe (neueste zuerst), für Anzeige/Erneut-Sync."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, started_at, finished_at, base_url, status, summary_json "
            "FROM tradeserver_sync_runs ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),)).fetchall()
    runs = []
    for row in rows:
        eintrag = dict(row)
        try:
            eintrag["summary"] = json.loads(eintrag.pop("summary_json") or "{}")
        except json.JSONDecodeError:
            eintrag["summary"] = {}
        runs.append(eintrag)
    return runs


def start_tradeserver_sync_run(base_url: str) -> int:
    """Persist the real start before preparing or transmitting a snapshot."""
    init_db()
    with _connect() as conn:
        cursor = conn.execute("INSERT INTO tradeserver_sync_runs "
            "(started_at,base_url,status,summary_json) VALUES (?,?,?,?)",
            (_now(), str(base_url), "running", "{}"))
        return int(cursor.lastrowid)


def finish_tradeserver_sync_run(run_id: int, status: str, summary: dict) -> None:
    with _connect() as conn:
        conn.execute("UPDATE tradeserver_sync_runs SET finished_at=?,status=?,summary_json=? WHERE id=?",
            (_now(), status, json.dumps(summary, ensure_ascii=False), run_id))


def store_ampel_verlauf(signal_id: int, ts: str, quelle: str, ampel: str,
                        score: float | None, urteil: str, matrix: dict | None, *, signal_quelle=None, signal_ref=None) -> None:
    init_db()
    """Farb-Chronik: ein append-only Eintrag je erfolgreich geprüftem Lauf.

    Kein UPDATE, kein DELETE — die Chronik darf nachträglich nicht verändert
    werden. Zwei Einträge desselben Signals in derselben Sekunde können nicht
    vorkommen (ein Signal wird je Lauf höchstens einmal geprüft); sollte es
    doch kollidieren, gewinnt der zuerst geschriebene Eintrag (OR IGNORE).
    """
    with _connect() as conn:
        identity = _write_identity(conn, signal_id, quelle=signal_quelle, signal_ref=signal_ref)
        signal_ref = identity.signal_ref
        conn.execute(
            "INSERT OR IGNORE INTO ampel_verlauf "
            "(signal_ref, ts, quelle, ampel, score, urteil, matrix) VALUES (?,?,?,?,?,?,?)",
            (signal_ref, ts, quelle, ampel, score, urteil,
             json.dumps(matrix or {}, ensure_ascii=False)))



def get_last_ampel_verlauf(signal_id: int, *, quelle=None, signal_ref=None) -> dict | None:
    """Der neueste Chronik-Eintrag eines Signals (Vergleichsbasis für Wechsel)."""
    identity = _read_ref(signal_id, quelle=quelle, signal_ref=signal_ref)
    if identity is None:
        return None
    signal_ref = identity.signal_ref
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT signal_ref, ts, quelle, ampel, score, urteil, matrix "
            "FROM ampel_verlauf WHERE signal_ref=? ORDER BY ts DESC LIMIT 1",
            (signal_ref,)).fetchone()
    if row is None:
        return None
    eintrag = {**dict(row), **_identity_fields(identity), "quelle": row["quelle"], "datenquelle": identity.quelle, "signal_quelle": identity.quelle}
    try:
        eintrag["matrix"] = json.loads(eintrag.get("matrix") or "{}")
    except json.JSONDecodeError:
        eintrag["matrix"] = {}
    return eintrag



def list_ampel_verlauf(signal_id: int, limit: int = 50, *, quelle=None, signal_ref=None) -> list[dict]:
    """Farb-Chronik eines Signals, neueste zuerst (Anzeige in der GUI)."""
    identity = _read_ref(signal_id, quelle=quelle, signal_ref=signal_ref)
    if identity is None:
        return []
    signal_ref = identity.signal_ref
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT signal_ref, ts, quelle, ampel, score, urteil FROM ampel_verlauf "
            "WHERE signal_ref=? ORDER BY ts DESC LIMIT ?",
            (signal_ref, max(1, int(limit)))).fetchall()
    return [{**dict(row), **_identity_fields(identity), "quelle": row["quelle"], "datenquelle": identity.quelle, "signal_quelle": identity.quelle} for row in rows]



def store_ampel_wechsel(signal_id: int, ts: str, quelle: str, ampel_alt: str | None,
                        ampel_neu: str, farbwechsel: bool, richtung: str,
                        gruende: list[dict], name: str = "", *, signal_quelle=None, signal_ref=None) -> int:
    init_db()
    """Ein protokollierter Wechsel (Farbe und/oder gekippte Kriterien).

    Der Signalname wird zum Zeitpunkt des Wechsels mitgespeichert — das
    Protokoll bleibt lesbar, selbst wenn das Signal später aus dem Katalog
    fällt oder umbenannt wird.
    """
    with _connect() as conn:
        identity = _write_identity(conn, signal_id, quelle=signal_quelle, signal_ref=signal_ref)
        signal_ref = identity.signal_ref
        cursor = conn.execute(
            "INSERT INTO ampel_wechsel "
            "(signal_ref, name, ts, quelle, ampel_alt, ampel_neu, farbwechsel, richtung, gruende) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (signal_ref, name, ts, quelle, ampel_alt, ampel_neu, int(farbwechsel),
             richtung, json.dumps(gruende, ensure_ascii=False)))
        return int(cursor.lastrowid or 0)



def list_ampel_wechsel(limit: int = 200, nur_farbwechsel=False, signal_id=None,
                      *, quelle=None, signal_ref=None) -> list[dict]:
    init_db()
    filters=[];args=[]
    if signal_id is not None or signal_ref is not None:
        identity=_read_ref(signal_id,quelle=quelle,signal_ref=signal_ref)
        if identity is None:
            return []
        filters.append("w.signal_ref=?");args.append(identity.signal_ref)
    elif quelle is not None:
        filters.append("q.kuerzel=?");args.append(kanonische_quelle(quelle))
    if nur_farbwechsel:
        filters.append("w.farbwechsel=1")
    sql="SELECT w.*,i.externe_id AS signal_id,q.quellen_uid,q.kuerzel AS signal_quelle,q.kuerzel AS datenquelle "
    sql+="FROM ampel_wechsel w JOIN signal_identitaeten i ON i.signal_ref=w.signal_ref JOIN quellen_identitaeten q ON q.quellen_uid=i.quellen_uid"
    if filters:
        sql+=' WHERE '+' AND '.join(filters)
    sql+=' ORDER BY w.id DESC LIMIT ?';args.append(max(1,int(limit)))
    with _connect() as conn:
        rows=conn.execute(sql,args).fetchall()
    out=[]
    for row in rows:
        item=dict(row);item["farbwechsel"]=bool(item["farbwechsel"])
        item["gruende"]=json.loads(item["gruende"] or '[]');out.append(item)
    return out



def count_ampel_wechsel() -> int:
    """Gesamtzahl protokollierter Wechsel (Button-Badge der GUI)."""
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM ampel_wechsel").fetchone()
    return int(row["n"]) if row else 0


# ------------------------------------------------- Datenquellen (doc/20)

def _row_zu_quelle(row) -> dict:
    eintrag = dict(row)
    eintrag["aktiv"] = bool(eintrag.get("aktiv"))
    try:
        eintrag["letzte_pruefung"] = json.loads(eintrag.pop("letzte_pruefung") or "null")
    except (json.JSONDecodeError, TypeError):
        eintrag["letzte_pruefung"] = None
    return eintrag


def list_quellen(nur_aktiv: bool = False) -> list[dict]:
    """Konfigurierte Datenquellen, oldest first (stabile Reihenfolge fürs Abholen)."""
    init_db()
    where = "WHERE archiviert=0 AND aktiv=1" if nur_aktiv else "WHERE archiviert=0"
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT id, kuerzel, quellen_uid, name, base_url, typ, aktiv, angelegt_am, "
            f"letzte_pruefung FROM datenquellen {where} ORDER BY id").fetchall()
    return [_row_zu_quelle(row) for row in rows]


def get_quelle(quelle_id: int) -> dict | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, kuerzel, quellen_uid, name, base_url, typ, aktiv, angelegt_am, "
            "letzte_pruefung FROM datenquellen WHERE id=? AND archiviert=0",
            (int(quelle_id),)).fetchone()
    return _row_zu_quelle(row) if row else None


def add_quelle(kuerzel: str, name: str, base_url: str, typ="mql5-downloader-v1", aktiv=True,
               *, quellen_uid=None) -> int:
    init_db()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not isinstance(kuerzel, str) or not kuerzel.strip():
            raise IdentityError("Signalquelle muss ein nichtleeres Kuerzel sein")
        label = kuerzel.strip()
        source = _source(conn,label)
        if quellen_uid is not None:
            owner = conn.execute("SELECT * FROM quellen_identitaeten WHERE quellen_uid=?",
                                 (str(quellen_uid),)).fetchone()
            if owner is None or (source is not None and source["quellen_uid"] != owner["quellen_uid"]):
                raise IdentityError("Quellen-UID passt nicht zum reservierten Alias")
            conn.execute("INSERT INTO quellen_alias(kuerzel,quellen_uid) VALUES(?,?) "
                         "ON CONFLICT(kuerzel) DO NOTHING",(label,owner["quellen_uid"]))
            source = owner
        elif source is not None and not conn.execute(
                "SELECT 1 FROM datenquellen WHERE quellen_uid=? AND archiviert=0",
                (source["quellen_uid"],)).fetchone():
            raise IdentityError("Reservierter Quellenalias erfordert ausdrueckliche quellen_uid")
        if source is None:
            source = _source(conn,label,create=True)
        archived = conn.execute("SELECT id FROM datenquellen WHERE kuerzel=? AND archiviert=1",
                                (label,)).fetchone()
        if archived is not None:
            conn.execute("UPDATE datenquellen SET archiviert=0,aktiv=?,name=?,base_url=?,typ=? WHERE id=?",
                         (int(bool(aktiv)),name,str(base_url).rstrip('/'),typ,archived[0]))
            return int(archived[0])
        cursor = conn.execute("INSERT INTO datenquellen(kuerzel,quellen_uid,name,base_url,typ,aktiv,angelegt_am) "
            "VALUES(?,?,?,?,?,?,?)",(label,source["quellen_uid"],name,str(base_url).rstrip('/'),typ,int(bool(aktiv)),_now()))
        return int(cursor.lastrowid)



def update_quelle(quelle_id: int, *, kuerzel=None, name=None, base_url=None, aktiv=None) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute("SELECT * FROM datenquellen WHERE id=? AND archiviert=0",(int(quelle_id),)).fetchone()
        if old is None:
            raise IdentityError("Datenquellen-Verbindung existiert nicht")
        sets,args = [],[]
        if kuerzel is not None:
            label = str(kuerzel).strip()
            if not label:
                raise IdentityError("Quellenkuerzel fehlt")
            alias = _source(conn,label)
            if alias is not None and alias["quellen_uid"] != old["quellen_uid"]:
                raise IdentityError("Quellenalias gehoert bereits einem anderen Namensraum")
            conn.execute("INSERT INTO quellen_alias(kuerzel,quellen_uid) VALUES(?,?) "
                         "ON CONFLICT(kuerzel) DO NOTHING",(label,old["quellen_uid"]))
            conn.execute("UPDATE quellen_identitaeten SET kuerzel=? WHERE quellen_uid=?",(label,old["quellen_uid"]))
            sets.append("kuerzel=?");args.append(label)
        for field,value in [("name",name),("base_url",base_url),("aktiv",aktiv)]:
            if value is not None:
                sets.append(field+"=?")
                args.append(int(bool(value)) if field=="aktiv" else str(value).strip())
        if sets:
            conn.execute("UPDATE datenquellen SET "+','.join(sets)+" WHERE id=?",(*args,int(quelle_id)))



def delete_quelle(quelle_id: int) -> None:
    """Archive the transport connection; never erase or reassign an owner UID."""
    with _connect() as conn:
        conn.execute("UPDATE datenquellen SET aktiv=0,archiviert=1 WHERE id=?",(int(quelle_id),))



def store_quell_pruefung(quelle_id: int, pruefung: dict) -> None:
    """Letzten Connection-Test je Quelle festhalten (Anzeige ohne neuen Aufruf)."""
    with _connect() as conn:
        conn.execute("UPDATE datenquellen SET letzte_pruefung=? WHERE id=?",
                     (json.dumps(pruefung, ensure_ascii=False, default=str), int(quelle_id)))


# Katalog-DELETE in Blöcken: SQLite begrenzt gebundene Parameter pro Statement
# (historisch 999, heute 32 766) — sourceübergreifend korrekt ist NUR das
# löschen konkret berechneter Stale-IDs per IN (NOT IN in Blöcken würde die
# IDs der anderen Blöcke fälschlich mitlöschen).
_KATALOG_STALE_CHUNK = 500


def katalog_upsert_many(quelle_kuerzel: str, items: list[dict]) -> tuple[int,int]:
    init_db()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        source = _source(conn,quelle_kuerzel,create=True)
        old = {row[0] for row in conn.execute("SELECT k.signal_ref FROM katalog_signale k "
            "JOIN signal_identitaeten i ON i.signal_ref=k.signal_ref WHERE i.quellen_uid=?",(source["quellen_uid"],))}
        kept = set()
        for item in items:
            external = item.get("signal_id",item.get("id"))
            identity = resolve_identity(external,quelle=source["kuerzel"],create=True,_connection=conn)
            _guard_platform(conn,identity.signal_ref,item.get("platform"),item.get("version"))
            kept.add(identity.signal_ref)
            conn.execute("""INSERT INTO katalog_signale(quelle,signal_ref,name,platform,url,version,
                abonnenten,wochen,risiko,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(signal_ref) DO UPDATE SET quelle=excluded.quelle,name=excluded.name,
                platform=excluded.platform,url=excluded.url,version=excluded.version,
                abonnenten=excluded.abonnenten,wochen=excluded.wochen,risiko=excluded.risiko,
                updated_at=excluded.updated_at""",(identity.quelle,identity.signal_ref,item.get("name"),
                item.get("platform"),item.get("url"),item.get("version"),item.get("abonnenten"),
                item.get("wochen"),item.get("risiko"),_now()))
        stale = old-kept
        for ref in stale:
            conn.execute("DELETE FROM katalog_signale WHERE signal_ref=?",(ref,))
    return len(kept),len(stale)



def katalog_list() -> list[dict]:
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT k.*,i.externe_id AS signal_id,q.quellen_uid,q.kuerzel AS aktuelle_quelle "
            "FROM katalog_signale k JOIN signal_identitaeten i ON i.signal_ref=k.signal_ref "
            "JOIN quellen_identitaeten q ON q.quellen_uid=i.quellen_uid ORDER BY k.abonnenten DESC").fetchall()
    out=[]
    for row in rows:
        item=dict(row);item["quelle"]=item.pop("aktuelle_quelle");out.append(item)
    return out



def katalog_sync_vermerken(quelle_kuerzel: str, anzahl: int,
                           fehler: str | None = None) -> None:
    """Sync-Ergebnis je Quelle stempeln (auch Fehler — ein fehlgeschlagener
    Auto-Sync bei Seitenstart soll nicht bei jedem Rerun wiederholt werden)."""
    init_db()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO katalog_sync (quelle, gelaufen_am, anzahl, fehler)
               VALUES (?,?,?,?)
               ON CONFLICT(quelle) DO UPDATE SET
                 gelaufen_am=excluded.gelaufen_am, anzahl=excluded.anzahl,
                 fehler=excluded.fehler""",
            (kanonische_quelle(quelle_kuerzel), _now(), int(anzahl), fehler))


def katalog_sync_status() -> dict[str, dict]:
    """Letzter Katalog-Sync je Quelle: {"kuerzel": {"gelaufen_am", "anzahl", "fehler"}}."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT quelle, gelaufen_am, anzahl, fehler FROM katalog_sync ORDER BY gelaufen_am").fetchall()
    return {kanonische_quelle(row["quelle"]): {"gelaufen_am": row["gelaufen_am"],
                            "anzahl": row["anzahl"], "fehler": row["fehler"]}
            for row in rows}


def store_equity_studie(signal_id: int, trades_sha: str, report: dict, *,
                        cagr_jahr_pct: float | None = None,
                        ertrag_monat_geom_pct: float | None = None,
                        dd_usd: float | None = None,
                        basislos: bool = False,
                        virtuell: bool = False, quelle=None, signal_ref=None) -> None:
    init_db()
    """Batch-Equity-Studie persistieren (Nutzer 08.10.2026).

    `report` ist das volle equity_rekonstruktion-dict (dieselbe Struktur wie
    im Forensik-Snapshot — results_from_db kann es 1:1 mappen). cagr/geom
    stammen aus der Vorstufen-Statistik zum Studienzeitpunkt; daraus rechnet
    das Laden TrueRetDD. dd_usd ist basis-unabhängig und existiert auch bei
    kapitalbasielosen Signalen (basislos=True → kein % speichern).
    """
    from .analysis_version import FORENSICS_VERSION
    init_db()
    with _connect() as conn:
        identity = _write_identity(conn, signal_id, quelle=quelle, signal_ref=signal_ref)
        signal_ref = identity.signal_ref
        conn.execute(
            """INSERT INTO equity_studien (signal_ref, trades_sha, json,
               cagr_jahr_pct, ertrag_monat_geom_pct, dd_usd, basislos, virtuell,
               updated_at, forensics_version)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(signal_ref) DO UPDATE SET
                 trades_sha=excluded.trades_sha, json=excluded.json,
                 cagr_jahr_pct=excluded.cagr_jahr_pct,
                 ertrag_monat_geom_pct=excluded.ertrag_monat_geom_pct,
                 dd_usd=excluded.dd_usd, basislos=excluded.basislos,
                 virtuell=excluded.virtuell, updated_at=excluded.updated_at,
                 forensics_version=excluded.forensics_version""",
            (int(signal_ref), trades_sha,
             json.dumps(report, ensure_ascii=False, sort_keys=True, default=str),
             cagr_jahr_pct, ertrag_monat_geom_pct, dd_usd,
             1 if basislos else 0, 1 if virtuell else 0, _now(), FORENSICS_VERSION))



def get_equity_studie(signal_id: int | None = None, *, quelle=None, signal_ref=None) -> dict | None:
    from .analysis_version import FORENSICS_VERSION
    identity = _read_ref(signal_id,quelle=quelle,signal_ref=signal_ref)
    if identity is None:
        return None
    with _connect() as conn:
        row = conn.execute("SELECT * FROM equity_studien WHERE signal_ref=? AND forensics_version=?",
                           (identity.signal_ref,FORENSICS_VERSION)).fetchone()
    if row is None:
        return None
    item = {**dict(row),**_identity_fields(identity)}
    try:
        item["report"] = json.loads(item.pop("json") or "{}")
    except ValueError:
        return None
    return item



def list_equity_studien(*, identitaeten=False, quelle=None) -> dict:
    from .analysis_version import FORENSICS_VERSION
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT e.*,i.externe_id AS signal_id,q.quellen_uid,q.kuerzel AS quelle "
            "FROM equity_studien e JOIN signal_identitaeten i ON i.signal_ref=e.signal_ref "
            "JOIN quellen_identitaeten q ON q.quellen_uid=i.quellen_uid "
            "WHERE e.forensics_version=?",(FORENSICS_VERSION,)).fetchall()
        ambiguous = {row[0] for row in conn.execute("SELECT externe_id FROM signal_identitaeten "
            "GROUP BY externe_id HAVING COUNT(*)>1")}
    result = {}
    source = kanonische_quelle(quelle) if quelle is not None else None
    for row in rows:
        item = dict(row)
        if source is not None and item["quelle"] != source:
            continue
        if not identitaeten and source is None and item["signal_id"] in ambiguous:
            continue
        try:
            item["report"] = json.loads(item.pop("json") or "{}")
        except ValueError:
            continue
        key = (item["quelle"],item["signal_id"]) if identitaeten else item["signal_id"]
        result[key] = item
    return result



def store_quellen_artefakt(quelle_id: int, signal_id: int, version: str, art: str,
                          sha256: str, path: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        identity = _connection_identity(conn,quelle_id,signal_id,create=True)
        conn.execute("""INSERT INTO quellen_artefakte(quelle_id,signal_ref,version,art,sha256,path,fetched_at)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(quelle_id,signal_ref,version,art) DO UPDATE SET
            sha256=excluded.sha256,path=excluded.path,fetched_at=excluded.fetched_at""",
            (int(quelle_id),identity.signal_ref,version,art,sha256,path,_now()))



def list_quellen_artefakte() -> dict:
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT a.*,i.externe_id AS signal_id,q.quellen_uid,q.kuerzel AS quelle "
            "FROM quellen_artefakte a JOIN signal_identitaeten i ON i.signal_ref=a.signal_ref "
            "JOIN quellen_identitaeten q ON q.quellen_uid=i.quellen_uid").fetchall()
    return {(row["quelle_id"],row["signal_id"],row["version"],row["art"]):dict(row) for row in rows}



def get_quellen_artefakt(quelle_id: int, signal_id: int, version: str, art: str) -> dict | None:
    init_db()
    with _connect() as conn:
        identity = _connection_identity(conn,quelle_id,signal_id)
        if identity is None:
            return None
        row = conn.execute("SELECT * FROM quellen_artefakte WHERE quelle_id=? AND signal_ref=? AND version=? AND art=?",
                           (int(quelle_id),identity.signal_ref,version,art)).fetchone()
    return {**dict(row),**_identity_fields(identity)} if row else None



# ── Stufe 0 „Clients aktualisieren" (doc/23 §6.4) ─────────────────────

def store_client_update(*, quelle_id: int, kuerzel: str, base_url: str = "",
                        job_id: str = "", status: str, dauer_s: float = 0.0,
                        signale_geliefert=None, tradelisten_neu=None,
                        tradelisten_aktualisiert=None, datenstand: str = "",
                        fehler: str = "", hinweise=None) -> None:
    """Ergebnis EINER Quelle eines Stufe-0-Laufs (append-only, wie
    ampel_verlauf) — die Chronik im Stufe-0-Dialog „Letzte Läufe"."""
    init_db()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO client_updates
               (ts, quelle_id, kuerzel, base_url, job_id, status, dauer_s,
                signale_geliefert, tradelisten_neu, tradelisten_aktualisiert,
                datenstand, fehler, hinweise)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (_now(), int(quelle_id), str(kuerzel), str(base_url or ""),
             str(job_id or ""), str(status), float(dauer_s or 0.0),
             (int(signale_geliefert) if signale_geliefert is not None else None),
             (int(tradelisten_neu) if tradelisten_neu is not None else None),
             (int(tradelisten_aktualisiert)
              if tradelisten_aktualisiert is not None else None),
             str(datenstand or ""), str(fehler or ""),
             json.dumps(list(hinweise or []), ensure_ascii=False)))


def list_client_updates(limit: int = 100) -> list[dict]:
    """Chronik neueste zuerst."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM client_updates ORDER BY id DESC LIMIT ?",
            (int(limit),)).fetchall()
    out = []
    for row in rows:
        eintrag = dict(row)
        try:
            eintrag["hinweise"] = json.loads(eintrag.get("hinweise") or "[]")
        except ValueError:
            eintrag["hinweise"] = []
        out.append(eintrag)
    return out


def letzte_client_updates_je_quelle() -> dict[str, dict]:
    """Je Kürzel der NEUESTE Eintrag (Admin/Datenquellen-Spalte „letztes Update")."""
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT c.* FROM client_updates c JOIN "
            "(SELECT kuerzel,MAX(id) AS latest FROM client_updates GROUP BY kuerzel) n "
            "ON c.id=n.latest ORDER BY c.id DESC").fetchall()
    eintraege = [dict(row) for row in rows]
    for row in eintraege:
        try:
            row["hinweise"] = json.loads(row.get("hinweise") or "[]")
        except ValueError:
            row["hinweise"] = []
    neueste: dict[str, dict] = {}
    for eintrag in eintraege:  # absteigend — erster Treffer je Kürzel gewinnt
        neueste.setdefault(str(eintrag.get("kuerzel")), eintrag)
    return neueste


def setze_markierung(signal_id: int, farbe: str | None, *, quelle=None, signal_ref=None) -> None:
    init_db()
    """Nutzer-Markierung setzen (gruen/gelb/orange) oder entfernen (None)."""
    init_db()
    with _connect() as conn:
        identity = _write_identity(conn, signal_id, quelle=quelle, signal_ref=signal_ref)
        signal_ref = identity.signal_ref
        if farbe is None:
            conn.execute("DELETE FROM signal_markierungen WHERE signal_ref=?",
                         (int(signal_ref),))
        else:
            conn.execute(
                """INSERT INTO signal_markierungen (signal_ref, farbe, updated_at)
                   VALUES (?,?,?)
                   ON CONFLICT(signal_ref) DO UPDATE SET
                     farbe=excluded.farbe, updated_at=excluded.updated_at""",
                (int(signal_ref), str(farbe), _now()))



def list_markierungen(*, quelle=None, identitaeten=False) -> dict:
    return _list_user_state("signal_markierungen","farbe",quelle=quelle,identitaeten=identitaeten)


def setze_beobachtung(signal_id: int, beobachten: bool = True, *,
                      quelle=None, signal_ref=None) -> None:
    """Signal auf die Beobachtungsliste setzen (True) oder entfernen (False).

    Nutzer-Wunsch 20.10.2026: ausgewählte Signale der Abonnentenstatistik
    dauerhaft beobachten — eigener Tab, unabhängig vom Abonnenten-Filter.
    """
    init_db()
    with _connect() as conn:
        identity = _write_identity(conn, signal_id, quelle=quelle, signal_ref=signal_ref)
        if beobachten:
            conn.execute(
                "INSERT INTO beobachtungsliste(signal_ref,angelegt_am) VALUES(?,?) "
                "ON CONFLICT(signal_ref) DO UPDATE SET angelegt_am=excluded.angelegt_am",
                (identity.signal_ref, _now()))
        else:
            conn.execute("DELETE FROM beobachtungsliste WHERE signal_ref=?",
                         (identity.signal_ref,))


def list_beobachtungen() -> set[int]:
    """Signal-Referenzen der Beobachtungsliste (Set für Tabellenzugehörigkeit)."""
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT signal_ref FROM beobachtungsliste").fetchall()
    return {int(row["signal_ref"]) for row in rows}



def setze_kommentar(signal_id: int, kommentar: str | None, *, quelle=None, signal_ref=None) -> None:
    init_db()
    """Freitext-Kommentar setzen (None/leer = löschen)."""
    init_db()
    text_wert = (kommentar or "").strip()
    with _connect() as conn:
        identity = _write_identity(conn, signal_id, quelle=quelle, signal_ref=signal_ref)
        signal_ref = identity.signal_ref
        if not text_wert:
            conn.execute("DELETE FROM signal_kommentare WHERE signal_ref=?",
                         (int(signal_ref),))
        else:
            conn.execute(
                """INSERT INTO signal_kommentare (signal_ref, kommentar, updated_at)
                   VALUES (?,?,?)
                   ON CONFLICT(signal_ref) DO UPDATE SET
                     kommentar=excluded.kommentar,
                     updated_at=excluded.updated_at""",
                (int(signal_ref), text_wert, _now()))



def get_kommentar(signal_id: int, *, quelle=None, signal_ref=None) -> str:
    """Kommentar je Signal ("" = keiner)."""
    identity = _read_ref(signal_id, quelle=quelle, signal_ref=signal_ref)
    if identity is None:
        return ""
    signal_ref = identity.signal_ref
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT kommentar FROM signal_kommentare WHERE signal_ref=?",
            (int(signal_ref),)).fetchone()
    return (row["kommentar"] if row else "") or ""



def list_kommentare(*, quelle=None, identitaeten=False) -> dict:
    return _list_user_state("signal_kommentare","kommentar",quelle=quelle,identitaeten=identitaeten)
