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
CREATE TABLE IF NOT EXISTS datenquellen (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    kuerzel          TEXT NOT NULL UNIQUE,
    name             TEXT,
    base_url         TEXT NOT NULL,
    typ              TEXT NOT NULL DEFAULT 'mql5-downloader-v1',
    aktiv            INTEGER NOT NULL DEFAULT 1,
    angelegt_am      TEXT,
    letzte_pruefung  TEXT
);
CREATE TABLE IF NOT EXISTS quellen_artefakte (
    quelle_id   INTEGER NOT NULL REFERENCES datenquellen(id),
    signal_id   INTEGER NOT NULL,
    version     TEXT NOT NULL,
    art         TEXT NOT NULL,
    sha256      TEXT,
    path        TEXT,
    fetched_at  TEXT,
    PRIMARY KEY (quelle_id, signal_id, version, art)
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
    signal_id   INTEGER NOT NULL,
    name        TEXT,
    platform    TEXT,
    url         TEXT,
    version     TEXT,
    abonnenten  REAL,
    wochen      REAL,
    risiko      TEXT,
    updated_at  TEXT,
    PRIMARY KEY (quelle, signal_id)
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
    signal_id   INTEGER PRIMARY KEY,
    kommentar   TEXT NOT NULL,
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS signal_markierungen (
    signal_id   INTEGER PRIMARY KEY,
    farbe       TEXT NOT NULL,
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS equity_studien (
    signal_id   INTEGER PRIMARY KEY,
    trades_sha  TEXT,
    json        TEXT,
    cagr_jahr_pct REAL,
    ertrag_monat_geom_pct REAL,
    dd_usd      REAL,
    basislos    INTEGER,
    virtuell    INTEGER,
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
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        # Serialize the additive migration across simultaneous page/worker starts.
        conn.execute("BEGIN IMMEDIATE")
        if "basis" not in {row["name"] for row in conn.execute("PRAGMA table_info(analyses)")}:
            conn.execute("ALTER TABLE analyses ADD COLUMN basis TEXT")
        # Multi-Source-Hub (doc/20): Herkunfts-Kürzel je Signal. Bestand ist
        # ausnahmslos MQL5-Welt; spätere Quellen schreiben ihr Kürzel dazu.
        if "quelle" not in {row["name"] for row in conn.execute("PRAGMA table_info(signals)")}:
            conn.execute("ALTER TABLE signals ADD COLUMN quelle TEXT DEFAULT 'mql5'")
        conn.execute("UPDATE signals SET quelle='mql5' WHERE quelle IS NULL")
        # Globale Portfolios haben kein Elternsignal. Alte 0-Platzhalter ohne
        # Änderung des Berichtsinhalts auf den bereits erlaubten NULL-Wert heben.
        conn.execute("UPDATE analyses SET signal_id=NULL "
                     "WHERE kind='portfolio' AND signal_id=0")
        # equity_studien: virtuelle-Basis-Flag (08.10.) — Alt-Bestand None
        if "virtuell" not in {row["name"] for row in
                              conn.execute("PRAGMA table_info(equity_studien)")}:
            conn.execute("ALTER TABLE equity_studien ADD COLUMN virtuell INTEGER")
            conn.execute("UPDATE equity_studien SET virtuell=0 WHERE virtuell IS NULL")


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
                  stats: dict | None = None, quelle: str | None = None, *,
                  _connection=None) -> None:
    """Kopfdaten je Signal. `quelle` (Herkunfts-Kürzel) wird nur geschrieben,
    wenn übergeben — ein Update aus einer anderen Quelle überklebtert die
    dokumentierte Herkunft nicht stillschweigend.

    R1 (Intensiv-Review 29./30.09.2026): Schreibt eine ANDERE Quelle dieselbe
    Signal-ID (numerischer Überlapp mql5 ~2,37 Mio. vs. pelik ~2,0–2,1 Mio.),
    bleibt die dokumentierte Herkunft stehen und der Vorfall wird geloggt —
    kein stillsprechendes Überschreiben mehr, bis die Composite-Identität
    (quelle, signal_id) aus doc/20 Stufe 2 migriert ist."""
    import logging as _logging
    with (contextlib.nullcontext(_connection) if _connection is not None else _connect()) as conn:
        if quelle is not None:
            alt = conn.execute(
                "SELECT quelle FROM signals WHERE signal_id=?",
                (signal_id,)).fetchone()
            alt_quelle = (alt[0] if alt and alt[0] else None)
            if alt_quelle and alt_quelle != quelle:
                # F3 (Fremd-Review 01.10.): Ein unverändertes Quellenlabel
                # ist KEIN Kollisionsschutz — Name/Plattform/Forensik würden
                # trotzdem mit den Inhalten der fremden Quelle überschrieben
                # (Gegenprobe: MQL5 123, dann Pelican 123 -> Pelican-Inhalt
                # unter Label mql5). Bei Konflikt wird der SCHREIBVERSUCH
                # ganz abgewiesen; die Identität (quelle, signal_id) ist
                # bis zur Composite-Migration (doc/20 Stufe 2) getrennt.
                raise ValueError(
                    f"ID-Kollision abgewehrt: Signal {signal_id} gehört "
                    f"Quelle {alt_quelle!r}; Schreibversuch aus Quelle "
                    f"{quelle!r} verworfen (bis Composite-Identität, "
                    "doc/20 Stufe 2).")
        if quelle is None:
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
        else:
            conn.execute(
                """INSERT INTO signals (signal_id, name, platform, url, autor, abo_preis,
                   abonnenten, wochen, stats_json, updated_at, quelle)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(signal_id) DO UPDATE SET
                     name=excluded.name, platform=excluded.platform, url=excluded.url,
                     autor=excluded.autor, abo_preis=excluded.abo_preis,
                     abonnenten=excluded.abonnenten, wochen=excluded.wochen,
                     stats_json=excluded.stats_json, updated_at=excluded.updated_at,
                     quelle=excluded.quelle""",
                (signal_id, name, platform, url, autor, abo_preis, abonnenten, wochen,
                 json.dumps(stats or {}, ensure_ascii=False), _now(), quelle))


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
                   s.abonnenten, s.wochen, s.quelle,
                   s.stats_json, s.updated_at AS signal_updated,
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
    where = "WHERE aktiv=1" if nur_aktiv else ""
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT id, kuerzel, name, base_url, typ, aktiv, angelegt_am, "
            f"letzte_pruefung FROM datenquellen {where} ORDER BY id").fetchall()
    return [_row_zu_quelle(row) for row in rows]


def get_quelle(quelle_id: int) -> dict | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, kuerzel, name, base_url, typ, aktiv, angelegt_am, "
            "letzte_pruefung FROM datenquellen WHERE id=?",
            (int(quelle_id),)).fetchone()
    return _row_zu_quelle(row) if row else None


def add_quelle(kuerzel: str, name: str, base_url: str, typ: str = "mql5-downloader-v1",
               aktiv: bool = True) -> int:
    """Neue Datenquelle anlegen; Kürzel ist eindeutig (sqlite3.IntegrityError)."""
    init_db()
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO datenquellen (kuerzel, name, base_url, typ, aktiv, angelegt_am) "
            "VALUES (?,?,?,?,?,?)",
            (str(kuerzel).strip(), str(name).strip(), str(base_url).strip(),
             str(typ).strip(), int(bool(aktiv)), _now()))
        return int(cursor.lastrowid or 0)


def update_quelle(quelle_id: int, *, kuerzel: str | None = None, name: str | None = None,
                  base_url: str | None = None, aktiv: bool | None = None) -> None:
    """Einzelne Felder einer Quelle ändern; None lässt das Feld unberührt."""
    sets, args = [], []
    if kuerzel is not None:
        sets.append("kuerzel=?")
        args.append(str(kuerzel).strip())
    if name is not None:
        sets.append("name=?")
        args.append(str(name).strip())
    if base_url is not None:
        sets.append("base_url=?")
        args.append(str(base_url).strip())
    if aktiv is not None:
        sets.append("aktiv=?")
        args.append(int(bool(aktiv)))
    if not sets:
        return
    args.append(int(quelle_id))
    with _connect() as conn:
        conn.execute(f"UPDATE datenquellen SET {', '.join(sets)} WHERE id=?", args)


def delete_quelle(quelle_id: int) -> None:
    """Quelle löschen. Cache-Dateien bleiben liegen (bewusst — Neuanlage mit
    gleichem Kürzel findet unveränderte Artefakte nicht mehr, SHA schützt)."""
    with _connect() as conn:
        conn.execute("DELETE FROM quellen_artefakte WHERE quelle_id=?", (int(quelle_id),))
        conn.execute("DELETE FROM datenquellen WHERE id=?", (int(quelle_id),))


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


def katalog_upsert_many(quelle_kuerzel: str, items: list[dict]) -> tuple[int, int]:
    """Vollkatalog einer Quelle schreiben (Nutzer 08.10.2026).

    Insert/Update je (quelle, signal_id); Zeilen dieser Quelle, die im
    frischen Katalog NICHT mehr auftauchen, werden gelöscht (der Client
    kennt nur sichtbare Provider — rausgefallene sind dann wirklich weg).
    Rückgabe (gespeichert, geloescht).
    """
    init_db()
    jetzt = _now()
    with _connect() as conn:
        frisch: set[int] = set()
        for item in items:
            signal_id = int(item["signal_id"])
            frisch.add(signal_id)
            conn.execute(
                """INSERT INTO katalog_signale (quelle, signal_id, name, platform,
                   url, version, abonnenten, wochen, risiko, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(quelle, signal_id) DO UPDATE SET
                     name=excluded.name, platform=excluded.platform, url=excluded.url,
                     version=excluded.version, abonnenten=excluded.abonnenten,
                     wochen=excluded.wochen, risiko=excluded.risiko,
                     updated_at=excluded.updated_at""",
                (str(quelle_kuerzel), signal_id, item.get("name"),
                 item.get("platform"), item.get("url"), item.get("version"),
                 item.get("abonnenten"), item.get("wochen"), item.get("risiko"),
                 jetzt))
        alt = {int(row["signal_id"]) for row in conn.execute(
            "SELECT signal_id FROM katalog_signale WHERE quelle=?",
            (str(quelle_kuerzel),))}
        stale = sorted(alt - frisch)
        geloescht = 0
        for i in range(0, len(stale), _KATALOG_STALE_CHUNK):
            block = stale[i:i + _KATALOG_STALE_CHUNK]
            cur = conn.execute(
                f"DELETE FROM katalog_signale WHERE quelle=? AND signal_id IN "
                f"({','.join('?' * len(block))})",
                [str(quelle_kuerzel), *block])
            geloescht += cur.rowcount or 0
    return len(frisch), geloescht


def katalog_list() -> list[dict]:
    """Alle Katalogzeilen (je Quelle + Signal), Abonnenten absteigend."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT quelle, signal_id, name, platform, url, version, abonnenten, "
            "wochen, risiko, updated_at FROM katalog_signale "
            "ORDER BY abonnenten DESC, quelle, signal_id").fetchall()
    return [dict(row) for row in rows]


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
            (str(quelle_kuerzel), _now(), int(anzahl), fehler))


def katalog_sync_status() -> dict[str, dict]:
    """Letzter Katalog-Sync je Quelle: {"kuerzel": {"gelaufen_am", "anzahl", "fehler"}}."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT quelle, gelaufen_am, anzahl, fehler FROM katalog_sync").fetchall()
    return {row["quelle"]: {"gelaufen_am": row["gelaufen_am"],
                            "anzahl": row["anzahl"], "fehler": row["fehler"]}
            for row in rows}


def store_equity_studie(signal_id: int, trades_sha: str, report: dict, *,
                        cagr_jahr_pct: float | None = None,
                        ertrag_monat_geom_pct: float | None = None,
                        dd_usd: float | None = None,
                        basislos: bool = False,
                        virtuell: bool = False) -> None:
    """Batch-Equity-Studie persistieren (Nutzer 08.10.2026).

    `report` ist das volle equity_rekonstruktion-dict (dieselbe Struktur wie
    im Forensik-Snapshot — results_from_db kann es 1:1 mappen). cagr/geom
    stammen aus der Vorstufen-Statistik zum Studienzeitpunkt; daraus rechnet
    das Laden TrueRetDD. dd_usd ist basis-unabhängig und existiert auch bei
    kapitalbasielosen Signalen (basislos=True → kein % speichern).
    """
    init_db()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO equity_studien (signal_id, trades_sha, json,
               cagr_jahr_pct, ertrag_monat_geom_pct, dd_usd, basislos, virtuell,
               updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(signal_id) DO UPDATE SET
                 trades_sha=excluded.trades_sha, json=excluded.json,
                 cagr_jahr_pct=excluded.cagr_jahr_pct,
                 ertrag_monat_geom_pct=excluded.ertrag_monat_geom_pct,
                 dd_usd=excluded.dd_usd, basislos=excluded.basislos,
                 virtuell=excluded.virtuell, updated_at=excluded.updated_at""",
            (int(signal_id), trades_sha,
             json.dumps(report, ensure_ascii=False, sort_keys=True, default=str),
             cagr_jahr_pct, ertrag_monat_geom_pct, dd_usd,
             1 if basislos else 0, 1 if virtuell else 0, _now()))


def get_equity_studie(signal_id: int) -> dict | None:
    """Studien-Zeile je Signal (dict mit geparstem json) oder None."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT signal_id, trades_sha, json, cagr_jahr_pct, "
            "ertrag_monat_geom_pct, dd_usd, basislos, virtuell, updated_at "
            "FROM equity_studien WHERE signal_id=?",
            (int(signal_id),)).fetchone()
    if row is None:
        return None
    daten = dict(row)
    try:
        daten["report"] = json.loads(daten.pop("json") or "{}")
    except ValueError:
        return None
    return daten


def list_equity_studien() -> dict[int, dict]:
    """Alle Studien als {signal_id: zeile} — für das Befüllen der Tabellen."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT signal_id, trades_sha, json, cagr_jahr_pct, "
            "ertrag_monat_geom_pct, dd_usd, basislos, virtuell, updated_at "
            "FROM equity_studien").fetchall()
    out: dict[int, dict] = {}
    for row in rows:
        daten = dict(row)
        try:
            daten["report"] = json.loads(daten.pop("json") or "{}")
        except ValueError:
            continue
        out[int(daten["signal_id"])] = daten
    return out


def store_quellen_artefakt(quelle_id: int, signal_id: int, version: str, art: str,
                           sha256: str, path: str) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO quellen_artefakte
               (quelle_id, signal_id, version, art, sha256, path, fetched_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(quelle_id, signal_id, version, art) DO UPDATE SET
                 sha256=excluded.sha256, path=excluded.path,
                 fetched_at=excluded.fetched_at""",
            (int(quelle_id), int(signal_id), str(version), str(art),
             str(sha256), str(path), _now()))


def get_quellen_artefakt(quelle_id: int, signal_id: int, version: str,
                         art: str) -> dict | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT sha256, path, fetched_at FROM quellen_artefakte "
            "WHERE quelle_id=? AND signal_id=? AND version=? AND art=?",
            (int(quelle_id), int(signal_id), str(version), str(art))).fetchone()
    return dict(row) if row else None


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
    eintraege = list_client_updates(limit=500)
    neueste: dict[str, dict] = {}
    for eintrag in eintraege:  # absteigend — erster Treffer je Kürzel gewinnt
        neueste.setdefault(str(eintrag.get("kuerzel")), eintrag)
    return neueste


def setze_markierung(signal_id: int, farbe: str | None) -> None:
    """Nutzer-Markierung setzen (gruen/gelb/orange) oder entfernen (None)."""
    init_db()
    with _connect() as conn:
        if farbe is None:
            conn.execute("DELETE FROM signal_markierungen WHERE signal_id=?",
                         (int(signal_id),))
        else:
            conn.execute(
                """INSERT INTO signal_markierungen (signal_id, farbe, updated_at)
                   VALUES (?,?,?)
                   ON CONFLICT(signal_id) DO UPDATE SET
                     farbe=excluded.farbe, updated_at=excluded.updated_at""",
                (int(signal_id), str(farbe), _now()))


def list_markierungen() -> dict[int, str]:
    """Alle Markierungen als {signal_id: farbe}."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT signal_id, farbe FROM signal_markierungen").fetchall()
    return {int(r["signal_id"]): str(r["farbe"]) for r in rows}


def setze_kommentar(signal_id: int, kommentar: str | None) -> None:
    """Freitext-Kommentar setzen (None/leer = löschen)."""
    init_db()
    text_wert = (kommentar or "").strip()
    with _connect() as conn:
        if not text_wert:
            conn.execute("DELETE FROM signal_kommentare WHERE signal_id=?",
                         (int(signal_id),))
        else:
            conn.execute(
                """INSERT INTO signal_kommentare (signal_id, kommentar, updated_at)
                   VALUES (?,?,?)
                   ON CONFLICT(signal_id) DO UPDATE SET
                     kommentar=excluded.kommentar,
                     updated_at=excluded.updated_at""",
                (int(signal_id), text_wert, _now()))


def get_kommentar(signal_id: int) -> str:
    """Kommentar je Signal ("" = keiner)."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT kommentar FROM signal_kommentare WHERE signal_id=?",
            (int(signal_id),)).fetchone()
    return (row["kommentar"] if row else "") or ""


def list_kommentare() -> dict[int, str]:
    """Alle Kommentare als {signal_id: text} — für die Tabellenanzeige."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT signal_id, kommentar FROM signal_kommentare").fetchall()
    return {int(r["signal_id"]): (r["kommentar"] or "") for r in rows}
