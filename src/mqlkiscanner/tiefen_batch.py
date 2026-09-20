# -*- coding: utf-8 -*-
"""Batch-Erweiterte-KI-Analyse: alle Signale nacheinander im Hintergrund.

Der Nutzer startet per Button auf der Ergebnisseite einen Lauf ueber ALLE
Signale der gewählten Quelle. Regeln:
- **Skip:** Signal hat bereits eine Tiefenanalyse in der DB (frisch je
  Iteration geprueft) → wird uebersprungen. Der Lauf ist dadurch
  fortsetzbar: Stop/Abbruch/App-Ende kosten nichts, ein neuer Start
  macht dort weiter.
- Fehler je Signal (z. B. kein Trade-Export) werden gezaehlt und der
  Lauf laeuft weiter.
- Läuft in einem Daemon-Thread, Register in builtins (gegen Streamlit-
  Modul-Reloads, gleiche Technik wie scan_worker). Jede Analyse schreibt
  sich sofort selbst in die DB — Fortschritt geht nie verloren.

Grundregel bleibt: Die Batch-Analyse bewertet NICHT neu — Ampeln,
Urteile, Scores bleiben unberuehrt.
"""
from __future__ import annotations

import builtins
import threading
from datetime import datetime
from typing import Callable

from . import config, db, secrets_store
from .llm_runner import run_tiefenanalyse_einzeln

_BATCH_ATTR = "_mqlkiscanner_tiefen_batch"


def aktiver_batch() -> dict | None:
    """Laufenden Batch-Zustand oder None (Register liegt in builtins)."""
    return getattr(builtins, _BATCH_ATTR, None)


def batch_laeuft() -> bool:
    batch = aktiver_batch()
    thread = (batch or {}).get("thread")
    return bool(thread and thread.is_alive())


def batch_starten(ziele: list, settings: dict | None = None,
                  log: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """Batch ueber die gegebenen ScanResults starten.

    Rueckgabe (gestartet?, Meldung). Ablehnung, wenn bereits ein Batch
    oder ein Scan-Workflow laeuft, kein GLM-Key gesetzt ist oder keine
    Ziele uebrig bleiben.
    """
    if batch_laeuft():
        return False, "Es läuft bereits eine Batch-Erweiterte-KI-Analyse."
    if not secrets_store.get_secret("glm_api_key"):
        return False, "Kein GLM-Key hinterlegt (Admin-Bereich → Zugänge)."
    if not ziele:
        return False, "Keine geeigneten Signale (mit Trade-Daten) in der Quelle."
    einstellungen = {**config.load_settings(), **(settings or {})}

    zustand = {
        "total": len(ziele),
        "done": 0,
        "aktuell": "",
        "uebersprungen": 0,
        "fehler": 0,
        "fehler_liste": [],
        "fertig": False,
        "abgebrochen": False,
        "start": datetime.now(),
        "ende": None,
        "stop": False,
        "thread": None,
    }

    def worker() -> None:
        for i, result in enumerate(ziele, 1):
            if zustand["stop"]:
                zustand["abgebrochen"] = True
                break
            # Skip frisch aus der DB: fertige Tiefenanalysen kosten nichts.
            if db.get_latest_analysis(result.id, "tiefenanalyse"):
                zustand["uebersprungen"] += 1
                zustand["done"] = i
                continue
            zustand["aktuell"] = f"{result.name or 'Unbenannt'} (#{result.id})"
            try:
                run_tiefenanalyse_einzeln(result, settings=einstellungen, log=None)
            except Exception as exc:  # Einzelfehler: weiter mit dem naechsten
                zustand["fehler"] += 1
                zustand["fehler_liste"].append(
                    f"{result.name or 'Unbenannt'} (#{result.id}): "
                    f"{type(exc).__name__}: {exc}")
            zustand["done"] = i
        zustand["fertig"] = True
        zustand["ende"] = datetime.now()

    thread = threading.Thread(target=worker, daemon=True, name="tiefen-batch")
    zustand["thread"] = thread
    setattr(builtins, _BATCH_ATTR, zustand)
    if log:
        log(f"Batch-Erweiterte-KI-Analyse gestartet: {len(ziele)} Strategien "
            "(vorhandene werden übersprungen).")
    thread.start()
    return True, ""


def batch_stoppen() -> None:
    """Stop anfordern: laufende Analyse endet sauber, Loop bricht danach ab."""
    batch = aktiver_batch()
    if batch is not None:
        batch["stop"] = True
