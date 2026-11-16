#!/usr/bin/env python3
"""Run either arm of the prepared UML flowchart experiment."""

import argparse
from pathlib import Path
import subprocess
import sys

from prepare import HERE, ROOT, TASK, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=("text", "image"))
    parser.add_argument("--agent", help="override EXP_AGENT from the workspace .env")
    parser.add_argument("--model", help="override EXP_MODEL from the workspace .env")
    parser.add_argument("--effort")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--jobs-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--no-shared-opencode", action="store_true")
    args = parser.parse_args()
    verify()
    jobs = args.jobs_dir or ROOT / "jobs/uml-flowchart/forced-v1" / args.arm
    command = [
        sys.executable, str(ROOT / "experiments/run.py"), "custom",
        "--task", TASK,
        "--skills-dir", str(HERE / "bundles" / args.arm),
        "--delivery-arm", args.arm,
        "--trials", str(args.trials),
        "--concurrency", str(args.concurrency),
        "--jobs-dir", str(jobs.resolve()),
    ]
    if args.agent:
        command += ["--agent", args.agent]
    if args.model:
        command += ["--model", args.model]
    if args.effort:
        command += ["--effort", args.effort]
    if args.dry_run:
        command += ["--dry-run"]
    if args.fresh:
        command += ["--fresh"]
    if args.no_shared_opencode:
        command += ["--no-shared-opencode"]
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
