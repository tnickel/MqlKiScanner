"""Explicit, guarded deployment phases; private runtime backup never enters review.

Run phases separately: attach, close, backup, start, update, status.
The old worker is synchronously guarded by the previously tested Java agent.
There is no kill, Thread.stop, unguarded interrupt, or forced JVM termination.
"""
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

import psutil

REVIEW = Path(__file__).resolve().parent
ROOT = REVIEW.parents[2]
REPO = ROOT.parent / "zulumonitor"
OLD_PID = 52084
OLD_JOB = "u-20261018-184200-b328fbb6"
JAVA = Path(r"C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot\bin")
BUILD = json.loads((REVIEW / "zulu_build_snapshot.json").read_text())
SNAPSHOT = Path(BUILD["snapshot_jar"]).parent
STATE = SNAPSHOT / "transition.json"
REPORT = REVIEW / "zulu_alt_cancel_live.jsonl"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def api(path, method="GET", body=None):
    headers = {}
    config_file = REPO / "data/rest_api.json"
    if config_file.is_file():
        token = json.loads(config_file.read_text(encoding="utf-8-sig")).get("token", "").strip()
        if token:
            headers["Authorization"] = "Bearer " + token
    data = None if body is None else json.dumps(body).encode()
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request("http://127.0.0.1:8093" + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def old_process():
    p = psutil.Process(OLD_PID)
    expected = json.loads((REVIEW / "zulu_shutdown_assessment_runtime.json").read_text(encoding="utf-8-sig"))
    assert p.cwd() == str(REPO) and p.exe() == expected["exe"] and p.cmdline() == expected["cmdline"], "Old process identity changed"
    return p


def old_job():
    status = api("/api/v1/update/status")
    assert status["jobId"] == OLD_JOB, "Job identity changed"
    return status


def guard_complete():
    events = [json.loads(line) for line in REPORT.read_text().splitlines()]
    assert events[-1]["phase"] == "WORKER_ENDED_ARCHIVES_IDENTICAL", "Guard has not verified worker completion"
    assert not any(event["phase"] in ("FAILED", "TRANSFORM_FAILED") for event in events)
    return events


phase = sys.argv[1]
state = json.loads(STATE.read_text()) if STATE.is_file() else {"started_utc": now()}

if phase == "attach":
    old_process()
    before = old_job()
    assert before["state"] == "running" and before["phase"] == "tradelisten"
    assert not REPORT.exists(), "Do not repeat a one-shot live attach"
    tested = json.loads((REVIEW / "zulu_alt_cancel_fixture_summary.json").read_text())
    agent = Path(tested["agent_jar"])
    assert sha(agent) == tested["agent_sha256"]
    assert len(tested["results"]) == 4 and all(item["exit_code"] == 0 for item in tested["results"])
    catalogue = REPO / "data/traders.csv"
    rows = list(csv.DictReader(io.StringIO(catalogue.read_text(encoding="utf-8-sig")), delimiter=";"))
    ids = [int(row["ProviderId"]) for row in rows]
    assert len(ids) == before["total"] == 200 and len(set(ids)) == 200
    config = SNAPSHOT / "guard_live.properties"
    # Java Properties backslash escaping is explicit; no shell interpolation.
    properties = {"pid": str(OLD_PID), "dataDir": str(REPO / "data"), "jobId": OLD_JOB,
                  "report": str(REPORT), "catalogueSha256": sha(catalogue), "providerIds": ",".join(map(str, ids)),
                  "statusUrl": "http://127.0.0.1:8093/api/v1/update/status",
                  "expectedStoreShape": tested["expectedStoreShape"], "expectedJobShape": tested["expectedJobShape"]}
    config.write_text("\n".join(key + "=" + value.replace("\\", "\\\\") for key, value in properties.items()) + "\n")
    state["attach"] = {"started_utc": now(), "before": before, "agent_sha256": tested["agent_sha256"]}
    write(STATE, state)
    with (SNAPSHOT / "attach_live.log").open("wb") as log:
        result = subprocess.run([str(JAVA / "java.exe"), "--add-modules", "jdk.attach", "-cp", str(agent),
                                 "zulu.audit.Attach", str(OLD_PID), str(agent), str(config)],
                                cwd=REPO, stdout=log, stderr=subprocess.STDOUT, timeout=20,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, "Attachment failed; no process close permitted"
    deadline = time.monotonic() + 65
    while time.monotonic() < deadline:
        if REPORT.is_file():
            events = [json.loads(line) for line in REPORT.read_text().splitlines()]
            if events[-1]["phase"] == "FAILED":
                raise RuntimeError("Guard precondition failed; old process must remain alive: " + events[-1]["detail"])
            if events[-1]["phase"] == "WORKER_ENDED_ARCHIVES_IDENTICAL":
                break
        time.sleep(0.1)
    guard_complete()
    after = old_job()
    assert after["state"] == "error" and after["ergebnis"]["tradelistenAbgebrochen"] is True
    assert after["ergebnis"]["datenstand"] is None
    dump = subprocess.check_output([str(JAVA / "jcmd.exe"), str(OLD_PID), "Thread.print"], cwd=REPO, text=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    assert '"update-job"' not in dump, "Old worker still exists"
    (SNAPSHOT / "after_cancel_threads.log").write_text(dump)
    state["attach"].update({"finished_utc": now(), "after": after, "worker_thread_absent": True,
                            "archive_hashes_identical": True})
    write(STATE, state)
    write(REVIEW / "zulu_live_transition_status.json", state)
    print(json.dumps(state["attach"], ensure_ascii=False, indent=2))

elif phase == "close":
    p = old_process()
    guard_complete()
    status = old_job()
    assert status["state"] == "error" and status["ergebnis"]["tradelistenAbgebrochen"] is True
    dump = subprocess.check_output([str(JAVA / "jcmd.exe"), str(OLD_PID), "Thread.print"], cwd=REPO, text=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    assert '"update-job"' not in dump
    assert "de.zulumonitor.store.DataStore.write" not in dump, "A datastore writer is still active"
    command = "$p = Get-Process -Id 52084 -ErrorAction Stop; $p.Refresh(); $p.CloseMainWindow()"
    result = subprocess.check_output(["powershell", "-NoProfile", "-Command", command], text=True,
                                     creationflags=subprocess.CREATE_NO_WINDOW).strip()
    assert result == "True", "No closeable main window; no forced termination permitted"
    p.wait(timeout=25)
    state["close"] = {"utc": now(), "normal_window_close": True, "old_pid_exited": True, "forced_termination": False}
    write(STATE, state)
    write(REVIEW / "zulu_live_transition_status.json", state)
    print(json.dumps(state["close"]))

elif phase == "backup":
    assert state.get("close", {}).get("old_pid_exited") and not psutil.pid_exists(OLD_PID)
    destination = SNAPSHOT / "data_after_old_shutdown"
    assert not destination.exists()
    size = sum(path.stat().st_size for path in (REPO / "data").rglob("*") if path.is_file())
    assert shutil.disk_usage(SNAPSHOT).free > size * 2 + 500_000_000
    shutil.copytree(REPO / "data", destination)
    files = []
    for path in sorted((REPO / "data").rglob("*")):
        if not path.is_file():
            continue
        copied = destination / path.relative_to(REPO / "data")
        assert sha(path) == sha(copied)
        files.append({"path": path.relative_to(REPO / "data").as_posix(), "sha256": sha(path), "size": path.stat().st_size})
    write(SNAPSHOT / "private_backup_manifest.json", {"utc": now(), "files": files})
    state["backup"] = {"utc": now(), "file_count": len(files), "bytes": size, "private_only": True, "all_copied_hashes_verified": True}
    write(STATE, state)
    write(REVIEW / "zulu_live_transition_status.json", state)
    print(json.dumps(state["backup"]))

elif phase == "start":
    assert state.get("backup", {}).get("all_copied_hashes_verified") and not psutil.pid_exists(OLD_PID)
    assert sha(Path(BUILD["snapshot_jar"])) == BUILD["jar_sha256"]
    # The host disables .ps1 execution. Invoke the authorized process launch
    # directly; no execution-policy change or script evaluation is needed.
    literal = lambda value: "'" + str(value).replace("'", "''") + "'"
    command = "\n".join([
        "$ErrorActionPreference = 'Stop'",
        "$spec = Get-Content -LiteralPath " + literal(SNAPSHOT / "launch.json") + " -Raw | ConvertFrom-Json",
        "if (Get-NetTCPConnection -State Listen -LocalPort 8093 -ErrorAction SilentlyContinue) { throw 'Port 8093 is still occupied' }",
        "$p = Start-Process -FilePath $spec.exe -ArgumentList $spec.windows_argument_line -WorkingDirectory $spec.cwd -WindowStyle Hidden -PassThru -RedirectStandardOutput "
            + literal(SNAPSHOT / "runtime.stdout.log") + " -RedirectStandardError " + literal(SNAPSHOT / "runtime.stderr.log"),
        "$p.Id | Set-Content -LiteralPath " + literal(SNAPSHOT / "runtime.pid"),
    ])
    listeners = {connection.pid for connection in psutil.net_connections(kind="tcp")
                 if connection.status == psutil.CONN_LISTEN and connection.laddr.port == 8093}
    if listeners:
        # Recovery from a launcher whose stdout pipe was inherited by the JVM:
        # adopt only the exact already-running frozen build, never launch twice.
        assert len(listeners) == 1
        new_pid = listeners.pop()
        p = psutil.Process(new_pid)
        assert p.cwd() == str(REPO) and str(Path(BUILD["snapshot_jar"])) in p.cmdline()[p.cmdline().index("-classpath") + 1]
        (SNAPSHOT / "runtime.pid").write_text(str(new_pid))
    else:
        with (SNAPSHOT / "launcher.log").open("wb") as log:
            result = subprocess.run(["powershell", "-NoProfile", "-Command", command], cwd=REPO,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=15,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0
        new_pid = int((SNAPSHOT / "runtime.pid").read_text(encoding="utf-8-sig").strip())
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            health = api("/api/v1/health")
            break
        except Exception:
            assert psutil.pid_exists(new_pid)
            time.sleep(0.25)
    else:
        raise RuntimeError("New process did not become healthy")
    p = psutil.Process(new_pid)
    assert str(Path(BUILD["snapshot_jar"])) in p.cmdline()[p.cmdline().index("-classpath") + 1]
    state["new_process"] = {"utc": now(), "pid": new_pid, "cwd": p.cwd(), "frozen_jar_sha256": BUILD["jar_sha256"],
                            "health": health, "hidden_launch": True}
    write(STATE, state)
    write(REVIEW / "zulu_live_transition_status.json", state)
    print(json.dumps(state["new_process"], indent=2))

elif phase == "update":
    p = psutil.Process(state["new_process"]["pid"])
    assert p.cwd() == str(REPO)
    assert api("/api/v1/update/status")["state"] == "idle", "Do not overlap or replace a current job"
    response = api("/api/v1/update", "POST", {"target": 200, "tradelisten": True, "katalogMaxAlterH": 0})
    state["new_update"] = {"utc": now(), "request": {"target": 200, "tradelisten": True, "katalogMaxAlterH": 0}, "response": response}
    write(STATE, state)
    write(REVIEW / "zulu_live_transition_status.json", state)
    print(json.dumps(state["new_update"], ensure_ascii=False, indent=2))

elif phase == "status":
    status = api("/api/v1/update/status")
    state["latest_status"] = {"utc": now(), "status": status}
    write(STATE, state)
    write(REVIEW / "zulu_live_transition_status.json", state)
    print(json.dumps(state["latest_status"], ensure_ascii=False, indent=2))
else:
    raise ValueError("Unknown explicit phase")
