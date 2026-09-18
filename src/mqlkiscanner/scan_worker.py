"""Prozessweite Workflow-Koordination, unabhängig von Streamlit-Sitzungen."""
from __future__ import annotations

import builtins
import threading
from dataclasses import dataclass
from typing import Callable


@dataclass
class WorkerRun:
    workflow: dict
    control: dict
    logs: dict
    results: list
    thread: threading.Thread | None = None


# Das Register liegt absichtlich in builtins statt im Modul: Streamlit lädt
# lokale Module neu, wenn sich Dateien ändern — mitten in einem Lauf würde ein
# frisches Modul sonst ein leeres Register sehen und einen zweiten Lauf
# zulassen, während der alte Thread noch arbeitet. builtins gehört dem
# Prozess, nicht der Modulversion.
_REGISTRY_ATTR = "_mqlkiscanner_worker_registry"


def _registry() -> dict:
    reg = getattr(builtins, _REGISTRY_ATTR, None)
    if reg is None:
        reg = {"active": None, "lock": threading.Lock()}
        setattr(builtins, _REGISTRY_ATTR, reg)
    return reg


def active_run() -> WorkerRun | None:
    return _registry()["active"]


def start(target: Callable[[], None], *, workflow: dict, control: dict,
          logs: dict, results: list) -> WorkerRun | None:
    """Starte atomar genau einen Worker; None bedeutet bereits belegt.

    Die Registry hält Daten für wiederverbundene Sitzungen. Der Mutex wird
    nur während Start/Freigabe gehalten, niemals während des Workflows.
    """
    reg = _registry()
    lock = reg["lock"]
    with lock:
        if reg["active"] is not None:
            return None
        run = WorkerRun(workflow, control, logs, results)

        def execute() -> None:
            try:
                target()
            finally:
                with lock:
                    if reg["active"] is run:
                        reg["active"] = None

        run.thread = threading.Thread(target=execute, name="mqlkiscanner-workflow", daemon=True)
        reg["active"] = run
        try:
            run.thread.start()
        except BaseException:
            reg["active"] = None
            raise
        return run
