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
from .agenten import lock
from .llm_runner import run_tiefenanalyse_einzeln
from .llm import prompts as llm_prompts
from .signal_identity import identity_key

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
    """Serialize session starts, then reserve the shared workflow lock."""
    start_lock = builtins.__dict__.setdefault("_mqlkiscanner_tiefen_start_lock", threading.Lock())
    with start_lock:
        return _batch_starten(ziele, settings, log)


def _batch_starten(ziele: list, settings: dict | None = None,
                   log: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """Batch ueber die gegebenen ScanResults starten.

    Rueckgabe (gestartet?, Meldung). Ablehnung, wenn bereits ein Batch
    oder ein Scan-Workflow laeuft, kein GLM-Key gesetzt ist oder keine
    Ziele uebrig bleiben.
    """
    if batch_laeuft():
        return False, "Es läuft bereits eine Batch-Erweiterte-KI-Analyse."
    fehlend = llm_prompts.fehlende_vorlagen()
    if fehlend:
        pfade = ", ".join(f"config/prompts/{k}.md" for k in fehlend)
        return False, ("Berichtsvorlage(n) fehlen oder sind leer: "
                       + pfade + " — im Admin unter Berichtsvorlagen "
                       "per Zurücksetzen wiederherstellen.")
    if not secrets_store.get_secret("glm_api_key"):
        return False, "Kein GLM-Key hinterlegt (Admin-Bereich → Zugänge)."
    if not ziele:
        return False, "Keine geeigneten Signale (mit Trade-Daten) in der Quelle."
    ziele = list({identity_key(result): result for result in ziele}.values())
    einstellungen = {**config.load_settings(), **(settings or {})}
    workflow_lock = lock.lauf_lock(config.DATA_DIR)
    try:
        workflow_lock.__enter__()
    except lock.LockBesetzt as exc:
        return False, str(exc)

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

    def process_targets() -> None:
        for i, result in enumerate(ziele, 1):
            if zustand["stop"]:
                zustand["abgebrochen"] = True
                break
            # Skip frisch aus der DB: fertige Tiefenanalysen kosten nichts.
            # B10 (Lauf-Review 02.10.): NUR bei AKTUELLER Datenbasis — alte
            # Texte neben geändertem Befund werden neu erstellt statt still
            # weiterverwendet (47 Bestandsfälle mit veralteter Basis).
            from .pipeline import report_basis_for as _basis_fuer
            _basis = _basis_fuer(result, einstellungen)
            if db.get_latest_analysis(result.id, "tiefenanalyse",
                                      basis=_basis, quelle=identity_key(result)[0]):
                zustand["uebersprungen"] += 1
                zustand["done"] = i
                continue
            zustand["aktuell"] = f"{result.name or 'Unbenannt'} ({identity_key(result)[0]}:{result.id})"
            try:
                run_tiefenanalyse_einzeln(result, settings=einstellungen, log=None)
            except Exception as exc:  # Einzelfehler: weiter mit dem naechsten
                zustand["fehler"] += 1
                zustand["fehler_liste"].append(
                    f"{result.name or 'Unbenannt'} ({identity_key(result)[0]}:{result.id}): "
                    f"{type(exc).__name__}: {exc}")
            zustand["done"] = i
        zustand["fertig"] = True
        zustand["ende"] = datetime.now()

    def worker() -> None:
        try:
            process_targets()
        except Exception as exc:
            zustand["abgebrochen"] = True
            zustand["fehler"] += 1
            zustand["fehler_liste"].append(f"{type(exc).__name__}: {exc}")
        finally:
            zustand["fertig"] = True
            zustand["ende"] = datetime.now()
            workflow_lock.__exit__(None, None, None)

    thread = threading.Thread(target=worker, daemon=True, name="tiefen-batch")
    zustand["thread"] = thread
    setattr(builtins, _BATCH_ATTR, zustand)
    try:
        if log:
            log(f"Batch-Erweiterte-KI-Analyse gestartet: {len(ziele)} Strategien "
                "(vorhandene werden übersprungen).")
        thread.start()
    except Exception:
        workflow_lock.__exit__(None, None, None)
        delattr(builtins, _BATCH_ATTR)
        raise
    return True, ""


def batch_stoppen() -> None:
    """Stop anfordern: laufende Analyse endet sauber, Loop bricht danach ab."""
    batch = aktiver_batch()
    if batch is not None:
        batch["stop"] = True
