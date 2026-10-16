"""Normalize agent snapshot records without altering tested files or original evidence."""
import json
from pathlib import Path

audit = Path(__file__).resolve().parent
workspace = audit.parents[1]
clients = json.loads((audit / "clients_manifest_final2.json").read_text(encoding="utf-8-sig"))
for repo in clients["repositories"]:
    snapshot = Path(repo["snapshot"])
    manifest = {"repo": str(workspace / repo["name"]), "destination": str(snapshot),
        "head": repo["head"], "overlay_sha256": {item["path"]: item["sha256"] for item in repo["overlayFiles"]},
        "provenance": "clients_manifest_final2.json; normalized schema, original retained"}
    (audit / (snapshot.name + ".manifest.json")).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

config = {
    "runs": [
        {"snapshot": "Scanner_final2", "manifest": "Scanner_final2.manifest.json",
         "xml": "Scanner_final2.pytest.xml", "log": "Scanner_final2.pytest.log"},
        {"snapshot": "MqlDownloader_snapshot", "manifest": "MqlDownloader_snapshot.manifest.json",
         "log": "mql_full_package.log", "package": True},
        {"snapshot": "PelicanTrading_final", "manifest": "PelicanTrading_final.manifest.json",
         "log": "PelicanTrading_final.maven.log", "package": True},
        {"snapshot": "roboforex_final", "manifest": "roboforex_final.manifest.json",
         "log": "roboforex_final.maven.log", "package": True},
        {"snapshot": "vantage_final2", "manifest": "vantage_final2.manifest.json",
         "log": "vantage_final2_package.log", "package": True},
        {"snapshot": "zulumonitor_final2", "manifest": "zulumonitor_final2.manifest.json",
         "log": "zulumonitor_final2.maven.log", "package": True},
    ],
    "attachments": [
        "clients.md", "clients_manifest.json", "clients_manifest_final2.json",
        "clients_vantage_epoch_followup.md", "quellen.md", "hub.md", "root_finance_filter.md",
        "review_oracles.py", "review_oracles.json", "configure_evidence.py",
        "root_before.log", "root_before.xml", "root_after3.log", "root_after3.xml",
        "root_after2.log", "root_after2.xml", "root_catalogue.log", "root_catalogue.xml",
        "Scanner_final.pytest.log", "Scanner_final.pytest.xml", "Scanner_final.manifest.json",
        "root_full_failure_probe.log", "hub_before.log", "hub_deep_batch_before.log",
        "hub_final_targeted.log", "hub_audit_failure_before.log", "hub_audit_failure_after.log",
        "roboforex_baseline_probe.maven.log", "zulumonitor_baseline_probe.maven.log",
        "zulumonitor_payload_baseline_probe.maven.log", "mql_before.log", "mql_targeted_after.log",
        "vantage_before.log", "vantage_legacy_before.log", "vantage_python_before.log",
        "vantage_python_schema_before.log", "vantage_python_after.log", "vantage_timezone_after.log",
        "vantage_full_package.log", "vantage_epoch_before.log", "vantage_epoch_after.log",
        "vantage_final2_python.log", "vantage_final2_timezone.log",
        "nachweise/root_currency_peer_review.md", "nachweise/root_currency_peer_reprobe.json",
        "nachweise/hub_failure_peer_review.md", "nachweise/hub_audit_write_peer_probe.json",
        "nachweise/hub_audit_write_peer_after.json", "nachweise/hub_sync_failure_peer_probe.json",
        "nachweise/hub_deep_batch_failure_peer_probe.json", "currency_reload_peer_probe.py",
        "currency_reload_peer_probe.json", "currency_reload_peer_review.md", "currency_reload_peer_probe_after.json",
        "root_integration.log", "root_currency_final2.log", "root_currency_final2.xml",
        "hub_manifest.json", "hub_result.json", "hub_hash_verification.json",
        "nachweise/ui_currency_fix.md", "nachweise/ui_currency_owned_hashes.json",
        "ui_currency_before.pytest.log", "ui_currency_before.pytest.xml",
        "ui_currency_before.manifest.json", "ui_currency_final2.pytest.log",
        "ui_currency_final2.pytest.xml", "ui_currency_final2.manifest.json",
    ],
    "additional_runs": [{"kind": "vantage_python", "log": "vantage_final2_python.log", "expected_passed": 21},
                        {"kind": "vantage_timezone_subset", "log": "vantage_final2_timezone.log", "expected_passed": 30}],
}
(audit / "final_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
print("Evidence configuration prepared; only completed final runs may pass collection.")
