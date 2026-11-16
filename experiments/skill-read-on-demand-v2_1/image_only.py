"""Four image-only reruns, after the user stopped the mixed-arm campaign."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from prepare import HERE, ROOT, build, inventory, load_policy
from protocol import METHOD, digest, public_policy

TASKS = ("llm-prefix-cache-replay", "energy-market-pricing", "manufacturing-fjsp-optimization", "exam-block-sequencing")
PYTHON = ROOT / "repos/benchflow/.venv/bin/python"


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def identities():
    paths = [HERE / n for n in ("image_only.py", "protocol.py", "prepare.py", "runner.py")]
    paths += [ROOT / "experiments" / n for n in ("shared_opencode.py", "env_config.py")]
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths}


def plan(directory):
    from benchflow._utils.task_authoring import task_digest
    sys.path.insert(0, str(ROOT / "experiments"))
    from env_config import load_env
    load_env(ROOT / ".env")
    assert os.environ.get("EXP_AGENT") == "opencode" and os.environ.get("EXP_MODEL")
    tasks_root = ROOT / ".runtime/uml-expanded/prepared-tasks"
    sources, schedule = {}, []
    for task in TASKS:
        source = tasks_root / task
        sources[task] = dict(root=str(tasks_root), files=inventory(source), task_digest=task_digest(source))
        policy = load_policy(build(task, "image", "uml-v1"))
        jobs = directory / task / "image"
        command = [str(PYTHON), str(HERE / "runner.py"), "--task", task, "--arm", "image", "--figures", "uml-v1",
                   "--tasks-root", str(tasks_root), "--model", os.environ["EXP_MODEL"], "--trials", "1", "--concurrency", "1", "--jobs-dir", str(jobs)]
        if os.environ.get("EXP_EFFORT"):
            command += ["--effort", os.environ["EXP_EFFORT"]]
        schedule.append(dict(task=task, arm="image", status="planned", jobs_dir=str(jobs), command=command, policy=public_policy(policy)))
    return dict(method=METHOD, created_at_utc=now(), purpose="User-requested fresh image-only reruns; mixed-arm batch stopped and preserved.",
                model=os.environ["EXP_MODEL"], agent="opencode", effort=os.environ.get("EXP_EFFORT") or None,
                concurrency=1, trials_per_task=1, retries=0, seed=None, task_sources=sources, code_sha256=identities(),
                shared_tool_image=json.loads((ROOT / ".runtime/shared-opencode/image.json").read_text()),
                change="Only allow the known native 'ripgrep execution failed' tool result to pass back to the agent without activation; no body, image, task or scoring changes.",
                stopped_campaign="jobs/skill-read-on-demand-v2/remaining-four-2026-11-16",
                scope=["four image-only trials", "no text trials launched", "one run per task", "non-activation retained", "no new paired baseline inferred"], schedule=schedule)


def validate(manifest):
    from benchflow._utils.task_authoring import task_digest
    assert identities() == manifest["code_sha256"]
    for task, source in manifest["task_sources"].items():
        path = Path(source["root"]) / task
        assert inventory(path) == source["files"] and task_digest(path) == source["task_digest"]
    for slot in manifest["schedule"]:
        assert public_policy(load_policy(build(slot["task"], "image", "uml-v1"))) == slot["policy"]


def summarize(directory):
    sys.path.insert(0, str(ROOT / "experiments/uml-expanded"))
    spec = importlib.util.spec_from_file_location("image_only_existing_metrics", ROOT / "experiments/uml-expanded/campaign.py")
    metrics = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(metrics)
    manifest = json.loads((directory / "campaign.json").read_text())
    rows = []
    for slot in manifest["schedule"]:
        row = metrics.collect(slot)
        if row.get("trial"):
            trial = ROOT / row["trial"]
            ap = trial / "skill-delivery.json"
            audit = json.loads(ap.read_text()) if ap.exists() else {}
            ctrf = trial / "verifier/ctrf.json"
            row.update(activated_skills=audit.get("activated_skills", []), activations=audit.get("activations", []),
                       delivery_integrity=audit.get("delivery_valid"), run_complete=audit.get("run_complete"),
                       test_summary=json.loads(ctrf.read_text()).get("results", {}).get("summary", {}) if ctrf.exists() else {})
            row["images_attached"] = sum(bool(a.get("image_attached")) for a in row["activations"])
            row["native_skill_loads"] = sum(a.get("trigger") == "native_skill" for a in row["activations"])
            row["file_read_loads"] = sum(a.get("trigger") == "file_read" for a in row["activations"])
            row["task_digest_matches"] = row["task_digest"] == manifest["task_sources"][row["task"]]["task_digest"]
            row["metric_admitted"] &= row["task_digest_matches"] and row["test_summary"].get("tests", 0) > 0
        rows.append(row)
    report = dict(method=METHOD, rows=rows, scope=manifest["scope"],
                  recorded_tokens=sum(r.get("total_tokens") or 0 for r in rows),
                  estimated_cost_usd=sum(r.get("estimated_cost_usd") or 0 for r in rows))
    write(directory / "comparison.json", report)
    lines = ["# 四题图片条件重跑", "", "用户已停止原文字／图片批次，本批仅重跑图片条件，每题一次，无自动重试。保留所有原始异常与中断记录；不据此构造新的文字对照。", "",
             "|题目|状态|原生得分|测试通过|总 token|Agent 秒|框架估算 USD|附图次数|实际加载 skill|传递完整性|",
             "|---|---|---:|---|---:|---:|---:|---:|---|---|"]
    for r in rows:
        t=r.get("test_summary") or {}
        values=(r["task"],r["status"],r.get("reward"),f"{t.get('passed',0)}/{t.get('tests',0)}",r.get("total_tokens"),r.get("agent_seconds"),r.get("estimated_cost_usd"),r.get("images_attached"),", ".join(r.get("activated_skills",[])) or "无／待完成",r.get("delivery_integrity"))
        lines.append("|" + "|".join(str(v) for v in values) + "|")
    for r in rows:
        if r.get("error"):
            lines += ["", f"- {r['task']} 原生错误：{r['error']}"]
    lines += ["", f"本批已记录 {report['recorded_tokens']:,} token，估算 ${report['estimated_cost_usd']:.6f}；不是供应商账单。", "",
              "首次读取正文前不附图，原生工具失败时不算成功加载；模型若自行改用文件读取，返回正文后才附对应图片。实际发图不等于已证明模型使用了图。", ""]
    for r in rows:
        if r.get("trial"):
            trial=ROOT/r["trial"]
            lines.append(f"- {r['task']}：[原始结果]({trial/'result.json'}) · [传递审计]({trial/'skill-delivery.json'}) · [完整请求]({trial/'trajectory/llm_trajectory.jsonl'})")
    (directory / "comparison.md").write_text("\n".join(lines) + "\n")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "run", "report"))
    parser.add_argument("--campaign", type=Path, required=True)
    args=parser.parse_args()
    directory=args.campaign.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target=directory/"campaign.json"
    if not target.exists():
        write(target, plan(directory))
    manifest=json.loads(target.read_text())
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
        print(json.dumps(dict(event="start",task=slot["task"],arm="image",at=now())),flush=True)
        with (directory/(slot["task"]+"--image.log")).open("w") as stream:
            result=subprocess.run(slot["command"], cwd=ROOT, env=dict(os.environ,LITELLM_LOCAL_MODEL_COST_MAP="True"),stdout=stream,stderr=subprocess.STDOUT)
        slot.update(status="finished" if result.returncode==0 else "failed",exit_code=result.returncode,finished_at_utc=now())
        write(target,manifest)
        summarize(directory)
        print(json.dumps(dict(event="end",task=slot["task"],arm="image",exit_code=result.returncode,at=now())),flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
