"""Explicit MQL-only retry after tested subscriber metadata conversion repair.

Uses the existing source-update state machine and preserves the first failed
job. Other source jobs are neither restarted nor adopted by this retry.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from mqlkiscanner import client_updates, config, db


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    here = Path(__file__).resolve().parent
    source = next(q for q in db.list_quellen(nur_aktiv=True) if q["kuerzel"] == "mql5")
    settings = dict(config.load_settings())
    settings["update_katalog_max_alter_h"] = 72
    started = datetime.now(timezone.utc).isoformat()

    def progress(row):
        (here / "sources_mql_conversion_update_progress.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")

    result = client_updates._update_eine_quelle(
        source, settings=settings, log=lambda message: print(message, flush=True),
        on_fortschritt=progress, gestopft=lambda: False,
        bereit_warten_s=60, poll_s=5, backoff_s=30, timeout_s=7200, login_timeout_s=600,
    )
    (here / "sources_mql_conversion_update_result.json").write_text(
        json.dumps({"started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
                    "catalogue_max_age_h": 72, "source": result}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
