"""Read-only, local HTTP audit. Persists only sanitized metadata, never trades/tokens.

Run from repository root: python doc/reviews/2026-10-18_download_datenfluss_pruefung/nachweise/downloads_probe.py
No imports from application modules, no POST, no writes to runtime storage.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SERVICES = {"mql5": 8089, "pelican": 8090, "robo": 8091, "vantage": 8092, "zulu": 8093}


def get(port: int, endpoint: str):
    assert endpoint.startswith("/")
    url = f"http://127.0.0.1:{port}/api/v1{endpoint}"
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            payload = response.read(8 * 1024 * 1024)
            try:
                return {"http": response.status, "data": json.loads(payload)}
            except ValueError:
                return {"http": response.status, "error": "not_json", "bytes": len(payload)}
    except urllib.error.HTTPError as exc:
        return {"http": exc.code}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"error": type(exc).__name__}


def probe(name: str, port: int):
    out = {"port": port, "probed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    health = get(port, "/health")
    raw_health = health.pop("data", {})
    out["health"] = health | {key: raw_health.get(key) for key in (
        "status", "service", "apiVersion", "instance", "uptimeSeconds", "providers", "tokenRequired")}
    if health.get("http") != 200:
        return name, out
    status = get(port, "/update/status")
    raw_status = status.pop("data", {})
    result = raw_status.get("ergebnis") or {}
    out["update"] = status | {key: raw_status.get(key) for key in (
        "jobId", "state", "phase", "done", "total", "startedAt", "finishedAt")}
    out["update"]["result_keys"] = sorted(result) if isinstance(result, dict) else []
    out["update"]["result"] = {key: result.get(key) for key in (
        "signaleGeliefert", "tradelistenNeu", "tradelistenAktualisiert", "tradelistenFehler",
        "tradelistenAbgebrochen", "katalogUebersprungen", "datenstand")}
    items, pages = [], []
    offset = 0
    for _ in range(100):
        fetched = get(port, f"/providers?limit=73&offset={offset}")
        page = fetched.pop("data", {})
        block = page.get("items") or []
        pages.append(fetched | {"requested_offset": offset, "offset": page.get("offset"),
                               "count": page.get("count"), "total": page.get("total"),
                               "actual_items": len(block)})
        if fetched.get("http") != 200:
            break
        items.extend(block)
        offset += len(block)
        total = page.get("total")
        if not block or (isinstance(total, int) and total and offset >= total):
            break
    identities = [(str(i.get("signalId")), str(i.get("version"))) for i in items]
    out["catalogue"] = {"pages": pages, "rows": len(items), "unique_identities": len(set(identities)),
                        "versions": sorted({x[1] for x in identities}),
                        "item_keys": sorted({k for i in items for k in i}),
                        "lastUpdated_present": sum(bool(i.get("lastUpdated")) for i in items),
                        "weeks_present": sum(i.get("weeks") is not None for i in items),
                        "subscribers_present": sum(i.get("subscribers") is not None for i in items)}
    for key in ("hasTrades", "hasMetrics", "tradesAvailable", "metricsAvailable"):
        if any(key in i for i in items):
            out["catalogue"][key] = {"true": sum(i.get(key) is True for i in items),
                                      "false": sum(i.get(key) is False for i in items),
                                      "missing": sum(key not in i for i in items)}
    # Small, deterministic metadata sample. Never request or save raw trades.
    samples = []
    positions = sorted(set([0, 1, len(items) // 2, len(items) - 2, len(items) - 1]))
    for position in positions:
        if not (0 <= position < len(items)):
            continue
        item = items[position]
        signal_id, version = item.get("signalId"), item.get("version")
        if not str(signal_id).isdigit() or not str(version).isalnum():
            continue
        fetched = get(port, f"/providers/{signal_id}/{version}/metrics")
        answer = fetched.pop("data", {})
        metrics = answer.get("metrics") or {}
        sample = fetched | {"signal_id": signal_id, "version": version,
                            "metric_keys": sorted(metrics)}
        sample["selected"] = {key: metrics.get(key) for key in (
            "Currency", "CurrencyConvertedToUsd", "Trades", "TradesStored", "TradesTotalAvailable",
            "TradesTruncated", "TradeHistoryComplete", "TradeHistoryQualityReasons", "CompletenessNote")}
        samples.append(sample)
    out["metrics_samples"] = samples
    return name, out


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = dict(pool.map(lambda pair: probe(*pair), SERVICES.items()))
    target = ROOT / "downloads_live_probe.json"
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({name: {"health": r["health"], "catalogue": r.get("catalogue"),
                             "update": r.get("update")} for name, r in results.items()}, ensure_ascii=False, indent=2))
