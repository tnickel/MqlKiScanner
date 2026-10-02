"""Prozessweite Workflow-Koordination, unabhängig von Streamlit-Sitzungen."""
from __future__ import annotations

import builtins
import threading
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class WorkerRun:
    workflow: dict
    control: dict
    logs: dict
    results: list
    thread: threading.Thread | None = None
    # B3 (Lauf-Review 02.10.): prozessübergreifendes Lauf-Lock — derselbe
    # Schutz, den der autonome Launcher hält (agenten.lock.lauf_lock). Wird
    # beim Start erworben und im Worker-Thread wieder freigegeben.
    lauf_lock_cm: object = None


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
          logs: dict, results: list,
          lock_basis=None) -> WorkerRun | None:
    """Starte atomar genau einen Worker; None bedeutet bereits belegt.

    Die Registry hält Daten für wiederverbundene Sitzungen. Der Mutex wird
    nur während Start/Freigabe gehalten, niemals während des Workflows.

    B3 (Lauf-Review 02.10.): Mit `lock_basis` (z. B. config.DATA_DIR) hält
    der Worker zusätzlich das DATEIbasierte Lauf-Lock des autonomen
    Scanners — vorher schützte die Registry nur innerhalb dieses einen
    Prozesses, ein Daemon-Lauf (oder eine zweite Streamlit-Instanz) konnte
    parallel denselben Datenbestand bearbeiten. Ist das Lock belegt, wirft
    start() eine RuntimeError mit dem Grund; die GUI zeigt sie über den
    bestehenden Fehlerpfad.
    """
    reg = _registry()
    lock = reg["lock"]
    with lock:
        if reg["active"] is not None:
            return None
        lauf_cm = None
        if lock_basis is not None:
            from .agenten import lock as _agenten_lock
            lauf_cm = _agenten_lock.lauf_lock(lock_basis)
            try:
                lauf_cm.__enter__()
            except _agenten_lock.LockBesetzt as exc:
                pid_info = f" (PID {exc.pid})" if getattr(exc, "pid", None) else ""
                raise RuntimeError(
                    "Ein anderer Scan-Lauf ist aktiv (autonomer Daemon oder "
                    f"zweiter Prozess{pid_info}) — gemeinsames Lauf-Lock belegt. "
                    "Diesen Lauf abwarten oder stoppen, dann erneut starten."
                ) from exc
        run = WorkerRun(workflow, control, logs, results)
        run.lauf_lock_cm = lauf_cm

        def execute() -> None:
            try:
                target()
            finally:
                if run.lauf_lock_cm is not None:
                    try:
                        run.lauf_lock_cm.__exit__(None, None, None)
                    except Exception:   # Aufräumen darf den Worker nie hängen lassen
                        pass
                with lock:
                    if reg["active"] is run:
                        reg["active"] = None

        run.thread = threading.Thread(target=execute, name="mqlkiscanner-workflow", daemon=True)
        reg["active"] = run
        try:
            run.thread.start()
        except BaseException:
            reg["active"] = None
            if run.lauf_lock_cm is not None:
                try:
                    run.lauf_lock_cm.__exit__(None, None, None)
                except Exception:
                    pass
            raise
        return run
