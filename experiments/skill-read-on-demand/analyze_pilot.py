"""Audit actual read-triggered experiments; do not regenerate any model output."""
import argparse
import json
from pathlib import Path
import re

from prepare import ROOT, build, load_policy
from protocol import digest, is_helper, message_text, validate_delivery


def read(path):
    return json.loads(path.read_text())


def normalize_skill_location(value):
    if isinstance(value, str):
        for prefix in ("/root/.agents/skills/", "/home/agent/.agents/skills/",
                       "/root/.opencode/skills/", "/home/agent/.opencode/skills/"):
            value = value.replace(prefix, "/skills/")
        return value
    if isinstance(value, list):
        return [normalize_skill_location(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize_skill_location(v) for k, v in value.items()}
    return value


def matrix_diagnostic(workspace):
    config = read(workspace / "system_config.json")
    params = read(workspace / "controller_params.json")
    ac, bc = [[0.0] * 12 for _ in range(12)], [[0.0] * 6 for _ in range(12)]
    vp, tp = config["v0"], 0.0
    for i, tension in enumerate(config["T_ref_initial"]):
        velocity = (config["EA"] - tp) / (config["EA"] - tension) * vp
        ac[i][i] = -velocity / config["L"]
        ac[i][i + 6] = (config["EA"] - tension) / config["L"]
        if i:
            ac[i][i - 1] = vp / config["L"]
            ac[i][i + 5] = (-config["EA"] + tp) / config["L"]
        ac[i + 6][i] = -config["R"] ** 2 / config["J"]
        ac[i + 6][i + 6] = -config["fb"] / config["J"]
        if i < 5:
            ac[i + 6][i + 1] = config["R"] ** 2 / config["J"]
        bc[i + 6][i] = config["R"] / config["J"]
        vp, tp = velocity, tension
    ad = [[float(i == j) + config["dt"] * ac[i][j] for j in range(12)] for i in range(12)]
    bd = [[config["dt"] * x for x in row] for row in bc]
    error = lambda a, b: max(abs(x - y) for xs, ys in zip(a, b) for x, y in zip(xs, ys))
    return dict(A_error_to_expected_euler=error(params["A_matrix"], ad),
                B_error_to_expected_euler=error(params["B_matrix"], bd),
                A_error_to_continuous=error(params["A_matrix"], ac),
                B_error_to_continuous=error(params["B_matrix"], bc))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    args = parser.parse_args()
    directory = args.campaign.resolve()
    manifest = read(directory / "campaign.json")
    assert all(s["status"] in ("finished", "failed") for s in manifest["schedule"]), "campaign is running"
    comparison = read(directory / "comparison.json")
    records, firsts = [], {}
    from benchflow.trajectories.types import redact_trajectory_obj
    for row in comparison["rows"]:
        if not row.get("trial"):
            records.append(dict(metrics=row, captured=False))
            continue
        trial = ROOT / row["trial"]
        policy = load_policy(build(row["task"], row["arm"], "uml-v1"))
        events = [json.loads(s) for s in (trial / "trajectory/llm_trajectory.jsonl").read_text().splitlines()]
        requests, loads_by_key, skill_tool_requests = [], {}, {}
        for n, event in enumerate(events, 1):
            data = event["request"]["body"]
            if is_helper(data):
                continue
            try:
                loads = validate_delivery(data, policy)
            except Exception:
                loads = validate_delivery(data, policy, body_transform=redact_trajectory_obj)
            images = [part for msg in data["messages"] if isinstance(msg.get("content"), list)
                      for part in msg["content"] if part.get("type") == "image_url"]
            for load in loads:
                loads_by_key.setdefault((load["call_id"], load["skill"]), dict(load, first_request=n))
            response = event.get("response", {})
            usage = (response.get("body") or {}).get("usage") or {}
            for choice in (response.get("body") or {}).get("choices") or []:
                for call in choice.get("message", {}).get("tool_calls") or []:
                    if call.get("function", {}).get("name") == "skill":
                        skill_tool_requests[call["id"]] = call["function"]
            requests.append(dict(trace_line=n, images=len(images), load_events=len(loads),
                                 image_skills=sorted({l["skill"] for l in loads if l["image_attached"]}),
                                 response_status=response.get("status_code"), usage=usage))
            if len(requests) == 1:
                firsts[(row["task"], row["arm"])] = data
                assert not images and not loads
                content = "\n".join(message_text(m.get("content")) for m in data["messages"])
                assert not any(a["body"] in content or redact_trajectory_obj(a["body"]) in content for a in policy["assets"])
            assert len(images) == sum(bool(l["image_attached"]) for l in loads)
        assert len(requests) == row["main_calls"]
        assert row["usage_matches_raw"] and row["task_digest_matches"]
        for name, expected in row["evidence_sha256"].items():
            assert digest((trial / name).read_bytes()) == expected
        inputs = []
        for name, sha in manifest["task_sources"][row["task"]]["files"].items():
            if not (name.endswith(".cif") or name in ("environment/r2r_simulator.py", "environment/system_config.json")):
                continue
            relative = "cif_files/" + Path(name).name if name.endswith(".cif") else name.removeprefix("environment/")
            saved = trial / "evidence/workspace" / relative
            inputs.append(dict(source=name, saved=str(saved.relative_to(ROOT)),
                               unchanged=saved.is_file() and digest(saved.read_bytes()) == sha))
        assert inputs and all(x["unchanged"] for x in inputs)
        accesses = []
        for n, line in enumerate((trial / "trajectory/acp_trajectory.jsonl").read_text().splitlines(), 1):
            e = json.loads(line)
            raw = e.get("raw_input") or {}
            if e.get("type") == "tool_call" and any(s in json.dumps(raw) for s in ("SKILL.md", "GUIDE.md", "/skills/")):
                accesses.append(dict(source_line=n, kind=e.get("kind"), input=raw))
        ctrf = trial / "verifier/ctrf.json"
        failed = ([t.get("name") for t in read(ctrf).get("results", {}).get("tests", []) if t.get("status") == "failed"]
                  if ctrf.exists() else re.findall(r"^FAILED\s+(.+)$", (trial / "verifier/test-stdout.txt").read_text(), re.M))
        if not ctrf.exists() and not failed:
            names = re.search(r"^Failed tests:\s*(.+)$", (trial / "verifier/test-stdout.txt").read_text(), re.M)
            failed = [s.strip() for s in names[1].split(",")] if names else []
        record = dict(metrics=row, captured=True, requests=requests, loads=list(loads_by_key.values()),
                      native_skill_requests=list(skill_tool_requests.values()), skill_file_accesses=accesses,
                      any_image_delivered=any(r["images"] for r in requests),
                      max_images_per_request=max((r["images"] for r in requests), default=0),
                      first_image_request=next((r["trace_line"] for r in requests if r["images"]), None),
                      image_request_count=sum(bool(r["images"]) for r in requests),
                      input_checks=inputs, failed_tests=failed)
        if row["task"] == "r2r-mpc-control" and (trial / "evidence/workspace/controller_params.json").exists():
            record["matrix_diagnostic"] = matrix_diagnostic(trial / "evidence/workspace")
        records.append(record)
    pairs = []
    for pair in comparison["pairs"]:
        task = pair["task"]
        a, b = firsts.get((task, "text")), firsts.get((task, "image"))
        pairs.append(dict(pair, first_requests_exactly_equal=a == b if a and b else None,
                          first_requests_equal_after_location_normalization=normalize_skill_location(a) == normalize_skill_location(b) if a and b else None))
    report = dict(method=manifest["method"], runs=records, pairs=pairs, recorded_tokens=comparison["recorded_tokens"],
                  estimated_cost_usd=comparison["estimated_cost_usd"],
                  analysis_code_sha256=digest(Path(__file__).read_bytes()),
                  scope="One run per task/arm, actual read-triggered media. Descriptive comparison, no stability or causal proof.")
    (directory / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 读取 skill 正文后自动附图：两题实际对照", "",
             f"协议 `{manifest['method']}`；模型 `{manifest['model']}`，OpenCode 1.19.5，原 v1 UML。晶体 text→image、R2R image→text，串行，每配置一次，无自动重试。", "",
             "开场只保留任务和原生目录信息；模型自行选择 skill 和工具。原生 skill 或文件／命令工具返回已登记 SKILL.md 正文后，图片条件自动附图，文字条件原样返回文字。未读取正文的运行保留。", "",
             "|题目|条件|原生分数|测试通过|总 token|Agent 秒|估算费用 USD|原生 skill 请求数|读取激活次数|实际图张数（单请求最多）|", "|---|---|---:|---|---:|---:|---:|---:|---:|---:|"]
    for x in records:
        r=x["metrics"];t=r.get("test_summary", {})
        label="晶体" if "crystallographic" in r["task"] else "R2R"
        lines.append(f"|{label}|{r['arm']}|{r.get('reward')}|{t.get('passed',0)}/{t.get('tests',0)}|{r.get('total_tokens',0):,}|{r.get('agent_seconds',0):.1f}|{r.get('estimated_cost_usd',0):.6f}|{len(x.get('native_skill_requests',[]))}|{len(x.get('loads',[]))}|{x.get('max_images_per_request',0)}|")
    lines += ["", "|题目|分数 文→图|token 变化|Agent 时间变化|估算费用变化|实际发图|首轮完全相同|", "|---|---|---:|---:|---:|---|---|"]
    for p in pairs:
        label="晶体" if "crystallographic" in p["task"] else "R2R"
        pct=lambda key:f"{p[key]:+.1f}%" if p.get(key) is not None else "无有效配对"
        lines.append(f"|{label}|{p['text_reward']}→{p['image_reward']}|{pct('total_tokens_change_pct')}|{pct('agent_seconds_change_pct')}|{pct('estimated_cost_usd_change_pct')}|{p['image_exposure']}|{p['first_requests_exactly_equal']}|")
    lines += ["", "## 用量与执行路径", "",
              "|题目／条件|缓存输入 token|非缓存输入 token|输出 token|主请求|工具调用|模型服务等待秒|Agent 其余执行秒|",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for x in records:
        r=x["metrics"]
        if not x.get("captured"):
            continue
        timing=r.get("timing") or {}
        lines.append(f"|{r['task']}／{r['arm']}|{r['cached_tokens']:,}|{r['input_tokens']-r['cached_tokens']:,}|{r['output_tokens']:,}|{r['main_calls']}|{r['tool_calls']}|{timing.get('provider_wait',0):.1f}|{timing.get('agent_without_provider_wait',0):.1f}|")
    lines += ["", "模型服务等待和 Agent 其余执行时间由原框架记录；后者包含仿真、搜索参数等工具执行，不能把时间差全部解释成图像处理开销。", "",
              "## 实际传递及文件访问", ""]
    for x in records:
        r=x["metrics"]
        lines += [f"### {r['task']} / {r['arm']}", "",
                  f"已识别 skill：{', '.join(r.get('activated_skills',[])) or '无'}。图片首次出现在原始请求行 {x.get('first_image_request')}；含图片的主请求 {x.get('image_request_count',0)} 次。", ""]
        for access in x.get("skill_file_accesses",[]):
            lines.append("- `" + json.dumps(access["input"], ensure_ascii=False).replace("`", "'") + "`")
        lines += ["", "未通过测试：" + (", ".join(x.get("failed_tests",[])) or "无") + "。", ""]
        if "matrix_diagnostic" in x:
            d=x["matrix_diagnostic"]
            lines += [f"已保存 A/B 与评分器 Euler 离散矩阵的最大误差分别为 {d['A_error_to_expected_euler']:.6f} / {d['B_error_to_expected_euler']:.6f}；与连续 Jacobian 的误差为 {d['A_error_to_continuous']:.6f} / {d['B_error_to_continuous']:.6f}。只核对提交，不修正或重跑。", ""]
    lines += ["## 解释范围", "",
              "同质量的效率变化只适用于两组得分相同的描述性比较；得分变化时优先报告质量。没有实际发图的配对不能评价图的效果。", "",
              "已核对每轮附件与实际读取的 skill、图片哈希、并行工具批次边界、完整用量、任务 digest 及留存输入文件。初始请求无全文或图；同一历史中不会重复追加相同 skill 的图片。发图证明模型请求包含图，不能证明模型使用了图进行推理。", "",
              "缓存 token 已计入输入，不能再加到总 token。输入、缓存输入和输出的计价不同，费用使用框架估算，不是供应商账单。Agent 时间不含容器准备与评分。每配置一次，采样、缓存和执行路径都会影响差异。", "",
              "首次请求因原生 skill 发现位置的 /root、/home/agent 以及 .agents、.opencode 别名不同；规范化这四类前缀后是否相同单列保存在 analysis.json，未改写原始请求。", "",
              f"四轮共记录 {report['recorded_tokens']:,} token，框架估算 ${report['estimated_cost_usd']:.6f}。上一轮 v1 零图发送的结果仅用于诊断传递机制，不用作本轮的配对控制。", "",
              "## 原始证据", ""]
    for x in records:
        r=x["metrics"]
        if not r.get("trial"):
            continue
        trial=ROOT/r["trial"]
        lines.append(f"- {r['task']}／{r['arm']}：[原生结果]({trial/'result.json'}) · [评分输出]({trial/'verifier/test-stdout.txt'}) · [传递审计]({trial/'skill-delivery.json'}) · [模型请求轨迹]({trial/'trajectory/llm_trajectory.jsonl'})")
    lines += ["", "[完整分析数据](analysis.json) · [预登记配置](campaign.json)"]
    (directory / "ANALYSIS.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(dict(runs=len(records), pairs=pairs, recorded_tokens=report["recorded_tokens"],
                         estimated_cost_usd=report["estimated_cost_usd"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
