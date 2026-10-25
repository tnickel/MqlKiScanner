"""Reproducible offline full-suite split; both shards use one frozen file list."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PLAN = HERE / "root_final_plan.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--shard", type=int, choices=(0, 1))
    args = parser.parse_args()
    if args.prepare:
        files = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").rglob("test_*.py"))
        plan = {"prepared_utc": datetime.now(timezone.utc).isoformat(),
                "files": files, "shards": [files[::2], files[1::2]],
                "python": sys.version, "paid_llm": False}
        PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Prepared {len(files)} files in two shards")
        return 0
    if args.shard is None:
        parser.error("--prepare or --shard is required")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    name = f"root_final_{args.shard}"
    command = [sys.executable, "-m", "pytest", *plan["shards"][args.shard],
               "-q", "--tb=short", "--disable-warnings",
               "--junitxml=" + str(HERE / (name + ".xml"))]
    (HERE / (name + "_command.json")).write_text(
        json.dumps({"cwd": str(ROOT), "command": command}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    with (HERE / (name + ".log")).open("w", encoding="utf-8") as log:
        code = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                              stderr=subprocess.STDOUT, check=False).returncode
    (HERE / (name + "_exit.txt")).write_text(str(code), encoding="utf-8")
    print(f"Shard {args.shard}: exit {code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
