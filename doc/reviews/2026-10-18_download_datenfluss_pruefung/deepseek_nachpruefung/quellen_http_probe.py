"""Bounded localhost GETs; persist aggregate catalogue metadata only.

No auth is read, no redirects, no POSTs, no trade endpoints or platform requests.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import urllib.error
import urllib.request

OUT = Path(__file__).resolve().parent
SOURCES = {"mql5": 8089, "pelik": 8090, "robo": 8091, "vant": 8092, "zulu": 8093}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def get(port, endpoint):
    out = {"at_utc": datetime.now(timezone.utc).isoformat(), "endpoint": endpoint}
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1{endpoint}", method="GET")
        with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
            payload = response.read(2 * 1024 * 1024)
            out.update(http=response.status, bytes=len(payload))
            return out, json.loads(payload)
    except urllib.error.HTTPError as exc:
        out["http"] = exc.code
    except (urllib.error.URLError, OSError, ValueError) as exc:
        out["error_type"] = type(exc).__name__
    return out, {}


def probe(pair):
    name, port = pair
    result = {"port": port}
    info, health = get(port, "/health")
    result["health"] = info | {key: health.get(key) for key in
                               ("status", "service", "apiVersion", "uptimeSeconds", "providers", "tokenRequired")}
    for label, query in (("default", ""), ("all_local", "&minSubscribers=0"),
                         ("all_local_unknown_control", "&minSubscribers=0&quellenProbeUnknown=1")):
        info, body = get(port, "/providers?limit=1&offset=0" + query)
        block = body.get("items") or []
        result[label] = info | {key: body.get(key) for key in ("total", "count", "offset")}
        result[label]["actual_items"] = len(block)
        if block:
            item = block[0]
            result[label]["first_identity"] = {key: item.get(key) for key in ("signalId", "version")}
            result[label]["first_weeks_field_present"] = "weeks" in item
            result[label]["first_weeks_proven"] = item.get("weeks") is not None
    default, all_local, control = (result[k] for k in ("default", "all_local", "all_local_unknown_control"))
    if default.get("http") == all_local.get("http") == control.get("http") == 200:
        result["additional_local_records"] = all_local["total"] - default["total"]
        result["unknown_parameter_ignored_in_probe"] = (
            all_local["total"] == control["total"] and all_local["first_identity"] == control["first_identity"])
    return name, result


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=5) as pool:
        sources = dict(pool.map(probe, SOURCES.items()))
    result = {"at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "20 bounded GETs: health plus three one-item local catalogue queries per source",
              "platform_requests": 0, "trade_endpoint_requests": 0, "auth_read": False,
              "sources": sources}
    (OUT / "quellen_http.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({name: {"default": row["default"].get("total"),
                            "all_local": row["all_local"].get("total"),
                            "unknown_ignored": row.get("unknown_parameter_ignored_in_probe")}
                      for name, row in sources.items()}, indent=2))
