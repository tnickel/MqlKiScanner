# -*- coding: utf-8 -*-
"""Ampel-Verlauf: Farb-Chronik je Signal und protokollierte Wechsel.

Nutzer-Anforderung: Farben werden bei jedem Scan aufgezeichnet; tritt ein
Wechsel ein (🟡→🟢, 🟢→🟡, …), muss das SPEZIELL protokolliert und in einer
Wechselliste sichtbar sein — inklusive Begründung, WELCHES Kriterium gekippt
ist und mit welchen Werten.

Aufbau:
- ampel_verlauf (DB): append-only Chronik — je erfolgreich geprüftem Lauf
  ein Eintrag mit Ampel, Score, Urteil und der 8-Kriterien-Matrix als
  Audit-Snapshot. Kein Reimport alter Läufe: Die Chronik beginnt mit dem
  ersten Eintrag, den dieses Modul schreibt.
- ampel_wechsel (DB): jedes Ereignis, bei dem sich die Farbe ODER mindestens
  eines der 8 Kriterien geändert hat (Kriterium-Kippen ohne Farbwechsel ist
  ein Frühindikator und wird deshalb ebenfalls protokolliert).

Bewertet wird ausschließlich die Engine (Code) — das LLM ändert nie eine
Ampel. Damit ist die Wechsel-Erkennung deterministisch: zwei Zustände
vergleichen, kein Modell im Spiel.

Fehlgeschlagene Prüfungen (result.fehler gesetzt, z. B. transienter
Export-Fehler) schreiben KEINEN Chronik-Eintrag: Der letzte gültige Stand
bleibt Vergleichsbasis, sonst würde ⚪-Flackern die Wechselliste zumüllen.
"""
from __future__ import annotations

from datetime import datetime

from . import db
from .ampel_matrix import KRITERIEN, matrix_payload

# Anzeigereihenfolge für die Einordnung eines Farbwechsels. ⚪ ist bewusst
# keine Stufe "unter rot": ohne Daten gibt es kein Urteil — der Übergang
# von einer Entscheidung zu ⚪ ist ein Datenverlust, kein Entlastungsbeweis.
_VERBESSERUNG = "verbesserung"
_VERSCHLECHTERUNG = "verschlechterung"
_HINWEIS = "hinweis"

_TITEL = {k.key: k.titel for k in KRITERIEN}


def _richtung(ampel_alt: str | None, ampel_neu: str) -> str:
    """Einordnung des Farbwechsels für die Anzeige (Verbesserung/Schlechter/Hinweis)."""
    if ampel_alt is None or ampel_alt == ampel_neu:
        return _HINWEIS
    if ampel_alt == "⚪":
        # Ohne Urteil zu einer Entscheidung: bei grün eine echte Verbesserung,
        # bei hart rot eine neu erkannte Ablehnung, gelb bleibt Einordnung.
        if ampel_neu == "🟢":
            return _VERBESSERUNG
        if ampel_neu in ("🔴", "⛔"):
            return _VERSCHLECHTERUNG
        return _HINWEIS
    if ampel_neu == "⚪":
        # Entscheidung fiel weg (Datenlage verloren) — Warnung, keine Entlastung.
        return _VERSCHLECHTERUNG
    rang = {"⛔": 0, "🔴": 0, "🟡": 1, "🟢": 2}
    if rang.get(ampel_neu, 1) > rang.get(ampel_alt, 1):
        return _VERBESSERUNG
    if rang.get(ampel_neu, 1) < rang.get(ampel_alt, 1):
        return _VERSCHLECHTERUNG
    return _HINWEIS


def _diff_matrix(matrix_alt: dict, matrix_neu: dict) -> list[dict]:
    """Jedes gekippte Kriterium mit alt/neu-Zustand und neuer Begründung.

    matrix_alt/matrix_neu sind matrix_payload-Snapshots:
    {"grenzen": {...}, "kriterien": {key: {ampel, kurz, detail}}}.
    Kriterien, die erst im neuen Stand existieren, zählen als neu bewertet.
    """
    kriterien_alt = (matrix_alt or {}).get("kriterien") or {}
    kriterien_neu = (matrix_neu or {}).get("kriterien") or {}
    gruende: list[dict] = []
    for key, zelle_neu in kriterien_neu.items():
        zelle_alt = kriterien_alt.get(key)
        if zelle_alt is None:
            continue  # Erstfassung ohne Vorgänger ist kein Wechsel.
        if zelle_alt.get("ampel") == zelle_neu.get("ampel"):
            continue
        gruende.append({
            "kriterium": key,
            "titel": _TITEL.get(key, key),
            "ampel_alt": zelle_alt.get("ampel"),
            "ampel_neu": zelle_neu.get("ampel"),
            "kurz_alt": zelle_alt.get("kurz"),
            "kurz_neu": zelle_neu.get("kurz"),
            "detail": zelle_neu.get("detail"),
        })
    return gruende


def wechsel_kurztext(ereignis: dict) -> str:
    """Eine kompakte Protokollzeile für Logs („#id name: 🟡 → 🟢 · Gründe …")."""
    pfeil = (f"{ereignis.get('ampel_alt') or '—'} → {ereignis.get('ampel_neu')}"
             if ereignis.get("farbwechsel") else "Kriterium gekippt")
    krit = "; ".join(f"{g.get('titel')}: {g.get('ampel_alt')}→{g.get('ampel_neu')} "
                     f"({g.get('kurz_alt')} → {g.get('kurz_neu')})"
                     for g in ereignis.get("gruende", []))
    return f"#{ereignis.get('signal_id')} {ereignis.get('name') or ''}: {pfeil}" \
           + (f" · {krit}" if krit else "")


def erfasse_bewertung(result, settings: dict, quelle: str = "full") -> dict | None:
    """Chronik-Eintrag schreiben und Wechsel gegen den Vorgänger prüfen.

    Voraussetzung: der Scan wurde persistiert UND ohne Fehler abgeschlossen
    (Aufrufer prüft persisted_this_run; fehlerhafte Läufe rufen gar nicht auf).
    Rückgabe: Wechsel-Ereignis (dict) oder None, wenn kein Vorgänger existiert
    bzw. weder Farbe noch ein Kriterium gekippt ist.
    """
    if result.fehler:
        return None
    db.init_db()
    # Vorgänger VOR dem eigenen Schreiben lesen — get_last_ampel_verlauf
    # liefert sonst den eben geschriebenen Eintrag zurück.
    alt = db.get_last_ampel_verlauf(result.id)
    ts = datetime.now().isoformat(sep=" ", timespec="seconds")
    matrix = matrix_payload(result, settings)
    db.store_ampel_verlauf(result.id, ts, quelle, result.ampel, result.score,
                           result.urteil or "", matrix)
    if alt is None:
        return None  # Erstfassung: Chronik beginnt, noch kein Vergleich.
    gruende = _diff_matrix(alt.get("matrix") or {}, matrix)
    farbwechsel = bool(alt.get("ampel") != result.ampel)
    if not farbwechsel and not gruende:
        return None
    ereignis = {
        "signal_id": result.id,
        "name": result.name,
        "ts": ts,
        "quelle": quelle,
        "ampel_alt": alt.get("ampel"),
        "ampel_neu": result.ampel,
        "farbwechsel": farbwechsel,
        "richtung": _richtung(alt.get("ampel"), result.ampel),
        "score_alt": alt.get("score"),
        "score_neu": result.score,
        "urteil_neu": result.urteil or "",
        "gruende": gruende,
    }
    db.store_ampel_wechsel(result.id, ts, quelle, alt.get("ampel"), result.ampel,
                           farbwechsel, ereignis["richtung"], gruende,
                           name=result.name or "")
    return ereignis
