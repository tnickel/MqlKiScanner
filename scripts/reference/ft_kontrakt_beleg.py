"""Read exact Vantage FT metadata under the shared scan lock; never fetch trades.

Uses the application's checked portable start and final cleanup policy.
No symbol aliases and no account fields other than the broker server name.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from mqlkiscanner import config
from mqlkiscanner.agenten.lock import LockBesetzt, lauf_lock
from mqlkiscanner.agenten.marktdata import terminal_laueft
from mqlkiscanner.kursdaten import KursDaten

EXACT_SYMBOLS = ("GER40ft", "UK100ft")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def exact_spec(sdk, symbol):
    info = sdk.symbol_info(symbol)
    if info is None or info.name != symbol:
        raise ValueError("exact_symbol_missing_or_different")
    result = {key: getattr(info, key) for key in (
        "name", "description", "trade_contract_size", "currency_profit",
        "currency_margin", "trade_calc_mode", "trade_tick_size", "trade_tick_value",
        "trade_tick_value_profit", "trade_tick_value_loss", "volume_min", "volume_max",
        "volume_step", "digits")}
    for key in ("trade_contract_size", "trade_tick_size", "volume_min", "volume_step"):
        value = result[key]
        if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError("invalid_symbol_specification")
    if not str(result["currency_profit"]).isalpha() or len(result["currency_profit"]) != 3:
        raise ValueError("unknown_profit_currency")
    result["observed_utc"] = utc_now()
    return result


def capture(settings, *, provider_factory=KursDaten, lock_factory=lauf_lock,
            process_running=terminal_laueft):
    paths = [str(p) for p in settings.get("kursdaten_terminals", [])
             if Path(p).parent.name.casefold() == "vantage"]
    if len(paths) != 1:
        return {"ok": False, "error": "exactly_one_configured_vantage_terminal_required"}
    path = paths[0]
    result = {"ok": False, "started_utc": utc_now(), "requested_symbols": list(EXACT_SYMBOLS),
              "configured_terminal": path, "account_fields_read": ["server"],
              "orders_or_trade_downloads": False, "aliases_used": False}
    try:
        # Nothing inspects or touches any terminal before this shared lock.
        with lock_factory(config.DATA_DIR):
            result["lock_acquired_utc"] = utc_now()
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
                                      "company": str(terminal.company), "connected": True,
                                      "broker_server": server}
                result["symbols"] = {s: exact_spec(sdk, s) for s in EXACT_SYMBOLS}
                if str(getattr(sdk.account_info(), "server", "") or "").strip() != server:
                    raise ValueError("broker_server_changed_during_capture")
                result["ok"] = True
            except Exception as error:
                result["ok"] = False
                result["error"] = str(error) if isinstance(error, ValueError) else type(error).__name__
            finally:
                provider.beenden()
                result["terminal_running_after_cleanup"] = process_running(path)
                result["cleanup_checked_utc"] = utc_now()
                if result["terminal_running_after_cleanup"]:
                    result["ok"] = False
                    result["error"] = "terminal_cleanup_not_confirmed"
    except LockBesetzt:
        result["error"] = "shared_scan_lock_busy_no_terminal_access"
    result["finished_utc"] = utc_now()
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
