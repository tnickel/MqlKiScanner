"""Read-only live assessment and private build/finished-archive snapshot.

Never cancels/closes/restarts a process and never writes the Zulu datastore.
No tokens, raw trades, names or capital data enter the public evidence.
"""
import csv
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[3]
REVIEW = Path(__file__).resolve().parent
REPO = ROOT.parent / "zulumonitor"
NOW = dt.datetime.now(dt.timezone.utc)
SHA = lambda b: hashlib.sha256(b).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


runtime = json.loads((REVIEW / "zulu_shutdown_assessment_runtime.json").read_text(encoding="utf-8-sig"))
snapshot = ROOT / ".tmp" / "zulu_deployment" / NOW.strftime("%Y%m%dT%H%M%SZ")
snapshot.mkdir(parents=True, exist_ok=False)
jar = REPO / "target/zulumonitor-1.2.0.jar"
jar_bytes = jar.read_bytes()
frozen_jar = snapshot / jar.name
frozen_jar.write_bytes(jar_bytes)
with zipfile.ZipFile(io.BytesIO(jar_bytes)) as archive:
    classes = list((REPO / "target/classes").rglob("*.class"))
    for path in classes:
        assert archive.read(path.relative_to(REPO / "target/classes").as_posix()) == path.read_bytes()
build = {
    "recorded_utc": NOW.isoformat(),
    "jar_sha256": SHA(jar_bytes),
    "jar_size": len(jar_bytes),
    "main_classes_verified_against_target": len(classes),
    "tests": {"command": ["mvn", "test", "-q"], "passed": 149, "failures": 0, "errors": 0, "skipped": 0, "exit_code": 0},
    "package": {"command": ["mvn", "-q", "-DskipTests", "package"], "exit_code": 0},
    "snapshot_jar": str(frozen_jar),
    "activated": False,
    "source_files": [
        {"path": "../zulumonitor/" + path.relative_to(REPO).as_posix(), "sha256": SHA(path.read_bytes())}
        for path in sorted([REPO / "pom.xml", *REPO.glob("src/**/*.java")])
    ],
}
write(snapshot / "build.json", build)
write(REVIEW / "zulu_build_snapshot.json", build)

# Retain the original runtime dependency/module paths; only substitute frozen jar.
args = list(runtime["cmdline"][1:])
cp_index = args.index("-classpath") + 1
old_cp = args[cp_index].split(";")
assert Path(old_cp[0]).resolve() == (REPO / "target/classes").resolve()
args[cp_index] = ";".join([str(frozen_jar), *old_cp[1:]])
for path in args[args.index("--module-path") + 1].split(";") + old_cp[1:]:
    assert Path(path).is_file(), path
launch = {"exe": runtime["exe"], "cwd": str(REPO), "args": args,
          "windows_argument_line": subprocess.list2cmdline(args), "jar_sha256": SHA(jar_bytes)}
write(snapshot / "launch.json", launch)
(snapshot / "start_hidden.ps1").write_text('''$ErrorActionPreference = 'Stop'
$spec = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'launch.json') -Raw | ConvertFrom-Json
$jar = Join-Path $PSScriptRoot 'zulumonitor-1.2.0.jar'
if ((Get-FileHash -LiteralPath $jar -Algorithm SHA256).Hash.ToLowerInvariant() -ne $spec.jar_sha256) { throw 'Frozen jar hash mismatch' }
if (Get-NetTCPConnection -State Listen -LocalPort 8093 -ErrorAction SilentlyContinue) { throw 'Port 8093 is still occupied; no second writer started' }
$started = Start-Process -FilePath $spec.exe -ArgumentList $spec.windows_argument_line -WorkingDirectory $spec.cwd -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'runtime.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'runtime.stderr.log')
$started.Id | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime.pid')
$started.Id
''', encoding="utf-8")

status = json.load(urllib.request.urlopen("http://127.0.0.1:8093/api/v1/update/status", timeout=10))
traders = list(csv.DictReader(io.StringIO((REPO / "data/traders.csv").read_text(encoding="utf-8-sig")), delimiter=";"))
completed = traders[:int(status["done"])]
saved = []
for row in completed:
    provider = int(row["ProviderId"])
    csv_path = REPO / f"data/trades/trades_{provider}.csv"
    meta_path = csv_path.with_suffix(".meta")
    csv_bytes, meta_bytes = csv_path.read_bytes(), meta_path.read_bytes()
    meta = dict(line.split("=", 1) for line in meta_bytes.decode().splitlines() if "=" in line)
    assert meta["sha256"] == SHA(csv_bytes)
    target = snapshot / "completed_archives"
    target.mkdir(exist_ok=True)
    (target / csv_path.name).write_bytes(csv_bytes)
    (target / meta_path.name).write_bytes(meta_bytes)
    # A concurrent change invalidates the observation instead of claiming backup.
    assert csv_path.read_bytes() == csv_bytes and meta_path.read_bytes() == meta_bytes
    saved.append({"provider_id": provider, "count": int(meta["count"]), "csv_sha256": SHA(csv_bytes),
                  "meta_sha256": SHA(meta_bytes), "published_utc": dt.datetime.fromtimestamp(csv_path.stat().st_mtime, dt.timezone.utc).isoformat()})

remaining_rows, remaining_pages, missing = 0, 0, 0
for row in traders[int(status["done"]):]:
    meta_path = REPO / f'data/trades/trades_{int(row["ProviderId"])}.meta'
    try:
        meta = dict(line.split("=", 1) for line in meta_path.read_text().splitlines() if "=" in line)
        count = int(meta["count"])
        remaining_rows += count
        remaining_pages += math.ceil(count / 100)
    except (OSError, ValueError, KeyError):
        missing += 1
assessment = {
    "observed_utc": NOW.isoformat(), "process_id": runtime["process_id"], "status": status,
    "completed_archives_privately_copied_and_reverified": saved,
    "remaining_previous_cache_rows": remaining_rows,
    "remaining_previous_cache_estimated_100row_pages": remaining_pages,
    "remaining_providers_without_previous_meta": missing,
    "rest_duration": {
        "reliable_eta_available": False,
        "reason": "The old callback discards page progress; remote histories, retry counts and current page are unknown. Previous caches are workload scenarios, not current download coverage.",
        "at_1_second_per_page_hours": remaining_pages / 3600,
        "at_5_seconds_per_page_hours": remaining_pages * 5 / 3600,
        "scenario_only_not_eta": True,
    },
    "active_process_modified": False, "datastore_written": False,
}
write(snapshot / "live_assessment.json", assessment)
write(REVIEW / "zulu_deploy_preparation.json", assessment)
print(json.dumps({"snapshot": str(snapshot), "jar_sha256": SHA(jar_bytes), "status_done": status["done"],
                  "saved_archives": len(saved), "remaining_previous_cache_pages": remaining_pages,
                  "missing_previous_meta": missing, "scenario_hours_1s_5s": [remaining_pages/3600, remaining_pages*5/3600]}, indent=2))
