"""Aggregate existing FT trades with cached ECB rates; no network or DB writes."""
from bisect import bisect_right
import csv
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from mqlkiscanner.parser import load_export

SNAPSHOT_SHA = "ded562719204af3799798084442b2c7b1759643cc42507659df7d0dcca44dd84"
SNAPSHOT = ROOT / "data/trade_snapshots" / (SNAPSHOT_SHA + ".csv")
FX = ROOT / "data/fx_rates/eurofxref-hist.csv"


def main():
    digest = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
    if digest != SNAPSHOT_SHA:
        raise ValueError("Snapshot hash mismatch")
    rates = {}
    with FX.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            row = {str(k).strip(): v for k, v in row.items() if k is not None}
            try:
                rates[date.fromisoformat(row["Date"])] = (float(row["USD"]), float(row["GBP"]))
            except (ValueError, KeyError):
                pass
    dates = sorted(rates)
    trades = load_export(str(SNAPSHOT)).trades
    results = {}
    for symbol, quote in (("GER40FT", "EUR"), ("UK100FT", "GBP")):
        selected = [t for t in trades if t.symbol.upper() == symbol]
        usd_factors, native_factors, excluded = [], [], 0
        walks = []
        for trade in selected:
            day = trade.close_time.date()
            ix = bisect_right(dates, day) - 1
            denominator = trade.sign * trade.volume * (trade.exit_price - trade.entry_price)
            if ix < 0 or (day - dates[ix]).days > 10 or not denominator:
                excluded += 1
                continue
            usd, gbp = rates[dates[ix]]
            native_usd = usd if quote == "EUR" else usd / gbp
            factor = trade.net / denominator
            usd_factors.append(factor)
            native_factors.append(factor / native_usd)
            walks.append((day - dates[ix]).days)
        results[symbol] = {
            "quote_hypothesis": quote, "selected_trades": len(selected),
            "usable_trades": len(usd_factors), "excluded": excluded,
            "first_close": min(t.close_time for t in selected).isoformat(),
            "last_close": max(t.close_time for t in selected).isoformat(),
            "nonzero_separate_fee_fields": sum(t.commission != 0 or t.swap != 0 for t in selected),
            "usd_factor_median": statistics.median(usd_factors),
            "usd_factor_quartiles": statistics.quantiles(usd_factors, n=4),
            "native_factor_median_after_cached_ecb": statistics.median(native_factors),
            "native_factor_min": min(native_factors), "native_factor_max": max(native_factors),
            "maximum_fx_walkback_days_used": max(walks)}
    result = {
        "observed_utc": datetime.now(timezone.utc).isoformat(), "read_only": True, "network": False,
        "source_identity": {"quelle": "vant", "signal_id": 178177, "provider_broker_label": "vantage",
                            "original_provider_server": None},
        "snapshot_path": str(SNAPSHOT.relative_to(ROOT)), "snapshot_sha256": digest,
        "cached_ecb_path": str(FX.relative_to(ROOT)), "cached_ecb_sha256": hashlib.sha256(FX.read_bytes()).hexdigest(),
        "formula": "USD net / (direction * lots * price_delta), then divide by cached close-date EURUSD or GBPUSD",
        "fx_policy": "latest cached ECB date <= CSV close date, maximum 10 calendar days; no refresh",
        "limits": ["Plausibility only: historical source server is unknown; generic vantage label does not prove it.",
                   "CSV timestamps have no certified timezone; daily reference FX is not the execution conversion rate.",
                   "Zero separate commission/swap fields do not prove absence of embedded fees.",
                   "No raw trades, tickets or account data are written; no exact-cent PnL reconciliation claimed."],
        "aggregates": results}
    target = Path(__file__).with_suffix(".json")
    target.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
