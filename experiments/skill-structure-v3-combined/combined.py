"""User-steered continuation: one combined-new-diagram run per remaining task.

This packages ALREADY FROZEN skill-derived figures. It does not author diagrams,
read task questions, instances, graders, or solutions for content generation.
"""
import argparse
import base64
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
V3=ROOT/"experiments/skill-structure-v3"
sys.path.insert(0,str(V3))
from materials import check as check_v3, inventory, sha, write
import delivery as previous_delivery
from delivery_protocol import METHOD,digest,policy_id,validate_policy
sys.path.insert(0,str(ROOT/"experiments/uml-expanded"))
spec=importlib.util.spec_from_file_location("combined_native_metrics",ROOT/"experiments/uml-expanded/campaign.py")
metrics=importlib.util.module_from_spec(spec);spec.loader.exec_module(metrics)
PYTHON=ROOT/"repos/benchflow/.venv/bin/python"
PREPARED=ROOT/".runtime/uml-expanded/prepared-tasks"
TASKS=("r2r-mpc-control","exam-block-sequencing","manufacturing-fjsp-optimization")


def code_identity():
    paths=[Path(__file__),V3/"materials.py",V3/"diagrams.py",V3/"delivery.py"]
    paths += [ROOT/"experiments/uml-flowchart"/n for n in ("delivery_runner.py","delivery_protocol.py")]
    paths += [ROOT/"experiments"/n for n in ("shared_opencode.py","env_config.py")]
    return {str(p.relative_to(ROOT)):sha(p) for p in paths}


def check():
    old=check_v3()
    m=json.loads((HERE/"manifest.json").read_text())
    assert m["v3_material_sha256"]==sha(V3/"manifest.json")
    assert m["packager_sha256"]==sha(Path(__file__))
    for task,row in m["tasks"].items():
        original=old["tasks"][task]["variants"]["baseline"]["files"]
        files=inventory(HERE/row["bundle"])
        assert files==row["files"]
        differences=sorted(p for p in set(files)|set(original) if files.get(p)!=original.get(p))
        assert differences==sorted(f"{s}/assets/flowchart.png" for s in row["changed_skills"])
        for s in row["changed_skills"]:
            assert (HERE/row["bundle"]/s/"assets/flowchart.png").read_bytes()==(V3/"figures"/s/"diagram.png").read_bytes()
    return m


def build():
    if (HERE/"manifest.json").exists():return check()
    old=check_v3()
    m=dict(created_at_utc=datetime.now(timezone.utc).isoformat(),v3_material_sha256=sha(V3/"manifest.json"),
           packager_sha256=sha(Path(__file__)),basis="Already frozen skill-derived figures; task identifiers used only to group their original evaluation environment.",
           tasks={})
    for task in TASKS:
        row=old["tasks"][task];skills=sorted(s for s in row["skills"] if s in old["figures"])
        bundle=HERE/"tasks"/task/"bundle"
        assert not bundle.exists(), "do not overwrite packaged materials"
        shutil.copytree(V3/row["variants"]["baseline"]["bundle"],bundle)
        for skill in skills:shutil.copyfile(V3/"figures"/skill/"diagram.png",bundle/skill/"assets/flowchart.png")
        m["tasks"][task]=dict(skills=row["skills"],changed_skills=skills,bundle=str(bundle.relative_to(HERE)),files=inventory(bundle))
    write(HERE/"manifest.json",m);return check()


def load_policy(arm,bundle):
    m=check();bundle=Path(bundle).resolve()
    matches=[(t,r) for t,r in m["tasks"].items() if (HERE/r["bundle"]).resolve()==bundle]
    assert arm=="image" and len(matches)==1
    task,row=matches[0];assets=[]
    for skill in row["skills"]:
        guide=(bundle/skill/"GUIDE.md").read_bytes();png=(bundle/skill/"assets/flowchart.png").read_bytes()
        assets.append(dict(skill=skill,guide_text=guide.decode(),guide_sha256=digest(guide),image_data=base64.b64encode(png).decode(),image_sha256=digest(png)))
    policy=dict(method=METHOD,arm="image",task=task,skill_names=row["skills"],study_sha256=sha(HERE/"manifest.json"),assets=assets,
                adapter_sha256={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/"experiments/uml-flowchart/delivery_runner.py",ROOT/"experiments/uml-flowchart/delivery_protocol.py")})
    policy["id"]=policy_id(policy);validate_policy(policy);return policy


def deliver():
    from env_config import load_env
    import shared_opencode
    load_env(ROOT/".env");os.environ.setdefault("DOCKER_CONFIG",str(ROOT/".runtime/docker"))
    record=shared_opencode.load_record();shared_opencode.install_adapter(record)
    previous_delivery.legacy.load_policy=load_policy
    return previous_delivery.legacy.main()


def plan(directory):
    from env_config import load_env
    load_env(ROOT/".env");m=build()
    old=json.loads((ROOT/"jobs/skill-structure-v3/campaign.json").read_text())
    assert os.environ.get("EXP_MODEL")==old["model"] and os.environ.get("EXP_AGENT")==old["agent"]
    schedule=[]
    for task,row in m["tasks"].items():
        bundle=HERE/row["bundle"];policy=load_policy("image",bundle);jobs=directory/task/"combined"
        cmd=[str(PYTHON),str(Path(__file__)),"deliver","--arm","image","--bundle",str(bundle),"--","run",str(PREPARED),"-i",task,
             "--agent",old["agent"],"--sandbox","docker","--trials","1","--concurrency","1","--retry-attempts","0","--save-outputs",
             "--jobs-dir",str(jobs),"--model",old["model"],"--skill-mode","with-skill","--skills-dir",str(bundle)]
        if old["effort"]:cmd += ["--reasoning-effort",old["effort"]]
        schedule.append(dict(task=task,arm="combined",variant="combined",changed_skills=row["changed_skills"],jobs_dir=str(jobs),command=cmd,policy_id=policy["id"],status="planned"))
    return dict(created_at_utc=datetime.now(timezone.utc).isoformat(),purpose="User-directed one combined-new-figure attempt per remaining task; no additional baseline runs",
                model=old["model"],agent=old["agent"],effort=old["effort"],seed=None,concurrency=1,
                material_sha256=sha(HERE/"manifest.json"),code_sha256=code_identity(),
                task_sources={t:old["task_sources"][t] for t in TASKS},controls=old["controls"],shared_tool_image=old["shared_tool_image"],
                baseline_rule="R2R: reuse this session's completed v3 baseline; exam/manufacturing: descriptive comparison with historical v2 image runs. Do not claim fresh randomized equivalence.",
                user_amendment=str((ROOT/"jobs/skill-structure-v3/user-steering-amendment.json").relative_to(ROOT)),schedule=schedule)


def validate(p):
    from benchflow._utils.task_authoring import task_digest
    check();assert p["code_sha256"]==code_identity();assert p["material_sha256"]==sha(HERE/"manifest.json")
    for t,row in p["task_sources"].items():
        assert inventory(PREPARED/t)==row["prepared_files"]
        control=p["controls"][t];assert control["reward"]==1 and not control["error"]
        assert task_digest(PREPARED/t)==control["task_digest"]


def summarize(directory):
    p=json.loads((directory/"campaign.json").read_text());rows=[]
    for slot in p["schedule"]:
        row=metrics.collect(slot);row["changed_skills"]=slot["changed_skills"]
        if row.get("trial"):
            ctrf=ROOT/row["trial"]/"verifier/ctrf.json"
            row["test_summary"]=((json.loads(ctrf.read_text()).get("results") or {}).get("summary") or {}) if ctrf.exists() else {}
            row["test_execution_confirmed"]=row["test_summary"].get("tests",0)>0
            row["matches_healthy_oracle_digest"]=row["task_digest"]==p["controls"][row["task"]]["task_digest"]
            row["metric_admitted"] &= row["test_execution_confirmed"] and row["matches_healthy_oracle_digest"]
        rows.append(row)
    result=dict(rows=rows,recorded_tokens=sum(r.get("total_tokens") or 0 for r in rows),estimated_cost_usd=sum(r.get("estimated_cost_usd") or 0 for r in rows),baseline_rule=p["baseline_rule"])
    write(directory/"comparison.json",result)
    lines=["# 用户调整后的组合图续跑", "",p["purpose"],"", "|评测环境|一起替换的 skill|状态|原生分数|token|工具|Agent 秒|", "|---|---|---|---:|---:|---:|---:|"]
    for r in rows:lines.append("|"+"|".join(str(x) for x in (r["task"],", ".join(r["changed_skills"]),r["status"],r.get("reward","—"),r.get("total_tokens","—"),r.get("tool_calls","—"),r.get("agent_seconds","—")))+"|")
    lines += ["",p["baseline_rule"],"",f"本续跑已记录 {result['recorded_tokens']:,} token，框架估算费用 ${result['estimated_cost_usd']:.6f}。"]
    (directory/"comparison.md").write_text("\n".join(lines)+"\n");return result


def main():
    if sys.argv[1:2]==["deliver"]:
        sys.argv.pop(1);return deliver()
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("action",choices=("plan","run","report","wire"));parser.add_argument("--campaign",type=Path,default=ROOT/"jobs/skill-structure-v3-combined")
    args=parser.parse_args();directory=args.campaign.resolve();directory.mkdir(parents=True,exist_ok=True)
    if args.action=="wire":
        import asyncio
        import smoke
        wire=smoke.wire if hasattr(smoke,"wire") else smoke
        m=build();checks=[]
        for task,row in m["tasks"].items():
            policy=load_policy("image",HERE/row["bundle"]);wire.load_policy=lambda *a,p=policy:p
            checks.append(asyncio.run(wire.check(task,False)))
        write(HERE/"wire-check.json",checks);print(json.dumps(dict(valid=all(r["valid"] for r in checks),payloads=len(checks))));return 0
    if args.action=="report":summarize(directory);return 0
    target=directory/"campaign.json"
    if not target.exists():write(target,plan(directory))
    p=json.loads(target.read_text());validate(p)
    if args.action=="plan":print(target);return 0
    assert not any(s["status"]=="launched" for s in p["schedule"]),"audit previously launched slot; do not duplicate"
    for s in p["schedule"]:
        if s["status"]!="planned":continue
        validate(p);assert shutil.disk_usage(ROOT).free>1500*1024**2
        s.update(status="launched",started_at_utc=datetime.now(timezone.utc).isoformat());write(target,p)
        print("START combined "+s["task"],flush=True)
        with (directory/(s["task"]+".log")).open("w") as log:r=subprocess.run(s["command"],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        s.update(status="finished" if r.returncode==0 else "failed",exit_code=r.returncode,finished_at_utc=datetime.now(timezone.utc).isoformat());write(target,p)
        result=summarize(directory);row=next(x for x in result["rows"] if x["task"]==s["task"])
        print(f"END combined {s['task']}: reward={row.get('reward')}, tokens={row.get('total_tokens')}",flush=True)
        if not row.get("trial") or row.get("verifier_error") or row.get("error_category") not in (None,"timeout"):return 3
    return 0


if __name__=="__main__":raise SystemExit(main())
