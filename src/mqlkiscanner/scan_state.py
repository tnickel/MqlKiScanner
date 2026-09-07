"""Gemeinsame Worker-Übernahme für Scan- und Ergebnisseite ohne UI-Aufrufe."""
from . import scan_worker


def attach_worker(state, run: scan_worker.WorkerRun) -> None:
    state["scan_thread"] = run.thread
    state["scan_workflow"] = run.workflow
    state["scan_control"] = run.control
    state["scan_logs"] = run.logs
    state["scan_results"] = run.results
    state["scan_running"] = run.workflow.get("mode")
    # Jeder Worker überträgt seinen vollständigen Eingabestand. Eine leere
    # Liste ist eine Invalidierung, keine Aufforderung alte Werte zu behalten.
    state["scan_signals"] = run.control.get("signals") or []
    state["scan_candidates"] = run.control.get("candidates") or []
    state["portfolio_result"] = run.control.get("portfolio")
    state["portfolio_bericht"] = run.control.get("portfolio_bericht", "")


def sync_worker_state(state) -> bool:
    """Lauf verbinden und fertige Metadaten je Sitzung einmal übernehmen."""
    active = scan_worker.active_run()
    reattached = active is not None and state.get("scan_thread") is not active.thread
    if active is not None:
        attach_worker(state, active)
    thread = state.get("scan_thread")
    control = state.get("scan_control") or {}
    if (thread is None or thread.is_alive()
            or state.get("_copied_scan_control") is control):
        return reattached
    state["portfolio_bericht"] = control.get("portfolio_bericht", "")
    state["portfolio_result"] = control.get("portfolio")
    state["scan_new_ids"] = control.get("new_ids", [])
    state["scan_signals"] = control.get("signals") or []
    state["scan_candidates"] = control.get("candidates") or []
    if control.get("last_run_file"):
        state["last_run_file"] = control["last_run_file"]
    if control.get("refreshed_ids") is not None:
        state["refreshed_signal_ids"] = control["refreshed_ids"]
    control["copied"] = True
    state["_copied_scan_control"] = control
    state["scan_running"] = None
    workflow = state["scan_workflow"]
    if workflow["status"] == "running":
        workflow.update(status="error",
                        activity="Lauf wurde unterbrochen. Vorliegende Ergebnisse bleiben erhalten.")
        for step in workflow["steps"].values():
            if step["status"] == "running":
                step.update(status="error", detail="Lauf unterbrochen; nicht abgeschlossen")
            elif step["status"] == "pending":
                step.update(status="skipped", detail="Nach Unterbrechung nicht ausgeführt")
    return reattached
