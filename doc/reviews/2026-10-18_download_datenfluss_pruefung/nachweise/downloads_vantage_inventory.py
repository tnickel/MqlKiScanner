"""Read-only metadata inventory, no CSV content persisted or changed."""
import collections
import json
import urllib.request
from pathlib import Path

here = Path(__file__).resolve().parent
repo = here.parents[3]
store = repo.parent / "vantage/data/trades"
versions = collections.Counter()
by_id = {}
for path in store.glob("*.meta"):
    metadata = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8-sig").splitlines() if "=" in line)
    versions[(metadata.get("version"), metadata.get("timeBasis"))] += 1
    by_id[path.stem.removeprefix("trades_")] = (path, metadata)
page = json.load(urllib.request.urlopen("http://127.0.0.1:8092/api/v1/providers?limit=500", timeout=10))
current = collections.Counter()
for item in page["items"]:
    found = by_id.get(str(item["signalId"]))
    if not found:
        current["missing_meta"] += 1
        continue
    path, metadata = found
    current["utc_v2" if metadata.get("version") == "2" and metadata.get("timeBasis") == "UTC" else "legacy"] += 1
    current["csv_present"] += path.with_suffix(".csv").exists()
result = {"meta_count": len(by_id), "versions": [{"version": key[0], "timeBasis": key[1], "count": n} for key, n in versions.items()],
          "live_catalogue": {"count": page["total"], **current}}
target = here / "downloads_vantage_metadata.json"
target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
