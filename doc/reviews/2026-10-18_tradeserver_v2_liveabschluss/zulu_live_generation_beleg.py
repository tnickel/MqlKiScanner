"""Public hashes/counts of immutable selected generations; no raw trades/amounts."""
import csv
import datetime as dt
import hashlib
import io
import json
import sys
from pathlib import Path
import urllib.request

REVIEW = Path(__file__).resolve().parent
ROOT = REVIEW.parents[2]
REPO = ROOT.parent / "zulumonitor"
DATA = REPO / "data"
sha = lambda blob: hashlib.sha256(blob).hexdigest()
headers = {}
config = DATA / "rest_api.json"
if config.is_file():
    token = json.loads(config.read_text(encoding="utf-8-sig")).get("token", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token


def fetch(path):
    return urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8093" + path, headers=headers), timeout=15).read()


def props(path):
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8-sig").splitlines() if "=" in line)


records = []
for pointer in sorted((DATA / "trades").glob("trades_*.current")):
    before = pointer.read_bytes()
    selected = props(pointer)
    provider = int(selected["provider"])
    generation_id = selected["generation"]
    assert len(generation_id) == 36 and all(ch in "0123456789abcdef-" for ch in generation_id)
    generation = DATA / "trades/.generations" / str(provider) / generation_id
    csv_blob = (generation / "trades.csv").read_bytes()
    meta = props(generation / "archive.meta")
    receipt = props(generation / "history.receipt")
    assert meta["sha256"] == receipt["sha256"] == sha(csv_blob)
    assert int(receipt["provider"]) == provider
    body = json.loads(fetch(f"/api/v1/providers/{provider}/zulu/metrics"))
    metrics = body["metrics"]
    fields = ("CatalogTrades", "TradesStored", "TradesTotalAvailable", "TradesTruncated", "TradesHistoryComplete",
              "TradesHistoryObservedUtc", "TradesDownloaded", "TradesCompletenessNote")
    csv_export = fetch(f"/api/v1/providers/{provider}/zulu/trades.csv")
    export_rows = list(csv.reader(io.StringIO(csv_export.decode("utf-8-sig")), delimiter=";"))
    assert export_rows and export_rows[0][0] == "Time"
    assert len(export_rows) - 1 == int(meta["count"]) == metrics["TradesStored"]
    assert pointer.read_bytes() == before, "Selected generation changed during probe; retry"
    records.append({"provider_id": provider, "generation": generation_id, "pointer_sha256": sha(before),
                    "csv_sha256": sha(csv_blob), "meta_sha256": sha((generation / "archive.meta").read_bytes()),
                    "receipt_sha256": sha((generation / "history.receipt").read_bytes()),
                    "archive_rows": int(meta["count"]), "history_receipt": receipt,
                    "rest_metrics": {field: metrics.get(field) for field in fields},
                    "export_csv_rows": len(export_rows) - 1, "export_csv_sha256": sha(csv_export),
                    "legacy_flat_csv_unchanged_since_shutdown_backup": None})
    backup = Path(json.loads((REVIEW / "zulu_build_snapshot.json").read_text())["snapshot_jar"]).parent / "data_after_old_shutdown"
    legacy = DATA / f"trades/trades_{provider}.csv"
    old = backup / legacy.relative_to(DATA)
    if legacy.is_file() and old.is_file():
        records[-1]["legacy_flat_csv_unchanged_since_shutdown_backup"] = sha(legacy.read_bytes()) == sha(old.read_bytes())

status = json.loads(fetch("/api/v1/update/status"))
out = {"observed_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "new_update_status": status,
       "committed_generations": records, "whole_top200_update_complete": status.get("state") == "done"
       and status.get("done") == 200 and not status.get("ergebnis", {}).get("tradelistenAbgebrochen")
       and status.get("ergebnis", {}).get("tradelistenFehler") == 0}
output_name = sys.argv[1] if len(sys.argv) > 1 else "zulu_live_generation_beleg.json"
assert Path(output_name).name == output_name and output_name.startswith("zulu_") and output_name.endswith(".json")
(REVIEW / output_name).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"observed_utc": out["observed_utc"], "job_id": status.get("jobId"), "job_done": status.get("done"),
                  "generation_count": len(records), "whole_top200_update_complete": out["whole_top200_update_complete"],
                  "providers": [{"id": r["provider_id"], "rows": r["archive_rows"], "history_pages": r["history_receipt"]["pages"],
                                 "history_end": r["history_receipt"]["complete"]} for r in records]}, indent=2))
