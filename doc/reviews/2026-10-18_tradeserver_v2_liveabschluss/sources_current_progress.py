"""Current source-attempt overview; preserve the initial batch as history.

Reads sanitized receipts and read-only local status APIs. Never issues POSTs.
Run from the scanner workspace; stop via .tmp/sources_current_progress.stop.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))


def read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def snapshot():
    original = read(HERE / "sources_live_progress.json") or {}
    current = dict(original.get("sources", {}))
    for row in current.values():
        row["evidence_file"] = "sources_live_progress.json"
        row["attempt_kind"] = "initial_batch"

    # Newer explicit MQL attempts supersede the failed initial batch for the
    # current display. Their original receipts remain separate and unchanged.
    for path in sorted(HERE.glob("*mql*progress.json"), key=lambda p: p.stat().st_mtime):
        value = read(path)
        if isinstance(value, dict) and value.get("job_id") and value.get("kuerzel") == "mql5":
            current["mql5"] = dict(value, evidence_file=path.name, attempt_kind="latest_explicit_retry")

    accepted = read(HERE / "root_pelican_live_acceptance.json")
    if accepted and isinstance(accepted.get("status"), dict):
        status = accepted["status"]
        current["pelik"] = {
            "status": status.get("state"), "phase": status.get("phase"),
            "done": status.get("done"), "total": status.get("total"),
            "job_id": status.get("jobId"), "detail": status.get("message"),
            "ergebnis": status.get("ergebnis"),
            "evidence_file": "root_pelican_live_acceptance.json",
            "verification_errors": accepted.get("verification_errors"),
            "attempt_kind": "latest_verified_repair_update",
        }

    # Query current local runtime attempts directly. This also handles a job
    # replaced by another owner without requiring a shared filename convention.
    # No token is copied into the output; the existing source client owns auth.
    from mqlkiscanner import db, quellen
    for source in db.list_quellen(nur_aktiv=True):
        key = source["kuerzel"]
        if key not in ("mql5", "robo", "zulu"):
            continue
        try:
            status = quellen.client_fuer_quelle(source, timeout=3).update_status()
            result = status.get("ergebnis") or {}
            current[key] = {
                "status": status.get("state"), "phase": status.get("phase"),
                "done": status.get("done"), "total": status.get("total"),
                "job_id": status.get("jobId"), "detail": status.get("message"),
                "ergebnis": result, "error": status.get("error"),
                "started_at": status.get("startedAt"), "finished_at": status.get("finishedAt"),
                "attempt_kind": "actual_current_local_api_attempt",
                "evidence_source": "read-only GET /api/v1/update/status",
            }
            if key == "zulu":
                current[key]["transition_evidence"] = "zulu_live_transition_status.json"
        except Exception as error:
            if key in current:
                current[key]["previous_observed_status"] = current[key].get("status")
                current[key]["status"] = "unreachable"
                current[key]["current_status_read_error"] = str(error)

    robo_repair = read(HERE / "sources_robo_repair_progress.json")
    if isinstance(robo_repair, dict):
        current["robo"] = dict(robo_repair, evidence_file="sources_robo_repair_progress.json")
        if robo_repair.get("status") == "waiting_for_initial_writer_end":
            initial = robo_repair.get("initial_status") or {}
            current["robo"].update(
                done=initial.get("done"), total=initial.get("total"),
                detail=initial.get("message"), job_id=initial.get("jobId"),
                ergebnis=initial.get("ergebnis"), phase=initial.get("phase"),
            )
        elif robo_repair.get("status") == "renewing_invalid_histories":
            provider = robo_repair.get("current_provider")
            try:
                live = (ROOT / f".tmp/sources_robo_repair_{int(provider)}.log").read_text(encoding="utf-8", errors="replace")
                loaded = re.findall(r"Deals [^\n]*: (\d+) geladen", live)
                if loaded:
                    current["robo"]["current_provider_loaded_raw_deals"] = int(loaded[-1])
                    current["robo"]["detail"] = f"Full raw history renewal for {provider}: {loaded[-1]} records loaded; API total unknown"
            except (OSError, ValueError, TypeError):
                pass
            current["robo"]["trade_unit_status"] = "unverified; scanner CSV disabled in staged195-test runtime"

    # The current Vantage run is an explicit full-history CLI repair while the
    # GUI/API is stopped. Its cancelled initial batch cannot stand in for it.
    full_log = ROOT / ".tmp/sources_vantage_ft_record_identity.log"
    if full_log.exists():
        ft_end = read(HERE / "sources_vantage_ft_record_identity_exit.json")
        other_end = read(HERE / "sources_vantage_other_record_identity_exit.json")
        phases = []
        for label, file in [("ft", full_log), ("other_workflow", ROOT / ".tmp/sources_vantage_other_record_identity.log")]:
            try:
                lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            progress = [line for line in lines if re.search(r"\[\d+/\d+\]|Trades geladen|FEHLER|FERTIG:", line)]
            phases.append({"phase": label, "latest_progress": progress[-1] if progress else "starting"})
        ended = ft_end is not None and other_end is not None
        successful = ended and ft_end.get("exit_code") == 0 and other_end.get("exit_code") == 0
        current["vant"] = {
            "status": "repair_complete_waiting_restart_verification" if successful else ("repair_failed" if ended else "full_history_repair_running"),
            "server": "offline_until_writer_end", "selected_providers": 19,
            "identity_basis": "historyRecordId", "phases": phases,
            "ft_exit": ft_end, "other_workflow_exit": other_end,
            "attempt_kind": "explicit_source_scoped_full_repair",
            "evidence_file": "sources_vantage_repair_plan.json",
        }
    ft_readonly = read(HERE / "sources_vantage_ft_readonly_acceptance.json")
    if isinstance(ft_readonly, dict) and not (ROOT / ".tmp/sources_vantage_readonly.stop").exists():
        current["vant"]["server"] = "GET-only REST8092 while unrelated full-history repair continues"
        current["vant"]["verified_ft_scope_only"] = ft_readonly.get("verified_scope_only")
        current["vant"]["verified_ft_evidence"] = "sources_vantage_ft_readonly_acceptance.json"
        current["vant"]["post_update_disabled"] = True
        try:
            vsource = next(q for q in db.list_quellen(nur_aktiv=True) if q["kuerzel"] == "vant")
            health = quellen.client_fuer_quelle(vsource, timeout=3).health()
            expected = ft_readonly.get("health") or {}
            if any(health.get(k) != expected.get(k) for k in ("service", "instance")):
                raise ValueError("Read-only source service/instance changed")
            current["vant"]["readonly_api_reachable"] = True
        except Exception as error:
            current["vant"]["server"] = "unreachable_readonly_listener"
            current["vant"]["readonly_api_reachable"] = False
            current["vant"]["current_status_read_error"] = str(error)
    vantage_accepted = read(HERE / "sources_vantage_live_acceptance.json")
    if isinstance(vantage_accepted, dict):
        current["vant"] = dict(vantage_accepted, evidence_file="sources_vantage_live_acceptance.json")
    output = {
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "meaning": "Latest known attempts; an active or partial job is never accepted as a completed source update.",
        "initial_batch_history": "sources_live_progress.json",
        "sources": current,
    }
    temporary = HERE / "sources_current_progress.json.tmp"
    temporary.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(HERE / "sources_current_progress.json")


if __name__ == "__main__":
    while not (ROOT / ".tmp/sources_current_progress.stop").exists():
        snapshot()
        time.sleep(15)
