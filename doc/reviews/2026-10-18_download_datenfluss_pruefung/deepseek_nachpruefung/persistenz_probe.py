"""Read-only, consistent DB/code cross-check; emit aggregates, never raw records."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from mqlkiscanner import config, db, pipeline  # noqa: E402
from mqlkiscanner.analysis_version import FORENSICS_VERSION  # noqa: E402


def distribution(values):
    return dict(sorted(Counter(str(value) for value in values).items()))


def main():
    db_path = ROOT / "data/mqlkiscanner.db"
    uri = db_path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, isolation_level=None) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")

        @contextmanager
        def read_connection():
            yield connection

        # Reuse production read/transform functions against the same read-only
        # transaction. Suppress schema initialization and PDF materialization.
        with patch.object(db, "_connect", read_connection), patch.object(db, "init_db", lambda: None):
            settings = config.load_settings()
            catalog = db.list_catalog()
            studies = db.list_equity_studien()
            results = pipeline.results_from_db(settings, catalog_rows=catalog,
                                              studien=studies, materialize_pdfs=False)
            result_rows = [row.to_row() for row in results]
            raw_catalog = [dict(row) for row in connection.execute(
                "SELECT quelle,signal_id FROM katalog_signale")]
            workflow_keys = {(str(row.get("quelle") or "mql5"), int(row["signal_id"]))
                             for row in catalog}
            catalog_keys = {(str(row["quelle"] or "mql5"), int(row["signal_id"]))
                            for row in raw_catalog}
            claims = {}
            for source, signal_id in workflow_keys | catalog_keys:
                claims.setdefault(signal_id, set()).add(source)
            forensic_rows = [dict(row) for row in connection.execute(
                "SELECT signal_id,json,updated_at FROM forensik")]
            forensic_payloads = [json.loads(row["json"]) for row in forensic_rows]
            table_names = ["signals", "forensik", "katalog_signale", "trade_files",
                           "quellen_artefakte", "equity_studien"]
            counts = {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                      for name in table_names}
            updates = [dict(row) for row in connection.execute(
                "SELECT json_extract(json,'$.version') AS version, "
                "substr(updated_at,1,10) AS stored_day, COUNT(*) AS count "
                "FROM forensik GROUP BY version,stored_day ORDER BY version,stored_day")]
            stale_ids = {row.id for row in results if row.forensik_stale}
            raw_by_id = {int(row["signal_id"]): row for row in catalog}
            not_stale = [raw_by_id[row.id] for row in results if not row.forensik_stale]
            aggregate = {
                "read_utc": datetime.now(timezone.utc).isoformat(),
                "access": {"uri_mode": "ro", "query_only": connection.execute(
                    "PRAGMA query_only").fetchone()[0], "single_read_transaction": True,
                    "schema_initialization_suppressed": True, "materialize_pdfs": False,
                    "network_or_terminal_calls": False},
                "forensics_version": FORENSICS_VERSION,
                "risk_settings_only": {key: settings.get(key) for key in
                    ["schranke_eq_dd_pct", "min_ertrag_pct_monat", "min_calmar_jahr"]},
                "counts": counts,
                "workflow_sources": distribution(row["quelle"] for row in catalog),
                "catalog_sources": distribution(row["quelle"] for row in raw_catalog),
                "identity_union": {"same_source_id_overlap": len(workflow_keys & catalog_keys),
                    "catalog_without_workflow": len(catalog_keys - workflow_keys),
                    "union_rows": len(workflow_keys | catalog_keys),
                    "cross_source_numeric_collisions": sum(len(value) > 1 for value in claims.values())},
                "workflow_forensics": {
                    "versions": distribution(row.get("version") for row in forensic_payloads),
                    "version_count_sum": len(forensic_payloads),
                    "completeness_flags": distribution(row.get("vollstaendig") for row in forensic_payloads),
                    "stored_dates_by_version": updates},
                "independent_studies": {"current_readable_studies": len(studies),
                    "stored_versions": [list(row) for row in connection.execute(
                        "SELECT forensics_version,COUNT(*) FROM equity_studien GROUP BY forensics_version")]},
                "actual_reload": {"rows": len(results),
                    "ampel": distribution(row.ampel for row in results),
                    "stale": len(stale_ids),
                    "current_complete": sum(bool(row.forensik_vorhanden) for row in results),
                    "not_stale": len(not_stale),
                    "not_stale_missing_forensic_payload": sum(not bool(row.get("forensik")) for row in not_stale),
                    "not_stale_incomplete_forensic_payload": sum(bool(row.get("forensik")) and
                        row["forensik"].get("vollstaendig") is False for row in not_stale),
                    "green_or_yellow": sum(row.ampel in {"🟢", "🟡"} for row in results),
                    "nonempty_fields": {key: sum(row.get(key) is not None for row in result_rows)
                        for key in ["Score", "Max-Drawdown %", "TrueRetDD", "TrueRetDD (Vorbehalt)"]},
                    "separate_study_display_values": sum(row.studie_anzeige_dd_pct is not None for row in results),
                    "account_currency": distribution(row.account_currency for row in results)},
                "code_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                    ["src/mqlkiscanner/pipeline.py", "src/mqlkiscanner/db.py",
                     "src/mqlkiscanner/app_ui.py", "src/mqlkiscanner/downloader_sync.py"]},
            }
        connection.execute("ROLLBACK")
    print(json.dumps(aggregate, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
