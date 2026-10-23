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


_SCHEMA = """
CREATE TABLE IF NOT EXISTS dossier_profil (
    signal_ref   INT NOT NULL REFERENCES signal_identitaeten(signal_ref),
    version     INTEGER NOT NULL,
    erstellt    TEXT NOT NULL,
    modell      TEXT,
    profil_json TEXT NOT NULL,
    profil_text TEXT NOT NULL,
    aenderungs_grund TEXT,
    PRIMARY KEY (signal_ref, version)
);
CREATE TABLE IF NOT EXISTS dossier_beobachtungen (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_ref   INT NOT NULL REFERENCES signal_identitaeten(signal_ref),
    ts          TEXT NOT NULL,
    einordnung  TEXT NOT NULL,
    text        TEXT NOT NULL,
    delta_ref   INTEGER,
    schritt_ref INTEGER
);
CREATE INDEX IF NOT EXISTS idx_dossier_beob_ts
    ON dossier_beobachtungen(signal_ref, id DESC);
CREATE TABLE IF NOT EXISTS trade_deltas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_ref   INT NOT NULL REFERENCES signal_identitaeten(signal_ref),
    ts          TEXT NOT NULL,
    alt_sha256  TEXT,
    neu_sha256  TEXT NOT NULL,
    neue_trades INTEGER NOT NULL,
    delta_json  TEXT
);
"""


def init_dossier() -> None:
    db.init_db()
    with db._connect() as conn:
        conn.executescript(_SCHEMA)


# ── Algo-Profil ───────────────────────────────────────────────────

def profil_speichern(signal_id: int, profil_text: str, modell: str,
                     grundlage: dict, aenderungs_grund: str = "", *, quelle=None, signal_ref=None) -> int:
    """Neue Profil-VERSION anlegen (nie überschreiben)."""
    init_dossier()
    with db._connect() as conn:
        identity = db._write_identity(conn, signal_id, quelle=quelle, signal_ref=signal_ref)
        signal_ref = identity.signal_ref
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS v FROM dossier_profil "
            "WHERE signal_ref=?", (signal_ref,)).fetchone()
        version = int(row["v"]) + 1 if row else 1
        conn.execute(
            "INSERT INTO dossier_profil (signal_ref, version, erstellt, modell, "
            "profil_json, profil_text, aenderungs_grund) VALUES (?,?,?,?,?,?,?)",
            (signal_ref, version, _jetzt(), modell,
             json.dumps(grundlage, ensure_ascii=False), profil_text,
             aenderungs_grund or "Erststellung"))
        return version



def profil_lesen(signal_id: int, *, quelle=None, signal_ref=None) -> dict | None:
    """Aktuellste Profil-Version (oder None)."""
    identity = db.resolve_identity(signal_id, quelle=quelle, signal_ref=signal_ref)
    if identity is None:
        return None
    signal_ref = identity.signal_ref
    init_dossier()
    with db._connect() as conn:
        row = conn.execute(
            "SELECT signal_ref, version, erstellt, modell, profil_json, "
            "profil_text, aenderungs_grund FROM dossier_profil "
            "WHERE signal_ref=? ORDER BY version DESC LIMIT 1",
            (signal_ref,)).fetchone()
    if row is None:
        return None
    eintrag = {**dict(row), **db._identity_fields(identity)}
    try:
        eintrag["grundlage"] = json.loads(eintrag.pop("profil_json") or "{}")
    except json.JSONDecodeError:
        eintrag["grundlage"] = {}
    return eintrag



def profil_historie(signal_id: int, *, quelle=None, signal_ref=None) -> list[dict]:
    identity = db.resolve_identity(signal_id, quelle=quelle, signal_ref=signal_ref)
    if identity is None:
        return []
    signal_ref = identity.signal_ref
    init_dossier()
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT signal_ref, version, erstellt, modell, aenderungs_grund "
            "FROM dossier_profil WHERE signal_ref=? ORDER BY version DESC",
            (signal_ref,)).fetchall()
    return [{**dict(r), **db._identity_fields(identity)} for r in rows]



# ── Beobachtungen ─────────────────────────────────────────────────

# F-6 (Review 29.09.): NICHT_GEPRUEFT = Betriebsstoerung (Key/Budget/API),
# keine Handelsauffaelligkeit —keine Bewertung des Handelns.
EINORDNUNGEN = ("KONFORM", "AUFFAELLIG", "STILBRUCH", "KEINE_NEUEN_TRADES",
                "NICHT_GEPRUEFT")


def beobachtung_speichern(signal_id: int, einordnung: str, text: str,
                          delta_ref: int | None = None,
                          schritt_ref: int | None = None, *, quelle=None, signal_ref=None) -> int:
    assert einordnung in EINORDNUNGEN, einordnung
    init_dossier()
    with db._connect() as conn:
        identity = db._write_identity(conn, signal_id, quelle=quelle, signal_ref=signal_ref)
        signal_ref = identity.signal_ref
        _validate_observation_links(conn, signal_ref, delta_ref, schritt_ref)
        cursor = conn.execute(
            "INSERT INTO dossier_beobachtungen "
            "(signal_ref, ts, einordnung, text, delta_ref, schritt_ref) "
            "VALUES (?,?,?,?,?,?)",
            (signal_ref, _jetzt(), einordnung, text, delta_ref, schritt_ref))
        return int(cursor.lastrowid or 0)



def beobachtungen_lesen(signal_id: int, limit: int = 50, *, quelle=None, signal_ref=None) -> list[dict]:
    identity = db.resolve_identity(signal_id, quelle=quelle, signal_ref=signal_ref)
    if identity is None:
        return []
    signal_ref = identity.signal_ref
    init_dossier()
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT id, signal_ref, ts, einordnung, text, delta_ref, schritt_ref "
            "FROM dossier_beobachtungen WHERE signal_ref=? "
            "ORDER BY id DESC LIMIT ?", (signal_ref, max(1, int(limit)))).fetchall()
    return [{**dict(r), **db._identity_fields(identity)} for r in rows]



def stilbruch_historie(signal_id: int, limit: int = 10, *, quelle=None, signal_ref=None) -> list[dict]:
    """Alle STILBRUCH-Beobachtungen eines Signals, neueste zuerst.

    Dauerhafte Verknüpfung Signal ↔ Stilbruch ↔ Datum (Nutzer-Wunsch
    22.09.2026): Auch wenn die Ampel später wechselt (z. B. 🟡 → 🟢),
    bleibt hier ablesbar, dass der Betreuer in der Vergangenheit eine
    Abweichung vom eigenen Algo-Profil festgestellt hat.
    """
    identity = db.resolve_identity(signal_id, quelle=quelle, signal_ref=signal_ref)
    if identity is None:
        return []
    signal_ref = identity.signal_ref
    init_dossier()
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT ts, text FROM dossier_beobachtungen "
            "WHERE signal_ref=? AND einordnung='STILBRUCH' "
            "ORDER BY id DESC LIMIT ?", (signal_ref, max(1, int(limit)))).fetchall()
    return [{**dict(r), **db._identity_fields(identity)} for r in rows]



def letzte_beobachtungen(signal_id: int, anzahl: int = 3, *, quelle=None, signal_ref=None) -> str:
    """Kurzer Verlaufstext für den Betreuer-Prompt ({letzte_beobachtungen})."""
    eintraege = list(reversed(beobachtungen_lesen(signal_id, limit=anzahl, quelle=quelle, signal_ref=signal_ref)))
    if not eintraege:
        return "Noch keine Beobachtungen."
    return "\n".join(f"{e['ts']} — {e['einordnung']}: {e['text'][:200]}"
                     for e in eintraege)



# ── Trade-Deltas ──────────────────────────────────────────────────

def delta_speichern(signal_id: int, alt_sha256: str | None, neu_sha256: str,
                    neue_trades: int, delta: dict, *, quelle=None, signal_ref=None) -> int:
    init_dossier()
    with db._connect() as conn:
        identity = db._write_identity(conn, signal_id, quelle=quelle, signal_ref=signal_ref)
        signal_ref = identity.signal_ref
        cursor = conn.execute(
            "INSERT INTO trade_deltas "
            "(signal_ref, ts, alt_sha256, neu_sha256, neue_trades, delta_json) "
            "VALUES (?,?,?,?,?,?)",
            (signal_ref, _jetzt(), alt_sha256, neu_sha256, int(neue_trades),
             json.dumps(delta, ensure_ascii=False, default=str)))
        return int(cursor.lastrowid or 0)



def deltas_lesen(signal_id: int, limit: int = 20, *, quelle=None, signal_ref=None) -> list[dict]:
    identity = db.resolve_identity(signal_id, quelle=quelle, signal_ref=signal_ref)
    if identity is None:
        return []
    signal_ref = identity.signal_ref
    init_dossier()
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT id, signal_ref, ts, alt_sha256, neu_sha256, neue_trades, "
            "delta_json FROM trade_deltas WHERE signal_ref=? "
            "ORDER BY id DESC LIMIT ?", (signal_ref, max(1, int(limit)))).fetchall()
    ergebnis = []
    for row in rows:
        eintrag = {**dict(row), **db._identity_fields(identity)}
        try:
            eintrag["delta"] = json.loads(eintrag.pop("delta_json") or "{}")
        except json.JSONDecodeError:
            eintrag["delta"] = {}
        ergebnis.append(eintrag)
    return ergebnis



def _jetzt() -> str:
    from datetime import datetime
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _validate_observation_links(conn, signal_ref, delta_ref, schritt_ref):
    if delta_ref is not None:
        row=conn.execute("SELECT signal_ref FROM trade_deltas WHERE id=?",(delta_ref,)).fetchone()
        if row is None or row[0] != signal_ref:
            raise db.IdentityError("Trade-Delta gehoert nicht zur Dossier-Identitaet")
    if schritt_ref is not None:
        row=conn.execute("SELECT l.signal_ref FROM agenten_schritte s JOIN agenten_laeufe l "
                         "ON l.id=s.lauf_id WHERE s.id=?",(schritt_ref,)).fetchone()
        if row is None or (row[0] is not None and row[0] != signal_ref):
            raise db.IdentityError("Journal-Schritt gehoert nicht zur Dossier-Identitaet")
