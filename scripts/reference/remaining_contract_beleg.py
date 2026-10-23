"""Capture exact remaining Vantage instruments under the shared workflow lock.

Only case is normalized for locating an export instrument. No cash/future proxy
or alternative instrument is accepted. No account fields except server are read.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mqlkiscanner import config
from mqlkiscanner.agenten.lock import LockBesetzt, lauf_lock
from mqlkiscanner.agenten.marktdata import terminal_laueft
from mqlkiscanner.kursdaten import KursDaten
from ft_kontrakt_beleg import exact_spec

REQUESTED = ("NIKKEI225", "SOYBEAN-C")


def capture(settings, *, provider_factory=KursDaten, lock_factory=lauf_lock,
            process_running=terminal_laueft):
    paths = [str(p) for p in settings.get("kursdaten_terminals", [])
             if Path(p).parent.name.casefold() == "vantage"]
    if len(paths) != 1:
        return {"ok": False, "error": "exactly_one_configured_vantage_terminal_required"}
    path = paths[0]
    result = {"ok": False, "started_utc": datetime.now(timezone.utc).isoformat(),
              "requested_symbols": list(REQUESTED), "configured_terminal": path,
              "account_fields_read": ["server"], "orders_or_trade_downloads": False,
              "symbol_matching": "exact spelling after case normalization; no proxy"}
    try:
        with lock_factory(config.DATA_DIR):
            result["terminal_was_running"] = process_running(path)
            provider = provider_factory({**settings, "kursdaten_terminals": [path]})
            try:
                ok, reason = provider.starten()
                result["connection_message"] = reason
                if not ok:
                    raise ValueError("portable_connection_failed")
                sdk = provider._mt5
                terminal = sdk.terminal_info()
                expected = os.path.normcase(os.path.realpath(str(Path(path).parent)))
                actual = os.path.normcase(os.path.realpath(str(terminal.data_path)))
                if not terminal.connected or expected != actual:
                    raise ValueError("portable_terminal_not_confirmed")
                server = str(getattr(sdk.account_info(), "server", "") or "").strip()
                if not server:
                    raise ValueError("broker_server_unknown")
                result["terminal"] = {"path": str(terminal.path), "data_path": str(terminal.data_path),
                    "company": str(terminal.company), "connected": True, "broker_server": server}
                names = [s.name for s in sdk.symbols_get()]
                result["symbols"] = {}
                for requested in REQUESTED:
                    matches = [s for s in names if s.upper() == requested]
                    if len(matches) != 1:
                        raise ValueError("exact_symbol_missing_or_ambiguous:" + requested)
                    result["symbols"][requested] = exact_spec(sdk, matches[0])
                if str(getattr(sdk.account_info(), "server", "") or "").strip() != server:
                    raise ValueError("broker_server_changed_during_capture")
                result["ok"] = True
            except Exception as error:
                result["ok"] = False
                result["error"] = str(error) if isinstance(error, ValueError) else type(error).__name__
            finally:
                provider.beenden()
                result["terminal_running_after_cleanup"] = process_running(path)
                if result["terminal_running_after_cleanup"]:
                    result["ok"] = False
                    result["error"] = "terminal_cleanup_not_confirmed"
    except LockBesetzt:
        result["error"] = "shared_scan_lock_busy_no_terminal_access"
    result["finished_utc"] = datetime.now(timezone.utc).isoformat()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture(config.load_settings())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
