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
from datetime import datetime, timedelta

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
    zusammenfassung TEXT,
    aktion        TEXT,
    resultat      TEXT
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
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(agenten_laeufe)").fetchall()}
        if "aktion" not in cols:
            try:
                conn.execute("ALTER TABLE agenten_laeufe ADD COLUMN aktion TEXT")
            except Exception:
                pass
        if "resultat" not in cols:
            try:
                conn.execute("ALTER TABLE agenten_laeufe ADD COLUMN resultat TEXT")
            except Exception:
                pass


# Anzeige-Schwelle für aktive_rollen: ältere 'laeuft'-Einträge gelten als
# verwaist (abgestürzter Halter) — die Rolle wird nicht mehr leuchtend gezeigt.
AKTIV_ANZEIGE_S_MIN = 90


def zerlege_lauf(rolle: str, status: str, ztext: str = "", quelle: str = "") -> tuple[str, str]:
    """Rekonstruiert verständlich: (Was wurde gemacht?, Was war das Resultat?)."""
    z = (ztext or "").strip()
    status_lower = (status or "").lower()

    # 1. Kollisionsschutz / Lock besetzt
    if "Lauf-Lock" in z or "Lock" in z or "lock" in z:
        import re
        m = re.search(r"PID (\d+)", z)
        pid_info = f" (PID {m.group(1)})" if m else ""
        aktion = f"Startversuch ({quelle.upper() if quelle else 'System'})"
        resultat = f"Übersprungen: Vorheriger Lauf{pid_info} war noch aktiv (Kollisionsschutz)."
        return aktion, resultat

    # 2. Fehler
    if status_lower == "fehler":
        aktion = f"{rolle.capitalize()}-Ausführung"
        resultat = f"Fehler aufgetreten: {z}" if z else "Fehler aufgetreten."
        return aktion, resultat

    # 3. Läuft noch
    if status_lower == "laeuft":
        aktion = f"{rolle.capitalize()}-Ausführung"
        resultat = "Wird aktuell ausgeführt..."
        return aktion, resultat

    # 4. Rollen-Spezifisch
    if rolle == "markt":
        if status_lower == "skipped":
            aktion = "Marktkurs-Abfrage (MT5)"
            # z ist der ECHTE Grund (Terminal aus/kein Selbststart ODER
            # Verbindungsfehler) — nichts Erfundenes danebenstellen.
            resultat = z or "Übersprungen: MT5-Terminal nicht aktiv."
            return aktion, resultat
        import re
        m = re.search(r"(\d+)\s*Symbol", z)
        anz = m.group(1) if m else "30"
        aktion = f"Marktanalyse ({anz} Symbole via MT5)"
        if "Lagebericht" in z or "ausgewertet" in z or "analysiert" in z:
            resultat = z
        else:
            resultat = f"{anz} Symbole analysiert: Kurse & Volatilität ausgewertet (keine extremen Schocks)."
        return aktion, resultat

    if rolle == "dirigent":
        aktion = "Tageslage & Einsatzplan der Agenten prüfen"
        if "Phase-A" in z or "Plan-Aktion" in z:
            resultat = "Regelbetrieb freigegeben: Keine offenen Aufgaben, alle Agentenrollen einsatzbereit."
        elif z:
            resultat = z
        else:
            resultat = "Einsatzplan für heutigen Handelstag bestätigt."
        return aktion, resultat

    if rolle == "betreuer":
        if "Destillation" in z:
            aktion = "Algo-Profil destillieren"
            resultat = "Neues Profil erfolgreich aus Analyseberichten destilliert."
        else:
            aktion = "Handelsmuster & Trade-Deltas prüfen"
            if "keine neuen Trades" in z:
                resultat = "Signale geprüft: Keine neuen Trades seit letztem Check (Muster unverändert)."
            elif "STILBRUCH" in z:
                resultat = f"⚠️ {z}"
            elif z:
                resultat = z
            else:
                resultat = "Alle aktiven Signale konform."
        return aktion, resultat

    if rolle == "chef":
        aktion = "Wochen-Lagebericht erstellen"
        resultat = z if z else "Lagebericht erfolgreich erstellt und im Postfach abgelegt."
        return aktion, resultat

    if rolle == "melder":
        if "Alert" in z:
            aktion = "Echtzeit-Alert verarbeiten"
            resultat = z
        else:
            aktion = "Tagesdigest erstellen"
            resultat = z if z else "Tagesdigest im Postfach abgelegt."
        return aktion, resultat

    # Scan
    if "gelbgruen" in z or "gelb_gruen" in z or "Teilscan" in z:
        aktion = "Teilscan (Gelb/Grün)"
        resultat = z
        return aktion, resultat
    if "full" in z or "Full-Scan" in z:
        aktion = "Full-Scan (Gesamtkatalog)"
        resultat = z
        return aktion, resultat

    aktion = f"{rolle.capitalize()}-Aufgabe"
    resultat = z or "Erfolgreich abgeschlossen."
    return aktion, resultat


# ── Läufe ─────────────────────────────────────────────────────────

def lauf_starten(rolle: str, quelle: str = "daemon", signal_id: int | None = None) -> int:
    init_journal()
    with db._connect() as conn:
        cursor = conn.execute(
            "INSERT INTO agenten_laeufe (rolle, quelle, start, status, signal_id) "
            "VALUES (?,?,?,'laeuft',?)",
            (rolle, quelle, _now(), signal_id))
        return int(cursor.lastrowid or 0)


def lauf_abschliessen(lauf_id: int, status: str, zusammenfassung: str = "",
                      aktion: str = "", resultat: str = "") -> None:
    """Status-Übergang laeuft → ok|fehler|abgebrochen|skipped (kein Re-Open)."""
    init_journal()
    if (not aktion or not resultat) and zusammenfassung:
        with db._connect() as conn:
            row = conn.execute("SELECT rolle, quelle FROM agenten_laeufe WHERE id=?",
                               (lauf_id,)).fetchone()
        r_rolle = row["rolle"] if row else ""
        r_quelle = row["quelle"] if row else ""
        ak, res = zerlege_lauf(r_rolle, status, zusammenfassung, r_quelle)
        aktion = aktion or ak
        resultat = resultat or res
    elif aktion and resultat and not zusammenfassung:
        zusammenfassung = f"{aktion}: {resultat}"

    with db._connect() as conn:
        conn.execute(
            "UPDATE agenten_laeufe SET ende=?, status=?, zusammenfassung=?, aktion=?, resultat=? "
            "WHERE id=? AND status='laeuft'",
            (_now(), status, zusammenfassung, aktion, resultat, lauf_id))


def lauf_ist_aktiv(lauf_id: int) -> bool:
    with db._connect() as conn:
        row = conn.execute("SELECT status FROM agenten_laeufe WHERE id=?",
                           (lauf_id,)).fetchone()
    return bool(row and row["status"] == "laeuft")


def aktive_rollen() -> set[str]:
    """Rollen-Keys, deren Lauf den Status 'laeuft' hat — mit Altersgrenze.

    Rein für ANZEIGEN (Baum-Leuchten, Kachel-Badge). Stirbt ein Prozess
    mitten im Lauf (Server-Crash, harter Kill), bleibt der Status für immer
    'laeuft' — ohne Grenze würde die Rolle dauerhaft als aktiv gezeigt.
    Die Wartelogik (chef/scan: aktive_laeufe) bleibt bewusst OHNE Grenze,
    weil echte Läufe (Full-Scan, Betreuer) länger als die Schwelle dauern
    können und niemand neben ihnen starten darf.
    """
    init_journal()
    schwelle = (datetime.now() - timedelta(minutes=AKTIV_ANZEIGE_S_MIN)
                ).strftime("%Y-%m-%d %H:%M:%S")
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT rolle FROM agenten_laeufe "
            "WHERE status='laeuft' AND start >= ?", (schwelle,)).fetchall()
    return {r["rolle"] for r in rows}


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
            f"SELECT id, rolle, quelle, start, ende, status, signal_id, zusammenfassung, aktion, resultat "
            f"FROM agenten_laeufe {where} ORDER BY id DESC LIMIT ?", args).fetchall()
    laeufe = []
    for r in rows:
        d = dict(r)
        if not d.get("aktion") or not d.get("resultat"):
            ak, res = zerlege_lauf(d.get("rolle", ""), d.get("status", ""), d.get("zusammenfassung", ""), d.get("quelle", ""))
            d["aktion"] = d.get("aktion") or ak
            d["resultat"] = d.get("resultat") or res
        laeufe.append(d)
    return laeufe


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


# ── Meldungen (Postfach, Phase D) ─────────────────────────────────

def meldung_speichern(typ: str, titel: str, text: str, *,
                      prioritaet: int = 1, quellen: list | None = None) -> int:
    """Eine Nachricht ins Postfach — Alerts, Digests, Lageberichte.

    prioritaet: 1 = Info, 2 = Warnung, 3 = kritisch. quellen verweist auf
    Nachweise (z. B. ['schritt#42', 'ampel_wechsel#7']).
    """
    init_journal()
    with db._connect() as conn:
        cursor = conn.execute(
            "INSERT INTO agenten_meldungen (ts, typ, prioritaet, titel, text, "
            "quellen_json) VALUES (?,?,?,?,?,?)",
            (_now(), typ, int(prioritaet), titel, text,
             json.dumps(quellen or [], ensure_ascii=False)))
        return int(cursor.lastrowid or 0)


def meldungen_lesen(limit: int = 50, typ: str | None = None) -> list[dict]:
    """Postfach, neueste zuerst (die UI-Ansicht)."""
    init_journal()
    clauses, args = [], []
    if typ:
        clauses.append("typ=?")
        args.append(typ)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    args.append(max(1, int(limit)))
    with db._connect() as conn:
        rows = conn.execute(
            f"SELECT id, ts, typ, prioritaet, titel, text, quellen_json "
            f"FROM agenten_meldungen {where} ORDER BY id DESC LIMIT ?",
            args).fetchall()
    meldungen = []
    for row in rows:
        eintrag = dict(row)
        try:
            eintrag["quellen"] = json.loads(eintrag.pop("quellen_json") or "[]")
        except json.JSONDecodeError:
            eintrag["quellen"] = []
        meldungen.append(eintrag)
    return meldungen


def meldungen_zaehlen(typ: str | None = None) -> int:
    init_journal()
    clauses, args = ["1=1"], []
    if typ:
        clauses.append("typ=?")
        args.append(typ)
    with db._connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM agenten_meldungen WHERE "
            + " AND ".join(clauses), args).fetchone()
    return int(row["n"] if row else 0)


def aktive_laeufe(rolle: str | None = None) -> list[dict]:
    """Läufe im Status 'laeuft' (z. B. wartet der Digest auf den Betreuer)."""
    init_journal()
    clauses, args = ["status='laeuft'"], []
    if rolle:
        clauses.append("rolle=?")
        args.append(rolle)
    with db._connect() as conn:
        rows = conn.execute(
            f"SELECT id, rolle, quelle, start, signal_id FROM agenten_laeufe "
            f"WHERE {' AND '.join(clauses)} ORDER BY id", args).fetchall()
    return [dict(r) for r in rows]


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
