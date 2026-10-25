"""Guarded follow-up of the already-started MQL pagination update; no source POST.

verify: read-only successful-end, pagination and fresh-file evidence.
append: append one successful Stufe-0 receipt, idempotent for this job/status.
verify-source: preserve exact successful end and every generation before idle restart.
after-guard PID SHA256: bind them to the idle replacement API and append once.
Scanner catalogue/scan maintenance uses the separate canonical live_abschluss CLI.
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
import sys
import urllib.request
import urllib.parse
import psutil

from mqlkiscanner import config, db
from mqlkiscanner.parser import load_export

REVIEW = Path(__file__).resolve().parent
ROOT = REVIEW.parents[2]
JOB = "u-35579920-eb3d-4db4-83ef-ae6a24b934c9"
START = dt.datetime.fromisoformat("2026-10-18T20:33:42").astimezone()
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


def catalog_snapshot(*, allow_preserved_labels=False):
    """Read every locally offered row without recording account/trade values."""
    rows, offset, expected_total = [], 0, None
    while expected_total is None or offset < expected_total:
        raw = get(f"providers?offset={offset}&limit=100&minSubscribers=0")
        page = json.loads(raw)
        if expected_total is None:
            expected_total = page["total"]
        assert page["total"] == expected_total, "Local catalogue changed during final verification"
        assert page["offset"] == offset and page["count"] == len(page["items"])
        assert page["count"] or offset == expected_total, "Catalogue pagination stalled"
        rows.extend(page["items"])
        offset += page["count"]
    identities = [(row["version"], str(row["signalId"])) for row in rows]
    assert len(rows) == expected_total and len(set(identities)) == len(identities)
    invalid = []
    known_labels = {("mql4", "test_1"), ("mql5", "test_2"), ("mql4", "page2"), ("mql5", "page2")}
    for row in rows:
        sid = str(row["signalId"])
        if not re.fullmatch(r"[1-9][0-9]*", sid):
            assert allow_preserved_labels and (row["version"], sid) in known_labels, "Invalid provider identity remains publicly exposed"
            invalid.append([row["version"], sid])
            continue
        assert row["version"] in ("mql4", "mql5")
        weeks = row.get("weeks")
        assert weeks is None or (isinstance(weeks, int) and not isinstance(weeks, bool) and weeks >= 0)
        parsed = urllib.parse.urlsplit(row["url"])
        assert parsed.hostname == "www.mql5.com"
        assert re.fullmatch(r"/[a-z]{2}/signals/" + re.escape(sid) + r"/?", parsed.path), "Provider URL/identity mismatch"
    return {"locally_offered_total": expected_total, "rows_checked": len(rows),
            "unique_source_platform_identities": len(set(identities)),
            "catalog_response_sha256": sha(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()),
            "unknown_age_rows": sum(row.get("weeks") is None for row in rows),
            "positive_subscriber_rows": sum(row["subscribers"] > 0 for row in rows),
            "preserved_invalid_identities_still_exposed": invalid,
            "catalog_identity_accepted": not invalid,
            "scope": "Complete locally offered catalogue, minSubscribers=0; no claim of all MQL5 website providers"}, set(identities)


def verify(*, source_snapshot=False, saved_status=None, bound_generations=None):
    status = saved_status if saved_status is not None else json.loads(get("update/status"))
    assert status.get("jobId") == JOB and status.get("state") == "done", "Exact MQL job is not successful and done"
    ergebnis = status["ergebnis"]
    assert ergebnis.get("tradelistenFehler") == 0 and ergebnis.get("tradelistenAbgebrochen") is False
    assert ergebnis.get("katalogUebersprungen") is False, "Forced pagination discovery was not performed"
    assert status.get("finishedAt") and ergebnis.get("datenstand")
    health = json.loads(get("health"))
    assert health.get("status") == "ok" and health.get("service") == "MqlDownloader"
    assert health.get("instance") == "Ryzen7950X", "Unexpected source instance/datastore context"
    catalog, catalog_ids = catalog_snapshot(allow_preserved_labels=source_snapshot)
    assert health.get("providers") == catalog["locally_offered_total"], "Health/catalogue provider totals disagree"
    observed = json.loads((REVIEW / "mql_corrected_watch_status.json").read_text(encoding="utf-8"))
    assert observed["job_id"] == JOB
    urls = observed["observed_list_urls"]
    scope = {}
    for platform, journal_name in (("mt4", "mql4"), ("mt5", "mql5")):
        followups = [entry for entry in urls if entry["platform"] == platform and entry["page"] >= 2]
        assert followups and all(entry["orderby"] == "subscribers" and "/list/page" in entry["url"] for entry in followups), "No actual sorted follow-up URL proof: " + platform
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
        # Validate every successful export of this exact new job, including
        # later pages. Never credit old files or rely on a three-file sample.
        selected = success_ids
        seen = set()
        for index, sid in selected:
            if sid in seen:
                continue
            seen.add(sid)
            assert (platform, str(sid)) in catalog_ids, "A fresh successful provider is missing from the local catalogue"
            directory = Path("C:/Forex/MqlAnalyzer/download") / platform
            file_info = json.loads(get(f"providers/{sid}/{platform}/trades?limit=1"))
            assert str(file_info["signalId"]) == str(sid) and file_info["version"] == platform
            filename = file_info["file"]["name"]
            assert Path(filename).name == filename and filename.lower().endswith(".csv")
            path = directory / filename
            assert path.resolve().parent == directory.resolve() and path.is_file()
            assert path.stat().st_mtime >= START.timestamp(), "An old file was reused as a fresh generation"
            before = path.read_bytes()
            if bound_generations is not None:
                prior = bound_generations[(platform, sid)]
                assert sha(before) == prior["csv_sha256"], "Published source generation changed after saved job completion"
            exported = get(f"providers/{sid}/{platform}/trades.csv")
            assert before == exported and path.read_bytes() == before
            metrics = json.loads(get(f"providers/{sid}/{platform}/metrics"))
            last_modified = dt.datetime.fromisoformat(metrics["file"]["lastModified"])
            if last_modified.tzinfo is None:
                last_modified = last_modified.astimezone()
            assert last_modified.timestamp() >= START.timestamp(), "Converted metrics predate this successful run"
            if bound_generations is not None:
                assert sha(json.dumps(metrics, sort_keys=True, ensure_ascii=False).encode()) == prior["metrics_response_sha256"], "Metrics changed after saved completion"
            rows = list(csv.reader(io.StringIO(before.decode("utf-8-sig")), delimiter=";"))
            assert rows and rows[0][0] == "Time"
            parsed = load_export(str(path))
            assert path.read_bytes() == before, "Source CSV changed while being parsed"
            generations.append({"platform": platform, "signal_id": sid, "provider_index_in_run": index,
                                "csv_name": path.name, "csv_sha256": sha(before), "rest_sha256": sha(exported),
                                "csv_mtime_utc": dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat(),
                                "raw_csv_rows_without_header": len(rows) - 1,
                                "rest_json_csv_rows": file_info["total"],
                                "scanner_parsed_trades": len(parsed.trades),
                                "scanner_parsed_balance_events": len(parsed.balances),
                                "scanner_parsed_pending_orders": len(parsed.pendings),
                                "scanner_parser_format": parsed.source_format,
                                "metrics_filename": metrics["file"]["name"], "metrics_last_modified": metrics["file"]["lastModified"],
                                "metrics_response_sha256": sha(json.dumps(metrics, sort_keys=True, ensure_ascii=False).encode()),
                                "account_currency": metrics.get("metrics", {}).get("Currency")})
    result = {"verified_utc": now(), "job_id": JOB, "source": "mql5", "status": status,
              "api_health": {key: health.get(key) for key in ("status", "service", "instance", "apiVersion")},
              "catalog_verification": catalog,
              "scope_proof": scope, "fresh_source_file_generations": generations,
              "source_generation_mechanism": "Direct source files with fresh mtime and exact REST-byte SHA; no atomic generation pointer is claimed"}
    write("mql_corrected_source_verification.json" if source_snapshot else "mql_corrected_final_verification.json", result)
    return result


def append(verified, status_label="fertig", note=None):
    assert verified["catalog_verification"]["catalog_identity_accepted"], "API catalogue identity guard is not deployed/accepted"
    sources = [source for source in db.list_quellen(nur_aktiv=True) if source["kuerzel"] == "mql5"]
    assert len(sources) == 1
    source = sources[0]
    assert source["quellen_uid"] == "0a8faef1-a341-4899-a199-a87166b69079"
    status = verified["status"]
    result = status["ergebnis"]
    note = note or "Pagination-Fix real abgenommen: /list/pageN sortiert und >48 erfolgreiche Provider je Plattform; alle erfolgreichen CSVs mit REST-Hashes, Scannerparser, frischen Metrics und lokalem Gesamtkatalog geprüft."
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
    write("mql_corrected_stufe0_receipt.json", receipt)
    return receipt


def main():
    phase = sys.argv[1]
    if phase == "after-guard":
        # The normal idle restart clears the source's in-memory job. Bind its
        # saved successful end to unchanged file hashes and the new local API.
        pid, expected_sha = int(sys.argv[2]), sys.argv[3]
        assert pid != 1663784 and re.fullmatch(r"[0-9a-f]{64}", expected_sha)
        process = psutil.Process(pid)
        assert Path(process.cwd()).resolve() == (ROOT.parent / "MqlDownloader").resolve()
        jars = [arg for arg in process.cmdline() if arg.lower().endswith(".jar")]
        assert len(jars) == 1
        jar = Path(jars[0]); jar = jar if jar.is_absolute() else Path(process.cwd()) / jar
        assert sha(jar.read_bytes()) == expected_sha
        assert any(c.status == psutil.CONN_LISTEN and c.laddr.port == 8089 for c in process.net_connections(kind="tcp"))
        assert json.loads(get("update/status")).get("state") == "idle", "A new source writer/job is active"
        saved = json.loads((REVIEW / "mql_corrected_source_verification.json").read_text(encoding="utf-8"))
        assert saved["job_id"] == JOB
        bound = {(row["platform"], row["signal_id"]): row for row in saved["fresh_source_file_generations"]}
        verified = verify(saved_status=saved["status"], bound_generations=bound)
        assert len(verified["fresh_source_file_generations"]) == len(bound)
        verified["after_guard_process"] = {"pid": pid, "jar_sha256": expected_sha,
                                           "job_state_after_normal_restart": "idle", "source_generations_unchanged": True}
        write("mql_corrected_final_verification.json", verified)
        print(json.dumps(append(verified), indent=2))
        return
    assert phase in ("verify-source", "verify", "append")
    if phase == "verify-source":
        verified = verify(source_snapshot=True)
        print(json.dumps({"job_id": JOB, "verified_generations": len(verified["fresh_source_file_generations"]),
                          "catalog_identity_accepted": verified["catalog_verification"]["catalog_identity_accepted"]}, indent=2))
        return
    verified = verify()
    if phase == "verify":
        print(json.dumps({"job_id": JOB, "verified_generations": len(verified["fresh_source_file_generations"])}, indent=2))
        return
    print(json.dumps(append(verified), indent=2))


if __name__ == "__main__":
    main()
