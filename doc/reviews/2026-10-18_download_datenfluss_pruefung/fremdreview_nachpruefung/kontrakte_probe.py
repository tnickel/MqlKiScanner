"""Read-only, static registry probe; no DB, REST, terminal or runtime data access."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))

from mqlkiscanner import config, symbols  # noqa: E402
from mqlkiscanner.forensics import exposure  # noqa: E402


def main() -> None:
    registry = ROOT / "data" / "contract_specs.json"
    config.CONTRACT_SPECS_FILE = registry
    symbols._SPECS_CACHE.clear()
    specs = symbols.load_specs()
    cases = []
    expected = []
    vantage = "Vantage International Group Limited"
    for symbol, factor, quote in (
        ("UKOUSD", 1000, "USD"), ("SP500", 1, "USD"),
        ("NAS100FT", 1, "USD"), ("CL-OIL", 1000, "USD"),
        ("DJ30", 1, "USD"), ("DJ30FT", 1, "USD"),
        ("SP500FT", 1, "USD"), ("XAUAUD", 100, "AUD"),
        ("XAUJPY", 100, "JPY"), ("COIN", 1, "USD"),
        # Existing broker-bound entries take precedence. Their conflicting
        # unscoped native-quote variants are disclosed separately below.
        ("GER40FT", 1.08, "USD"), ("UK100FT", 1.35, "USD"),
    ):
        cases.append((symbol, vantage))
        expected.append((factor, quote))
    for broker in ("AxiTraderUs07Live", "AxiTrader5"):
        for symbol in ("COIN", "TSLA", "USOIL", "USOIL-FUTURE"):
            cases.append((symbol, broker))
            expected.append(None)
    for symbol, broker, factor in (
        ("USOIL-FUTURE", "AxiTrader2", 1000),
        ("US500-FUTURE", "AxiTrader2", 50),
        ("TSLA", "RoboForex", 100),
    ):
        cases.append((symbol, broker))
        expected.append((factor, "USD"))
    rows = []
    for (symbol, broker), expectation in zip(cases, expected):
        entry = symbols.spec_for(symbol, broker=broker)
        resolved = exposure._resolve_symbol(symbol, broker=broker)
        actual = (resolved["factor"], resolved["quote"]) if resolved else None
        row = {
            "symbol": symbol, "broker": broker,
            "normalized": symbols.normalize_symbol(symbol),
            "registry_key": next((key for key, value in specs.items() if value is entry), None),
            "factor_and_native_quote": actual,
            "expected": expectation, "matches": actual == expectation,
            "source": entry.get("source") if entry else None,
            "cross_broker": entry.get("cross_broker") if entry else None,
            "allowed_brokers": entry.get("brokers") if entry else None,
        }
        rows.append(row)
    output = {
        "scope": "Static current registry/resolver, no new broker permission or current live instrument proof",
        "registry_sha256": hashlib.sha256(registry.read_bytes()).hexdigest(),
        "registry_changed": False,
        "rows": rows,
        "checks": len(rows),
        "mismatches": [row for row in rows if not row["matches"]],
        "unresolved_registry_conflicts": [
            {"symbol": symbol, "broker_bound": specs[symbol + "_VANTAGE"],
             "unscoped_alternative": specs[symbol],
             "status": "Registry conflict, no independent FT metadata found in inspected local snapshots; no factor or permission changed"}
            for symbol in ("GER40FT", "UK100FT")],
        "month_basis": {"year_days": 365.2425, "months": 3,
                        "minimum_days": 3 * (365.2425 / 12),
                        "minimum_weeks": 3 * (365.2425 / 12) / 7},
    }
    target = Path(__file__).with_name("kontrakte_resolver.json")
    target.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"checks": len(rows), "mismatches": len(output["mismatches"]),
                      "output": str(target)}, ensure_ascii=True))
    if output["mismatches"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
