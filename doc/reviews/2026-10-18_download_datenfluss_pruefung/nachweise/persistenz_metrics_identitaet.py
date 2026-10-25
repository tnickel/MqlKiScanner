"""Read cached Metrics JSONs without emitting response contents or paths."""
import collections
import json
import sqlite3
import sys
from pathlib import Path


def inspect(snapshot):
    connection = sqlite3.connect(Path(snapshot).resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    counts = collections.Counter()
    sources = collections.defaultdict(collections.Counter)
    exceptions = []
    for row in connection.execute(
        "SELECT a.quelle_id,a.signal_id,a.version,a.path,q.kuerzel FROM quellen_artefakte a "
        "LEFT JOIN datenquellen q ON q.id=a.quelle_id WHERE art='metrics' "
        "ORDER BY a.quelle_id,a.signal_id,a.version"):
        counts["metrics_artifacts"] += 1
        source = row["kuerzel"]
        sources[source]["metrics_artifacts"] += 1
        issues = []
        try:
            response = json.loads(Path(row["path"]).read_text(encoding="utf8"))
            counts["readable_json"] += 1
            if not isinstance(response, dict):
                issues.append("root_not_object")
            else:
                counts["json_objects"] += 1
                counts["metrics_is_object" if isinstance(response.get("metrics"), dict) else "metrics_missing_or_not_object"] += 1
                if response.get("signalId") is None:
                    counts["signal_id_missing"] += 1
                    sources[source]["signal_id_missing"] += 1
                elif str(response["signalId"]) == str(row["signal_id"]):
                    counts["signal_id_match"] += 1
                    sources[source]["signal_id_match"] += 1
                else:
                    issues.append("signal_id_mismatch")
                if not response.get("version"):
                    counts["version_missing"] += 1
                    sources[source]["version_missing"] += 1
                elif str(response["version"]) == row["version"]:
                    counts["version_match"] += 1
                    sources[source]["version_match"] += 1
                else:
                    issues.append("version_mismatch")
        except Exception as error:
            issues.append("read_or_json_error:" + type(error).__name__)
        for issue in issues:
            counts[issue] += 1
            sources[source][issue] += 1
        if issues:
            exceptions.append({"source": source, "signal_id": row["signal_id"], "version": row["version"], "issues": issues})
    connection.close()
    return {
        "scope": "Consistent SQLite snapshot mode=ro, cached Metrics files read only, counts and public signal IDs only",
        "counts": dict(counts), "by_source": {source: dict(values) for source, values in sources.items()},
        "exceptions": exceptions,
    }


if __name__ == "__main__":
    print(json.dumps(inspect(sys.argv[1]), ensure_ascii=True, indent=2))
