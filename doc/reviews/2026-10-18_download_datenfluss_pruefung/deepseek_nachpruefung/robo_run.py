"""Offline Maven evidence runner; never launches the application or updates data."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

EVIDENCE = Path(__file__).resolve().parent
SCANNER = EVIDENCE.parents[3]
PROJECT = SCANNER.parent / "roboforex"
JAVA = Path("C:/Program Files/Eclipse Adoptium/jdk-25.0.4.101-hotspot")
SOURCES = ["src/main/java/de/robomonitor/store/DataStore.java",
           "src/main/java/de/robomonitor/store/FileTransactions.java",
           "src/test/java/de/robomonitor/ReviewDataIntegrityTest.java",
           "src/test/java/de/robomonitor/DataStoreBundleReadLockTest.java"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(stage):
    if stage == "full":
        options = ["test"]
    elif stage.startswith("repeat_") and stage.removeprefix("repeat_").isdigit():
        options = ["-Dtest=ReviewDataIntegrityTest#parallelDailyStoresPublishVerifiableWholeBundles,DataStoreBundleReadLockTest", "test"]
    elif stage == "package":
        options = ["-DskipTests", "package"]
    else:
        raise ValueError(stage)
    maven = shutil.which("mvn.cmd") or shutil.which("mvn")
    if not maven:
        raise RuntimeError("Maven unavailable")
    args = [maven, "-o", "-q", *options]
    env = dict(os.environ)
    env["JAVA_HOME"] = str(JAVA)
    env["PATH"] = str(JAVA / "bin") + os.pathsep + env.get("PATH", "")
    prefix = EVIDENCE / f"robo_{stage}"
    metadata = {
        "args": args, "cwd": str(PROJECT), "offline_maven": True,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": {name: sha(PROJECT / name) for name in SOURCES},
        "child_env_overrides": {"JAVA_HOME": str(JAVA), "PATH_prefix": str(JAVA / "bin")},
    }
    Path(str(prefix) + "_command.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf8")
    start = time.monotonic()
    process = subprocess.run(args, cwd=PROJECT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = process.stdout.decode("utf8", errors="replace")
    prefix.with_suffix(".log").write_text(output, encoding="utf8")
    metadata.update(exit_code=process.returncode,
                    elapsed_seconds=round(time.monotonic() - start, 2),
                    finished_utc=datetime.now(timezone.utc).isoformat())
    metadata["source_hashes_unchanged_during_run"] = all(sha(PROJECT / name) == expected
        for name, expected in metadata["source_sha256"].items())
    metadata["compiled_class_sha256"] = {name: sha(PROJECT / "target/classes" / name) for name in
        ["de/robomonitor/store/DataStore.class", "de/robomonitor/store/FileTransactions.class"]}
    if stage != "package":
        reports = list((PROJECT / "target/surefire-reports").glob("TEST-*.xml"))
        if stage != "full":
            reports = [path for path in reports if path.name in {
                "TEST-de.robomonitor.ReviewDataIntegrityTest.xml", "TEST-de.robomonitor.DataStoreBundleReadLockTest.xml"}]
        cases = []
        metadata["xml_sha256"] = {}
        for report in reports:
            target = EVIDENCE / f"robo_{stage}_{report.name}"
            shutil.copy2(report, target)
            metadata["xml_sha256"][target.name] = sha(target)
            cases.extend(ET.parse(target).getroot().iter("testcase"))
        failed = sum(case.find("failure") is not None for case in cases)
        errors = sum(case.find("error") is not None for case in cases)
        skipped = sum(case.find("skipped") is not None for case in cases)
        metadata["tests"] = dict(cases=len(cases), passed=len(cases)-failed-errors-skipped,
                                 failures=failed, errors=errors, skipped=skipped)
    Path(str(prefix) + "_command.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf8")
    Path(str(prefix) + "_exit.txt").write_text(str(process.returncode) + "\n", encoding="utf8")
    print(json.dumps({key: metadata[key] for key in ["exit_code", "elapsed_seconds", "source_hashes_unchanged_during_run"]
                      + (["tests"] if "tests" in metadata else [])}))
    if process.returncode:
        print(output[-10000:].encode("ascii", "backslashreplace").decode())
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    run(sys.argv[1])
