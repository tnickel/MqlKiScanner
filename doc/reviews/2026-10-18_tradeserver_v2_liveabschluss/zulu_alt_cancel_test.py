"""Build the attach guard; test only isolated HEAD old-code JVMs and loopback HTTP."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import zipfile

REVIEW = Path(__file__).resolve().parent
ROOT = REVIEW.parents[2]
REPO = ROOT.parent / "zulumonitor"
JAVA = Path(r"C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot\bin")
ASM = Path(r"C:\Users\tnickel\.m2\repository\org\ow2\asm\asm\9.9.1\asm-9.9.1.jar")
MAVEN = Path(r"D:\DevelopmentTools\apache-maven-3.9.6\bin\mvn.cmd")
WORK = ROOT / ".tmp/zulu_alt_cancel_test" / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
WORK.mkdir(parents=True, exist_ok=False)


def run(args, cwd, log, timeout=90):
    with log.open("wb") as out:
        result = subprocess.run([str(x) for x in args], cwd=cwd, stdout=out, stderr=subprocess.STDOUT,
                                timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        print(log.read_text(errors="replace"))
        raise RuntimeError(f"exit {result.returncode}: {args[0]} ({log})")


old = WORK / "old"
old.mkdir()
tracked = subprocess.check_output(["git", "ls-files", "src/main", "pom.xml"], cwd=REPO, text=True).splitlines()
for name in tracked:
    path = old / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(subprocess.check_output(["git", "show", "HEAD:" + name], cwd=REPO))
run([MAVEN, "-q", "-DskipTests", "package"], old, WORK / "old_build.log")
runtime = json.loads((REVIEW / "zulu_shutdown_assessment_runtime.json").read_text(encoding="utf-8-sig"))
old_cp = runtime["cmdline"][runtime["cmdline"].index("-classpath") + 1].split(";")
deps = old_cp[1:]
classes = WORK / "guard_classes"
classes.mkdir()
source = REVIEW / "zulu_alt_cancel"
run([JAVA / "javac.exe", "-g", "--add-modules", "jdk.attach,jdk.httpserver", "-cp",
     ";".join([str(ASM), str(old / "target/classes"), *deps]), "-d", classes,
     *sorted(source.glob("*.java"))], WORK, WORK / "guard_compile.log")
agent = WORK / "guard.jar"
with zipfile.ZipFile(agent, "w", zipfile.ZIP_DEFLATED) as jar:
    jar.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nAgent-Class: zulu.audit.GuardAgent\nCan-Retransform-Classes: true\nCan-Redefine-Classes: true\n\n")
    for path in classes.rglob("*.class"):
        jar.write(path, path.relative_to(classes).as_posix())
    with zipfile.ZipFile(ASM) as dependency:
        for name in dependency.namelist():
            if name.endswith(".class") and name != "module-info.class":
                jar.writestr(name, dependency.read(name))
fixture_cp = ";".join([str(classes), str(old / "target/classes"), *deps])
shapes = subprocess.check_output([str(JAVA / "java.exe"), "-cp", str(agent), "zulu.audit.ClassShape",
          str(old / "target/classes/de/zulumonitor/store/DataStore.class"),
          str(old / "target/classes/de/zulumonitor/update/UpdateJob.class")], text=True).splitlines()
results = []
for mode in ("pending_http", "return_race", "prior_writer", "shape_mismatch"):
    cwd = WORK / mode
    cwd.mkdir()
    (cwd / "shapes.properties").write_text("expectedStoreShape=" + shapes[0] + "\nexpectedJobShape=" + shapes[1] + "\n")
    with (cwd / "fixture.log").open("wb") as log:
        proc = subprocess.Popen([str(JAVA / "java.exe"), "-cp", fixture_cp, "zulu.audit.AltFixture", mode],
                                cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 15
        while not (cwd / "ready").is_file() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if not (cwd / "ready").is_file():
            print((cwd / "fixture.log").read_text(errors="replace"))
            raise RuntimeError(f"Fixture {mode} not ready")
        run([JAVA / "java.exe", "--add-modules", "jdk.attach", "-cp", agent, "zulu.audit.Attach",
             str(proc.pid), agent, cwd / "attach.properties"], WORK, cwd / "attach.log", timeout=15)
        code = proc.wait(timeout=45)
    if code:
        print((cwd / "fixture.log").read_text(errors="replace"))
        print((cwd / "guard.jsonl").read_text(errors="replace") if (cwd / "guard.jsonl").exists() else "No guard report")
        raise RuntimeError(f"Fixture {mode} failed: {code}")
    events = [json.loads(line) for line in (cwd / "guard.jsonl").read_text().splitlines()]
    if mode == "shape_mismatch":
        assert events[-1]["phase"] == "FAILED"
        assert not any(event["phase"] in ("GUARD_INSTALLED", "HTTP_INTERRUPT") for event in events)
    else:
        assert events[-1]["phase"] == "WORKER_ENDED_ARCHIVES_IDENTICAL"
    result = {"mode": mode, "exit_code": code, "events": events,
              "old_worker_ended": True, "archive_bytes_unchanged_after_guard": mode != "shape_mismatch",
              "guard_rejected_before_any_interrupt": mode == "shape_mismatch",
              "job": json.loads((cwd / "outcome.json").read_text())}
    results.append(result)
    shutil.copy2(cwd / "guard.jsonl", REVIEW / f"zulu_alt_cancel_{mode}.jsonl")
    shutil.copy2(cwd / "fixture.log", REVIEW / f"zulu_alt_cancel_{mode}.log")
    print(mode + ": PASS", flush=True)

summary = {"recorded_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "production_process_modified": False,
           "agent_jar": str(agent), "agent_sha256": hashlib.sha256(agent.read_bytes()).hexdigest(),
           "old_source_ref": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
           "expectedStoreShape": shapes[0], "expectedJobShape": shapes[1],
           "results": results,
           "sources": [{"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                       for path in sorted(source.glob("*.java"))]}
(REVIEW / "zulu_alt_cancel_fixture_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps({"passed": len(results), "agent_jar": str(agent), "agent_sha256": summary["agent_sha256"]}, indent=2))
