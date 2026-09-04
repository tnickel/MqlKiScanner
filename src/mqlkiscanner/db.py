# -*- coding: utf-8 -*-
"""SQLite-Datenbank: alle Scan-Daten haltbar speichern (Nutzer-Prinzip).

"csv herunterladen, infos alle von mql5 herunterladen und alles in datenbank."

Tabellen:
- signals     : Signal-Kopfdaten + Kennzahlen-JSON (von der MQL5-Seite)
- trade_files : geladene Trade-CSVs je Signal (Pfad, Hash, Zeitpunkt)
- forensik    : Engine-Befund-JSON je Signal
- analyses    : LLM-Teilergebnisse (kind = trade_analyse | risiko_analyse |
                gesamtbericht), je (signal, kind) gilt der neueste Eintrag

Pfad: data/mqlkiscanner.db (gitignored). sqlite3 aus der Stdlib — kein
Server noetig.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
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
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_analyses_sig_kind ON analyses(signal_id, kind, id DESC);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


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
                  stats: dict | None = None) -> None:
    with _connect() as conn:
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


def store_trade_file(signal_id: int, path: str) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO trade_files (signal_id, path, sha256, fetched_at)
               VALUES (?,?,?,?)
               ON CONFLICT(signal_id) DO UPDATE SET path=excluded.path,
                 sha256=excluded.sha256, fetched_at=excluded.fetched_at""",
            (signal_id, path, file_sha256(path), _now()))


def store_forensik(signal_id: int, report: dict) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO forensik (signal_id, json, updated_at) VALUES (?,?,?)
               ON CONFLICT(signal_id) DO UPDATE SET json=excluded.json,
                 updated_at=excluded.updated_at""",
            (signal_id, json.dumps(report, ensure_ascii=False, default=str), _now()))


def store_analysis(signal_id: int, kind: str, model: str, tokens: int, text: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO analyses (signal_id, kind, model, tokens, text, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (signal_id, kind, model, tokens, text, _now()))


def get_latest_analysis(signal_id: int, kind: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT model, tokens, text, created_at FROM analyses "
            "WHERE signal_id=? AND kind=? ORDER BY id DESC LIMIT 1",
            (signal_id, kind)).fetchone()
    return dict(row) if row else None


def get_signal(signal_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM signals WHERE signal_id=?", (signal_id,)).fetchone()
    return dict(row) if row else None


def known_signal_ids() -> set[int]:
    with _connect() as conn:
        rows = conn.execute("SELECT signal_id FROM signals").fetchall()
    return {r["signal_id"] for r in rows}
