"""Run frozen single-skill PNG replacements with existing BenchFlow logic.

One fresh all-v2-figures control per evaluation task; eight single-skill variants.
Shared controls are not eight independent replicates. No text/no-figure reruns.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from materials import HERE, ROOT, check, inventory, sha, write
from delivery import load_policy

sys.path.insert(0, str(ROOT / "experiments/uml-expanded"))
spec = importlib.util.spec_from_file_location("v3_legacy_metrics", ROOT / "experiments/uml-expanded/campaign.py")
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)
PYTHON = ROOT / "repos/benchflow/.venv/bin/python"
PREPARED = ROOT / ".runtime/uml-expanded/prepared-tasks"


def identity():
    paths = [HERE / n for n in ("campaign.py", "delivery.py", "smoke.py", "materials.py", "diagrams.py")]
    paths += [ROOT / "experiments" / n for n in ("shared_opencode.py", "env_config.py")]
    paths += [ROOT / "experiments/uml-flowchart" / n for n in ("delivery_runner.py", "delivery_protocol.py")]
    paths += [ROOT / "experiments/uml-expanded" / n for n in ("campaign.py", "study.py")]
    return {str(p.relative_to(ROOT)):sha(p) for p in paths}


def plan(directory):
    from env_config import load_env
    load_env(ROOT / ".env")
    m = check()
    oldplan = json.loads((ROOT / "jobs/uml-expanded/paired-five-full-skill-v2/campaign.json").read_text())
    agent, model = os.environ.get("EXP_AGENT"), os.environ.get("EXP_MODEL")
    if agent != oldplan["agent"] or model != oldplan["model"] or not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        raise ValueError("same configured agent/model and nonempty provider key required")
    if (os.environ.get("EXP_EFFORT") or None) != oldplan["effort"]:
        raise ValueError("keep old effort setting")
    schedule, task_sources = [], {}
    for index, (task, row) in enumerate(m["tasks"].items()):
        task_sources[task] = dict(prepared_files=inventory(PREPARED / task), skill_names=row["skills"])
        variants = list(row["variants"])
        # Keep baseline close in time. For odd blocks, one replacement precedes it.
        if index % 2:
            variants[0], variants[1] = variants[1], variants[0]
        for variant in variants:
            bundle = HERE / row["variants"][variant]["bundle"]
            policy = load_policy("image", bundle)
            jobs = directory / task / variant
            command = [str(PYTHON), str(HERE/"delivery.py"), "--arm", "image", "--bundle", str(bundle), "--",
                       "run", str(PREPARED), "-i", task, "--agent", agent, "--sandbox", "docker", "--trials", "1",
                       "--concurrency", "1", "--retry-attempts", "0", "--save-outputs", "--jobs-dir", str(jobs),
                       "--model", model, "--skill-mode", "with-skill", "--skills-dir", str(bundle)]
            if oldplan["effort"]:
                command += ["--reasoning-effort",oldplan["effort"]]
            schedule.append(dict(task=task, arm=variant, variant=variant,
                                 changed_skill=None if variant=="baseline" else variant,
                                 delivery_arm="image", jobs_dir=str(jobs), command=command,
                                 policy_id=policy["id"], status="planned"))
    assert len(schedule)==13
    return dict(schema=3, created_at_utc=datetime.now(timezone.utc).isoformat(),
                purpose="skill-first redesign; one skill PNG replacement at a time vs fresh v2 image control",
                agent=agent, model=model, effort=oldplan["effort"], seed=None, concurrency=1, trials_per_variant=1,
                order="fixed original task catalog; baseline first except one variant preceding baseline in odd blocks",
                material_sha256=sha(HERE/"manifest.json"), code_sha256=identity(),
                selection_sha256=sha(HERE/"selection.json"), source_review_sha256=sha(HERE/"SOURCE_REVIEW.json"),
                task_sources=task_sources, controls=oldplan["controls"], shared_tool_image=oldplan["shared_tool_image"],
                unchanged="Native task, inputs, grading, model, toolchain, forced-prefix wire protocol, time limits; no grader changes.",
                retry_rule="No selective rerun based on score. All failures/timeouts retained; investigate infra errors before any explicitly registered complete-block recovery.",
                limits=["one trial per variant", "shared baseline within task; comparisons correlated", "post-results source-constrained authoring, not blinded", "not matched atom-count or equal-pixel-area ablation", "measures diagram content/layout replacement package, not pure diagram-type causality"],
                schedule=schedule)


def validate(p):
    from benchflow._utils.task_authoring import task_digest
    check()
    assert p["code_sha256"]==identity()
    assert p["material_sha256"]==sha(HERE/"manifest.json")
    assert p["source_review_sha256"]==sha(HERE/"SOURCE_REVIEW.json")
    for task,row in p["task_sources"].items():
        assert inventory(PREPARED/task)==row["prepared_files"], task
        control=p["controls"][task]
        assert control["reward"]==1 and not control["error"]
        assert sha(ROOT/control["path"])==control["sha256"]
        assert task_digest(PREPARED/task)==control["task_digest"],task


def summarize(directory):
    p=json.loads((directory/"campaign.json").read_text())
    rows=[]
    for slot in p["schedule"]:
        row=metrics.collect(slot)
        row["changed_skill"]=slot["changed_skill"]
        row["variant"]=slot["variant"]
        if row.get("trial"):
            trial=ROOT/row["trial"]
            ctrf=trial/"verifier/ctrf.json"
            row["test_summary"]=((json.loads(ctrf.read_text()).get("results") or {}).get("summary") or {}) if ctrf.exists() else {}
            row["test_execution_confirmed"]=row["test_summary"].get("tests",0)>0
            row["matches_healthy_oracle_digest"]=row["task_digest"]==p["controls"][row["task"]]["task_digest"]
            row["metric_admitted"] &= row["test_execution_confirmed"] and row["matches_healthy_oracle_digest"]
            row["ctrf_sha256"]=sha(ctrf) if ctrf.exists() else None
        rows.append(row)
    pairs=[]
    for row in rows:
        if row["variant"]=="baseline":continue
        base=next(r for r in rows if r["task"]==row["task"] and r["variant"]=="baseline")
        admitted=bool(base.get("metric_admitted") and row.get("metric_admitted"))
        pair=dict(skill=row["changed_skill"], task=row["task"], admitted=admitted,
                  baseline_reward=base.get("reward"), new_reward=row.get("reward"),
                  both_pass=base.get("reward")==1 and row.get("reward")==1,
                  baseline_trial=base.get("trial"), new_trial=row.get("trial"))
        for k in ("total_tokens","tool_calls","agent_seconds","estimated_cost_usd"):
            a,b=base.get(k),row.get(k)
            pair[k+"_change_pct"]=100*(b/a-1) if admitted and a and b is not None else None
        pairs.append(pair)
    result=dict(scope=p["purpose"], rows=rows, pairs=pairs,
                unique_runs=len([r for r in rows if r.get("trial")]),
                recorded_tokens=sum(r.get("total_tokens") or 0 for r in rows),
                estimated_cost_usd=sum(r.get("estimated_cost_usd") or 0 for r in rows),limits=p["limits"])
    write(directory/"comparison.json",result)
    lines=["# Skill 单图替换实验", "", f"模型 `{p['model']}`；每变体一次；每个评测环境共享一个当轮旧图控制。", "",
           "|skill / control|状态|原生分数|测试通过/总数|工具|主请求|token|Agent 秒|传递有效|", "|---|---|---:|---|---:|---:|---:|---:|---|"]
    for r in rows:
        test=r.get("test_summary",{})
        name=r["changed_skill"] or ("旧图控制："+r["task"])
        lines.append("|"+"|".join(str(v) for v in (name,r["status"],r.get("reward","—"),f"{test.get('passed','—')}/{test.get('tests','—')}",r.get("tool_calls","—"),r.get("main_calls","—"),r.get("total_tokens","—"),r.get("agent_seconds","—"),r.get("delivery_valid","—")))+"|")
    lines += ["", "## 相对当轮旧图控制", "", "|被替换 skill|旧/新分数|token 变化|耗时变化|计量纳入|", "|---|---|---:|---:|---|"]
    for r in pairs:
        tok=r["total_tokens_change_pct"];sec=r["agent_seconds_change_pct"]
        lines.append(f"|{r['skill']}|{r['baseline_reward']}/{r['new_reward']}|{tok:+.1f}%|{sec:+.1f}%|{r['admitted']}|" if tok is not None else f"|{r['skill']}|{r['baseline_reward']}/{r['new_reward']}|—|—|{r['admitted']}|")
    lines += ["",f"实际已记录 token：{result['recorded_tokens']:,}；框架估算费用 ${result['estimated_cost_usd']:.6f}。", "", "失败、超时全部保留；不把低分运行的 token 降幅称为同质量节省。共享控制使多 skill 比较相关，不能把八个配对当独立重复。图的内容提炼、布局和面积一起变化，本轮不是纯图型因果验证。"]
    (directory/"comparison.md").write_text("\n".join(lines)+"\n")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("plan","run","report"))
    parser.add_argument("--campaign",type=Path,default=ROOT/"jobs/skill-structure-v3")
    args=parser.parse_args();directory=args.campaign.resolve();directory.mkdir(parents=True,exist_ok=True)
    target=directory/"campaign.json"
    if args.action=="report":summarize(directory);return 0
    if not target.exists():
        p=plan(directory);validate(p);write(target,p)
        write(directory/"material-manifest.json",check())
    p=json.loads(target.read_text());validate(p)
    if args.action=="plan":print(target);return 0
    if any(s["status"]=="launched" for s in p["schedule"]):
        raise RuntimeError("previous launched slot requires audit before resuming; never duplicate it")
    for slot in p["schedule"]:
        if slot["status"]!="planned":continue
        validate(p)
        assert shutil.disk_usage(ROOT).free>1500*1024**2
        slot.update(status="launched",started_at_utc=datetime.now(timezone.utc).isoformat());write(target,p)
        print(f"START {slot['task']} / {slot['variant']}",flush=True)
        with (directory/f"{slot['task']}-{slot['variant']}.log").open("w") as log:
            run=subprocess.run(slot["command"],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        slot.update(status="finished" if run.returncode==0 else "failed",exit_code=run.returncode,finished_at_utc=datetime.now(timezone.utc).isoformat());write(target,p)
        result=summarize(directory)
        row=next(r for r in result["rows"] if r["task"]==slot["task"] and r["variant"]==slot["variant"])
        print(f"END {slot['variant']}: exit={run.returncode}, reward={row.get('reward')}, tokens={row.get('total_tokens')}",flush=True)
        # Stop the campaign for missing result or real infrastructure error, not native task failure.
        if not row.get("trial") or row.get("verifier_error") or row.get("error_category") not in (None,"timeout"):
            print("INFRASTRUCTURE REVIEW REQUIRED; unstarted slots remain planned",flush=True)
            return 3
    summarize(directory)
    return int(any(s["status"]!="finished" for s in p["schedule"]))


if __name__=="__main__":
    raise SystemExit(main())
