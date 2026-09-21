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
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR

DB_PATH = DATA_DIR / "mqlkiscanner.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    signal_id   INTEGER PRIMARY KEY,
    name        TEXT,
    platform    TEXT,
    url         TEXT,
    autor       TEXT,
    abo_preis   REAL,
    abonnenten  REAL,
    wochen      REAL,
    stats_json  TEXT,
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS trade_files (
    signal_id   INTEGER PRIMARY KEY REFERENCES signals(signal_id),
    path        TEXT,
    sha256      TEXT,
    fetched_at  TEXT
);
CREATE TABLE IF NOT EXISTS forensik (
    signal_id   INTEGER PRIMARY KEY REFERENCES signals(signal_id),
    json        TEXT,
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS analyses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   INTEGER REFERENCES signals(signal_id),
    kind        TEXT,
    model       TEXT,
    tokens      INTEGER,
    text        TEXT,
    created_at  TEXT,
    basis       TEXT
);
CREATE INDEX IF NOT EXISTS idx_analyses_sig_kind ON analyses(signal_id, kind, id DESC);
CREATE TABLE IF NOT EXISTS subscriber_history (
    signal_id   INTEGER NOT NULL,
    version     TEXT NOT NULL,
    ts          TEXT NOT NULL,
    subscribers INTEGER,
    change      INTEGER,
    fetched_at  TEXT,
    PRIMARY KEY (signal_id, version, ts)
);
CREATE TABLE IF NOT EXISTS downloader_reports (
    signal_id     INTEGER NOT NULL,
    version       TEXT NOT NULL,
    name          TEXT NOT NULL,
    path          TEXT NOT NULL,
    size_bytes    INTEGER,
    last_modified TEXT,
    fetched_at    TEXT,
    PRIMARY KEY (signal_id, version, name)
);
CREATE TABLE IF NOT EXISTS tradeserver_sync_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    base_url    TEXT,
    status      TEXT,
    summary_json TEXT
);
CREATE TABLE IF NOT EXISTS ampel_verlauf (
    signal_id  INTEGER NOT NULL,
    ts         TEXT NOT NULL,
    quelle     TEXT NOT NULL,
    ampel      TEXT NOT NULL,
    score      REAL,
    urteil     TEXT,
    matrix     TEXT,
    PRIMARY KEY (signal_id, ts)
);
CREATE TABLE IF NOT EXISTS ampel_wechsel (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   INTEGER NOT NULL,
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
"""


@contextlib.contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        # Serialize the additive migration across simultaneous page/worker starts.
        conn.execute("BEGIN IMMEDIATE")
        if "basis" not in {row["name"] for row in conn.execute("PRAGMA table_info(analyses)")}:
            conn.execute("ALTER TABLE analyses ADD COLUMN basis TEXT")
        # Globale Portfolios haben kein Elternsignal. Alte 0-Platzhalter ohne
        # Änderung des Berichtsinhalts auf den bereits erlaubten NULL-Wert heben.
        conn.execute("UPDATE analyses SET signal_id=NULL "
                     "WHERE kind='portfolio' AND signal_id=0")


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def upsert_signal(signal_id: int, name: str = "", platform: str = "", url: str = "",
                  autor: str = "", abo_preis=None, abonnenten=None, wochen=None,
                  stats: dict | None = None, *, _connection=None) -> None:
    with (contextlib.nullcontext(_connection) if _connection is not None else _connect()) as conn:
        conn.execute(
            """INSERT INTO signals (signal_id, name, platform, url, autor, abo_preis,
               abonnenten, wochen, stats_json, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(signal_id) DO UPDATE SET
                 name=excluded.name, platform=excluded.platform, url=excluded.url,
                 autor=excluded.autor, abo_preis=excluded.abo_preis,
                 abonnenten=excluded.abonnenten, wochen=excluded.wochen,
                 stats_json=excluded.stats_json, updated_at=excluded.updated_at""",
            (signal_id, name, platform, url, autor, abo_preis, abonnenten, wochen,
             json.dumps(stats or {}, ensure_ascii=False), _now()))


def _snapshot_trade_file(path: str) -> tuple[str, str]:
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
        snapshot = directory / f"{sha256}{suffix}"
        # Concurrent identical content has the same destination and bytes.
        os.replace(temporary, snapshot)
        return str(snapshot), sha256
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def store_trade_file(signal_id: int, path: str, *, _connection=None) -> str:
    snapshot, sha256 = _snapshot_trade_file(path)
    with (contextlib.nullcontext(_connection) if _connection is not None else _connect()) as conn:
        conn.execute(
            """INSERT INTO trade_files (signal_id, path, sha256, fetched_at)
               VALUES (?,?,?,?)
               ON CONFLICT(signal_id) DO UPDATE SET path=excluded.path,
                 sha256=excluded.sha256, fetched_at=excluded.fetched_at""",
            (signal_id, snapshot, sha256, _now()))
    return snapshot


def store_forensik(signal_id: int, report: dict, *, _connection=None) -> None:
    with (contextlib.nullcontext(_connection) if _connection is not None else _connect()) as conn:
        conn.execute(
            """INSERT INTO forensik (signal_id, json, updated_at) VALUES (?,?,?)
               ON CONFLICT(signal_id) DO UPDATE SET json=excluded.json,
                 updated_at=excluded.updated_at""",
            (signal_id, json.dumps(report, ensure_ascii=False, default=str), _now()))


def store_scan_result(signal_id: int, signal: dict, trades_path: str = "",
                      forensik: dict | None = None) -> str:
    """Kennzahlen und zugehörigen Befund gemeinsam bestätigen oder zurückrollen."""
    snapshot = ""
    with _connect() as conn:
        upsert_signal(signal_id, **signal, _connection=conn)
        if trades_path:
            snapshot = store_trade_file(signal_id, trades_path, _connection=conn)
        if forensik is not None:
            store_forensik(signal_id, forensik, _connection=conn)
    return snapshot


def store_analysis(signal_id: int | None, kind: str, model: str, tokens: int, text: str,
                   *, basis: str | None = None) -> str:
    if kind == "portfolio" and signal_id == 0:
        signal_id = None  # Kompatibilität für bisherige Aufrufer.
    created_at = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO analyses (signal_id, kind, model, tokens, text, created_at, basis) "
            "VALUES (?,?,?,?,?,?,?)",
            (signal_id, kind, model, tokens, text, created_at, basis))
    return created_at


def get_latest_analysis(signal_id: int | None, kind: str, *, basis: str | None = None) -> dict | None:
    if kind == "portfolio" and signal_id == 0:
        signal_id = None
    legacy_portfolio = kind == "portfolio" and signal_id is None
    with _connect() as conn:
        row = conn.execute(
            "SELECT model, tokens, text, created_at, basis FROM analyses "
            "WHERE (signal_id IS ? OR (? AND signal_id=0)) AND kind=? "
            "AND (? IS NULL OR basis=?) "
            "ORDER BY id DESC LIMIT 1",
            (signal_id, legacy_portfolio, kind, basis, basis)).fetchone()
    return dict(row) if row else None


def list_catalog() -> list[dict]:
    """Alle Signale mit Forensik und neuesten KI-Texten (eine Zeile je Signal)."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT s.signal_id, s.name, s.platform, s.url, s.autor, s.abo_preis,
                   s.abonnenten, s.wochen, s.stats_json, s.updated_at AS signal_updated,
                   t.path AS trades_path, t.sha256 AS trades_sha256, t.fetched_at AS trades_fetched,
                   f.json AS forensik_json, f.updated_at AS forensik_updated,
                   (SELECT text FROM analyses a WHERE a.signal_id=s.signal_id
                      AND a.kind='trade_analyse' ORDER BY a.id DESC LIMIT 1) AS trade_analyse,
                   (SELECT created_at FROM analyses a WHERE a.signal_id=s.signal_id
                      AND a.kind='trade_analyse' ORDER BY a.id DESC LIMIT 1) AS trade_at,
                   (SELECT model FROM analyses a WHERE a.signal_id=s.signal_id
                      AND a.kind='trade_analyse' ORDER BY a.id DESC LIMIT 1) AS trade_model,
                   (SELECT text FROM analyses a WHERE a.signal_id=s.signal_id
                      AND a.kind='risiko_analyse' ORDER BY a.id DESC LIMIT 1) AS risiko_analyse,
                   (SELECT created_at FROM analyses a WHERE a.signal_id=s.signal_id
                      AND a.kind='risiko_analyse' ORDER BY a.id DESC LIMIT 1) AS risiko_at,
                   (SELECT model FROM analyses a WHERE a.signal_id=s.signal_id
                      AND a.kind='risiko_analyse' ORDER BY a.id DESC LIMIT 1) AS risiko_model,
                   (SELECT text FROM analyses a WHERE a.signal_id=s.signal_id
                      AND a.kind='gesamtbericht' ORDER BY a.id DESC LIMIT 1) AS gesamtbericht,
                   (SELECT created_at FROM analyses a WHERE a.signal_id=s.signal_id
                      AND a.kind='gesamtbericht' ORDER BY a.id DESC LIMIT 1) AS gesamt_at,
                   (SELECT model FROM analyses a WHERE a.signal_id=s.signal_id
                      AND a.kind='gesamtbericht' ORDER BY a.id DESC LIMIT 1) AS gesamt_model,
                   (SELECT text FROM analyses a WHERE a.signal_id=s.signal_id
                      AND a.kind='tiefenanalyse' ORDER BY a.id DESC LIMIT 1) AS tiefenanalyse,
                   (SELECT created_at FROM analyses a WHERE a.signal_id=s.signal_id
                      AND a.kind='tiefenanalyse' ORDER BY a.id DESC LIMIT 1) AS tiefe_at,
                   (SELECT model FROM analyses a WHERE a.signal_id=s.signal_id
                      AND a.kind='tiefenanalyse' ORDER BY a.id DESC LIMIT 1) AS tiefe_model
            FROM signals s
            LEFT JOIN trade_files t ON t.signal_id = s.signal_id
            LEFT JOIN forensik f ON f.signal_id = s.signal_id
            ORDER BY COALESCE(f.updated_at, s.updated_at) DESC, s.signal_id DESC
            """
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["stats"] = json.loads(item.pop("stats_json") or "{}")
        item["forensik"] = json.loads(item.pop("forensik_json") or "null")
        out.append(item)
    return out


def get_signal(signal_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM signals WHERE signal_id=?", (signal_id,)).fetchone()
    return dict(row) if row else None


def known_signal_ids() -> set[int]:
    with _connect() as conn:
        rows = conn.execute("SELECT signal_id FROM signals").fetchall()
    return {r["signal_id"] for r in rows}


def store_history_points(signal_id: int, version: str, points: list[dict],
                         *, fetched_at: str | None = None) -> int:
    """Abonnenten-Punkte je Signal+Version ersetzen (Vollabgleich).

    Ein Punkt ohne Zeitstempel wäre ohne Bezug — er wird übersprungen.
    Rückgabe: Anzahl übernommener Punkte.
    """
    ts = fetched_at or _now()
    kept = 0
    with _connect() as conn:
        for point in points:
            stamp = str(point.get("timestamp") or "").strip()
            if not stamp:
                continue
            conn.execute(
                """INSERT INTO subscriber_history
                   (signal_id, version, ts, subscribers, change, fetched_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(signal_id, version, ts) DO UPDATE SET
                     subscribers=excluded.subscribers, change=excluded.change,
                     fetched_at=excluded.fetched_at""",
                (signal_id, version, stamp,
                 point.get("subscribers"), point.get("change"), ts))
            kept += 1
    return kept


def get_history(signal_id: int, version: str | None = None) -> list[dict]:
    """Abonnenten-Verlauf aufsteigend; ohne Version alle Versionen gemischt."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT signal_id, version, ts, subscribers, change, fetched_at "
            "FROM subscriber_history WHERE signal_id=? "
            "AND (? IS NULL OR version=?) ORDER BY version, ts",
            (signal_id, version, version)).fetchall()
    return [dict(row) for row in rows]


def store_downloader_report(signal_id: int, version: str, name: str, path: str,
                            size_bytes: int | None = None,
                            last_modified: str | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO downloader_reports
               (signal_id, version, name, path, size_bytes, last_modified, fetched_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(signal_id, version, name) DO UPDATE SET
                 path=excluded.path, size_bytes=excluded.size_bytes,
                 last_modified=excluded.last_modified, fetched_at=excluded.fetched_at""",
            (signal_id, version, name, path, size_bytes, last_modified, _now()))


def list_downloader_reports(signal_id: int) -> list[dict]:
    """Lokal gespiegelte Downloader-PDFs je Signal (Version, Name sortiert)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT version, name, path, size_bytes, last_modified, fetched_at "
            "FROM downloader_reports WHERE signal_id=? ORDER BY version, name",
            (signal_id,)).fetchall()
    return [dict(row) for row in rows]


def downloader_report_counts(signal_ids: list[int]) -> dict[int, int]:
    """Anzahl gespiegelter Downloader-PDFs je Signal (fuer Tabellenspalte)."""
    init_db()
    ids = sorted({int(signal_id) for signal_id in signal_ids if signal_id})
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT signal_id, COUNT(*) AS n FROM downloader_reports "
            f"WHERE signal_id IN ({placeholders}) GROUP BY signal_id",
            ids).fetchall()
    return {row["signal_id"]: row["n"] for row in rows}


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


def store_ampel_verlauf(signal_id: int, ts: str, quelle: str, ampel: str,
                        score: float | None, urteil: str, matrix: dict | None) -> None:
    """Farb-Chronik: ein append-only Eintrag je erfolgreich geprüftem Lauf.

    Kein UPDATE, kein DELETE — die Chronik darf nachträglich nicht verändert
    werden. Zwei Einträge desselben Signals in derselben Sekunde können nicht
    vorkommen (ein Signal wird je Lauf höchstens einmal geprüft); sollte es
    doch kollidieren, gewinnt der zuerst geschriebene Eintrag (OR IGNORE).
    """
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO ampel_verlauf "
            "(signal_id, ts, quelle, ampel, score, urteil, matrix) VALUES (?,?,?,?,?,?,?)",
            (signal_id, ts, quelle, ampel, score, urteil,
             json.dumps(matrix or {}, ensure_ascii=False)))


def get_last_ampel_verlauf(signal_id: int) -> dict | None:
    """Der neueste Chronik-Eintrag eines Signals (Vergleichsbasis für Wechsel)."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT signal_id, ts, quelle, ampel, score, urteil, matrix "
            "FROM ampel_verlauf WHERE signal_id=? ORDER BY ts DESC LIMIT 1",
            (signal_id,)).fetchone()
    if row is None:
        return None
    eintrag = dict(row)
    try:
        eintrag["matrix"] = json.loads(eintrag.get("matrix") or "{}")
    except json.JSONDecodeError:
        eintrag["matrix"] = {}
    return eintrag


def list_ampel_verlauf(signal_id: int, limit: int = 50) -> list[dict]:
    """Farb-Chronik eines Signals, neueste zuerst (Anzeige in der GUI)."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT signal_id, ts, quelle, ampel, score, urteil FROM ampel_verlauf "
            "WHERE signal_id=? ORDER BY ts DESC LIMIT ?",
            (signal_id, max(1, int(limit)))).fetchall()
    return [dict(row) for row in rows]


def store_ampel_wechsel(signal_id: int, ts: str, quelle: str, ampel_alt: str | None,
                        ampel_neu: str, farbwechsel: bool, richtung: str,
                        gruende: list[dict], name: str = "") -> int:
    """Ein protokollierter Wechsel (Farbe und/oder gekippte Kriterien).

    Der Signalname wird zum Zeitpunkt des Wechsels mitgespeichert — das
    Protokoll bleibt lesbar, selbst wenn das Signal später aus dem Katalog
    fällt oder umbenannt wird.
    """
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO ampel_wechsel "
            "(signal_id, name, ts, quelle, ampel_alt, ampel_neu, farbwechsel, richtung, gruende) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (signal_id, name, ts, quelle, ampel_alt, ampel_neu, int(farbwechsel),
             richtung, json.dumps(gruende, ensure_ascii=False)))
        return int(cursor.lastrowid or 0)


def list_ampel_wechsel(limit: int = 200, nur_farbwechsel: bool = False,
                       signal_id: int | None = None) -> list[dict]:
    """Wechsel-Protokoll, neueste zuerst (die Wechselliste der GUI)."""
    init_db()
    clauses, args = [], []
    if nur_farbwechsel:
        clauses.append("farbwechsel=1")
    if signal_id is not None:
        clauses.append("signal_id=?")
        args.append(signal_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    args.append(max(1, int(limit)))
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, signal_id, name, ts, quelle, ampel_alt, ampel_neu, farbwechsel, "
            f"richtung, gruende FROM ampel_wechsel {where} ORDER BY id DESC LIMIT ?",
            args).fetchall()
    wechsel = []
    for row in rows:
        eintrag = dict(row)
        eintrag["farbwechsel"] = bool(eintrag["farbwechsel"])
        try:
            eintrag["gruende"] = json.loads(eintrag.pop("gruende") or "[]")
        except json.JSONDecodeError:
            eintrag["gruende"] = []
        wechsel.append(eintrag)
    return wechsel


def count_ampel_wechsel() -> int:
    """Gesamtzahl protokollierter Wechsel (Button-Badge der GUI)."""
    init_db()
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM ampel_wechsel").fetchone()
    return int(row["n"]) if row else 0
