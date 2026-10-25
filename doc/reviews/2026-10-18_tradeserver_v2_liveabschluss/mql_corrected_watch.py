"""Read-only observation of the exact pagination-fix MQL job.

Uses only local HTTP GETs, the existing descendant WebDriver's GET current-URL
endpoint, process liveness, existing download journals and workflow lock status.
Never starts a source job/browser/terminal, writes source data, or cancels work.
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
import re
import sys
import time
import urllib.parse
import urllib.request

import psutil
from mqlkiscanner import config
from mqlkiscanner.agenten import lock

REVIEW = Path(__file__).resolve().parent
ROOT = REVIEW.parents[2]
PID = 1663784
JOB = "u-35579920-eb3d-4db4-83ef-ae6a24b934c9"
START = dt.datetime.fromisoformat("2026-10-18T20:33:43")
STATUS_FILE = REVIEW / "mql_corrected_watch_status.json"
EVENTS_FILE = REVIEW / "mql_corrected_observations.jsonl"
if "--locale-aware" in sys.argv:
    STATUS_FILE = REVIEW / "mql_corrected_watch_status.json"
    EVENTS_FILE = REVIEW / "mql_corrected_observations.jsonl"
BASE = "http://127.0.0.1:8089"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def get(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def save(value):
    tmp = STATUS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(STATUS_FILE)


def event(kind, value):
    entry = {"observed_utc": now(), "kind": kind, "value": value}
    with EVENTS_FILE.open("a", encoding="utf-8") as out:
        out.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, ensure_ascii=False), flush=True)


def journal(platform):
    path = Path("C:/Forex/MqlAnalyzer/download") / f"{platform}download.txt"
    result = {"success_max_index": 0, "started_max_index": 0, "error_max_index": 0, "pages": [], "success_count": 0}
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        stamp = re.match(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", line)
        if not stamp or dt.datetime.fromisoformat(stamp[1]) < START:
            continue
        found = re.search(r"\[(\d+)\] (SUCCESS|STARTING|ERROR):", line)
        if found:
            key = {"SUCCESS": "success_max_index", "STARTING": "started_max_index", "ERROR": "error_max_index"}[found[2]]
            result[key] = max(result[key], int(found[1]))
            if found[2] == "SUCCESS":
                result["success_count"] += 1
        page = re.search(r"PAGE (\d+): (\d+) Provider gefunden \| Gesamt verarbeitet: (\d+)", line)
        if page:
            result["pages"].append({"at_local": stamp[1], "page": int(page[1]), "logged_provider_count": int(page[2]),
                                    "processed": int(page[3])})
    return result


def drivers(process):
    entries = []
    for child in process.children(recursive=True):
        try:
            if child.name().lower() != "chromedriver.exe":
                continue
            port = next(int(arg.split("=", 1)[1]) for arg in child.cmdline() if arg.startswith("--port="))
            for session in get(f"http://127.0.0.1:{port}/sessions", timeout=2).get("value", []):
                entries.append((child.pid, port, session["id"]))
        except (OSError, psutil.Error, StopIteration):
            continue
    return entries


def list_url(url):
    parsed = urllib.parse.urlsplit(url)
    match = re.fullmatch(r"/[a-z]{2}/signals/(mt4|mt5)/(?:list(?:/page(\d+))?|page(\d+))", parsed.path)
    if parsed.hostname != "www.mql5.com" or not match:
        return None
    query = urllib.parse.parse_qs(parsed.query)
    return {"platform": match[1], "page": int(match[2] or match[3] or 1),
            "orderby": query.get("orderby", [None])[0],
            "url": urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                urllib.parse.urlencode({"orderby": query["orderby"][0]}) if "orderby" in query else "", ""))}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    process = psutil.Process(PID)
    assert process.cwd() == str(ROOT.parent / "MqlDownloader")
    observed = {}
    if STATUS_FILE.exists():
        old = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        assert old["job_id"] == JOB
        observed = {(entry["platform"], entry["page"], entry["orderby"]): entry for entry in old.get("observed_list_urls", [])}
    known_drivers, refresh_at, status_at = [], 0.0, 0.0
    last_status = None
    while True:
        if time.monotonic() >= status_at:
            status = get(BASE + "/api/v1/update/status", timeout=10)
            assert status.get("jobId") == JOB, "Source job changed: do not credit another job"
            journals = {platform: journal(platform) for platform in ("mql4", "mql5")}
            state = {"observed_utc": now(), "process_id": PID, "job_id": JOB, "status": status,
                     "observed_list_urls": list(observed.values()), "journals": journals,
                     "workflow_lock": lock.lock_status(config.DATA_DIR),
                     "browser_observation_method": "GET current URL from existing descendant ChromeDriver only; no navigation/script/website request"}
            save(state)
            current = (status.get("state"), status.get("phase"), status.get("done"), status.get("message"))
            if current != last_status:
                event("source_status", {key: status.get(key) for key in ("jobId", "state", "phase", "done", "total", "message")})
                last_status = current
            if status.get("state") in ("done", "error", "cancelled", "aborted"):
                event("terminal_state", status)
                return
            status_at = time.monotonic() + 15
        if time.monotonic() >= refresh_at:
            known_drivers = drivers(process)
            refresh_at = time.monotonic() + 10
        for driver_pid, port, session_id in known_drivers:
            try:
                url = get(f"http://127.0.0.1:{port}/session/{session_id}/url", timeout=2).get("value")
                value = list_url(url) if isinstance(url, str) else None
                if value:
                    key = value["platform"], value["page"], value["orderby"]
                    if key not in observed:
                        value.update(first_seen_utc=now(), driver_pid=driver_pid)
                        observed[key] = value
                        event("actual_list_url", value)
                        # Persist URL evidence immediately, not only at the next status poll.
                        status_at = 0.0
            except Exception:
                # Browser is between requests/platforms. No mutation or recovery action.
                refresh_at = 0.0
        time.sleep(1)


if __name__ == "__main__":
    main()
