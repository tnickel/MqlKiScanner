"""Offline source REST CSV -> pristine scanner parser; standard library only."""
import json
import sys
import faulthandler
from pathlib import Path

sys.dont_write_bytecode = True
faulthandler.dump_traceback_later(15, repeat=False)
root = Path(__file__).resolve().parent
scanner = Path(sys.argv[1])
sys.path.insert(0, str(scanner / "src"))
from mqlkiscanner.parser import load_export
from mqlkiscanner import client_updates
from unittest.mock import patch

result = {}
for repo in ("PelicanTrading", "vantage", "zulumonitor"):
    parsed = load_export(str(root / "run" / f"{repo}.csv"))
    trades = parsed.trades
    result[repo] = {
        "trade_count": len(trades),
        "net_profit": sum(t.net for t in trades),
        "directions": [t.direction for t in trades],
        "symbols": [t.symbol for t in trades],
        "commission": [t.commission for t in trades],
        "swap": [t.swap for t in trades],
    }
    assert len(trades) == 1
    if repo == "PelicanTrading":
        assert trades[0].net == -25 and trades[0].direction == "Buy"
    else:
        # Unknown source values have already been forged to concrete values.
        assert trades[0].net == 0 and trades[0].direction == "Sell"

raw_results = json.loads((root / "run/results.json").read_text(encoding="utf-8"))
for repo in ("vantage", "zulumonitor"):
    status = raw_results[f"{repo}_runner_failed_download"]["status"]
    class FakeClient:
        def health(self): return {"status": "ok"}
        def update_starten(self, **kwargs): return {"jobId": status["jobId"]}
        def update_status(self): return status
    with patch.object(client_updates.quellen, "client_fuer_quelle", return_value=FakeClient()), \
            patch.object(client_updates, "_persistiere", side_effect=lambda z: None):
        state = client_updates._update_eine_quelle(
            {"id": 1, "kuerzel": repo, "name": repo, "base_url": "http://audit.invalid"},
            settings={}, log=None, on_fortschritt=None, gestopft=lambda: False,
            bereit_warten_s=0, poll_s=0, backoff_s=0,
            timeout_s=2,
        )
    result[f"{repo}_failed_update_in_scanner"] = {
        key: state[key] for key in ("status", "tradelisten_fehler", "tradelisten_abgebrochen", "hinweise")
    }
    assert state["status"] == "fertig" and state["tradelisten_fehler"] == 0

(root / "scanner_contract_results.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(result, ensure_ascii=False, indent=2))
