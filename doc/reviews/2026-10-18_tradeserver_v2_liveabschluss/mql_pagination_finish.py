"""Guarded follow-up of the already-started MQL pagination update; no source POST.

verify: read-only successful-end, pagination and fresh-file evidence.
append: append one successful Stufe-0 receipt, idempotent for this job/status.
catalog/scan: explicit existing maintenance CLI, only after verification and a
free shared lock. The CLI still acquires the lock atomically on its own.
"""
from __future__ import annotations
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import urllib.request

from mqlkiscanner import config, db
from mqlkiscanner.agenten import lock

REVIEW = Path(__file__).resolve().parent
ROOT = REVIEW.parents[2]
OUTPUT = ROOT / "data/runs/liveabschluss_20261018"
JOB = "u-559dfc47-4a38-4426-b51d-59adf5ffb5db"
START = dt.datetime.fromisoformat("2026-10-18T20:04:14").astimezone()
PYTHON = Path(r"C:/Users/tnickel/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe")
sha = lambda data: hashlib.sha256(data).hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def get(path):
    with urllib.request.urlopen("http://127.0.0.1:8089/api/v1/" + path, timeout=15) as response:
        return response.read()


def write(name, value):
    path = REVIEW / name
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    temp.replace(path)


def verify():
    status = json.loads(get("update/status"))
    assert status.get("jobId") == JOB and status.get("state") == "done", "Exact MQL job is not successful and done"
    ergebnis = status["ergebnis"]
    assert ergebnis.get("tradelistenFehler") == 0 and ergebnis.get("tradelistenAbgebrochen") is False
    assert ergebnis.get("katalogUebersprungen") is False, "Forced pagination discovery was not performed"
    assert status.get("finishedAt") and ergebnis.get("datenstand")
    observed = json.loads((REVIEW / "mql_pagination_live_watch_status.json").read_text(encoding="utf-8"))
    assert observed["job_id"] == JOB
    urls = observed["observed_list_urls"]
    scope = {}
    for platform, journal_name in (("mt4", "mql4"), ("mt5", "mql5")):
        followups = [entry for entry in urls if entry["platform"] == platform and entry["page"] >= 2]
        assert followups and all(entry["orderby"] == "subscribers" for entry in followups), "No actual sorted follow-up URL proof: " + platform
        journal = observed["journals"][journal_name]
        assert journal["success_max_index"] > 48, "Only first-page successful exports proved: " + platform
        scope[platform] = {"actual_followup_urls": followups, "journal": journal}
    # Raw source generations are direct files in this client, not Zulu-style
    # atomic generation pointers. Bind the fresh file SHA to the actual REST
    # bytes; persist counts/hashes only, never raw trades or account amounts.
    generations = []
    for platform in ("mql4", "mql5"):
        journal = Path("C:/Forex/MqlAnalyzer/download") / f"{platform}download.txt"
        success_ids = []
        current_id = None
        for line in journal.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            stamp = re.match(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", line)
            if not stamp or dt.datetime.fromisoformat(stamp[1]).astimezone() < START:
                continue
            attempt = re.search(r"\[(\d+)\] STARTING: .*\(ID: (\d+)\)", line)
            if attempt:
                current_id = int(attempt[2])
            success = re.search(r"\[(\d+)\] SUCCESS:", line)
            if success and current_id:
                success_ids.append((int(success[1]), current_id))
        assert any(index > 48 for index, sid in success_ids)
        # First export, first real second-page export, and final success give
        # independently scoped fresh generations across this platform's run.
        selected = [success_ids[0], next(item for item in success_ids if item[0] > 48), success_ids[-1]]
        seen = set()
        for index, sid in selected:
            if sid in seen:
                continue
            seen.add(sid)
            directory = Path("C:/Forex/MqlAnalyzer/download") / platform
            file_info = json.loads(get(f"providers/{sid}/{platform}/trades?limit=1"))
            assert str(file_info["signalId"]) == str(sid) and file_info["version"] == platform
            filename = file_info["file"]["name"]
            assert Path(filename).name == filename and filename.lower().endswith(".csv")
            path = directory / filename
            assert path.resolve().parent == directory.resolve() and path.is_file()
            assert path.stat().st_mtime >= START.timestamp(), "An old file was reused as a fresh generation"
            before = path.read_bytes()
            exported = get(f"providers/{sid}/{platform}/trades.csv")
            assert before == exported and path.read_bytes() == before
            metrics = json.loads(get(f"providers/{sid}/{platform}/metrics"))
            last_modified = dt.datetime.fromisoformat(metrics["file"]["lastModified"])
            if last_modified.tzinfo is None:
                last_modified = last_modified.astimezone()
            assert last_modified.timestamp() >= START.timestamp(), "Converted metrics predate this successful run"
            rows = list(csv.reader(io.StringIO(before.decode("utf-8-sig")), delimiter=";"))
            assert rows and rows[0][0] == "Time"
            generations.append({"platform": platform, "signal_id": sid, "provider_index_in_run": index,
                                "csv_name": path.name, "csv_sha256": sha(before), "rest_sha256": sha(exported),
                                "csv_mtime_utc": dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat(),
                                "raw_csv_rows_without_header": len(rows) - 1,
                                "metrics_filename": metrics["file"]["name"], "metrics_last_modified": metrics["file"]["lastModified"],
                                "metrics_response_sha256": sha(json.dumps(metrics, sort_keys=True, ensure_ascii=False).encode()),
                                "account_currency": metrics.get("metrics", {}).get("Currency")})
    result = {"verified_utc": now(), "job_id": JOB, "source": "mql5", "status": status,
              "scope_proof": scope, "fresh_source_file_generations": generations,
              "source_generation_mechanism": "Direct source files with fresh mtime and exact REST-byte SHA; no atomic generation pointer is claimed"}
    write("mql_pagination_final_verification.json", result)
    return result


def append(verified, status_label="fertig", note=None):
    sources = [source for source in db.list_quellen(nur_aktiv=True) if source["kuerzel"] == "mql5"]
    assert len(sources) == 1
    source = sources[0]
    assert source["quellen_uid"] == "0a8faef1-a341-4899-a199-a87166b69079"
    status = verified["status"]
    result = status["ergebnis"]
    note = note or "Pagination-Fix real abgenommen: sortierte Folgeseiten und >48 erfolgreiche Provider je Plattform, frische CSV-/REST-Hashes."
    # A single conditional INSERT is atomic and cannot double-append the same
    # job/status even if a separate observer happened to finish concurrently.
    with db._connect() as connection:
        connection.execute("""INSERT INTO client_updates
            (ts,quelle_id,kuerzel,base_url,job_id,status,dauer_s,signale_geliefert,
             tradelisten_neu,tradelisten_aktualisiert,datenstand,fehler,hinweise)
            SELECT ?,?,?,?,?,?,?,?,?,?,?,?,?
            WHERE NOT EXISTS(SELECT 1 FROM client_updates WHERE quelle_id=? AND job_id=? AND status=?)""",
            (dt.datetime.now().isoformat(timespec="seconds"), source["id"], "mql5", source["base_url"], JOB, status_label,
             (dt.datetime.fromisoformat(status["finishedAt"]) - dt.datetime.fromisoformat(status["startedAt"])).total_seconds(),
             result.get("signaleGeliefert"), result.get("tradelistenNeu"), result.get("tradelistenAktualisiert"),
             result["datenstand"], note if status_label != "fertig" else "",
             json.dumps([*result.get("hinweise", []), note], ensure_ascii=False), source["id"], JOB, status_label))
        rows = connection.execute("SELECT id,ts,job_id,status FROM client_updates WHERE quelle_id=? AND job_id=? AND status=?", (source["id"], JOB, status_label)).fetchall()
        assert len(rows) == 1
    receipt = {"recorded_utc": now(), "job_id": JOB, "status": status_label, "db_rows": [dict(row) for row in rows]}
    write("mql_pagination_stufe0_receipt.json", receipt)
    return receipt


def main():
    phase = sys.argv[1]
    if phase == "record-incomplete":
        observed = json.loads((REVIEW / "mql_pagination_live_watch_status.json").read_text(encoding="utf-8"))
        status = observed["status"]
        assert observed["job_id"] == status["jobId"] == JOB and status["state"] == "done"
        assert observed["journals"]["mql4"]["success_max_index"] == 48
        original = json.loads((REVIEW / "mql_pagination_dom_original_page2.json").read_text(encoding="utf-8"))
        assert original["http_status"] == 200 and original["positive_subscribers"] == 44
        value = {"recorded_utc": now(), "job_id": JOB, "raw_source_terminal": status,
                 "external_review_status": "teilweise", "pagination_accepted": False,
                 "reason": "MT4 nur48 Exporte, Original-Tabellen-Page2 enthaelt44 weitere abonnierte Provider; kein erfolgreicher Gesamtkatalog"}
        write("mql_pagination_unaccepted_terminal.json", value)
        receipt = append({"status": status}, "teilweise", value["reason"])
        print(json.dumps(receipt, indent=2))
        return
    verified = verify()
    if phase == "verify":
        print(json.dumps({"job_id": JOB, "verified_generations": len(verified["fresh_source_file_generations"])}, indent=2))
        return
    appended = append(verified)
    if phase == "append":
        print(json.dumps(appended, indent=2))
        return
    assert phase in ("catalog", "scan")
    lock_state = lock.lock_status(config.DATA_DIR)
    assert lock_state.get("frei") or lock_state.get("verwaist"), "Shared workflow lock held; do not touch terminals"
    args = [str(PYTHON), str(ROOT / "scripts/reference/live_abschluss.py"), "catalog" if phase == "catalog" else "source-scan",
            "--source", "mql5", "--live", "--expected-version", "21", "--output", str(OUTPUT)]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    log = OUTPUT / f"mql_pagination_{phase}.log"
    with log.open("wb") as stream:
        completed = subprocess.run(args, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    receipt = {"phase": phase, "finished_utc": now(), "exit_code": completed.returncode,
               "private_log": str(log), "job_id": JOB}
    write(f"mql_pagination_{phase}_receipt.json", receipt)
    print(json.dumps(receipt, indent=2))
    assert completed.returncode == 0


if __name__ == "__main__":
    main()
