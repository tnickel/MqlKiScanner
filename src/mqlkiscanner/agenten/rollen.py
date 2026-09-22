# -*- coding: utf-8 -*-
"""Rollen-Registry des Agentenbetriebs (doc/19_agentenbetrieb-bauplan.md).

Fünf Rollen mit festen Aufträgen, Takten und Standard-Modellen. Nutzer-Vorgabe
vom 22.09.2026: GLM-5.3 (NICHT Flash) ist Standard für ALLE Rollen; das
Flash-Modell bleibt pro Rolle als Kostenschraube wählbar.

Dieses Modul bewusst frei von Imports aus dem Paket-Inneren (kein config-,
kein db-Import): config.py zieht die Rollen-Defaults hierher, damit
app_settings.json und Rollen-Registry nie auseinanderlaufen.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rolle:
    key: str            # Settings-Präfix: agenten_{key}_aktiv / _modell / _max_tokens
    name: str           # Anzeigename
    icon: str           # Streamlit-Material-Icon (Form ':material/name:')
    beschreibung: str   # Klartext-Auftrag für die Rollenkarte
    phase: str          # Ausbaustufe (doc/19), in der die Rolle aktiv wird
    takt: str           # Klartext-Takt
    max_tokens: int     # Default-Ausgabelimit je Modellaufruf


ROLLEN: tuple[Rolle, ...] = (
    Rolle(
        "dirigent", "Dirigent", ":material/tune:",
        "Plant und steuert den Betrieb: Budget, Sperren, Markt-Kalender, "
        "Rollen wecken und Läufe anstoßen. Entscheidungen nur innerhalb "
        "einer im Code validierten Aktions-Whitelist.",
        "A", "täglich (werktags)", 8192,
    ),
    Rolle(
        "markt", "Marktbeobachter", ":material/query_stats:",
        "Holt Kursdaten aus dem MetaTrader (offizielles Python-Paket, nur "
        "lesend); Code berechnet Kennzahlen, das LLM fasst die Marktlage.",
        "C", "täglich (werktags)", 4096,
    ),
    Rolle(
        "betreuer", "Signal-Betreuer", ":material/manage_search:",
        "Prüft je Kandidat das Trade-Delta gegen das Algo-Profil im Dossier "
        "und erkennt Stilbrüche.",
        "B", "täglich (werktags)", 8192,
    ),
    Rolle(
        "chef", "Chefermittler", ":material/fact_check:",
        "Synthese über alle Dossiers, Marktkontext und Ampel-Wechsel: "
        "Wochen-Lagebericht mit Empfehlungen — nie eine Neubewertung.",
        "E", "wöchentlich (so) + monatlich", 16384,
    ),
    Rolle(
        "melder", "Melder", ":material/report:",
        "Verdichtet das Agenten-Journal: sofortige Alerts bei Ampelwechsel "
        "und Stilbruch, sonst Tagesdigest — nur ins Postfach der App.",
        "D", "bei Ereignis + täglich", 4096,
    ),
)

ROLLEN_NACH_KEY: dict[str, Rolle] = {r.key: r for r in ROLLEN}

# Standard-Modell JE Rolle (Nutzer-Vorgabe 22.09.2026: glm-5.3, nicht Flash).
STANDARD_MODELL = "glm-5.3"

# Auswahl im Admin-Bereich; Freitext erlaubt beliebige OpenAI-kompatible Modelle.
MODELL_AUSWAHL = ("glm-5.3", "glm-5.3-flash")

# Wie weit der Agentenbetrieb umgesetzt ist (doc/19 Phasenplan).
# A: Fundament/Dirigent · B: Dossiers/Betreuer · C: Marktdaten ·
# D: Melder/Postfach (V1-Attach-Test des Terminals mit dem Nutzer bleibt
# offen, bis es läuft). Die UI zeigt Rollen über dieser Stufe als 'geplant'.
AKTUELLE_PHASE = "D"


def rollen_defaults() -> dict:
    """Settings-Defaults für alle Rollen (flache Schlüssel wie config.py)."""
    defaults: dict = {}
    for r in ROLLEN:
        defaults[f"agenten_{r.key}_aktiv"] = True
        defaults[f"agenten_{r.key}_modell"] = STANDARD_MODELL
        defaults[f"agenten_{r.key}_max_tokens"] = r.max_tokens
    return defaults


def phase_aktiv(rolle: Rolle, phase: str) -> bool:
    """Ist die Rolle in der erreichten Ausbaustufe bereits ausführbar?

    Phasen-Reihenfolge A < B < C < D < E (doc/19, Abschnitt 13). Die UI zeigt
    noch nicht erreichte Rollen als 'geplant' — konfigurierbar, aber ohne
    Lauflogik.
    """
    reihenfolge = ["A", "B", "C", "D", "E"]
    return reihenfolge.index(rolle.phase) <= reihenfolge.index(phase)
