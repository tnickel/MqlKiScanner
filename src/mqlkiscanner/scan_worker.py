"""Prozessweite Workflow-Koordination, unabhängig von Streamlit-Sitzungen."""
from __future__ import annotations

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


_lock = threading.Lock()
_active: WorkerRun | None = None


def active_run() -> WorkerRun | None:
    with _lock:
        return _active


def start(target: Callable[[], None], *, workflow: dict, control: dict,
          logs: dict, results: list) -> WorkerRun | None:
    """Starte atomar genau einen Worker; None bedeutet bereits belegt.

    Die Registry hält Daten für wiederverbundene Sitzungen. Der Mutex wird
    nur während Start/Freigabe gehalten, niemals während des Workflows.
    """
    global _active
    with _lock:
        if _active is not None:
            return None
        run = WorkerRun(workflow, control, logs, results)

        def execute() -> None:
            global _active
            try:
                target()
            finally:
                with _lock:
                    if _active is run:
                        _active = None

        run.thread = threading.Thread(target=execute, name="mqlkiscanner-workflow", daemon=True)
        _active = run
        try:
            run.thread.start()
        except BaseException:
            _active = None
            raise
        return run
