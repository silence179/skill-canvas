#!/usr/bin/env python3
"""Write a Slurm array plan; submit it only with --submit."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from run import ROOT, TASKS, positive_int

UML_V2 = ROOT / "experiments/uml-expanded/full-skill-v2"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=("oracle", "nop", "baseline", "curated", "custom", "text", "image", "uml-v2"))
    parser.add_argument("--task", action="append")
    parser.add_argument("--tasks-file", type=Path, help="one task id per line; blank lines and # comments are ignored")
    parser.add_argument("--trials", type=positive_int, default=1)
    parser.add_argument("--max-parallel", type=positive_int, default=4)
    parser.add_argument("--cpus", type=positive_int, default=2)
    parser.add_argument("--mem", default="4G", help="memory per array element, e.g. 4G")
    parser.add_argument("--time", default="01:00:00")
    parser.add_argument("--partition")
    parser.add_argument("--nodelist", help="require the listed Slurm node names")
    parser.add_argument("--account")
    parser.add_argument("--agent")
    parser.add_argument("--model")
    parser.add_argument("--effort")
    parser.add_argument("--skills-dir", type=Path)
    parser.add_argument("--tasks-root", type=Path, default=TASKS)
    parser.add_argument("--images-dir", type=Path)
    parser.add_argument("--allow-cloud-metadata", action="store_true", help="explicitly pass BenchFlow's cluster metadata opt-out")
    parser.add_argument("--jobs-dir", type=Path)
    parser.add_argument("--submit", action="store_true", help="call sbatch after writing the plan")
    args = parser.parse_args()
    tasks = list(args.task or [])
    if args.tasks_file:
        tasks += [line.split("#", 1)[0].strip() for line in args.tasks_file.read_text().splitlines()]
        tasks = [task for task in tasks if task]
    paired = args.arm == "uml-v2"
    study = json.loads((UML_V2 / "manifest.json").read_text()) if paired else None
    tasks = list(dict.fromkeys(tasks or (list(study["tasks"]) if paired else ["llm-prefix-cache-replay"])))
    tasks_root = args.tasks_root.resolve()
    for task in tasks:
        if Path(task).name != task or not (tasks_root / task / "task.md").is_file():
            parser.error(f"unknown task id: {task}")
    if args.arm == "custom" and not args.skills_dir:
        parser.error("custom requires --skills-dir")
    if args.arm != "custom" and args.skills_dir:
        parser.error("--skills-dir is only used with custom")
    control = args.arm in ("oracle", "nop")
    if control and any((args.agent, args.model, args.effort)):
        parser.error("oracle/nop do not use a model")
    if args.arm in ("text", "image"):
        if args.agent or args.skills_dir:
            parser.error("text/image use OpenCode with the registered read-on-demand v2.1 bundles")
        sys.path.insert(0, str(ROOT / "experiments/skill-read-on-demand-v2_1"))
        from prepare import TASKS as allowed
        if any(task not in allowed for task in tasks):
            parser.error("text/image support the six registered image tasks; use curated for an original-text batch")
    if paired:
        if args.agent and args.agent != "opencode":
            parser.error("uml-v2 requires OpenCode")
        if any(task not in study["tasks"] for task in tasks):
            parser.error("uml-v2 requires a task registered in the full-skill-v2 materials")
        if args.submit:
            from env_config import load_env
            load_env(ROOT / ".env")
            if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
                parser.error("fill DEEPSEEK_API_KEY in the server .env before submitting")
    # Paths are resolved on the server that generates the plan, never on the
    # local development machine. The checkout can live anywhere on shared disk.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    jobs = (args.jobs_dir or ROOT / "jobs/slurm" / f"{args.arm}-{stamp}").resolve()
    if jobs.exists():
        parser.error("use a new --jobs-dir for each array submission")
    jobs.mkdir(parents=True)
    if args.arm in ("text", "image"):
        common = [str(ROOT / "repos/benchflow/.venv/bin/python"),
                  str(ROOT / "experiments/skill-read-on-demand-v2_1/runner.py"), "--arm", args.arm]
    else:
        common = [str(ROOT / "repos/benchflow/.venv/bin/python"), str(ROOT / "experiments/run.py"), args.arm, "--fresh"]
    common += ["--tasks-root", str(tasks_root), "--trials", "1", "--concurrency", "1"]
    if args.allow_cloud_metadata:
        common += ["--allow-cloud-metadata"]
    for flag in ("agent", "model", "effort", "skills_dir", "images_dir"):
        value = getattr(args, flag)
        if value:
            common += ["--" + flag.replace("_", "-"), str(value.resolve() if isinstance(value, Path) else value)]
    commands = []
    schedule = []
    for task in tasks:
        for trial in range(1, args.trials + 1):
            if not paired:
                command = common + ["--task", task, "--jobs-dir", str(jobs / task / f"trial-{trial}")]
                commands.append(shlex.join(command))
                continue
            for arm in ("text", "image"):
                bundle = UML_V2 / "tasks" / task / "bundles" / arm
                job_dir = jobs / task / arm / f"trial-{trial}"
                command = [str(ROOT / "repos/benchflow/.venv/bin/python"), str(UML_V2 / "delivery.py"),
                           "--arm", arm, "--bundle", str(bundle), "--", "run", str(tasks_root), "-i", task,
                           "--sandbox", "singularity", "--agent", "opencode", "--model", args.model or "deepseek/deepseek-flash",
                           "--skill-mode", "with-skill", "--skills-dir", str(bundle), "--trials", "1",
                           "--concurrency", "1", "--retry-attempts", "0", "--save-outputs", "--fresh", "--jobs-dir", str(job_dir)]
                if args.effort:
                    command += ["--reasoning-effort", args.effort]
                if args.allow_cloud_metadata:
                    command.append("--allow-cloud-metadata")
                if args.images_dir:
                    command = ["env", f"SKILLCANVAS_IMAGES={args.images_dir.resolve()}", *command]
                schedule.append({"task": task, "arm": arm, "jobs_dir": str(job_dir)})
                commands.append(shlex.join(command))
    commands_file = jobs / "commands.txt"
    commands_file.write_text("\n".join(commands) + "\n")
    script = jobs / "array.sbatch"
    # Slurm's spool copy of this file has a different location, so ROOT is
    # captured explicitly instead of deriving it from $0 at job runtime.
    script.write_text(
        "#!/bin/bash\nset -euo pipefail\n"
        f"cd {shlex.quote(str(ROOT))}\n"
        'export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"\n'
        'export OPENBLAS_NUM_THREADS="$OMP_NUM_THREADS"\n'
        'export MKL_NUM_THREADS="$OMP_NUM_THREADS"\n'
        'export NUMEXPR_NUM_THREADS="$OMP_NUM_THREADS"\n'
        f'command=$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" {shlex.quote(str(commands_file))})\n'
        'exec /bin/bash -c "$command"\n'
    )
    sbatch = ["sbatch", "--parsable", "--job-name", f"skillcanvas-{args.arm}",
              "--array", f"0-{len(commands)-1}%{args.max_parallel}",
              "--nodes", "1", "--ntasks", "1", "--cpus-per-task", str(args.cpus),
              "--mem", args.mem, "--time", args.time,
              "--output", str(jobs / "%A_%a.out"), "--error", str(jobs / "%A_%a.err")]
    for flag in ("partition", "account", "nodelist"):
        if getattr(args, flag):
            sbatch += ["--" + flag, getattr(args, flag)]
    sbatch.append(str(script))
    plan = {"arm": args.arm, "tasks": tasks, "trials_per_task": args.trials,
            "array_size": len(commands), "max_parallel": args.max_parallel,
            "cpus_per_task": args.cpus, "mem_per_task": args.mem,
            "command": sbatch, "code_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    if paired:
        plan.update(schedule=schedule, protocol="forced-prefix-v1", materials="full-skill-v2")
    (jobs / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(f"{len(commands)} trials; at most {args.max_parallel} running at once.")
    print(shlex.join(sbatch), flush=True)
    if args.submit:
        result = subprocess.run(sbatch, check=True, capture_output=True, text=True)
        (jobs / "slurm-job-id.txt").write_text(result.stdout)
        print(result.stdout.strip())


if __name__ == "__main__":
    main()
