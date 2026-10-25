"""Offline aggregate explanation of remaining BTCETH price evidence gaps."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from mqlkiscanner.forensics.equity_rekonstruktion import _epoch, _PREIS_TOLERANZ
from mqlkiscanner.forensics.exposure_fx import ExposureUsdUmrechnung
from mqlkiscanner.parser import load_export


def main():
    sha = "a2bfac766b902580f925a7a410bd0e1927902ab8ca64d7801f6568de8c52b631"
    path = ROOT / "data/trade_snapshots" / (sha + ".csv")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
    parsed = load_export(str(path))
    parsed.trades = [t for t in parsed.trades if t.symbol.upper() == "BTCETH"]
    with sqlite3.connect((ROOT / "data/kursdaten.db").resolve().as_uri()+"?mode=ro", uri=True) as conn:
        feeds = [r[0] for r in conn.execute("SELECT DISTINCT feed FROM h1_bars WHERE symbol='BTCETH'")
                 if json.loads(r[0])[1] == "VantageMarkets-Live 10"]
        assert len(feeds) == 1
        feed = feeds[0]
        class CachedProvider:
            def _feed_identitaet(self): return "installation", feed
            def hole_h1(self, symbol, low, high):
                return [dict(zip(("time", "open", "high", "low", "close"), row))
                    for row in conn.execute("SELECT epoch,open,high,low,close FROM h1_bars "
                        "WHERE feed=? AND symbol=? AND epoch BETWEEN ? AND ? AND abgeschlossen=1 ORDER BY epoch",
                        (feed, symbol, low, high))]
        provider = CachedProvider()
        converter = ExposureUsdUmrechnung(parsed, provider, {"BTCETH": {"quote": "ETH"}})
        context = converter._prepare("BTCETH", "ETH")
        assert context is not None
        basis = context["basis"]
        bars = {b["time"]: b for b in provider.hole_h1("BTCETH", 0, 2**40)}
        reasons = Counter()
        deviations = []
        invalid_trades = 0
        for trade in parsed.trades:
            if not basis._trade_sicher[id(trade)]: invalid_trades += 1
            for when, price in ((trade.open_time, trade.entry_price), (trade.close_time, trade.exit_price)):
                bar = bars.get(basis.nach_referenz(_epoch(when)) // 3600 * 3600)
                if bar is None:
                    reasons["missing_own_reference_event_bar"] += 1
                else:
                    distance = max(bar["low"]-price, price-bar["high"], 0)
                    if distance > abs(price)*_PREIS_TOLERANZ + 1e-12:
                        reasons["price_outside_own_bar_tolerance"] += 1
                        deviations.append(distance/abs(price)*100)
        result = {"observed_utc": datetime.now(timezone.utc).isoformat(), "source": "vant/504191",
            "trade_sha256": sha, "read_only": True, "network_requests": 0, "terminal_access": False,
            "feed": feed, "btceth_trades": len(parsed.trades), "invalid_trade_count": invalid_trades,
            "event_gap_reasons": dict(reasons), "price_tolerance_pct": _PREIS_TOLERANZ*100,
            "maximum_price_distance_outside_own_bar_pct": max(deviations) if deviations else None,
            "time_basis_reliable": basis.verlaesslich,
            "gmt_offsets_h": sorted({p["offset_s"]/3600 for p in basis.perioden}),
            "conclusion": "Individual own-bar price evidence remains missing; no rate/clock tolerance was relaxed."}
    Path(__file__).with_suffix(".json").write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
