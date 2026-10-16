"""Read-only parser contract probe: no pipeline, DB, network or test suite."""
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
review_root = Path(__file__).resolve().parent
workspace = review_root.parents[2]
sys.path.insert(0, str(workspace / "SignalKiScanner" / "src"))
from mqlkiscanner.parser import load_export

results = {}
for file in [review_root / "mql_probe_data" / "normal_mql4.csv",
             review_root / "mql_probe_data" / "normal_mql5.csv",
             review_root / "robo_probe_data" / "partial_trades.csv",
             review_root / "robo_probe_data" / "orphan_trades.csv"]:
    parsed = load_export(str(file))
    results[file.name] = {
        "format": parsed.source_format,
        "trades": len(parsed.trades),
        "net": parsed.net_total,
        "positions": [{"volume": t.volume, "holding_hours": t.holding_hours,
                       "entry_price": t.entry_price, "exit_price": t.exit_price,
                       "profit": t.profit, "commission": t.commission,
                       "swap": t.swap} for t in parsed.trades],
    }
output = json.dumps(results, ensure_ascii=False, indent=2)
(review_root / "scanner_csv_probe.json").write_text(output, encoding="utf-8")
print(output)
