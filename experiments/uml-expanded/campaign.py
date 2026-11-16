#!/usr/bin/env python3
"""Run and summarize a predeclared, alternating-order five-task paired pilot."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from study import HERE, ROOT, TASKS, verify_study


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity():
    files = [HERE / name for name in ("study.py", "campaign.py", "build_diagrams.py", "prepare_environments.py", "smoke.py")]
    files += [HERE.parent / "uml-flowchart" / name for name in ("delivery_runner.py", "delivery_protocol.py")]
    files += [HERE.parent / name for name in ("run.py", "shared_opencode.py", "env_config.py")]
    return {str(path.relative_to(ROOT)): hash_file(path) for path in files}


def controls():
    rows = {}
    for path in sorted((ROOT / "jobs/uml-expanded/environment-controls-prepared").glob("*/*/result.json")):
        row = json.loads(path.read_text())
        rows[row["task_name"]] = {"path": str(path.relative_to(ROOT)),
            "sha256": hash_file(path), "reward": (row.get("rewards") or {}).get("reward"),
            "error": row.get("error"), "task_digest": row.get("task_digest")}
    return rows


def plan(directory):
    sys.path.insert(0, str(ROOT / "experiments"))
    from env_config import load_env
    load_env(ROOT / ".env")
    model = os.environ.get("EXP_MODEL")
    agent = os.environ.get("EXP_AGENT")
    if agent != "opencode" or not model:
        raise ValueError("this pilot requires configured OpenCode and model")
    identities = {}
    schedule = []
    for index, task in enumerate(TASKS):
        study = HERE / "tasks" / task
        manifest = verify_study(study)
        identities[task] = {"manifest_sha256": hash_file(study / "manifest.json"),
            "skill_names": list(manifest["skills"]),
            "guide_bytes": sum(item["guide_bytes"] for item in manifest["skills"].values())}
        for arm in (("text", "image") if index % 2 == 0 else ("image", "text")):
            jobs = directory / task / arm
            command = [sys.executable, str(ROOT / "experiments/run.py"), "custom",
                "--tasks-root", str(ROOT / ".runtime/uml-expanded/prepared-tasks"),
                "--task", task, "--skills-dir", str(study / "bundles" / arm),
                "--delivery-arm", arm, "--agent", agent, "--model", model,
                "--trials", "1", "--concurrency", "1", "--jobs-dir", str(jobs)]
            if os.environ.get("EXP_EFFORT"):
                command += ["--effort", os.environ["EXP_EFFORT"]]
            schedule.append({"task": task, "arm": arm, "jobs_dir": str(jobs),
                "command": command, "status": "planned"})
    return {"schema": 1, "created_at_utc": subprocess.check_output(
        ["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"], text=True).strip(),
        "purpose": "pilot: full skill text vs PNG-first plus same full text",
        "model": model, "agent": agent, "trials_per_arm": 1, "concurrency": 1,
        "seed": None, "effort": os.environ.get("EXP_EFFORT") or None,
        "order": "task order fixed; text/image order alternates by task",
        "task_sources": identities, "code_sha256": source_identity(),
        "shared_tool_image": json.loads((ROOT / ".runtime/shared-opencode/image.json").read_text()),
        "prepared_environment_sha256": hash_file(ROOT / ".runtime/uml-expanded/prepared-environments.json"),
        "controls": controls(), "schedule": schedule}


def collect(slot):
    found = sorted(Path(slot["jobs_dir"]).glob("*/*/result.json"))
    if len(found) != 1:
        return {"task": slot["task"], "arm": slot["arm"], "status": slot["status"],
                "metric_admitted": False, "reason": f"expected one result, found {len(found)}"}
    path = found[0]
    row = json.loads(path.read_text())
    trial = path.parent
    audit_path = trial / "skill-delivery.json"
    audit = json.loads(audit_path.read_text()) if audit_path.exists() else {}
    trace = trial / "trajectory/llm_trajectory.jsonl"
    calls, raw_in, raw_out, raw_cached = 0, 0, 0, 0
    raw_complete = True
    if trace.exists():
        for line in trace.read_text().splitlines():
            event = json.loads(line)
            usage = event.get("response", {}).get("body", {}).get("usage")
            if not usage:
                raw_complete = False
                continue
            calls += 1
            raw_in += usage.get("prompt_tokens", 0)
            raw_out += usage.get("completion_tokens", 0)
            raw_cached += (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
    metrics = row.get("final_metrics") or {}
    result = {"task": slot["task"], "arm": slot["arm"], "status": slot["status"],
        "trial": str(trial.relative_to(ROOT)), "reward": (row.get("rewards") or {}).get("reward"),
        "error": row.get("error"), "error_category": row.get("error_category"),
        "verifier_error": row.get("verifier_error"), "task_digest": row.get("task_digest"),
        "tool_calls": row.get("n_tool_calls"), "trajectory": row.get("trajectory_summary"),
        "input_tokens": metrics.get("total_prompt_tokens"), "output_tokens": metrics.get("total_completion_tokens"),
        "cached_tokens": metrics.get("total_cached_tokens"),
        "estimated_cost_usd": metrics.get("total_cost_usd"),
        "agent_seconds": (row.get("timing") or {}).get("agent_execution"),
        "timing": row.get("timing"), "delivery_valid": audit.get("valid", False),
        "main_calls": audit.get("main_calls"), "helper_calls": audit.get("helper_calls"),
        "delivery_errors": audit.get("errors"), "actual_versions": row.get("harness_versions"),
        "raw_usage": {"calls": calls, "input": raw_in, "output": raw_out, "cached": raw_cached,
                      "complete": raw_complete},
        "shared_tools_confirmed": (trial / "shared-opencode.json").is_file(),
        "evidence_sha256": {str(p.relative_to(trial)): hash_file(p) for p in
            (path, audit_path, trace, trial / "trajectory/acp_trajectory.jsonl",
             trial / "shared-opencode.json", trial / "verifier/test-stdout.txt") if p.exists()}}
    result["total_tokens"] = (result["input_tokens"] + result["output_tokens"]
                              if result["input_tokens"] is not None and result["output_tokens"] is not None else None)
    result["usage_matches_raw"] = (raw_complete and calls > 0 and
        result["input_tokens"] == raw_in and result["output_tokens"] == raw_out)
    result["metric_admitted"] = (result["delivery_valid"] and not result["error"]
        and not result["verifier_error"] and result["reward"] is not None and result["usage_matches_raw"])
    return result


def summarize(directory):
    manifest = json.loads((directory / "campaign.json").read_text())
    rows = [collect(slot) for slot in manifest["schedule"]]
    report = {"campaign": str(directory.relative_to(ROOT)), "manifest_sha256": hash_file(directory / "campaign.json"),
              "rows": rows, "scope": "5 tasks, 1 trial per arm; descriptive pilot, not causal/stability proof"}
    write(directory / "comparison.json", report)
    lines = ["# 五任务 UML 辅助 skill 初步对照", "",
        f"模型：`{manifest['model']}`；OpenCode；每任务每组 1 次，串行，组别先后顺序交替。", "",
        "两组均强制提供完整原文，image 组额外先提供该任务全部 skill 的 PNG。总 token 含标题等辅助调用；缓存命中已包含在输入内，不能重复相加。", "",
        "| Task | 组别 | 得分 | 工具调用 | 任务模型调用 | 总 token | Agent 秒 | 传递检查 |", "|---|---|---:|---:|---:|---:|---:|---|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(k, "—")) for k in
            ("task", "arm", "reward", "tool_calls", "main_calls", "total_tokens", "agent_seconds", "delivery_valid")) + " |")
    lines += ["", "只将传递完整、正常评分且原始 usage 与汇总一致的完成运行纳入 token 对照；失败、超时、缺失与排除行仍保留在 comparison.json。每个任务只有一次重复，差异可能来自采样与求解过程。流程图同时提供了提炼内容，当前不能分离‘视觉形式’与‘总结内容’的作用。", "",
              "本报告只核查评分、传递和计量证据，不是训练数据或无评分投机的完整认证。原始配置、调用、评分、源文件哈希和公共工具记录见同目录与 comparison.json。"]
    (directory / "comparison.md").write_text("\n".join(lines) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "run", "report"))
    parser.add_argument("--campaign", type=Path)
    parser.add_argument("--only-ready", action="store_true", help="run healthy-control slots, leave others planned for a later resume")
    args = parser.parse_args()
    directory = (args.campaign or ROOT / "jobs/uml-expanded" /
                 datetime.now(timezone.utc).strftime("paired-%Y%m%dT%H%M%SZ")).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "campaign.json"
    if args.action == "report":
        summarize(directory)
        return 0
    if target.exists():
        manifest = json.loads(target.read_text())
        if manifest["code_sha256"] != source_identity():
            parser.error("campaign implementation changed; choose a new campaign")
    else:
        manifest = plan(directory)
        write(target, manifest)
    if args.action == "plan":
        print(target)
        return 0
    if not args.only_ready:
        for task in TASKS:
            control = controls().get(task)
            if not control or control["reward"] != 1 or control["error"]:
                parser.error(f"oracle control not healthy for {task}")
    manifest["controls"] = controls()
    write(target, manifest)
    for slot in manifest["schedule"]:
        if slot["status"] != "planned":
            continue
        control = controls().get(slot["task"])
        if not control or control["reward"] != 1 or control["error"]:
            print(f"WAIT {slot['task']}: oracle control not yet healthy; remains planned", flush=True)
            continue
        manifest["controls"] = controls()
        slot["status"] = "launched"
        slot["started_at_utc"] = datetime.now(timezone.utc).isoformat()
        write(target, manifest)
        log = directory / f"{slot['task']}-{slot['arm']}.log"
        print(f"START {slot['task']} / {slot['arm']}", flush=True)
        with log.open("w") as output:
            completed = subprocess.run(slot["command"], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
        slot["exit_code"] = completed.returncode
        slot["status"] = "finished" if completed.returncode == 0 else "failed"
        slot["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        write(target, manifest)
        summarize(directory)
        print(f"END {slot['task']} / {slot['arm']}: exit {completed.returncode}", flush=True)
    summarize(directory)
    print(directory / "comparison.md", flush=True)
    return int(any(slot["status"] != "finished" for slot in manifest["schedule"]))


if __name__ == "__main__":
    raise SystemExit(main())
