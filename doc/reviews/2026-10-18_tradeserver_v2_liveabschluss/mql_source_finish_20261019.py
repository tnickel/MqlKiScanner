"""MQL-only closeout: offline preservation and read-only post-guard checks.

No Scanner database access, update POST, scan, or completion-history write.
"""
from __future__ import annotations

import datetime as dt
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import socket
import sys
import urllib.error
import urllib.request

import psutil

from mqlkiscanner.parser import load_export

REVIEW = Path(__file__).resolve().parent
ROOT = REVIEW.parents[2]
REPO = ROOT.parent / "MqlDownloader"
RUNTIME = Path("C:/Forex/MqlAnalyzer")
PRIVATE = ROOT / "data/runs/liveabschluss_20261019/mql"
JOB = "u-35579920-eb3d-4db4-83ef-ae6a24b934c9"
EXPECTED = "59b6a9996628c040bfdcb36042eeecf1e68c52437ef1a3003a4f5fc138db37a7"
START = dt.datetime.fromisoformat("2026-10-18T20:33:42+02:00")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def no_writer():
    active = []
    for process in psutil.process_iter(["pid", "name", "cmdline", "cwd", "create_time"]):
        try:
            if process.info["name"].lower() not in ("java.exe", "javaw.exe"):
                continue
            command = " ".join(process.info["cmdline"] or []).lower()
            cwd = str(process.info["cwd"] or "").lower()
            if "mqldownloader" in command or "mqlanalyzer" in command or cwd == str(REPO).lower():
                active.append({"pid": process.pid, "name": process.info["name"]})
        except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
            continue
    with socket.socket() as connection:
        connection.settimeout(1)
        listening = connection.connect_ex(("127.0.0.1", 8089)) == 0
    assert not active and not listening, f"MQL source process/listener exists: {active}"
    return {"checked_utc": now(), "matching_java_processes": active, "port_8089_listening": listening}


def saved_job():
    observation = json.loads((REVIEW / "mql_corrected_watch_status.json").read_text(encoding="utf-8"))
    status = observation["status"]
    assert observation["job_id"] == JOB == status["jobId"]
    assert status["state"] == "done" and status["finishedAt"]
    result = status["ergebnis"]
    assert result["tradelistenFehler"] == 0 and not result["tradelistenAbgebrochen"]
    assert result["katalogUebersprungen"] is False
    for platform in ("mt4", "mt5"):
        pages = [row for row in observation["observed_list_urls"] if row["platform"] == platform and row["page"] >= 2]
        assert pages and all("/list/page" in row["url"] and row["orderby"] == "subscribers" for row in pages)
    return observation


def successful_ids(platform):
    journal = RUNTIME / "download" / f"{platform}download.txt"
    success = []
    current = None
    for line in journal.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        timestamp = re.match(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", line)
        if not timestamp or dt.datetime.fromisoformat(timestamp[1] + "+02:00") < START:
            continue
        match = re.search(r"\[(\d+)\] STARTING: .*\(ID: (\d+)\)", line)
        if match:
            current = (int(match[1]), int(match[2]))
        match = re.search(r"\[(\d+)\] SUCCESS:", line)
        if match:
            assert current and current[0] == int(match[1]), "Unbound successful export"
            success.append(current)
    assert success and max(index for index, _ in success) > 48
    assert len(success) == len({sid for _, sid in success}), "Duplicate job export identities"
    return success


def generations():
    rows = []
    for platform in ("mql4", "mql5"):
        directory = RUNTIME / "download" / platform
        for index, sid in successful_ids(platform):
            candidates = [p for p in directory.glob(f"*_{sid}.csv") if p.is_file()]
            assert candidates, f"CSV missing for {platform}/{sid}"
            path = max(candidates, key=lambda p: p.stat().st_mtime_ns)
            stem = path.with_suffix("")
            html = stem.with_name(stem.name + "_root.html")
            metrics = stem.with_name(stem.name + "_root.txt")
            for source in (path, html, metrics):
                assert source.is_file() and source.stat().st_mtime >= START.timestamp(), f"Missing/stale generation: {source.name}"
            before = sha(path)
            parsed, parser_error = None, None
            try:
                parsed = load_export(str(path))
            except ValueError as error:
                parser_error = str(error)
            assert sha(path) == before, "CSV changed during parsing"
            rows.append({"platform": platform, "signal_id": sid, "provider_index_in_run": index,
                         "csv_name": path.name, "csv_sha256": before,
                         "html_name": html.name, "html_sha256": sha(html),
                         "metrics_name": metrics.name, "metrics_file_sha256": sha(metrics),
                         "csv_mtime_utc": dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat(),
                         "metrics_mtime_utc": dt.datetime.fromtimestamp(metrics.stat().st_mtime, dt.timezone.utc).isoformat(),
                         "scanner_parsed_trades": len(parsed.trades) if parsed else None,
                         "scanner_parsed_balance_events": len(parsed.balances) if parsed else None,
                         "scanner_parsed_pending_orders": len(parsed.pendings) if parsed else None,
                         "scanner_parser_format": parsed.source_format if parsed else None,
                         "scanner_parser_error": parser_error})
    return rows


def assert_source_unchanged(rows):
    for row in rows:
        directory = RUNTIME / "download" / row["platform"]
        for name_key, hash_key in (("csv_name", "csv_sha256"), ("html_name", "html_sha256"),
                                   ("metrics_name", "metrics_file_sha256")):
            assert sha(directory / row[name_key]) == row[hash_key], "Preserved source generation changed"


def offline():
    absence = no_writer()
    observed = saved_job()
    rows = generations()
    assert len(rows) == observed["status"]["ergebnis"]["signaleGeliefert"] == 268
    assert sum(row["platform"] == "mql4" for row in rows) == 92
    assert sum(row["platform"] == "mql5" for row in rows) == 176
    PRIVATE.mkdir(parents=True, exist_ok=True)
    write(PRIVATE / "saved_terminal_observation.json", observed)
    backup = PRIVATE / ("offline_backup_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    backup.mkdir()
    manifest = []
    for name in ("config", "database", "download"):
        source = RUNTIME / name
        shutil.copytree(source, backup / name)
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(RUNTIME)
            original_sha = sha(path)
            assert sha(backup / relative) == original_sha, "Offline backup hash mismatch"
            manifest.append({"path": str(relative), "size": path.stat().st_size, "sha256": original_sha})
    for path, name in ((REPO / "config/update_state.json", "update_state.json"),
                       (REPO / "target/MqlDownloader-0.0.35-SNAPSHOT-jar-with-dependencies.jar", "previous.jar")):
        shutil.copy2(path, backup / name)
        assert sha(path) == sha(backup / name)
    assert_source_unchanged(rows)
    no_writer()
    write(backup / "manifest.json", manifest)
    result = {"verified_utc": now(), "source": "mql5", "job_id": JOB,
              "status": observed["status"], "absence": absence,
              "saved_status_origin": "Read-only observer, 2026-10-18T19:37:59Z; source API was already offline on resume",
              "old_pid_absent": not psutil.pid_exists(1663784),
              "generation_counts": {platform: sum(row["platform"] == platform for row in rows) for platform in ("mql4", "mql5")},
              "all_successful_generations_parsed": all(not row["scanner_parser_error"] for row in rows),
              "scanner_parser_error_count": sum(bool(row["scanner_parser_error"]) for row in rows),
              "fresh_source_file_generations": rows,
              "offline_backup_files": len(manifest), "offline_backup_hashes_verified": True,
              "scanner_db_or_settings_accessed": False, "source_update_post_sent": False}
    write(PRIVATE / "offline_verification.json", {**result, "private_backup_path": str(backup)})
    write(REVIEW / "mql_source_offline_preservation_20261019.json", result)
    print(json.dumps({"job_id": JOB, "generations": len(rows), "generation_counts": result["generation_counts"],
                      "backup_files": len(manifest), "offline_backup_hashes_verified": True,
                      "parser_errors": [{"platform": row["platform"], "signal_id": row["signal_id"],
                                         "error": row["scanner_parser_error"]} for row in rows if row["scanner_parser_error"]]}))


def after_guard(pid, expected_sha=EXPECTED):
    assert re.fullmatch(r"[0-9a-f]{64}", expected_sha)
    saved = json.loads((PRIVATE / "offline_verification.json").read_text(encoding="utf-8"))
    assert_source_unchanged(saved["fresh_source_file_generations"])
    process = psutil.Process(pid)
    assert Path(process.cwd()).resolve() == REPO.resolve()
    jars = [arg for arg in process.cmdline() if arg.lower().endswith(".jar")]
    assert len(jars) == 1
    jar = Path(jars[0]); jar = jar if jar.is_absolute() else REPO / jar
    assert sha(jar) == expected_sha
    assert any(connection.status == psutil.CONN_LISTEN and connection.laddr.port == 8089
               for connection in process.net_connections(kind="tcp"))
    spec = importlib.util.spec_from_file_location("mql_original_finish", REVIEW / "mql_corrected_finish.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    idle = json.loads(helper.get("update/status"))
    assert idle.get("state") == "idle", "New source writer is active"
    health = json.loads(helper.get("health"))
    assert health["status"] == "ok" and health["service"] == "MqlDownloader"
    assert health["instance"] == "Ryzen7950X"
    catalog, identities = helper.catalog_snapshot()
    assert health["providers"] == catalog["locally_offered_total"]
    previous = {(row["platform"], row["signal_id"]): row for row in saved["fresh_source_file_generations"]}
    published = []
    for (platform, sid), row in previous.items():
        assert (platform, str(sid)) in identities
        exported = helper.get(f"providers/{sid}/{platform}/trades.csv")
        assert hashlib.sha256(exported).hexdigest() == row["csv_sha256"]
        file_info = json.loads(helper.get(f"providers/{sid}/{platform}/trades?limit=1"))
        assert str(file_info["signalId"]) == str(sid) and file_info["version"] == platform
        assert file_info["file"]["name"] == row["csv_name"]
        metrics = json.loads(helper.get(f"providers/{sid}/{platform}/metrics"))
        assert metrics["file"]["name"] == row["metrics_name"]
        modified = dt.datetime.fromisoformat(metrics["file"]["lastModified"])
        if modified.tzinfo is None:
            modified = modified.astimezone()
        assert modified.timestamp() >= START.timestamp()
        published.append({**row, "rest_sha256": hashlib.sha256(exported).hexdigest(),
                          "rest_json_csv_rows": file_info["total"],
                          "metrics_response_sha256": hashlib.sha256(json.dumps(metrics, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                          "metrics_last_modified": metrics["file"]["lastModified"],
                          "account_currency": metrics.get("metrics", {}).get("Currency")})
    assert_source_unchanged(saved["fresh_source_file_generations"])
    verified = {"verified_utc": now(), "source": "mql5", "job_id": JOB, "status": saved["status"],
                "api_health": {key: health.get(key) for key in ("status", "service", "instance", "apiVersion")},
                "catalog_verification": catalog, "fresh_source_file_generations": published,
                "all_successful_generations_parsed": saved["all_successful_generations_parsed"],
                "scanner_parser_error_count": saved["scanner_parser_error_count"],
                "source_generation_mechanism": "Direct files bound before activation and checked byte-for-byte through REST; no atomic generation pointer claimed"}
    guard_checks = []
    for path in ("providers/test_1/mql4/trades.csv", "providers/test_2/mql5/metrics",
                 "providers/page2/mql4/history", "providers/page2/mql5/reports"):
        try:
            helper.get(path)
        except urllib.error.HTTPError as error:
            assert error.code == 404
            guard_checks.append({"path": path, "http_status": error.code})
        else:
            raise AssertionError("Invalid provider identity publicly available: " + path)
    csv_rows = list(csv.DictReader(io.StringIO(helper.get(
        "providers?format=csv&minSubscribers=0&limit=10000").decode("utf-8-sig")), delimiter=";"))
    assert len(csv_rows) == catalog["locally_offered_total"]
    assert all(re.fullmatch(r"[1-9][0-9]*", row["signalId"]) for row in csv_rows)
    summary = json.loads(helper.get("summary"))
    assert summary["providers"]["total"] == catalog["locally_offered_total"]
    events = json.loads(helper.get("events?includeUnchanged=true&limit=1000"))
    assert events["count"] == len(events["items"])
    assert all(re.fullmatch(r"[1-9][0-9]*", row["signalId"]) for row in events["items"])
    trades = json.loads(helper.get("trades?limit=10000"))
    assert trades["count"] == len(trades["items"]) == trades["total"]
    assert all(re.fullmatch(r"[1-9][0-9]*", row["signalId"]) for row in trades["items"])
    verified["public_api_identity_checks"] = {
        "providers_json_rows": catalog["rows_checked"], "providers_csv_rows": len(csv_rows),
        "health_and_summary_agree": True, "event_rows_checked": len(events["items"]),
        "trade_catalog_rows_checked": len(trades["items"]), "invalid_ids_exposed": False}
    verified["after_guard_process"] = {"pid": pid, "jar_sha256": expected_sha,
                                       "job_state_after_normal_start": "idle", "source_generations_unchanged": True}
    verified["guard_http_checks"] = guard_checks
    verified["scanner_db_or_settings_accessed"] = False
    verified["scanner_completion_history_appended"] = False
    verified["source_update_post_sent"] = False
    write(REVIEW / "mql_corrected_final_verification.json", verified)
    write(PRIVATE / "final_verification.json", verified)
    print(json.dumps({"job_id": JOB, "verified_generations": len(previous),
                      "catalog": verified["catalog_verification"], "guard_checks": guard_checks,
                      "scanner_completion_history_appended": False}))


if __name__ == "__main__":
    assert sys.argv[1] in ("offline", "after-guard")
    if sys.argv[1] == "offline":
        offline()
    else:
        after_guard(int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else EXPECTED)
