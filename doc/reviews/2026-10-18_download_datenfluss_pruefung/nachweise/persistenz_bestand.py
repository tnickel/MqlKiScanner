"""Read-only inventory of processing/persistence consistency.

The supplied snapshot is opened mode=ro; application reload uses its own
temporary backup because db.init_db() is a writer. Only sanitized aggregates
and public signal IDs are emitted; never CSV contents or analysis texts.
"""
from __future__ import annotations

import collections
import contextlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from mqlkiscanner import config, db, parser, pipeline, secrets_store, stats
from mqlkiscanner.analysis_version import FORENSICS_VERSION


def counted(values):
    return dict(sorted(collections.Counter(str(x) for x in values).items()))


def error_class(message):
    if not message:
        return "none"
    prefix = str(message).split(":", 1)[0]
    return prefix if prefix.isidentifier() and prefix.endswith(("Error", "Exception")) else "untyped_error"


def error_category(message):
    if not message:
        return "none"
    for token in ("Forensik unvollständig", "Schock-Test unvollständig", "Keine abgeschlossenen Trades",
                  "Export", "Kontowährung", "Connection", "HTTP", "Kapitalbasis", "historie", "Timeout"):
        if token.casefold() in str(message).casefold():
            return token
    return "other"


def main(filename):
    origin = Path(filename).resolve()
    connection = sqlite3.connect(origin.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = [dict(x) for x in connection.execute(
        "SELECT s.signal_id,s.quelle,s.platform,s.stats_json,s.updated_at,"
        "f.json AS forensics,f.updated_at AS forensics_at,t.path,t.sha256 "
        "FROM signals s LEFT JOIN forensik f USING(signal_id) "
        "LEFT JOIN trade_files t USING(signal_id) ORDER BY s.signal_id")]
    for row in rows:
        row["stats"] = json.loads(row.pop("stats_json") or "{}")
        row["forensics"] = json.loads(row["forensics"] or "null") or {}
    output = {
        "scope": "Consistent production snapshot, mode=ro; original CSVs read only; no network/secrets",
        "forensics_version": FORENSICS_VERSION,
        "signals": len(rows),
        "by_source": counted(row["quelle"] for row in rows),
        "stored_forensics_versions": counted(row["forensics"].get("version") for row in rows if row["forensics"]),
        "stored_stats_versions": counted(row["stats"].get("forensik_version") for row in rows),
        "stored_forensics_ok": counted(row["stats"].get("forensik_ok") for row in rows),
        "currency_evidence_versions": counted(row["stats"].get("account_currency_evidence_version") for row in rows),
        "currency_values": counted(row["stats"].get("account_currency") for row in rows),
        "last_error_classes": counted(error_class(row["stats"].get("last_fehler")) for row in rows),
        "last_error_categories": counted(error_category(row["stats"].get("last_fehler")) for row in rows),
        "signal_updated_range": [min(row["updated_at"] for row in rows), max(row["updated_at"] for row in rows)],
        "forensics_updated_range": [min(row["forensics_at"] for row in rows if row["forensics_at"]), max(row["forensics_at"] for row in rows if row["forensics_at"])],
        "forensics_snapshot_binding": counted(
            "missing" if not row["forensics"].get("trades_sha256") else
            "match" if row["forensics"]["trades_sha256"] == row["sha256"] else "mismatch"
            for row in rows if row["forensics"]),
    }
    failures = []
    for entry in connection.execute("PRAGMA foreign_key_check"):
        item = dict(entry)
        if item["table"] == "analyses":
            record = connection.execute("SELECT id,signal_id,kind,created_at,basis FROM analyses WHERE rowid=?", (item["rowid"],)).fetchone()
            item["record"] = dict(record)
            item["visible_in_signal_catalog_join"] = any(x["signal_id"] == record["signal_id"] for x in rows)
        failures.append(item)
    output["foreign_key_violations"] = failures
    comparisons, errors = [], []
    for row in rows:
        f = row["forensics"]
        if not row["path"] or not f:
            continue
        try:
            parsed = parser.load_export(row["path"], plattform_positions=f.get("plattform_trades"))
            calculated = stats.compute(parsed)
            mismatches = {}
            for saved, actual in (("trades_anzahl", "trades_anzahl"), ("winrate_pct", "winrate_pct"), ("max_verlustserie", "max_consecutive_losses"), ("verlustserie_usd", "max_consecutive_losses_sum")):
                if f.get(saved) is not None and f[saved] != calculated.get(actual):
                    mismatches[saved] = {"stored": f[saved], "from_current_parser": calculated.get(actual)}
            comparisons.append({
                "signal_id": row["signal_id"], "source": row["quelle"], "version": f.get("version"),
                "forensics_ok": row["stats"].get("forensik_ok"), "mismatches": mismatches,
            })
        except Exception as error:
            errors.append({"signal_id": row["signal_id"], "source": row["quelle"], "version": f.get("version"), "error_class": type(error).__name__})
    output["csv_reparse"] = {
        "checked": len(comparisons), "errors": errors,
        "exact_for_compared_fields": sum(not x["mismatches"] for x in comparisons),
        "different": [x for x in comparisons if x["mismatches"]],
        "method": "Reparse every existing scanned CSV; compare available count, winrate, max loss streak length and sum. Old versions may legitimately differ from current semantics.",
    }
    with tempfile.TemporaryDirectory(prefix="persistenz_bestand_") as directory:
        target = sqlite3.connect(str(Path(directory) / "working.db"))
        connection.backup(target)
        target.close()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(db, "DB_PATH", Path(directory) / "working.db"))
            stack.enter_context(patch.object(config, "DATA_DIR", Path(directory)))
            stack.enter_context(patch.object(secrets_store, "get_secret", lambda *a, **kw: None))
            stack.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("No network")))
            loaded = pipeline.results_from_db(materialize_pdfs=False)
        output["application_reload"] = {
            "rows": len(loaded), "ampel": counted(x.ampel for x in loaded),
            "forensics_current": sum(x.forensik_vorhanden for x in loaded),
            "forensics_stale": sum(x.forensik_stale for x in loaded),
            "errors": sum(bool(x.fehler) for x in loaded),
            "stale_but_green": [x.id for x in loaded if x.forensik_stale and x.ampel == "\U0001f7e2"],
            "current_but_missing_file": [x.id for x in loaded if x.forensik_vorhanden and (not x.trades_path or not Path(x.trades_path).is_file())],
            "currency": counted(x.account_currency for x in loaded),
        }
    connection.close()
    print(json.dumps(output, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
