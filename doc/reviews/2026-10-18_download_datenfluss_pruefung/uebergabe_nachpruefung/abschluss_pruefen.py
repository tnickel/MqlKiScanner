"""Validate this follow-up without rewriting any preceding evidence manifest."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET


REPORT = Path(__file__).resolve().parent
REVIEW = REPORT.parent
SCANNER = REVIEW.parents[2]
WORKSPACE = SCANNER.parent
EXPECTED_CHANGES = {"src/mqlkiscanner/db.py", "tests/test_source_identity_contract.py"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cases(path):
    rows = list(ET.parse(path).getroot().iter("testcase"))
    failures = sum(row.find("failure") is not None for row in rows)
    errors = sum(row.find("error") is not None for row in rows)
    skipped = sum(row.find("skipped") is not None for row in rows)
    return dict(tests=len(rows), passed=len(rows)-failures-errors-skipped,
                failures=failures, errors=errors, skipped=skipped)


def git(project, *args):
    return subprocess.run(["git", "-c", "core.quotepath=false", "-C",
                           str(WORKSPACE / project), *args], check=True,
                          capture_output=True, text=True).stdout


def main():
    baseline_path = REVIEW / "fremdreview_nachpruefung/manifest.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf8"))
    current_sources = {}
    differences = {}
    for project, recorded in baseline["source_sha256"].items():
        assert git(project, "rev-parse", "HEAD").strip() == baseline["heads"][project]
        paths = set(git(project, "diff", "--name-only", "--diff-filter=ACMRT").splitlines())
        paths.update(git(project, "ls-files", "--others", "--exclude-standard").splitlines())
        paths = {p for p in paths if p.startswith(("src/", "app_pages/", "tests/")) or p == "AGENTS.md"}
        assert paths == set(recorded), (project, paths.symmetric_difference(recorded))
        current_sources[project] = {p: sha(WORKSPACE / project / p) for p in sorted(paths)}
        differences[project] = [p for p, old in recorded.items()
                                if current_sources[project][p] != old]
        git(project, "diff", "--check")
    assert set(differences["SignalKiScanner"]) == EXPECTED_CHANGES, differences
    assert not differences["MqlDownloader"] and not differences["vantage"]

    for name, digest in baseline["evidence_sha256"].items():
        assert sha(baseline_path.parent / name) == digest, name
    original_path = REVIEW / "nachweise/manifest.json"
    original = json.loads(original_path.read_text(encoding="utf8"))
    for name, digest in original["evidence_sha256"].items():
        assert sha(REVIEW / name) == digest, name
    previous_path = REVIEW / "BEHEBUNG.manifest.json"
    assert sha(previous_path) == baseline["previous_fix_manifest_sha256"]
    assert sha(original_path) == baseline["original_audit_manifest_sha256"]
    assert sha(SCANNER / "data/contract_specs.json") == baseline["contract_registry_sha256"]

    identity = lambda p: Counter((n.get("classname"), n.get("name"))
                                 for n in ET.parse(p).getroot().iter("testcase"))
    shards = [baseline_path.parent / f"scanner_shard_{i}.xml" for i in range(3)]
    selected = sum((identity(p) for p in shards), Counter())
    assert selected == identity(baseline_path.parent / "scanner_full.xml")
    assert sum(selected.values()) == 2499
    assert all(cases(p)["failures"] == cases(p)["errors"] == cases(p)["skipped"] == 0 for p in shards)

    before = cases(REPORT / "legacy_quelle_before.xml")
    assert before["tests"] == before["failures"] == 6
    assert (REPORT / "legacy_quelle_before_exit.txt").read_text().strip() == "1"
    final = cases(REPORT / "legacy_quelle_final.xml")
    assert final["tests"] == final["passed"] == 150, final
    assert final["failures"] == final["errors"] == final["skipped"] == 0
    assert (REPORT / "legacy_quelle_final_exit.txt").read_text().strip() == "0"
    command = json.loads((REPORT / "legacy_quelle_final_command.json").read_text(encoding="utf8"))
    for name, digest in command["source_sha256"].items():
        assert sha(SCANNER / name) == digest, name

    java = {}
    for project, expected in (("MqlDownloader", 148), ("vantage", 88)):
        reports = list((WORKSPACE / project / "target/surefire-reports").glob("TEST-*.xml"))
        java[project] = {key: sum(cases(p)[key] for p in reports)
                         for key in ("tests", "passed", "failures", "errors", "skipped")}
        assert java[project]["tests"] == java[project]["passed"] == expected
        assert java[project]["failures"] == java[project]["errors"] == java[project]["skipped"] == 0
    assert sha(baseline["mql_artifact"]["path"]) == baseline["mql_artifact"]["sha256"]
    for artifact in json.loads(previous_path.read_text(encoding="utf8"))["build_artifacts"]:
        if "/vantage/" in artifact["path"]:
            assert sha(artifact["path"]) == artifact["sha256"]

    broken = []
    for document in REPORT.glob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf8")):
            if "://" in target or target.startswith("#") or target == "manifest.json":
                continue
            path = re.sub(r":\d+$", "", target.strip("<>").split("#")[0])
            candidate = Path(path) if Path(path).is_absolute() else REPORT / path
            if not candidate.exists():
                broken.append([document.name, target])
    assert not broken, broken
    handoff = json.loads((REVIEW / "KI_UEBERGABE.manifest.json").read_text(encoding="utf8"))
    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Critical review of the pasted Z.ai handoff plus a separate reproduced legacy source edge case",
        "baseline_manifest_sha256": sha(baseline_path),
        "original_audit_evidence_verified": len(original["evidence_sha256"]),
        "prior_followup_evidence_verified": len(baseline["evidence_sha256"]),
        "expected_source_changes_since_baseline": differences,
        "source_sha256": current_sources,
        "before_fix_reproduction": before,
        "final_targeted_regression": final,
        "new_regression_cases": 8,
        "prior_full_suite_passed": 2499,
        "prior_full_suite_repeated_after_this_fix": False,
        "prior_full_suite_collection_rechecked": True,
        "java_tests_from_unchanged_existing_reports": java,
        "java_test_runs_performed_this_followup": False,
        "test_groups_overlap_do_not_sum": True,
        "broken_report_links": broken,
        "handoff_text_matches_its_historical_manifest": sha(REVIEW / "KI_UEBERGABE.md") == handoff["handoff_sha256"],
        "handoff_manifest_instructions_hash_is_current": sha(SCANNER / "AGENTS.md") == handoff["project_instructions_sha256"],
        "production_mutations_performed": False,
        "real_http_calls_performed": False,
        "commits_performed": False,
        "evidence_sha256": {p.name: sha(p) for p in sorted(REPORT.iterdir())
                            if p.is_file() and p.name != "manifest.json"},
    }
    (REPORT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf8")
    print(json.dumps({key: manifest[key] for key in ("final_targeted_regression", "expected_source_changes_since_baseline",
          "original_audit_evidence_verified", "prior_followup_evidence_verified", "broken_report_links")}, indent=2))


if __name__ == "__main__":
    main()
