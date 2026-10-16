"""Independent read-only probes; no terminals, network or production storage."""
import hashlib
import json
import sys
import sqlite3
import tempfile
from unittest.mock import patch, Mock
from pathlib import Path

audit = Path(__file__).resolve().parent
scanner = audit.parents[1] / "SignalKiScanner"
sys.path.insert(0, str(scanner / "src"))
from mqlkiscanner import pipeline, equity_studie_ui
from mqlkiscanner import db, config
from mqlkiscanner.analysis_version import FORENSICS_VERSION
from mqlkiscanner.mql5 import signal_stats

results = {}
for name, fields in {
    "mixed_money_rows": [("Balance", "1100 USD"), ("Initial Deposit", "1000 USC")],
    "unitless_money_row": [("Balance", "1100 USD"), ("Initial Deposit", "1000")],
    "usd_rows_and_unrelated_eur_text": [("Balance", "1100 USD"), ("Initial Deposit", "1000 USD")],
}.items():
    html = "".join(f'<div class="s-list-info__item"><div class="s-list-info__label">{label}:</div>'
                   f'<div class="s-list-info__value">{value}</div></div>' for label, value in fields)
    html += "<p>Unrelated broker USD / EUR / USC</p>"
    stats = signal_stats.parse_detail_html(html)
    results[name] = {k: stats[k] for k in ("account_currency", "balance_usd", "initial_deposit_usd")}

study = {"trades_sha": "synthetic-sha", "basislos": False, "virtuell": False,
         "dd_usd": 42, "report": {"equity_dd_pct_raw": 4, "verlaesslich": True}}
for unit in (None, "USC", "USD"):
    result = pipeline.ScanResult(id=999001, quelle="mql5", account_currency=unit,
                                 trades_sha256="synthetic-sha", forensik_stale=True)
    pipeline.studie_anwenden(result, {999001: study})
    results[f"old_study_{unit}"] = {
        "true_dd_usd": result.true_dd_usd, "display_dd_pct": result.studie_anzeige_dd_pct,
    }
usd = pipeline.ScanResult(id=999001, quelle="mql5", account_currency="USD", trades_sha256="synthetic-sha")
usc = pipeline.ScanResult(id=999001, quelle="mql5", account_currency="USC", trades_sha256="synthetic-sha")
results["ui_cache_currency_isolated"] = equity_studie_ui._cache_key(usd) != equity_studie_ui._cache_key(usc)
for version in (FORENSICS_VERSION - 1, FORENSICS_VERSION):
    tagged = {**study, "report": {**study["report"], "account_currency": "USD", "analysis_version": version}}
    result = pipeline.ScanResult(id=999001, quelle="mql5", account_currency="USD",
                                 trades_sha256="synthetic-sha", forensik_stale=True)
    pipeline.studie_anwenden(result, {999001: tagged})
    results[f"tagged_study_model_{version}"] = {
        "true_dd_usd": result.true_dd_usd, "display_dd_pct": result.studie_anzeige_dd_pct}

with tempfile.TemporaryDirectory(dir=audit, prefix="fin7_db_") as temporary:
    with patch.object(db, "DB_PATH", Path(temporary) / "synthetic.sqlite"):
        db.init_db()
        db.store_equity_studie(999001, "synthetic-sha", study["report"], dd_usd=42)
        results["db_current_study_visible"] = db.get_equity_studie(999001) is not None
        with sqlite3.connect(db.DB_PATH) as connection:
            connection.execute("UPDATE equity_studien SET forensics_version=?", (FORENSICS_VERSION - 1,))
        connection.close()
        results["db_old_model_study_hidden"] = (
            db.get_equity_studie(999001) is None and 999001 not in db.list_equity_studien())

with patch.object(config, "load_known_signals", return_value={}), \
     patch.object(db, "init_db"), \
     patch.object(db, "get_signal", return_value={"platform": "MT5", "quelle": "mql5"}), \
     patch.object(signal_stats, "fetch_signal_stats", side_effect=AssertionError("No HTTP allowed")) as stats_call:
    result = pipeline.ScanPipeline({})._analyze_candidate_once(None,
            {"id": 999001, "platform": "MT4"}, lambda _: None)
    results["persisted_platform_collision_blocked_before_http"] = (
        "Kollision" in result.fehler and not result.persisted_this_run and stats_call.call_count == 0)
    reasons=[]
    candidates = pipeline.ScanPipeline({}).build_candidates([
        {"id":999002,"platform":"MT4","abonnenten":1,"wochen":52},
        {"id":999002,"platform":"MT5","abonnenten":1,"wochen":52}], lambda _: None, reasons)
    results["simultaneous_platform_collision_rejected"] = not candidates and len(reasons)==2
results["source_sha256"] = {
    relative: hashlib.sha256((scanner / "src/mqlkiscanner" / relative).read_bytes()).hexdigest()
    for relative in ("pipeline.py", "equity_studie_ui.py", "mql5/signal_stats.py")
}
(audit / (sys.argv[1] if len(sys.argv)>1 else "fin7_peer_probe_results.json")).write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results, indent=2))
