"""GET catalogue identity comparison against read-only scanner snapshot."""
import collections
import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

snapshot = sys.argv[1]
connection = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)
with urllib.request.urlopen("http://127.0.0.1:8089/api/v1/providers?limit=500") as response:
    live = json.load(response)
with urllib.request.urlopen("http://127.0.0.1:8089/api/v1/providers?limit=500&minSubscribers=0") as response:
    including_zero = json.load(response)
counts = collections.Counter(str(i["signalId"]) for i in live["items"])
duplicate_ids = {sid: [i["version"] for i in live["items"] if str(i["signalId"]) == sid]
                 for sid, n in counts.items() if n > 1}
stored = {(str(r[0]), r[1]) for r in connection.execute("SELECT signal_id,version FROM katalog_signale WHERE quelle='mql5'")}
live_ids = {(str(i["signalId"]), i["version"]) for i in live["items"]}
result = {"live_total": live["total"], "live_distinct_ids": len(counts),
          "including_zero_subscribers": including_zero["total"], "duplicate_ids_versions": duplicate_ids,
          "stored_total": len(stored), "live_missing_from_stored": sorted(live_ids - stored),
          "stored_missing_from_live": sorted(stored - live_ids)}
target = Path(__file__).with_name("downloads_catalogue_identity.json")
target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2))
