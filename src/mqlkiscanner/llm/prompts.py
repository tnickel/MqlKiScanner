# -*- coding: utf-8 -*-
"""Prompt-Vorlagen: Laden, Bearbeiten, Zuruecksetzen (config/prompts/).

Die Vorlagen sind Dateien, damit sie in der GUI per Button angezeigt und
editiert werden koennen. Platzhalter werden von pipeline.py ersetzt:
  Stufe 1: {kandidat_json}, {forensik_json}, {kriterien}
  Stufe 2: {kandidat_json}, {forensik_json}, {stufe1_profil}, {kriterien}
Fehlt eine Datei, wird die eingebettete DEFAULT-Vorlage neu angelegt.
"""
from __future__ import annotations

from pathlib import Path

from ..config import PROMPTS_DIR

PROMPT_FILES = {
    "stufe1_profil": PROMPTS_DIR / "stufe1_profil.md",
    "stufe2_verdict": PROMPTS_DIR / "stufe2_verdict.md",
}

DEFAULT_STUFE1 = """# Stufe 1 — Massen-Profil (GLM Flash)

Du bist ein forensischer Analyst fuer MetaTrader-Signale. Dir liegen NUR
gepruefte Maschinendaten vor: Kandidaten-Kennzahlen (von der MQL5-Seite)
und — falls vorhanden — Forensik-Ergebnisse aus dem Trade-Export. Die
Zahlen wurden von der Engine berechnet; erfinde keine weiteren.

## Kandidat
{kandidat_json}

## Forensik der Engine (leer = noch kein Trade-Export ausgewertet)
{forensik_json}

## Entscheidungs-Kriterien des Nutzers
{kriterien}

## Aufgabe
Schreibe ein kompaktes deutsches Profil (max. 200 Woerter):
1. **Was das System offenbar macht** (Strategie-Hypothese aus den Daten).
2. **Risikobefunde**: Martingale/Grid/Exposure/Stop-Nachweis/Verlustserien —
   mit den konkreten Zahlen. Kein Befund, keine Aussage.
3. **Copy-Eignung**: Slippage-/Kontogroessen-Risiken.
4. **Ein Satz Fazit**: Empfehlung oder Warnung — mit Hauptgrund.

Ton: nuedtern, technisch, keine Anlageberatung, keine Emojis.
Wenn zentrale Forensik fehlt, sage das explizit ("keine positive Einstufung
vor vollstaendiger Forensik").
"""

DEFAULT_STUFE2 = """# Stufe 2 — Verdict fuer Finalisten (GLM stark)

Du bist der leitende Pruefer. Vor dir: ein Kandidat mit vollstaendiger
Forensik (Engine) und dem Stufe-1-Profil (Flash-Modell). Deine Aufgabe ist
ein verbindliches Urteil mit Widerspruchscheck.

## Kandidat
{kandidat_json}

## Forensik der Engine (maschinell berechnet, massgeblich)
{forensik_json}

## Stufe-1-Profil (zur Kritik, nicht zur Uebernahme)
{stufe1_profil}

## Bindende Kriterien des Nutzers
{kriterien}

## Aufgabe
1. **Widerspruchscheck**: Widerspricht das Stufe-1-Profil den Forensik-
   Zahlen? Streiche nicht-belegbare Behauptungen.
2. **Kriterien-Check**: Schranke EQ-DD > 30 % = AUTOMATISCHE ABLEHNUNG.
   Ertrag < 5 %/Monat = Ablehnung. Ohne Stop-Nachweis = keine Empfehlung
   ("bewiesen" heisst nur Orderbuch oder klare Cluster-Signatur).
3. **Urteil**: genau eines von EMPFEHLUNG | WATCHLIST | ABLEHNUNG.
4. **Risiko-Score 1-10** (hoch = riskant) mit einzeiliger Begruendung je
   Dimension: Drawdown, Struktur (SL/Grid/Martingale), Exposure, Copy,
   Track-Record.
5. **Bedingungen** fuer Wiederaufnahme bei Ablehnung.

Format (Markdown, max. 250 Woerter):
**Urteil:** ... | **Score:** n/10
**Begruendung:** ...
**Kritische Punkte:** - ...
**Bedingungen:** - ... (nur bei ABLEHNUNG/WATCHLIST)
Nuedtern, keine Anlageberatung. Zahlen nur aus den gelieferten Daten.
"""


def _write_default(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


DEFAULTS = {
    "stufe1_profil": DEFAULT_STUFE1,
    "stufe2_verdict": DEFAULT_STUFE2,
}


def load_prompt(key: str) -> str:
    """Aktuelle Vorlage; legt die Default-Datei an, wenn sie fehlt."""
    path = PROMPT_FILES[key]
    if not path.exists():
        _write_default(path, DEFAULTS[key])
    return path.read_text(encoding="utf-8")


def save_prompt(key: str, text: str) -> None:
    PROMPT_FILES[key].write_text(text, encoding="utf-8")


def reset_prompt(key: str) -> None:
    _write_default(PROMPT_FILES[key], DEFAULTS[key])


def prompt_is_modified(key: str) -> bool:
    return load_prompt(key).strip() != DEFAULTS[key].strip()
