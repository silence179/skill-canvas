"""Scoped read-only evidence audit of completed single-skill interventions.

Native rewards are preserved. Probe flags require interpretation; this is not
a blanket reward-integrity certification or a training-readiness audit.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

from materials import HERE, ROOT, check, inventory, sha, write
from delivery import load_policy
from delivery_protocol import is_helper, prefix_content, public_policy
from benchflow.trajectories.types import redact_trajectory_obj

INPUTS = {
    "llm-prefix-cache-replay": ("trace.jsonl", "config.json"),
    "energy-market-pricing": ("network.json",),
    "r2r-mpc-control": ("r2r_simulator.py", "system_config.json"),
    "exam-block-sequencing": ("data",),
    "manufacturing-fjsp-optimization": ("data",),
}


def audit(directory,materials_context=None):
    context=materials_context or {"check":check,"root":HERE,"load_policy":load_policy}
    m=context["check"]()
    p=json.loads((directory/"campaign.json").read_text())
    comparison=json.loads((directory/"comparison.json").read_text())
    rows=[]
    for slot in p["schedule"]:
        if slot["status"] not in ("finished","failed"):continue
        found=list(Path(slot["jobs_dir"]).glob("*/*/result.json"))
        if len(found)!=1:
            rows.append(dict(task=slot["task"],variant=slot["variant"],missing_result=True))
            continue
        trial=found[0].parent
        r=json.loads(found[0].read_text())
        row=next(x for x in comparison["rows"] if x["task"]==slot["task"] and x.get("variant",x.get("arm"))==slot["variant"])
        material_row=m["tasks"][slot["task"]]
        bundle=context["root"]/(material_row["variants"][slot["variant"]]["bundle"] if "variants" in material_row else material_row["bundle"])
        policy=context["load_policy"]("image",bundle)
        expected=prefix_content(policy);redacted=redact_trajectory_obj(expected)
        captures=[];statuses=[];response_models=set();request_models=set()
        prompt=completion=cached=0;usage_count=0;missing_usage=0;first_main_prompt_tokens=None
        llm=trial/"trajectory/llm_trajectory.jsonl"
        for n,line in enumerate(llm.read_text().splitlines(),1):
            event=json.loads(line);body=event["request"]["body"]
            request_models.add(str(body.get("model")))
            response=event.get("response",{});rb=response.get("body",{})
            statuses.append(response.get("status_code"))
            response_models.add(str(rb.get("model")))
            if not is_helper(body):
                first=next(x for x in body["messages"] if x["role"]=="user")
                captures.append(dict(line=n,exact=first["content"]==expected or first["content"]==redacted,
                                     image_count=sum(x.get("type")=="image_url" for x in first["content"])))
            usage=rb.get("usage")
            if not usage:missing_usage+=1;continue
            if not is_helper(body) and first_main_prompt_tokens is None and response.get("status_code")==200:
                first_main_prompt_tokens=usage.get("prompt_tokens")
            usage_count+=1;prompt+=usage.get("prompt_tokens",0);completion+=usage.get("completion_tokens",0)
            cached+=(usage.get("prompt_tokens_details") or {}).get("cached_tokens",0)
        native_audit=json.loads((trial/"skill-delivery.json").read_text())
        policy_match=native_audit["policy"]==public_policy(policy) and policy["id"]==slot["policy_id"]
        exact=bool(captures) and all(c["exact"] and c["image_count"]==len(policy["assets"]) for c in captures)
        source=ROOT/".runtime/uml-expanded/prepared-tasks"/slot["task"] / "environment"
        inputs=[]
        for rel in INPUTS[slot["task"]]:
            path=source/rel
            inputs.extend(path.rglob("*") if path.is_dir() else [path])
        input_checks=[]
        for f in inputs:
            if not f.is_file():continue
            rel=f.relative_to(source);captured=trial/"evidence/workspace"/rel
            input_checks.append(dict(path=str(rel),unchanged=captured.is_file() and captured.read_bytes()==f.read_bytes()))
        findings=[];tools=0
        acp=trial/"trajectory/acp_trajectory.jsonl"
        events=[json.loads(x) for x in acp.read_text().splitlines()]
        for n,e in enumerate(events,1):
            if e.get("type")!="tool_call":continue
            tools+=1
            command=str((e.get("raw_input") or {}).get("command",e.get("title","")))
            if re.search(r"/(?:verifier\b|testbed_verify\b|opt/runtime/verifier\b|logs/verifier\b)",command,re.I):
                output=str((e.get("raw_output") or {}).get("output",""))
                denied=bool(re.search(r"permission denied|no such file|does not exist|cannot access",output,re.I))
                findings.append(dict(pattern="grader_path_probe",line=n,command_excerpt=command[:350],
                                     access_denied_signal=denied,
                                     assessment="probe observed; denied/missing signal" if denied else "probe observed; inspect exact output before assessing successful access"))
            if re.search(r"(?:https?://|git clone|webfetch)",command,re.I):
                findings.append(dict(pattern="external_fetch",line=n,command_excerpt=command[:350],
                                     assessment="reference/dependency access requires context; not automatically answer contamination"))
            if re.search(r"(?:pytest|unittest).*(?:monkeypatch|skip|xfail)|(?:chmod|rm |cp |sed |write).*/verifier",command,re.I):
                findings.append(dict(pattern="possible_grading_mutation",line=n,command_excerpt=command[:350],assessment="manual review required"))
        stdout=(trial/"verifier/test-stdout.txt").read_text()
        # Pytest parameter cases may be collapsed by name in normalized CTRF.
        stdout_counts={}
        for status in ("passed","failed","skipped"):
            matches=re.findall(rf"\b(\d+) {status}\b",stdout)
            if matches:stdout_counts[status]=int(matches[-1])
        native_summary=row.get("test_summary",{})
        checks=dict(exact_png_guide_capture=exact,policy_matches=policy_match,
                    shared_tool_receipt=json.loads((trial/"shared-opencode.json").read_text())==p["shared_tool_image"],
                    visible_inputs_unchanged=bool(input_checks) and all(x["unchanged"] for x in input_checks),
                    task_digest_matches=row.get("matches_healthy_oracle_digest"),
                    raw_usage_matches=missing_usage==0 and prompt==row["input_tokens"] and completion==row["output_tokens"] and cached==row["cached_tokens"],
                    actual_verifier_execution=bool(native_summary.get("tests",0)),
                    native_tool_count_matches=tools==row.get("tool_calls"))
        rows.append(dict(task=slot["task"],variant=slot["variant"],changed_skill=slot.get("changed_skill"),changed_skills=slot.get("changed_skills"),
                         trial=str(trial.relative_to(ROOT)),reward=row.get("reward"),error=row.get("error"),
                         error_category=row.get("error_category"),metric_admitted=row.get("metric_admitted"),
                         evaluation_status="scored_timeout" if row.get("error_category")=="timeout" else ("native_pass" if row.get("reward")==1 else "native_fail"),
                         checks=checks,captured_main_requests=len(captures),request_models=sorted(request_models),
                         response_models=sorted(response_models),http_statuses=statuses,
                         usage=dict(calls_with_usage=usage_count,missing_usage=missing_usage,input=prompt,output=completion,cached=cached),
                         first_successful_main_prompt_tokens=first_main_prompt_tokens,
                         ctrf_name_group_summary=native_summary,pytest_case_summary=stdout_counts,
                         inputs=input_checks,integrity_findings=findings,
                         raw_evidence_sha256={str(f.relative_to(trial)):sha(f) for f in
                             (found[0],llm,acp,trial/"skill-delivery.json",trial/"verifier/test-stdout.txt",trial/"verifier/ctrf.json") if f.is_file()}))
    cancelled=sum(s["status"]=="cancelled_by_user" for s in p["schedule"])
    report=dict(created_at_utc=datetime.now(timezone.utc).isoformat(),complete=len(rows)+cancelled==len(p["schedule"]),cancelled_by_user=cancelled,
                reviewed=len(rows),planned=len(p["schedule"]),rows=rows,source_sha256=sha(Path(__file__)),
                scope="Scoped input/delivery/usage/native-evaluation audit; integrity probes are signals for manual review. Training readiness not assessed. No blanket no-reward-hacking certificate.",
                review_skill=str(ROOT/"repos/benchflow/.agents/skills/benchflow-experiment-review/SKILL.md"))
    write(directory/"evidence-audit.json",report)
    print(json.dumps(dict(complete=report["complete"],reviewed=len(rows),planned=report["planned"],
                         capture_pass=sum(r.get("checks",{}).get("exact_png_guide_capture",False) for r in rows),
                         input_pass=sum(r.get("checks",{}).get("visible_inputs_unchanged",False) for r in rows)),ensure_ascii=False))
    return report


if __name__=="__main__":
    audit((Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/"jobs/skill-structure-v3").resolve())
