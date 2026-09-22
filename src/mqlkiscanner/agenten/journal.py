# -*- coding: utf-8 -*-
"""Agenten-Journal: Läufe, Schritte und Steuerung in SQLite (append-only).

Tabellen (doc/19, Abschnitt 6):
- agenten_laeufe     je Zyklus einer Rolle (Start, Ende, Status, Zusammenfassung)
- agenten_schritte   je Code- oder LLM-Schritt — bei LLM mit VOLLSTÄNDIGEM
                     gefülltem Prompt und VOLLSTÄNDIGER Antwort (das Protokoll,
                     das den Trockenmodus ersetzt; Nutzer-Entscheidung 22.09.:
                     kein Trockenmodus, dafür lückenlose Nachvollziehbarkeit)
- agenten_meldungen  Alerts/Digests (Phase D; Schema steht von Anfang an)
- agenten_steuerung  kleine Schlüssel-Wert-Tabelle für Daemon-Steuerung
                     (pid, gestartet, letzter_tick, stop_wunsch)

Das Journal nutzt dieselbe Datenbankdatei wie der Rest (db.DB_PATH wird zur
Laufzeit gelesen — Tests lenken sie per monkeypatch um). Alles append-only:
kein UPDATE auf Chronik-Zeilen, kein DELETE.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from .. import db


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _heute() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _monat() -> str:
    return datetime.now().strftime("%Y-%m")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS agenten_laeufe (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    rolle         TEXT NOT NULL,
    quelle        TEXT NOT NULL,
    start         TEXT NOT NULL,
    ende          TEXT,
    status        TEXT NOT NULL,
    signal_id     INTEGER,
    zusammenfassung TEXT
);
CREATE INDEX IF NOT EXISTS idx_agenten_laeufe_start ON agenten_laeufe(start DESC);
CREATE TABLE IF NOT EXISTS agenten_schritte (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    lauf_id     INTEGER REFERENCES agenten_laeufe(id),
    ts          TEXT NOT NULL,
    rolle       TEXT NOT NULL,
    schritt     TEXT NOT NULL,
    status      TEXT NOT NULL,
    prompt      TEXT,
    antwort     TEXT,
    modell      TEXT,
    tokens      INTEGER,
    dauer_s     REAL,
    detail_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_agenten_schritte_ts ON agenten_schritte(ts DESC);
CREATE INDEX IF NOT EXISTS idx_agenten_schritte_lauf ON agenten_schritte(lauf_id);
CREATE TABLE IF NOT EXISTS agenten_meldungen (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    typ          TEXT NOT NULL,
    prioritaet   INTEGER NOT NULL DEFAULT 1,
    titel        TEXT NOT NULL,
    text         TEXT NOT NULL,
    quellen_json TEXT
);
CREATE TABLE IF NOT EXISTS agenten_steuerung (
    schluessel TEXT PRIMARY KEY,
    wert       TEXT,
    geaendert  TEXT
);
"""


def init_journal() -> None:
    """Tabellen anlegen (idempotent; auch neben der Streamlit-App aufrufbar)."""
    with db._connect() as conn:
        conn.executescript(_SCHEMA)


# ── Läufe ─────────────────────────────────────────────────────────

def lauf_starten(rolle: str, quelle: str = "daemon", signal_id: int | None = None) -> int:
    init_journal()
    with db._connect() as conn:
        cursor = conn.execute(
            "INSERT INTO agenten_laeufe (rolle, quelle, start, status, signal_id) "
            "VALUES (?,?,?,'laeuft',?)",
            (rolle, quelle, _now(), signal_id))
        return int(cursor.lastrowid or 0)


def lauf_abschliessen(lauf_id: int, status: str, zusammenfassung: str = "") -> None:
    """Status-Übergang laeuft → ok|fehler|abgebrochen|skipped (kein Re-Open)."""
    with db._connect() as conn:
        conn.execute(
            "UPDATE agenten_laeufe SET ende=?, status=?, zusammenfassung=? "
            "WHERE id=? AND status='laeuft'",
            (_now(), status, zusammenfassung, lauf_id))


def lauf_ist_aktiv(lauf_id: int) -> bool:
    with db._connect() as conn:
        row = conn.execute("SELECT status FROM agenten_laeufe WHERE id=?",
                           (lauf_id,)).fetchone()
    return bool(row and row["status"] == "laeuft")


def lauf_heute_erfolgreich(rolle: str, quelle: str) -> bool:
    """Gab es heute bereits einen ok-Lauf dieser Rolle aus dieser Quelle?

    Die scheduler-Takt-Prüfung: pro Tag und Rolle genau ein Daemon-Lauf.
    """
    init_journal()
    with db._connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM agenten_laeufe "
            "WHERE rolle=? AND quelle=? AND status='ok' AND start LIKE ?",
            (rolle, quelle, _heute() + "%")).fetchone()
    return int(row["n"] if row else 0) > 0


def list_laeufe(limit: int = 25, rolle: str | None = None) -> list[dict]:
    init_journal()
    clauses, args = [], []
    if rolle:
        clauses.append("rolle=?")
        args.append(rolle)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    args.append(max(1, int(limit)))
    with db._connect() as conn:
        rows = conn.execute(
            f"SELECT id, rolle, quelle, start, ende, status, signal_id, zusammenfassung "
            f"FROM agenten_laeufe {where} ORDER BY id DESC LIMIT ?", args).fetchall()
    return [dict(r) for r in rows]


def letzter_lauf(rolle: str | None = None) -> dict | None:
    laeufe = list_laeufe(limit=1, rolle=rolle)
    return laeufe[0] if laeufe else None


# ── Schritte (das Protokoll) ──────────────────────────────────────

def schritt_protokollieren(lauf_id: int, rolle: str, schritt: str, *,
                           status: str = "ok", prompt: str | None = None,
                           antwort: str | None = None, modell: str | None = None,
                           tokens: int = 0, dauer_s: float | None = None,
                           detail: dict | None = None) -> int:
    """Ein Schritt im Protokoll — LLM-Aufrufe MIT vollem Prompt und Antwort."""
    init_journal()
    with db._connect() as conn:
        cursor = conn.execute(
            "INSERT INTO agenten_schritte "
            "(lauf_id, ts, rolle, schritt, status, prompt, antwort, modell, "
            " tokens, dauer_s, detail_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (lauf_id, _now(), rolle, schritt, status, prompt, antwort, modell,
             int(tokens), dauer_s,
             json.dumps(detail or {}, ensure_ascii=False, default=str)))
        return int(cursor.lastrowid or 0)


def list_schritte(limit: int = 100, rolle: str | None = None,
                  tag: str | None = None) -> list[dict]:
    """Protokoll, neueste zuerst; ohne Inhaltsspalten (Übersicht der UI)."""
    init_journal()
    clauses, args = [], []
    if rolle:
        clauses.append("rolle=?")
        args.append(rolle)
    if tag:
        clauses.append("ts LIKE ?")
        args.append(tag + "%")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    args.append(max(1, int(limit)))
    with db._connect() as conn:
        rows = conn.execute(
            f"SELECT id, lauf_id, ts, rolle, schritt, status, modell, tokens, "
            f"dauer_s, LENGTH(prompt) AS prompt_zeichen, "
            f"LENGTH(antwort) AS antwort_zeichen "
            f"FROM agenten_schritte {where} ORDER BY id DESC LIMIT ?", args).fetchall()
    return [dict(r) for r in rows]


def schritt_lesen(schritt_id: int) -> dict | None:
    """Vollständiger Schritt inklusive Prompt/Antwort (Detailansicht)."""
    init_journal()
    with db._connect() as conn:
        row = conn.execute(
            "SELECT id, lauf_id, ts, rolle, schritt, status, prompt, antwort, "
            "modell, tokens, dauer_s, detail_json FROM agenten_schritte WHERE id=?",
            (schritt_id,)).fetchone()
    if row is None:
        return None
    eintrag = dict(row)
    try:
        eintrag["detail"] = json.loads(eintrag.pop("detail_json") or "{}")
    except json.JSONDecodeError:
        eintrag["detail"] = {}
    return eintrag


# ── Budget ────────────────────────────────────────────────────────

def tokens_heute() -> int:
    """Summe der Token aller LLM-Schritte heute (Agenten-Budget, doc/19 §10)."""
    init_journal()
    with db._connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(tokens),0) AS n FROM agenten_schritte "
            "WHERE tokens IS NOT NULL AND ts LIKE ? AND prompt IS NOT NULL",
            (_heute() + "%",)).fetchone()
    return int(row["n"] if row else 0)


def tokens_monat() -> int:
    init_journal()
    with db._connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(tokens),0) AS n FROM agenten_schritte "
            "WHERE tokens IS NOT NULL AND ts LIKE ? AND prompt IS NOT NULL",
            (_monat() + "%",)).fetchone()
    return int(row["n"] if row else 0)


# ── Steuerung (Daemon-Status, Start/Stopp über die UI) ────────────

def steuerung_setzen(schluessel: str, wert: str) -> None:
    init_journal()
    with db._connect() as conn:
        conn.execute(
            "INSERT INTO agenten_steuerung (schluessel, wert, geaendert) "
            "VALUES (?,?,?) ON CONFLICT(schluessel) DO UPDATE SET "
            "wert=excluded.wert, geaendert=excluded.geaendert",
            (schluessel, str(wert), _now()))


def steuerung_lesen() -> dict[str, str]:
    init_journal()
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT schluessel, wert FROM agenten_steuerung").fetchall()
    return {r["schluessel"]: (r["wert"] or "") for r in rows}
