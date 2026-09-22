# -*- coding: utf-8 -*-
"""Dossier-Datenbasis: Algo-Profile, Beobachtungen, Trade-Deltas (Phase B).

Tabellen (doc/19, Abschnitt 6) — append-only wie das übrige Journal:
- dossier_profil        Algo-Profil je Signal, versioniert (Version 1 = n)
- dossier_beobachtungen Einordnungen des Betreuers, verlinkt auf Delta
                        und den protokollierten LLM-Schritt (Nachweis)
- trade_deltas          je Abruf: alter/neuer Snapshot-Hash, Anzahl neuer
                        Trades, maschinell berechnete Delta-Kennzahlen

Das Profil ist Beobachtungsbasis, nie Bewertungsgrundlage: Ampel, Urteil
und Score bleiben allein Sache der Engine in regulären Scan-Läufen.
"""
from __future__ import annotations

import json

from .. import db


def init_dossier() -> None:
    with db._connect() as conn:
        conn.executescript("""
CREATE TABLE IF NOT EXISTS dossier_profil (
    signal_id   INTEGER NOT NULL,
    version     INTEGER NOT NULL,
    erstellt    TEXT NOT NULL,
    modell      TEXT,
    profil_json TEXT NOT NULL,
    profil_text TEXT NOT NULL,
    aenderungs_grund TEXT,
    PRIMARY KEY (signal_id, version)
);
CREATE TABLE IF NOT EXISTS dossier_beobachtungen (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   INTEGER NOT NULL,
    ts          TEXT NOT NULL,
    einordnung  TEXT NOT NULL,
    text        TEXT NOT NULL,
    delta_ref   INTEGER,
    schritt_ref INTEGER
);
CREATE INDEX IF NOT EXISTS idx_dossier_beob_ts
    ON dossier_beobachtungen(signal_id, id DESC);
CREATE TABLE IF NOT EXISTS trade_deltas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id   INTEGER NOT NULL,
    ts          TEXT NOT NULL,
    alt_sha256  TEXT,
    neu_sha256  TEXT NOT NULL,
    neue_trades INTEGER NOT NULL,
    delta_json  TEXT
);
""")


# ── Algo-Profil ───────────────────────────────────────────────────

def profil_speichern(signal_id: int, profil_text: str, modell: str,
                     grundlage: dict, aenderungs_grund: str = "") -> int:
    """Neue Profil-VERSION anlegen (nie überschreiben)."""
    init_dossier()
    with db._connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM dossier_profil "
            "WHERE signal_id=?", (signal_id,)).fetchone()
        version = int(row["v"]) + 1 if row else 1
        conn.execute(
            "INSERT INTO dossier_profil (signal_id, version, erstellt, modell, "
            "profil_json, profil_text, aenderungs_grund) VALUES (?,?,?,?,?,?,?)",
            (signal_id, version, _jetzt(), modell,
             json.dumps(grundlage, ensure_ascii=False), profil_text,
             aenderungs_grund or "Erststellung"))
        return version


def profil_lesen(signal_id: int) -> dict | None:
    """Aktuellste Profil-Version (oder None)."""
    init_dossier()
    with db._connect() as conn:
        row = conn.execute(
            "SELECT signal_id, version, erstellt, modell, profil_json, "
            "profil_text, aenderungs_grund FROM dossier_profil "
            "WHERE signal_id=? ORDER BY version DESC LIMIT 1",
            (signal_id,)).fetchone()
    if row is None:
        return None
    eintrag = dict(row)
    try:
        eintrag["grundlage"] = json.loads(eintrag.pop("profil_json") or "{}")
    except json.JSONDecodeError:
        eintrag["grundlage"] = {}
    return eintrag


def profil_historie(signal_id: int) -> list[dict]:
    init_dossier()
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT signal_id, version, erstellt, modell, aenderungs_grund "
            "FROM dossier_profil WHERE signal_id=? ORDER BY version DESC",
            (signal_id,)).fetchall()
    return [dict(r) for r in rows]


# ── Beobachtungen ─────────────────────────────────────────────────

EINORDNUNGEN = ("KONFORM", "AUFFAELLIG", "STILBRUCH", "KEINE_NEUEN_TRADES")


def beobachtung_speichern(signal_id: int, einordnung: str, text: str,
                          delta_ref: int | None = None,
                          schritt_ref: int | None = None) -> int:
    assert einordnung in EINORDNUNGEN, einordnung
    init_dossier()
    with db._connect() as conn:
        cursor = conn.execute(
            "INSERT INTO dossier_beobachtungen "
            "(signal_id, ts, einordnung, text, delta_ref, schritt_ref) "
            "VALUES (?,?,?,?,?,?)",
            (signal_id, _jetzt(), einordnung, text, delta_ref, schritt_ref))
        return int(cursor.lastrowid or 0)


def beobachtungen_lesen(signal_id: int, limit: int = 50) -> list[dict]:
    init_dossier()
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT id, signal_id, ts, einordnung, text, delta_ref, schritt_ref "
            "FROM dossier_beobachtungen WHERE signal_id=? "
            "ORDER BY id DESC LIMIT ?", (signal_id, max(1, int(limit)))).fetchall()
    return [dict(r) for r in rows]


def stilbruch_historie(signal_id: int, limit: int = 10) -> list[dict]:
    """Alle STILBRUCH-Beobachtungen eines Signals, neueste zuerst.

    Dauerhafte Verknüpfung Signal ↔ Stilbruch ↔ Datum (Nutzer-Wunsch
    22.09.2026): Auch wenn die Ampel später wechselt (z. B. 🟡 → 🟢),
    bleibt hier ablesbar, dass der Betreuer in der Vergangenheit eine
    Abweichung vom eigenen Algo-Profil festgestellt hat.
    """
    init_dossier()
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT ts, text FROM dossier_beobachtungen "
            "WHERE signal_id=? AND einordnung='STILBRUCH' "
            "ORDER BY id DESC LIMIT ?", (signal_id, max(1, int(limit)))).fetchall()
    return [dict(r) for r in rows]


def letzte_beobachtungen(signal_id: int, anzahl: int = 3) -> str:
    """Kurzer Verlaufstext für den Betreuer-Prompt ({letzte_beobachtungen})."""
    eintraege = list(reversed(beobachtungen_lesen(signal_id, limit=anzahl)))
    if not eintraege:
        return "Noch keine Beobachtungen."
    return "\n".join(f"{e['ts']} — {e['einordnung']}: {e['text'][:200]}"
                     for e in eintraege)


# ── Trade-Deltas ──────────────────────────────────────────────────

def delta_speichern(signal_id: int, alt_sha256: str | None, neu_sha256: str,
                    neue_trades: int, delta: dict) -> int:
    init_dossier()
    with db._connect() as conn:
        cursor = conn.execute(
            "INSERT INTO trade_deltas "
            "(signal_id, ts, alt_sha256, neu_sha256, neue_trades, delta_json) "
            "VALUES (?,?,?,?,?,?)",
            (signal_id, _jetzt(), alt_sha256, neu_sha256, int(neue_trades),
             json.dumps(delta, ensure_ascii=False, default=str)))
        return int(cursor.lastrowid or 0)


def deltas_lesen(signal_id: int, limit: int = 20) -> list[dict]:
    init_dossier()
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT id, signal_id, ts, alt_sha256, neu_sha256, neue_trades, "
            "delta_json FROM trade_deltas WHERE signal_id=? "
            "ORDER BY id DESC LIMIT ?", (signal_id, max(1, int(limit)))).fetchall()
    ergebnis = []
    for row in rows:
        eintrag = dict(row)
        try:
            eintrag["delta"] = json.loads(eintrag.pop("delta_json") or "{}")
        except json.JSONDecodeError:
            eintrag["delta"] = {}
        ergebnis.append(eintrag)
    return ergebnis


def _jetzt() -> str:
    from datetime import datetime
    return datetime.now().isoformat(sep=" ", timespec="seconds")
