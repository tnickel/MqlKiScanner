"""Synthetic foreign-review verification; all DB writes use TemporaryDirectory."""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from mqlkiscanner import db, katalog


def attempt(call):
    try:
        call()
        return {"blocked": False}
    except ValueError as error:
        return {"blocked": True, "error_class": type(error).__name__}


def run():
    with tempfile.TemporaryDirectory(prefix="foreign_identity_review_") as directory, \
            patch.object(db, "DB_PATH", Path(directory) / "isolated.db"):
        db.init_db()
        db.upsert_signal(123, name="Original", quelle="mql5")
        scan = attempt(lambda: db.store_scan_result(123, {"name": "Replacement"}))
        low_level = attempt(lambda: db.upsert_signal(123, name="Replacement"))
        stored = db.get_signal(123)
        other_source = attempt(lambda: db.upsert_signal(123, name="Other", quelle="pelik"))
        with db._connect() as connection:
            key_columns = [row["name"] for row in connection.execute("PRAGMA table_info(signals)") if row["pk"]]
        rows = [
            {"signal_id": 7, "quelle": "mql5", "platform": "mt5", "version": "mql5", "name": "MQL"},
            {"signal_id": 7, "quelle": "vant", "platform": "vantage", "version": "vantage", "name": "Vantage"},
        ]
        result, _ = katalog.katalog_resultate(gescannt=set(), studien={}, katalog_rows=rows,
                                              quellen_rows=[], artefakte={})
        return {
            "scope": "Synthetic temporary DB only; no production database, network, secrets or app startup",
            "store_scan_result_without_source": scan,
            "upsert_signal_without_source": low_level,
            "low_level_changed_name_without_claiming_source": stored["name"] == "Replacement" and stored["quelle"] == "mql5",
            "explicit_other_source": other_source,
            "signals_primary_key": key_columns,
            "catalogue_collision": {"input_identities": [[r["quelle"], r["signal_id"]] for r in rows],
                                    "displayed_identities": [[r.quelle, r.id] for r in result]},
        }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=True, indent=2))
