"""Explicitly authorized live source updates; uses existing throttled clients.

Run from the scanner root with PYTHONPATH=src. This performs no scan, study,
terminal start or LLM request. Tokens stay inside the configured clients.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading

from mqlkiscanner import client_updates, config

HERE = Path(__file__).resolve().parent
LOCK = threading.Lock()
LATEST: dict = {}


def progress(row: dict) -> None:
    with LOCK:
        LATEST[row["kuerzel"]] = row
        payload = {"utc": datetime.now(timezone.utc).isoformat(), "sources": LATEST}
        target = HERE / "sources_live_progress.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    settings = dict(config.load_settings())
    # This one run refreshes discovery as well as histories. Production settings
    # are preserved; their ordinary 72 h catalogue window remains unchanged.
    settings["update_katalog_max_alter_h"] = 0
    started = datetime.now(timezone.utc).isoformat()
    result = client_updates.starte_alle_updates(
        settings, log=lambda text: print(text, flush=True),
        on_fortschritt=progress, timeout_s=7200, login_timeout_s=600,
    )
    final = {
        "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "request": {"target": settings.get("update_ziel_signale", 200),
                    "tradelisten": True, "katalogMaxAlterH": 0},
        "sources": result,
        "summary": client_updates.aggregat_text(result),
    }
    (HERE / "sources_live_result.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(final["summary"], flush=True)


if __name__ == "__main__":
    main()
