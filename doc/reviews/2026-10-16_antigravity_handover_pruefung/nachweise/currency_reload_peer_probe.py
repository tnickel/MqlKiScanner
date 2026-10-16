"""Execute the actual catalogue module with inert imports: no real DB/cache/network."""
import importlib.util
import json
import sys
import types
import ast
import math
from pathlib import Path

package = types.ModuleType("catalogue_peer")
package.__path__ = []
sys.modules[package.__name__] = package
for name in ("db", "downloader_client", "ingest", "pipeline", "quellen"):
    module = types.ModuleType(package.__name__ + "." + name)
    setattr(package, name, module)
    sys.modules[module.__name__] = module

class DownloaderError(Exception):
    pass

package.downloader_client.DownloaderError = DownloaderError
package.db.get_quelle = lambda _: {"kuerzel": "mql", "id": 1}

def unavailable(*_):
    raise DownloaderError("synthetic metrics unavailable")

package.ingest.hole_metrics = unavailable
package.ingest.hole_trades = lambda *_: ("synthetic-new-native.csv", True)
source = Path(__file__).parents[2] / "SignalKiScanner/src/mqlkiscanner/katalog.py"
ingest_source = source.with_name("ingest.py")
tree = ast.parse(ingest_source.read_text(encoding="utf-8-sig"))
definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name in ("metrics_zu_stats", "_zahl", "_anzahl")]
namespace = {"math": math, "QUELLEN_BROKER_FALLBACK": {}}
exec(compile(ast.Module(body=definitions, type_ignores=[]), str(ingest_source), "exec"), namespace)
package.ingest.metrics_zu_stats = namespace["metrics_zu_stats"]
spec = importlib.util.spec_from_file_location(package.__name__ + ".katalog", source)
catalogue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalogue)
result = types.SimpleNamespace(id=123, quelle="mql", quelle_id=1,
                               quelle_version="mql5", account_currency="USD")
path, changed = catalogue.lade_signal_daten(result)
guard_source = source.with_name("pipeline.py")
guard_tree = ast.parse(guard_source.read_text(encoding="utf-8-sig"))
guard_node = next(node for node in guard_tree.body if isinstance(node, ast.FunctionDef) and node.name == "require_usd_account")
guard_namespace = {"ScanResult": types.SimpleNamespace}
exec(compile(ast.Module(body=[guard_node], type_ignores=[]), str(guard_source), "exec"), guard_namespace)
record = {"new_csv": path, "changed": changed,
          "currency_after_failed_metrics": result.account_currency,
          "stale_usd_proof_retained": result.account_currency == "USD"}
record["versions"] = []
for version in ("mql4", "mql5", "pelican", "vantage", "zulu"):
    case = types.SimpleNamespace(id=123, quelle="synthetic", quelle_id=1,
                                 quelle_version=version, account_currency="USD", source_kind="live")
    catalogue.lade_signal_daten(case)
    blocked = False
    try:
        guard_namespace["require_usd_account"](case)
    except ValueError:
        blocked = True
    record["versions"].append({"version": version, "currency": case.account_currency, "usd_guard_blocked": blocked})
    assert blocked == (version in {"mql4", "mql5"})
print(json.dumps(record))
Path(__file__).with_name("currency_reload_peer_probe_after.json").write_text(json.dumps(record, indent=2))
