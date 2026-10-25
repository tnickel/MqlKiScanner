"""Recalculate existing FT exposures with live H1 data; no signal verdict writes.

Uses immutable, hash-verified snapshots where available, schema-2 owners and
the common scan lock. Only aggregate contract/conversion evidence is exported.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from mqlkiscanner import config, fx_rates
from mqlkiscanner.analysis_version import FORENSICS_VERSION
from mqlkiscanner.agenten.lock import lauf_lock
from mqlkiscanner.agenten.marktdata import terminal_laueft
from mqlkiscanner.forensics import exposure
from mqlkiscanner.kursdaten import KursDaten
from mqlkiscanner.parser import load_export

IDS = (178177, 1231244, 504191, 692325, 762452)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    settings = config.load_settings()
    paths = [p for p in settings["kursdaten_terminals"] if Path(p).parent.name.casefold() == "vantage"]
    assert len(paths) == 1
    path = paths[0]
    result = {"started_utc": datetime.now(timezone.utc).isoformat(),
        "forensics_version": FORENSICS_VERSION, "database_access": "read_only",
        "signal_verdict_writes": False, "trade_updates": False,
        "inputs": "existing SHA-verified FT snapshots; source history completeness not certified here",
        "fx_cache_sha256": digest(Path(fx_rates.csv_path())),
        "registry_sha256": digest(config.CONTRACT_SPECS_FILE), "signals": []}
    with lauf_lock(config.DATA_DIR):
        result["terminal_was_running"] = terminal_laueft(path)
        provider = KursDaten({**settings, "kursdaten_terminals": [path]})
        try:
            ok, message = provider.starten()
            result["connection_message"] = message
            assert ok, message
            result["reference_feed"] = provider._feed_identitaet()[1]
            with sqlite3.connect((config.DATA_DIR / "mqlkiscanner.db").resolve().as_uri()+"?mode=ro", uri=True) as conn:
                conn.row_factory = sqlite3.Row
                for sid in IDS:
                    rows = [dict(r) for r in conn.execute(
                        "SELECT a.*,i.quellen_uid FROM quellen_artefakte a JOIN datenquellen q ON q.id=a.quelle_id "
                        "JOIN signal_identitaeten i ON i.signal_ref=a.signal_ref "
                        "WHERE q.kuerzel='vant' AND i.externe_id=? AND a.version='vantage'", (sid,))]
                    artifacts = {r["art"]: r for r in rows}
                    trade = artifacts["trades"]
                    snapshot = ROOT / "data/trade_snapshots" / (trade["sha256"] + ".csv")
                    chosen = snapshot if snapshot.exists() else Path(trade["path"])
                    assert digest(chosen) == trade["sha256"]
                    parsed = load_export(str(chosen))
                    item = {"quelle": "vant", "external_id": sid, "quellen_uid": trade["quellen_uid"],
                        "trade_sha256": trade["sha256"], "trade_count": len(parsed.trades)}
                    try:
                        calculated = exposure.run(parsed, broker="vantage", kursanbieter=provider)
                        item.update({k: calculated[k] for k in (
                            "contract_complete", "conversion_complete", "temporal_risk_available",
                            "capital_history_complete", "shock_usd", "fx_conversion", "warnings")})
                        item["status"] = "computed"
                    except Exception as error:
                        item.update(status="blocked", reason=str(error), error_type=type(error).__name__)
                    result["signals"].append(item)
                    print(json.dumps({k:v for k,v in item.items() if k != "fx_conversion"}, ensure_ascii=True), flush=True)
        finally:
            provider.beenden()
            result["terminal_running_after_cleanup"] = terminal_laueft(path)
    result["finished_utc"] = datetime.now(timezone.utc).isoformat()
    target = Path(__file__).with_suffix(".json")
    target.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    assert result["terminal_running_after_cleanup"] is False


if __name__ == "__main__":
    main()
