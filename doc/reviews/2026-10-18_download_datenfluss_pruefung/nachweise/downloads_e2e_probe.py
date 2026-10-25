"""Local GET -> RAM -> production parser, plus read-only scanner artifact checks.

Usage: python .../downloads_e2e_probe.py PATH_TO_READ_ONLY_SCANNER_DB_SNAPSHOT
Never persists raw CSV, never invokes ingest.hole_*, scans, SDKs or update POSTs.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import io
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "src"))
from mqlkiscanner import parser, ingest  # noqa: E402

SERVICES = {"mql5": (8089, "mql5"), "pelican": (8090, "pelik"),
            "robo": (8091, "robo"), "vantage": (8092, "vant"), "zulu": (8093, "zulu")}


def sanitize_normalization(value):
    if not isinstance(value, dict):
        return None
    permitted = {"status", "providerCurrency", "sourceCurrency", "sourceCurrencies", "targetCurrency",
                 "storedPnlCurrency", "method", "dateBasis", "closeDateBasis", "source",
                 "maxWalkbackDays", "fieldsScaled", "tradesStored", "note", "reason"}
    return {key: val for key, val in value.items() if key in permitted
            and (isinstance(val, (str, int, float, bool)) or val is None
                 or (isinstance(val, list) and len(val) < 30 and all(isinstance(x, str) for x in val)))}


def request(port, path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1{path}", timeout=15) as r:
            return r.status, r.read(40 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return type(exc).__name__, b""


def parsed_bytes(raw):
    # Override only the parser's file lookup. The actual productive parser runs
    # unchanged, sees a text stream, and does not touch any runtime file.
    with patch.object(parser, "open", lambda *a, **kw: io.StringIO(raw.decode("utf-8-sig")), create=True):
        parsed = parser.load_export("audit_ram.csv")
    return {"format": parsed.source_format, "trades": len(parsed.trades),
            "balances": len(parsed.balances), "costs": len(parsed.costs),
            "duplicate_rows_kept": parsed.identische_tradezeilen,
            "first_open": min((t.open_time for t in parsed.trades), default=None),
            "last_close": max((t.close_time for t in parsed.trades), default=None),
            "net": parsed.net_total}


def catalogue(port):
    items, offset = [], 0
    for _ in range(50):
        status, raw = request(port, f"/providers?limit=100&offset={offset}")
        if status != 200:
            return [], status
        page = json.loads(raw)
        block = page.get("items") or []
        items.extend(block)
        offset += len(block)
        if not block or offset >= int(page.get("total") or 0):
            break
    return items, 200


def source_probe(name, port, alias, db_path):
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    cached = {str(r["signal_id"]): dict(r) for r in connection.execute(
        "SELECT a.signal_id,a.version,a.path,a.sha256,a.fetched_at FROM quellen_artefakte a "
        "JOIN datenquellen q ON q.id=a.quelle_id WHERE q.kuerzel=? AND a.art='trades'", (alias,))}
    scanned = {str(r[0]) for r in connection.execute("SELECT signal_id FROM signals WHERE quelle=?", (alias,))}
    direct_cached = {str(r["signal_id"]): dict(r) for r in connection.execute("SELECT * FROM trade_files")}
    connection.close()
    items, status = catalogue(port)
    out = {"catalogue_http": status, "rows": len(items), "scanner_cached_rows": len(cached), "samples": []}
    if not items:
        return name, out
    # Top candidate, first two candidates already scanned, one later catalogue row.
    choices = [items[0]] + [i for i in items if str(i.get("signalId")) in scanned][:2] + [items[-2]]
    seen = set()
    for item in choices:
        signal_id, version = str(item.get("signalId")), str(item.get("version"))
        if (signal_id, version) in seen:
            continue
        seen.add((signal_id, version))
        metrics_http, metrics_raw = request(port, f"/providers/{signal_id}/{version}/metrics")
        answer = json.loads(metrics_raw) if metrics_http == 200 else {}
        metrics = answer.get("metrics") or {}
        mapped = ingest.metrics_zu_stats(answer, alias, quelle_version=version)
        sample = {"signal_id": signal_id, "version": version, "scanned_in_snapshot": signal_id in scanned,
                  "net_currency": metrics.get("Currency") if name == "mql5" else "USD",
                  "metrics_http": metrics_http, "account_currency": metrics.get("Currency"),
                  "normalization": sanitize_normalization(metrics.get("UsdNormalization")),
                  "completeness": {key: metrics.get(key) for key in ("Trades", "TradesStored", "TradesTotalAvailable",
                      "TradesTruncated", "TradeHistoryComplete", "TradeHistoryQualityReasons", "CompletenessNote", "TradesCompletenessNote")},
                  "mapped_completeness_note": mapped.get("quelle_trades_completeness_note")}
        trades_http, raw = request(port, f"/providers/{signal_id}/{version}/trades.csv")
        sample["trades_http"] = trades_http
        if trades_http == 200:
            sha = hashlib.sha256(raw).hexdigest()
            sample.update(bytes=len(raw), sha256=sha)
            try:
                sample["parsed"] = parsed_bytes(raw)
            except Exception as exc:
                sample["parse_error"] = str(exc)
            old = cached.get(signal_id)
            if old and old["version"] == version:
                old_path = Path(old["path"])
                if not old_path.is_absolute():
                    old_path = REPO / old_path
                check = {"fetched_at": old["fetched_at"], "file_exists": old_path.is_file(),
                         "db_sha_matches_live": old["sha256"] == sha}
                if old_path.is_file():
                    old_raw = old_path.read_bytes()
                    old_sha = hashlib.sha256(old_raw).hexdigest()
                    check.update(file_sha_matches_db=old_sha == old["sha256"], file_sha_matches_live=old_sha == sha)
                    try:
                        check["parsed"] = parsed_bytes(old_raw)
                    except Exception as exc:
                        check["parse_error"] = type(exc).__name__
                sample["scanner_source_cache"] = check
            direct = direct_cached.get(signal_id)
            if direct and name == "mql5":
                old_path = Path(direct["path"])
                if not old_path.is_absolute():
                    old_path = REPO / old_path
                if old_path.is_file():
                    sample["scanner_trade_file"] = {"file_sha_matches_live": hashlib.sha256(old_path.read_bytes()).hexdigest() == sha,
                                                     "fetched_at": direct["fetched_at"]}
        out["samples"].append(sample)
    return name, out


if __name__ == "__main__":
    # Parser stream monkeypatch is per-process: run sources sequentially.
    result = {name: source_probe(name, port, alias, sys.argv[1])[1] for name, (port, alias) in SERVICES.items()}
    result["probed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    (HERE / "downloads_e2e_live.json").write_text(json.dumps(result, default=str, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({name: {"rows": value["rows"], "samples": [{"id": s["signal_id"], "http": s["trades_http"],
        "parse_error": s.get("parse_error"), "parsed": s.get("parsed"), "cache": s.get("scanner_source_cache")} for s in value["samples"]]}
        for name, value in result.items() if isinstance(value, dict)}, default=str, ensure_ascii=False, indent=2))
