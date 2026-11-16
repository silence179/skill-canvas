"""Audit image-only outcomes, actual exposure and native-tool failures offline."""
import argparse
import json
from pathlib import Path

from prepare import ROOT, build, load_policy
from protocol import digest, is_helper, validate_delivery

LABELS = {"llm-prefix-cache-replay": "前缀缓存回放", "energy-market-pricing": "电力市场定价",
          "manufacturing-fjsp-optimization": "制造排程", "exam-block-sequencing": "考试排程"}


def read(path):
    return json.loads(path.read_text())


def union_seconds(intervals):
    merged = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return sum(end-start for start,end in merged) / 1e9


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--campaign", type=Path, required=True)
    args = p.parse_args()
    directory = args.campaign.resolve()
    manifest = read(directory / "campaign.json")
    assert all(s["status"] in ("finished", "failed") for s in manifest["schedule"])
    comparison = read(directory / "comparison.json")
    from benchflow.trajectories.types import redact_trajectory_obj
    records = []
    for row in comparison["rows"]:
        if not row.get("trial"):
            records.append(dict(metrics=row, captured=False))
            continue
        trial = ROOT / row["trial"]
        policy = load_policy(build(row["task"], "image", "uml-v1"))
        requests, unique = [], {}
        for n, line in enumerate((trial / "trajectory/llm_trajectory.jsonl").read_text().splitlines(), 1):
            event= json.loads(line)
            data=event["request"]["body"]
            if is_helper(data):
                continue
            try:
                loads=validate_delivery(data,policy)
            except Exception:
                loads=validate_delivery(data,policy,body_transform=redact_trajectory_obj)
            count=sum(part.get("type")=="image_url" for m in data["messages"] if isinstance(m.get("content"),list) for part in m["content"])
            assert count==sum(bool(l["image_attached"]) for l in loads)
            if not requests:
                assert not count and not loads
            for load in loads:
                unique.setdefault((load["call_id"],load["skill"]),dict(load,first_request=n))
            requests.append(dict(trace_line=n,images=count,status=event.get("response",{}).get("status_code"),
                                 skill_reads=len(loads), image_skills=sorted({l["skill"] for l in loads if l["image_attached"]})))
        for name,sha in row["evidence_sha256"].items():
            assert digest((trial/name).read_bytes())==sha
        tools, intervals, failed = [], [], []
        for n,line in enumerate((trial/"trajectory/acp_trajectory.jsonl").read_text().splitlines(),1):
            e=json.loads(line)
            if e.get("type")!="tool_call":
                continue
            inp=e.get("raw_input") or {}
            if e.get("kind")=="skill" or any(s in json.dumps(inp) for s in ("SKILL.md","GUIDE.md","/skills/")):
                tools.append(dict(line=n,call_id=e.get("tool_call_id"),kind=e.get("kind"),status=e.get("status"),input=inp))
            if e.get("kind")=="skill":
                receipt=e.get("receipt") or {}
                a,b=receipt.get("first_observed_ns"),receipt.get("last_observed_ns")
                if a and b:
                    intervals.append((int(a),int(b)))
                if e.get("status")=="failed":
                    failed.append(dict(call_id=e.get("tool_call_id"),error=e.get("raw_output")))
        inputs=[]
        for name,sha in manifest["task_sources"][row["task"]]["files"].items():
            if not name.startswith("environment/") or name.startswith("environment/skills/") or name=="environment/Dockerfile":
                continue
            saved=trial/"evidence/workspace"/name.removeprefix("environment/")
            inputs.append(dict(source=name,saved=str(saved.relative_to(ROOT)),unchanged=saved.is_file() and digest(saved.read_bytes())==sha))
        tests=trial/"verifier/ctrf.json"
        failures=([dict(name=t.get("name"),message=t.get("message")) for t in read(tests).get("results",{}).get("tests",[]) if t.get("status")=="failed"] if tests.exists() else [])
        audit=read(trial/"skill-delivery.json")
        records.append(dict(metrics=row,captured=True,requests=requests,reads=list(unique.values()),skill_tools=tools,
                            actual_images=max((r["images"] for r in requests),default=0),
                            first_image_request=next((r["trace_line"] for r in requests if r["images"]),None),
                            successful_image_requests=sum(bool(r["images"] and r["status"]==200) for r in requests),
                            native_tool_failures=failed,native_skill_span_union_seconds=union_seconds(intervals),
                            input_checks=inputs,inputs_unchanged=bool(inputs) and all(x["unchanged"] for x in inputs),
                            failed_tests=failures,delivery_integrity=audit.get("delivery_valid"),run_complete=audit.get("run_complete")))
    report=dict(method=manifest["method"],runs=records,recorded_tokens=comparison["recorded_tokens"],estimated_cost_usd=comparison["estimated_cost_usd"],
                analysis_code_sha256=digest(Path(__file__).read_bytes()),scope="Four image-only reruns. No new text controls; no efficacy percentages inferred.")
    (directory/"analysis.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    fmt=lambda value,d=1: "—" if value is None else f"{value:.{d}f}"
    lines=["# 图片条件重跑：实际结果与传递核验","",
           f"协议 `{manifest['method']}`，模型 `{manifest['model']}`；原 v1 UML，OpenCode 1.19.5，串行，每题一次，无自动重试。旧混合批次按用户要求停止；本批只跑四个图片条件，没有新增文字对照。","",
           "|题目|原生得分|测试通过|总 token|Agent 秒|估算 USD|实际图张数（每请求最多）|成功携图请求|原生工具失败次数|",
           "|---|---:|---|---:|---:|---:|---:|---:|---:|"]
    for x in records:
        r=x["metrics"];t=r.get("test_summary") or {}
        lines.append(f"|{LABELS[r['task']]}|{r.get('reward')}|{t.get('passed',0)}/{t.get('tests',0)}|{r.get('total_tokens') or 0:,}|{fmt(r.get('agent_seconds'))}|{fmt(r.get('estimated_cost_usd'),6)}|{x.get('actual_images',0)}|{x.get('successful_image_requests',0)}|{len(x.get('native_tool_failures',[]))}|")
    lines += ["","## 逐题轨迹与原生失败"," "]
    for x in records:
        r=x["metrics"]
        lines += [f"### {LABELS[r['task']]}","",f"实际加载：{', '.join(r.get('activated_skills',[])) or '无'}；首张图在请求行 {x.get('first_image_request')}。","",
                  f"传递完整性 {x.get('delivery_integrity')}，运行完成 {x.get('run_complete')}，留存输入未变 {x.get('inputs_unchanged')}。原生错误：{r.get('error') or '无'}。","",
                  f"原生 skill 工具的时间跨度并集为 {x.get('native_skill_span_union_seconds',0):.1f} 秒（并行调用不重复累计）。该跨度可含下载／枚举等等待，不能直接等同图像处理。"," "]
        for t in x.get("skill_tools",[]):
            lines.append("- `"+json.dumps(t,ensure_ascii=False).replace("`","'")+"`")
        for f in x.get("native_tool_failures",[]):
            lines.append("- 原生工具失败：`"+json.dumps(f,ensure_ascii=False).replace("`","'")+"`")
        for f in x.get("failed_tests",[]):
            lines.append("- 评分失败："+str(f["name"])+"；"+str(f.get("message") or "见原始评分输出"))
        if r.get("trial"):
            trial=ROOT/r["trial"]
            lines += ["",f"[原生结果]({trial/'result.json'}) · [评分日志]({trial/'verifier/test-stdout.txt'}) · [图片审计]({trial/'skill-delivery.json'}) · [完整模型请求]({trial/'trajectory/llm_trajectory.jsonl'})"," "]
    lines += ["## 范围与计量","",
              "本批只验证图片条件是否完成任务以及是否实际收到图片。缺少本批文字对照，不能据此计算图的质量提升或 token 节省；不把旧强制输入结果拼接为控制组。每题一次，不能推断稳定效应。","",
              "所有初始请求无预置正文或图；图片与成功返回的 skill 正文关联，PNG 哈希核对原图，重复历史不累加副本。工具失败本身不触发图。HTTP 200 及携图请求证明附件进入请求，不能证明模型如何利用图。","",
              f"本批记录 {report['recorded_tokens']:,} token，框架估算 ${report['estimated_cost_usd']:.6f}；缓存 token 已包含在输入，费用不是供应商账单。旧批次的已完成、异常和用户中断尝试另保留，不覆盖、不重新标为成功。","",
              "[完整机器可读审计](analysis.json) · [预登记配置](campaign.json)"]
    (directory/"ANALYSIS.md").write_text("\n".join(lines)+"\n")
    print(json.dumps(dict(runs=len(records),actual_images={r["metrics"]["task"]:r.get("actual_images",0) for r in records},recorded_tokens=report["recorded_tokens"],estimated_cost_usd=report["estimated_cost_usd"]),ensure_ascii=False))


if __name__=="__main__":
    main()
