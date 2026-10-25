"""Bind the DeepSeek follow-up to its actual source, tests and build evidence."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile


REPORT = Path(__file__).resolve().parent
REVIEW = REPORT.parent
SCANNER = REVIEW.parents[2]
WORKSPACE = SCANNER.parent
EXPECTED_SCANNER_CHANGES = {
    "AGENTS.md", "src/mqlkiscanner/downloader_client.py", "src/mqlkiscanner/ingest.py",
    "src/mqlkiscanner/katalog.py", "tests/test_deepseek_catalog_scope.py",
    "tests/test_quellen.py", "tests/test_download_review_fixes.py", "tests/test_katalog.py",
}
EXPECTED_ROBO_CHANGES = {"src/main/java/de/robomonitor/store/DataStore.java",
                         "src/test/java/de/robomonitor/DataStoreBundleReadLockTest.java"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf8"))


def git(project, *args):
    return subprocess.run(["git", "-c", "core.quotepath=false", "-C", str(WORKSPACE / project),
                           *args], check=True, capture_output=True, text=True).stdout


def source_hashes(project):
    paths = set(git(project, "diff", "--name-only", "--diff-filter=ACMRT").splitlines())
    paths.update(git(project, "ls-files", "--others", "--exclude-standard").splitlines())
    return {name: sha(WORKSPACE / project / name) for name in sorted(paths)
            if name.startswith(("src/", "tests/", "app_pages/")) or name == "AGENTS.md"}


def rows(path):
    return list(ET.parse(path).getroot().iter("testcase"))


def total(paths):
    cases = [row for path in paths for row in rows(path)]
    failed = sum(row.find("failure") is not None for row in cases)
    errors = sum(row.find("error") is not None for row in cases)
    skipped = sum(row.find("skipped") is not None for row in cases)
    return dict(tests=len(cases), passed=len(cases)-failed-errors-skipped,
                failures=failed, errors=errors, skipped=skipped)


def successful(paths, expected):
    result = total(paths)
    assert result["tests"] == result["passed"] == expected, result
    assert result["failures"] == result["errors"] == result["skipped"] == 0
    return result


def main():
    baseline_path = REVIEW / "uebergabe_nachpruefung/manifest.json"
    baseline = read(baseline_path)
    evidence_verified = {}
    for directory in ("nachweise", "fremdreview_nachpruefung", "uebergabe_nachpruefung"):
        manifest = read(REVIEW / directory / "manifest.json")
        for name, digest in manifest["evidence_sha256"].items():
            base = REVIEW if directory == "nachweise" else REVIEW / directory
            assert sha(base / name) == digest, (directory, name)
        evidence_verified[directory] = len(manifest["evidence_sha256"])

    sources = {project: source_hashes(project)
               for project in ("SignalKiScanner", "MqlDownloader", "vantage", "roboforex")}
    changed = {}
    for project, previous in baseline["source_sha256"].items():
        current = sources[project]
        assert not set(previous) - set(current), project
        changed[project] = [name for name, digest in current.items() if previous.get(name) != digest]
    assert set(changed["SignalKiScanner"]) == EXPECTED_SCANNER_CHANGES, changed
    assert not changed["MqlDownloader"] and not changed["vantage"]
    assert set(sources["roboforex"]) == EXPECTED_ROBO_CHANGES
    for project in sources:
        git(project, "diff", "--check")

    scanner = successful([REPORT / "scanner_regression.xml"], 407)
    command = read(REPORT / "scanner_regression_command.json")
    assert command["exit_code"] == 0
    for name, digest in command["source_sha256"].items():
        assert sha(SCANNER / name) == digest, name
    before = total([REPORT / "scope_before.xml"])
    assert before["tests"] == before["failures"] == 7
    assert (REPORT / "scope_before_exit.txt").read_text().strip() == "1"
    selected = lambda cases: Counter((row.get("classname"), row.get("name")) for row in cases)
    final_scope = [row for row in rows(REPORT / "scanner_regression.xml")
                   if row.get("classname") == "tests.test_deepseek_catalog_scope"]
    assert selected(final_scope) == selected(rows(REPORT / "scope_before.xml"))

    robo = successful(sorted(REPORT.glob("robo_full_TEST-*.xml")), 185)
    robo_command = read(REPORT / "robo_full_command.json")
    assert robo_command["exit_code"] == 0 and robo_command["source_hashes_unchanged_during_run"]
    for name, digest in robo_command["source_sha256"].items():
        assert sha(WORKSPACE / "roboforex" / name) == digest, name
    for name, digest in robo_command["xml_sha256"].items():
        assert sha(REPORT / name) == digest, name
    repeats = []
    for index in range(1, 6):
        repeats.append(successful(sorted(REPORT.glob(f"robo_repeat_{index}_TEST-*.xml")), 3))
        assert (REPORT / f"robo_repeat_{index}_exit.txt").read_text().strip() == "0"
    assert total([REPORT / "robo_before_parallel.xml"])["errors"] == 1
    repro = total(sorted(REPORT.glob("robo_repro_TEST-*.xml")))
    assert repro["tests"] == 3 and repro["failures"] == 2 and repro["errors"] == 1
    for name, data in read(REPORT / "robo_before_manifest.json")["files"].items():
        assert sha(REPORT / name) == data["sha256"]
    verification = read(REPORT / "robo_verification.json")
    artifact = verification["artifact"]
    assert sha(artifact["path"]) == artifact["sha256"]
    with zipfile.ZipFile(artifact["path"]) as jar:
        class_bytes = jar.read(artifact["changed_class"])
    assert hashlib.sha256(class_bytes).hexdigest() == artifact["class_sha256"]
    assert artifact["class_sha256"] == robo_command["compiled_class_sha256"][artifact["changed_class"]]
    assert class_bytes == (WORKSPACE / "roboforex/target/classes" / artifact["changed_class"]).read_bytes()
    assert read(REPORT / "robo_package_command.json")["exit_code"] == 0

    broken = []
    for document in REPORT.glob("*.md"):
        # The supplied review is evidence, not a maintained document.
        if document.name == "DEEPSEEK_ORIGINAL.md":
            continue
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf8")):
            if "://" in target or target.startswith("#") or target == "manifest.json":
                continue
            target_path = re.sub(r":\d+$", "", target.strip("<>").split("#")[0])
            path = Path(target_path)
            if not (path if path.is_absolute() else REPORT / path).exists():
                broken.append([document.name, target])
    assert not broken, broken
    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "foreign_review_sha256": sha(REPORT / "DEEPSEEK_ORIGINAL.md"),
        "baseline_manifest_sha256": sha(baseline_path),
        "previous_evidence_verified": evidence_verified,
        "changed_source_paths_since_baseline": changed,
        "additional_robo_changed_sources": sorted(EXPECTED_ROBO_CHANGES),
        "source_sha256": sources,
        "documentation_sha256": {name: sha(SCANNER / name) for name in
                                  ("AGENTS.md", "doc/23_stufe0-client-updates.md")},
        "heads": {project: git(project, "rev-parse", "HEAD").strip() for project in sources},
        "scanner_targeted_regression": scanner,
        "scanner_full_suite_repeated": False,
        "new_scanner_cases": 7,
        "robo_full_suite": robo,
        "new_robo_cases": 2,
        "robo_repeated_concurrency_runs": repeats,
        "groups_overlap_do_not_sum": True,
        "robo_build_artifact": artifact,
        "broken_report_links": broken,
        "runtime_actions": {"local_http_gets": 20, "database_access": "read-only",
                            "productive_posts": False, "productive_scans": False,
                            "platform_downloads": False, "restarts": False,
                            "terminal_starts": False, "real_llm_calls": False},
        "evidence_sha256": {path.name: sha(path) for path in sorted(REPORT.iterdir())
                            if path.is_file() and path.name != "manifest.json"},
    }
    (REPORT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf8")
    print(json.dumps({key: manifest[key] for key in ("scanner_targeted_regression", "robo_full_suite",
          "previous_evidence_verified", "broken_report_links")}, indent=2))


if __name__ == "__main__":
    main()
