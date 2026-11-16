"""Two-task paired pilot of on-demand skill loading, using original UML PNGs."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from prepare import HERE, ROOT, CRYSTAL, build, inventory, load_policy
from protocol import METHOD, digest, public_policy

PYTHON = ROOT / "repos/benchflow/.venv/bin/python"
TASKS = (CRYSTAL, "r2r-mpc-control")


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def identities():
    paths = [HERE / name for name in ("pilot.py", "runner.py", "prepare.py", "protocol.py")]
    paths += [ROOT / "experiments" / name for name in ("shared_opencode.py", "env_config.py")]
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths}


def plan(directory):
    from benchflow._utils.task_authoring import task_digest
    sys.path.insert(0, str(ROOT / "experiments"))
    from env_config import load_env
    load_env(ROOT / ".env")
    model = os.environ.get("EXP_MODEL")
    assert model and os.environ.get("EXP_AGENT") == "opencode"
    sources, schedule = {}, []
    for i, task in enumerate(TASKS):
        tasks = ROOT / ("repos/skillsbench/tasks" if task == CRYSTAL else ".runtime/uml-expanded/prepared-tasks")
        sources[task] = dict(root=str(tasks), task_digest=task_digest(tasks / task), files=inventory(tasks / task))
        for arm in (("text", "image") if i == 0 else ("image", "text")):
            bundle = build(task, arm, "uml-v1")
            policy = load_policy(bundle)
            jobs = directory / task / arm
            command = [str(PYTHON), str(HERE / "runner.py"), "--task", task, "--arm", arm,
                       "--figures", "uml-v1", "--tasks-root", str(tasks), "--model", model,
                       "--trials", "1", "--concurrency", "1", "--jobs-dir", str(jobs)]
            if os.environ.get("EXP_EFFORT"):
                command += ["--effort", os.environ["EXP_EFFORT"]]
            schedule.append(dict(task=task, arm=arm, jobs_dir=str(jobs), command=command,
                                 policy=public_policy(policy), status="planned"))
    return dict(created_at_utc=now(), method=METHOD, purpose="Two tasks, native on-demand text versus same text plus original UML at skill activation",
                model=model, agent="opencode", effort=os.environ.get("EXP_EFFORT") or None,
                trials_per_arm=1, concurrency=1, retries=0, seed=None,
                order="Crystal text/image, R2R image/text; serial",
                code_sha256=identities(), task_sources=sources,
                shared_tool_image=json.loads((ROOT / ".runtime/shared-opencode/image.json").read_text()),
                limits=["one observation per task/arm", "native non-activation is retained, not excluded",
                        "no forced-prefix historical run is used as a paired control", "original UML images fixed"],
                schedule=schedule)


def validate(manifest):
    from benchflow._utils.task_authoring import task_digest
    assert manifest["code_sha256"] == identities(), "campaign code changed"
    for task, source in manifest["task_sources"].items():
        p = Path(source["root"]) / task
        assert inventory(p) == source["files"] and task_digest(p) == source["task_digest"]
    for slot in manifest["schedule"]:
        bundle = build(slot["task"], slot["arm"], "uml-v1")
        assert public_policy(load_policy(bundle)) == slot["policy"]


def summarize(directory):
    # Reuse the established raw usage/result collector, with the new audit's
    # native-activation fields added. It does not launch anything.
    sys.path.insert(0, str(ROOT / "experiments/uml-expanded"))
    spec = importlib.util.spec_from_file_location("on_demand_existing_metrics", ROOT / "experiments/uml-expanded/campaign.py")
    metrics = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(metrics)
    manifest = json.loads((directory / "campaign.json").read_text())
    rows = []
    for slot in manifest["schedule"]:
        row = metrics.collect(slot)
        if row.get("trial"):
            trial = ROOT / row["trial"]
            audit = json.loads((trial / "skill-delivery.json").read_text()) if (trial / "skill-delivery.json").exists() else {}
            row.update(activated_skills=audit.get("activated_skills", []), no_activation=audit.get("no_activation"),
                       activations=audit.get("activations", []))
            ctrf = trial / "verifier/ctrf.json"
            row["test_summary"] = (json.loads(ctrf.read_text()).get("results", {}).get("summary", {}) if ctrf.exists() else {})
            row["task_digest_matches"] = row["task_digest"] == manifest["task_sources"][row["task"]]["task_digest"]
            row["metric_admitted"] &= row["task_digest_matches"] and row["test_summary"].get("tests", 0) > 0
        rows.append(row)
    pairs = []
    for task in TASKS:
        a, b = (next(r for r in rows if r["task"] == task and r["arm"] == arm) for arm in ("text", "image"))
        valid = bool(a.get("metric_admitted") and b.get("metric_admitted"))
        pair = dict(task=task, admitted=valid, text_reward=a.get("reward"), image_reward=b.get("reward"),
                    image_exposure=bool(b.get("activations")),
                    activation_mismatch=a.get("activated_skills") != b.get("activated_skills"))
        for key in ("total_tokens", "agent_seconds", "estimated_cost_usd", "tool_calls", "main_calls"):
            pair[key + "_change_pct"] = 100 * (b[key]/a[key] - 1) if valid and a.get(key) else None
        pairs.append(pair)
    result = dict(method=METHOD, rows=rows, pairs=pairs, scope=manifest["limits"],
                  recorded_tokens=sum(r.get("total_tokens") or 0 for r in rows),
                  estimated_cost_usd=sum(r.get("estimated_cost_usd") or 0 for r in rows))
    write(directory / "comparison.json", result)
    lines = ["# 按需加载：晶体与 R2R 两题对照", "", "每题每组一次，使用原 v1 UML；模型自行选择 skill。未调用 skill 的运行保留。", "",
             "|题目|组别|状态|分数|token|Agent 秒|估算费用 USD|主请求|实际加载 skill|传递有效|",
             "|---|---|---|---:|---:|---:|---:|---:|---|---|"]
    for r in rows:
        lines.append("|" + "|".join(str(x) for x in (r["task"], r["arm"], r["status"], r.get("reward", "—"),
            r.get("total_tokens", "—"), r.get("agent_seconds", "—"), r.get("estimated_cost_usd", "—"),
            r.get("main_calls", "—"), ", ".join(r.get("activated_skills", [])) or "未调用／待完成", r.get("delivery_valid", "—"))) + "|")
    lines += ["", "|题目|分数 文→图|token 变化|Agent 时间变化|估算费用变化|图片实际送达|",
              "|---|---|---:|---:|---:|---|"]
    for p in pairs:
        fmt = lambda k: f"{p[k]:+.1f}%" if p[k] is not None else "未完成有效配对"
        lines.append(f"|{p['task']}|{p['text_reward']}→{p['image_reward']}|{fmt('total_tokens_change_pct')}|{fmt('agent_seconds_change_pct')}|{fmt('estimated_cost_usd_change_pct')}|{p['image_exposure']}|")
    lines += ["", "完整原文通过原生 skill 工具加载；图片只跟随成功加载的工具结果。相邻脚本和参考文件按需读取。", "",
              "一次观察不能推断稳定收益；得分不同时不能将 token 减少称为同质量节省。未激活的图像组不能证明图像有效或无效。", "",
              f"本批已记录 {result['recorded_tokens']:,} token，估算费用 ${result['estimated_cost_usd']:.6f}；不是供应商账单。"]
    (directory / "comparison.md").write_text("\n".join(lines) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "run", "report"))
    parser.add_argument("--campaign", type=Path, required=True)
    args = parser.parse_args()
    directory = args.campaign.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "campaign.json"
    if not target.exists():
        write(target, plan(directory))
    manifest = json.loads(target.read_text())
    validate(manifest)
    if args.action == "plan":
        print(target)
        return 0
    if args.action == "report":
        summarize(directory)
        return 0
    for slot in manifest["schedule"]:
        if slot["status"] != "planned":
            continue
        validate(manifest)
        slot.update(status="launched", started_at_utc=now())
        write(target, manifest)
        log = directory / (slot["task"] + "--" + slot["arm"] + ".log")
        print(json.dumps(dict(event="start", task=slot["task"], arm=slot["arm"], at=now())), flush=True)
        env = dict(os.environ, LITELLM_LOCAL_MODEL_COST_MAP="True")
        with log.open("w") as stream:
            completed = subprocess.run(slot["command"], cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        slot.update(status="finished" if completed.returncode == 0 else "failed", exit_code=completed.returncode, finished_at_utc=now())
        write(target, manifest)
        summarize(directory)
        print(json.dumps(dict(event="end", task=slot["task"], arm=slot["arm"], exit_code=completed.returncode, at=now())), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
