#!/usr/bin/env python3
"""Small, explicit experiment launcher; all execution stays in BenchFlow."""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
from datetime import datetime, timezone

from env_config import load_env

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "repos/benchflow/.venv/bin/bench"
TASKS = ROOT / "repos/skillsbench/tasks"


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=["oracle", "nop", "baseline", "curated", "custom"])
    parser.add_argument("--task", action="append", help="repeat for multiple task ids")
    parser.add_argument("--tasks-root", type=Path, default=TASKS, help="explicit prepared task copies (prompts/verifiers must be preserved)")
    parser.add_argument("--agent", help="e.g. claude-agent-acp, codex-acp, gemini")
    parser.add_argument("--model", help="exact provider/model identifier")
    parser.add_argument("--effort", help="reasoning effort supported by this model")
    parser.add_argument("--trials", type=positive_int, default=1)
    parser.add_argument("--concurrency", type=positive_int, default=1)
    parser.add_argument("--skills-dir", type=Path)
    parser.add_argument("--jobs-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="ask BenchFlow to plan without running")
    parser.add_argument("--fresh", action="store_true", help="start a new job instead of resuming")
    parser.add_argument("--delivery-arm", choices=("text", "image"), help="strict UML experiment input adapter")
    parser.add_argument("--no-shared-opencode", action="store_true", help="use the original per-task OpenCode installer")
    args = parser.parse_args()
    try:
        load_env(ROOT / ".env")
    except ValueError as error:
        parser.error(str(error))
    tasks = args.task or ["econ-detrending-correlation"]
    task_root = args.tasks_root.resolve()
    for task in tasks:
        if Path(task).name != task or not (task_root / task / "task.md").is_file():
            parser.error(f"unknown task id: {task}")
    control = args.arm in {"oracle", "nop"}
    if not control:
        args.agent = args.agent or os.environ.get("EXP_AGENT") or None
        args.model = args.model or os.environ.get("EXP_MODEL") or None
        args.effort = args.effort or os.environ.get("EXP_EFFORT") or None
    if not control and (not args.agent or not args.model):
        parser.error("set EXP_AGENT and EXP_MODEL in .env, or pass --agent and --model")
    if control and (args.agent or args.model or args.effort):
        parser.error("oracle/nop use no model; omit --agent, --model and --effort")
    if args.arm == "custom":
        if not args.skills_dir or not args.skills_dir.is_dir():
            parser.error("custom requires an existing --skills-dir")
        if not any(args.skills_dir.glob("*/SKILL.md")):
            parser.error("--skills-dir must contain child folders with SKILL.md")
    elif args.skills_dir:
        parser.error("--skills-dir is only used with custom")
    if not BENCH.is_file():
        parser.error("BenchFlow is not installed; see README.md")
    if (
        not control
        and not args.dry_run
        and args.model.startswith("deepseek/")
        and not os.environ.get("DEEPSEEK_API_KEY", "").strip()
    ):
        parser.error("DEEPSEEK_API_KEY is empty; fill it in the workspace .env first")
    jobs = (args.jobs_dir or ROOT / "jobs" / args.arm).resolve()
    command = [str(BENCH), "run", str(task_root)]
    for task in tasks:
        command += ["-i", task]
    command += ["--agent", args.arm if control else args.agent,
                "--sandbox", "docker", "--trials", str(args.trials),
                "--concurrency", str(args.concurrency), "--retry-attempts", "0",
                "--save-outputs", "--jobs-dir", str(jobs)]
    if not control:
        command += ["--model", args.model]
        if args.effort:
            command += ["--reasoning-effort", args.effort]
    if args.arm == "curated":
        command += ["--skill-mode", "with-skill"]
    elif args.arm == "custom":
        command += ["--skill-mode", "with-skill", "--skills-dir", str(args.skills_dir.resolve())]
    else:
        command += ["--skill-mode", "no-skill"]
    if args.fresh:
        command += ["--fresh"]
    if args.dry_run:
        command += ["--dry-run"]
    if args.delivery_arm:
        if args.arm != "custom" or args.agent != "opencode":
            parser.error("strict skill delivery requires custom skills and --agent opencode")
        command = [
            str(BENCH.parent / "python"),
            str(ROOT / "experiments/uml-flowchart/delivery_runner.py"),
            "--arm", args.delivery_arm, "--bundle", str(args.skills_dir.resolve()),
            "--", *command[1:],
        ]
    shared_record = ROOT / ".runtime/shared-opencode/image.json"
    use_shared = (not control and args.agent == "opencode"
                  and not args.no_shared_opencode and shared_record.is_file())
    if use_shared:
        tail = (["--delivery-runner", *command[2:]] if args.delivery_arm else command[1:])
        command = [str(BENCH.parent / "python"), str(ROOT / "experiments/shared_opencode.py"),
                   "run", "--", *tail]
    print(shlex.join(command), flush=True)
    if not args.dry_run:
        sources = {}
        # Only the task source and actual runner are required. Harbor is an
        # optional reference checkout, never a prerequisite for this harness.
        for name in ("skillsbench", "benchflow"):
            repo = ROOT / "repos" / name
            sources[name] = {
                "commit": subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
                "status": subprocess.check_output(["git", "-C", str(repo), "status", "--short"], text=True),
            }
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        manifest = ROOT / "experiments/manifests" / f"{args.arm}-{stamp}.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        record = {"arm": args.arm, "command": command, "sources": sources, "task_root": str(task_root)}
        if use_shared:
            import hashlib
            record["shared_opencode"] = json.loads(shared_record.read_text())
            record["shared_opencode_adapter_sha256"] = hashlib.sha256(
                (ROOT / "experiments/shared_opencode.py").read_bytes()).hexdigest()
        if args.delivery_arm:
            import hashlib
            record["delivery_adapter"] = {
                name: hashlib.sha256((ROOT / "experiments/uml-flowchart" / name).read_bytes()).hexdigest()
                for name in ("delivery_runner.py", "delivery_protocol.py")
            }
        manifest.write_text(json.dumps(record, indent=2) + "\n")
    environment = os.environ.copy()
    local_docker = ROOT / ".runtime/docker"
    if (local_docker / "cli-plugins/docker-compose").is_file():
        environment.setdefault("DOCKER_CONFIG", str(local_docker))
    return subprocess.call(command, cwd=ROOT, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
