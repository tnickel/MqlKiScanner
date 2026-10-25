"""Offline exposure comparison; original DB/CSVs/FX/registry remain read-only."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from mqlkiscanner import fx_rates, ingest, symbols
from mqlkiscanner.forensics import exposure
from mqlkiscanner.models import ParsedExport
from mqlkiscanner.parser import load_export

IDS = (178177, 1231244, 504191, 692325, 762452)
FT = {"GER40FT", "UK100FT"}
FX_PATH = ROOT / "data/fx_rates/eurofxref-hist.csv"
DB_PATH = ROOT / "data/mqlkiscanner.db"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    # Runtime patches below are confined to this short-lived audit process.
    # No production service is connected and no fallback may fetch rates.
    def forbidden(*args, **kwargs):
        raise AssertionError("Network is forbidden in this offline calculation")
    import requests
    requests.sessions.Session.request = forbidden
    cached_table = fx_rates._parse_csv(FX_PATH.read_text(encoding="utf-8-sig"), strict=True)
    latest = cached_table["USD"][0][-1]
    # Keep the production parser and cross-rate/date/walkback implementation;
    # replace only its loader so that a stale cache cannot trigger a refresh.
    fx_rates.load = lambda: cached_table

    git = subprocess.run(["git", "show", "HEAD:data/contract_specs.json"], cwd=ROOT, capture_output=True, check=True)
    before = json.loads(git.stdout)["symbols"]
    after = json.loads((ROOT / "data/contract_specs.json").read_text(encoding="utf-8"))["symbols"]
    result = {"observed_utc": datetime.now(timezone.utc).isoformat(), "read_only": True,
              "network_requests": 0, "terminals_used": False, "equity_reconstruction_run": False,
              "models": {"before_registry_sha256": hashlib.sha256(git.stdout).hexdigest(),
                         "after_registry_sha256": digest(ROOT / "data/contract_specs.json"),
                         "before": {k: {f: before[k][f] for f in ("contract_size", "quote_currency", "stress_move")}
                                    for k in ("GER40FT_VANTAGE", "UK100FT_VANTAGE")},
                         "after": {k: {f: after[k][f] for f in ("contract_size", "quote_currency", "stress_move")}
                                   for k in ("GER40FT_VANTAGE", "UK100FT_VANTAGE")}},
              "fx_cache_sha256": digest(FX_PATH), "fx_latest_date": latest,
              "fx_policy": f"production fx_rates.usd_per, cached ECB only, max {fx_rates.MAX_WALKBACK_DAYS} calendar days, no refresh",
              "limits": ["Exposure scenarios only, no H1 equity reconstruction, Calmar or new signal verdict.",
                         "No synthetic capital injected; shock percentages unavailable without proven capital.",
                         "Existing Vantage family contract is derived by the production metrics mapper; historical original server remains unknown.",
                         "CSV event timezone is not certified; daily reference FX is a model conversion, not execution FX.",
                         "Local cached exports may be partial/legacy UTC; this audit does not renew or certify their completeness."],
              "signals": []}
    with sqlite3.connect(DB_PATH.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        for signal_id in IDS:
            entries = [dict(r) for r in conn.execute(
                "SELECT a.* FROM quellen_artefakte a JOIN datenquellen q ON q.id=a.quelle_id "
                "WHERE q.kuerzel='vant' AND a.signal_id=? AND a.version='vantage'", (signal_id,))]
            artifacts = {r["art"]: r for r in entries}
            item = {"quelle": "vant", "signal_id": signal_id, "version": "vantage"}
            result["signals"].append(item)
            try:
                trade = artifacts["trades"]
                snapshot = ROOT / "data/trade_snapshots" / (trade["sha256"] + ".csv")
                chosen = snapshot if snapshot.exists() else Path(trade["path"])
                if digest(chosen) != trade["sha256"]: raise ValueError("Trade SHA mismatch")
                metric = artifacts["metrics"]
                metric_path = Path(metric["path"])
                if digest(metric_path) != metric["sha256"]: raise ValueError("Metrics SHA mismatch")
                answer = json.loads(metric_path.read_text(encoding="utf-8"))
                metrics = answer.get("metrics") or {}
                stats = ingest.metrics_zu_stats(answer, quelle_kuerzel="vant", quelle_version="vantage")
                broker = stats.get("broker_server")
                item.update({"trade_sha256": trade["sha256"], "metrics_sha256": metric["sha256"],
                             "input_kind": "existing_immutable_snapshot" if chosen == snapshot else "verified_existing_artifact_cache",
                             "metrics_broker_label": metrics.get("Broker"), "effective_broker_profile": broker,
                             "original_provider_server": None,
                             "reported_history_complete": metrics.get("TradeHistoryComplete"),
                             "reported_truncated": metrics.get("TradesTruncated")})
                parsed = load_export(str(chosen))
                selected = [t for t in parsed.trades if t.symbol.upper() in FT]
                item.update({"all_trade_count": len(parsed.trades),
                             "ft_trade_counts": dict(Counter(t.symbol.upper() for t in selected)),
                             "ft_first_open": min(t.open_time for t in selected).isoformat(),
                             "ft_last_close": max(t.close_time for t in selected).isoformat()})
                for label, registry in (("before", before), ("after", after)):
                    symbols.load_specs = lambda registry=registry: registry
                    summary = {}
                    for scope, sample in (("entire_cached_export", parsed),
                                          ("ft_positions_only_without_capital", ParsedExport(str(chosen), parsed.source_format, selected))):
                        try:
                            calculated = exposure.run(sample, broker=broker)
                            keys = ("peak_open_positions", "peak_net_lots", "shock_usd", "conversion_complete",
                                    "contract_complete", "temporal_risk_available", "capital_history_complete", "shock_pct_max")
                            summary[scope] = {key: calculated.get(key) for key in keys}
                            summary[scope]["status"] = "computed"
                        except (ValueError, KeyError) as error:
                            summary[scope] = {"status": "blocked", "reason": str(error)}
                    item[label] = summary
            except (OSError, ValueError, KeyError) as error:
                item["status"] = "blocked"
                item["reason"] = str(error)
    target = Path(__file__).with_suffix(".json")
    target.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
