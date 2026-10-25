"""Feed real, sanitized age evidence through Scanner normalization and its gate.

No network, no scans, no production writes. The candidate JSON goes into TempDir.
"""
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path.cwd() / "src"))
from mqlkiscanner import config, ingest, pipeline

evidence = json.loads(Path(__file__).with_name("mql_age_evidence.json").read_text(encoding="utf-8-sig"))
out = []
with tempfile.TemporaryDirectory(prefix="mql_age_scanner_contract_") as temporary:
    original_data = config.DATA_DIR
    config.DATA_DIR = Path(temporary)
    try:
        for version in ("mql4", "mql5"):
            cases = dict(evidence[version]["samples"])
            cases.update({sid: None for sid in evidence[version]["unknownIds"]})
            for sid, weeks in cases.items():
                item = {"signalId": sid, "version": version, "weeks": weeks,
                        "weeksSource": evidence["source"] if weeks is not None else None,
                        "subscribers": 10}
                entry = ingest.kandidaten({"id": 7, "kuerzel": "mql5"}, [item])[0]
                reasons = []
                accepted = pipeline.ScanPipeline({"min_wochen": 26, "min_abonnenten": 0,
                                                  "fix_signal_ids": []}).build_candidates(
                    [entry], lambda _: None, reasons)
                expected = weeks is not None and weeks >= 26
                assert bool(accepted) == expected
                assert entry["wochen"] == weeks
                out.append({"signalId": sid, "version": version, "weeks": weeks,
                            "accepted": bool(accepted), "reason": reasons[0]["grund"]})
    finally:
        config.DATA_DIR = original_data
print(json.dumps({"readOnlyProduction": True, "networkRequests": 0, "minimumWeeks": 26,
                  "fixIds": [], "cases": out, "assertionsPassed": len(out) * 2},
                 ensure_ascii=True, indent=2))
