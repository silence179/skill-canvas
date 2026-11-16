"""Offline audit of this pilot; supports both native verifier output formats."""
import argparse
import copy
import json
from pathlib import Path
import re

from prepare import HERE, ROOT, build, load_policy
from protocol import digest, is_helper, message_text, validate_delivery


def read(path):
    return json.loads(path.read_text())


def normalize_skill_location(value):
    if isinstance(value, str):
        return value.replace("/home/agent/.opencode/skills/", "/root/.opencode/skills/")
    if isinstance(value, list):
        return [normalize_skill_location(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize_skill_location(v) for k, v in value.items()}
    return value


def matrix_diagnostic(workspace):
    """Compare saved outputs with the native grader's specified Euler matrices."""
    c, p = read(workspace / "system_config.json"), read(workspace / "controller_params.json")
    ac, bc = [[0.0] * 12 for _ in range(12)], [[0.0] * 6 for _ in range(12)]
    vp, tp = c["v0"], 0.0
    for i, tension in enumerate(c["T_ref_initial"]):
        velocity = (c["EA"] - tp) / (c["EA"] - tension) * vp
        ac[i][i] = -velocity / c["L"]
        ac[i][i + 6] = (c["EA"] - tension) / c["L"]
        if i:
            ac[i][i - 1] = vp / c["L"]
            ac[i][i + 5] = (-c["EA"] + tp) / c["L"]
        ac[i + 6][i] = -c["R"] ** 2 / c["J"]
        ac[i + 6][i + 6] = -c["fb"] / c["J"]
        if i < 5:
            ac[i + 6][i + 1] = c["R"] ** 2 / c["J"]
        bc[i + 6][i] = c["R"] / c["J"]
        vp, tp = velocity, tension
    ad = [[float(i == j) + c["dt"] * ac[i][j] for j in range(12)] for i in range(12)]
    bd = [[c["dt"] * x for x in row] for row in bc]
    error = lambda a, b: max(abs(x - y) for xs, ys in zip(a, b) for x, y in zip(xs, ys))
    return dict(A_error_to_expected_euler=error(p["A_matrix"], ad),
                B_error_to_expected_euler=error(p["B_matrix"], bd),
                A_error_to_continuous=error(p["A_matrix"], ac),
                B_error_to_continuous=error(p["B_matrix"], bc))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    args = parser.parse_args()
    directory = args.campaign.resolve()
    campaign = read(directory / "campaign.json")
    assert all(s["status"] in ("finished", "failed") for s in campaign["schedule"]), "pilot is still running"
    metrics = read(directory / "comparison.json")
    records, firsts = [], {}
    for source in metrics["rows"]:
        row = copy.deepcopy(source)
        trial = ROOT / row["trial"]
        policy = load_policy(build(row["task"], row["arm"], "uml-v1"))
        trace = trial / "trajectory/llm_trajectory.jsonl"
        requests, helpers = [], 0
        body_seen = {}
        original_bodies = {a["skill"]: a["body"] for a in policy["assets"]}
        for n, line in enumerate(trace.read_text().splitlines(), 1):
            event = json.loads(line)
            body = event["request"]["body"]
            if is_helper(body):
                helpers += 1
                continue
            try:
                loads = validate_delivery(body, policy)
            except Exception:
                from benchflow.trajectories.types import redact_trajectory_obj
                loads = validate_delivery(body, policy, body_transform=redact_trajectory_obj)
            messages = body["messages"]
            count = sum(p.get("type") == "image_url" for m in messages if isinstance(m.get("content"), list) for p in m["content"])
            combined = "\n".join(message_text(m.get("content")) for m in messages)
            for skill, text in original_bodies.items():
                if text in combined:
                    body_seen.setdefault(skill, n)
            requests.append(dict(trace_line=n, images=count, successful_skill_calls=len(loads),
                                 status=event["response"].get("status_code"),
                                 input_tokens=(event["response"].get("body", {}).get("usage") or {}).get("prompt_tokens")))
            if len(requests) == 1:
                firsts[(row["task"], row["arm"])] = body
        assert requests and requests[0]["images"] == 0 and requests[0]["successful_skill_calls"] == 0
        first_text = "\n".join(message_text(m.get("content")) for m in firsts[(row["task"], row["arm"])]["messages"])
        assert not any(text in first_text for text in original_bodies.values())
        test_stdout = (trial / "verifier/test-stdout.txt").read_text(errors="replace")
        ctrf = trial / "verifier/ctrf.json"
        if ctrf.exists():
            tests = read(ctrf).get("results", {}).get("summary", {})
            format_name = "native_ctrf"
        else:
            match = re.search(r"Total tests:\s*(\d+)\s+Passed:\s*(\d+)\s+Failed:\s*(\d+)", test_stdout)
            assert match, "native test execution evidence missing"
            tests = dict(tests=int(match[1]), passed=int(match[2]), failed=int(match[3]))
            format_name = "native_stdout_summary"
        row["tests"] = tests
        row["native_test_format"] = format_name
        row["analysis_admitted"] = bool(row.get("delivery_valid") and row.get("usage_matches_raw")
            and row.get("task_digest_matches") and not row.get("error") and not row.get("verifier_error") and tests.get("tests", 0) > 0)
        accesses = []
        acp = trial / "trajectory/acp_trajectory.jsonl"
        for n, line in enumerate(acp.read_text().splitlines(), 1):
            event = json.loads(line)
            if event.get("type") != "tool_call":
                continue
            inp = event.get("raw_input") or {}
            text = json.dumps(inp, ensure_ascii=False)
            if any(s in text for s in ("/skills/", "SKILL.md", "GUIDE.md")):
                accesses.append(dict(source_line=n, kind=event.get("kind"), input=inp))
        hashes = {}
        for name, expected in row.get("evidence_sha256", {}).items():
            actual = digest((trial / name).read_bytes())
            assert actual == expected
            hashes[name] = actual
        input_checks = []
        for rel, sha in campaign["task_sources"][row["task"]]["files"].items():
            if not (rel.endswith(".cif") or rel in ("environment/r2r_simulator.py", "environment/system_config.json")):
                continue
            saved_rel = "cif_files/" + Path(rel).name if rel.endswith(".cif") else rel.removeprefix("environment/")
            saved = trial / "evidence/workspace" / saved_rel
            input_checks.append(dict(path=rel, saved=str(saved.relative_to(ROOT)),
                                     unchanged=saved.exists() and digest(saved.read_bytes()) == sha))
        assert input_checks and all(x["unchanged"] for x in input_checks)
        records.append(dict(metrics=row, requests=requests, helper_calls=helpers,
            native_skill_calls=row.get("activations", []), any_image_delivered=any(x["images"] for x in requests),
            full_skill_body_observed=body_seen, skill_file_accesses=accesses,
            first_request_sha256=digest(json.dumps(firsts[(row["task"], row["arm"])], sort_keys=True).encode()),
            input_checks=input_checks, raw_evidence_hashes=hashes))
        if row["task"] == "r2r-mpc-control":
            records[-1]["matrix_diagnostic"] = matrix_diagnostic(trial / "evidence/workspace")
    pairs = []
    for task in campaign["task_sources"]:
        a, b = (next(r for r in records if r["metrics"]["task"] == task and r["metrics"]["arm"] == arm) for arm in ("text", "image"))
        p = dict(task=task, first_requests_exactly_equal=firsts[(task,"text")] == firsts[(task,"image")],
                 first_requests_equal_after_skill_path_normalization=normalize_skill_location(firsts[(task,"text")]) == normalize_skill_location(firsts[(task,"image")]),
                 image_delivered=b["any_image_delivered"], text_score=a["metrics"]["reward"], image_score=b["metrics"]["reward"])
        valid = a["metrics"]["analysis_admitted"] and b["metrics"]["analysis_admitted"]
        for key in ("total_tokens", "agent_seconds", "estimated_cost_usd"):
            p[key + "_change_pct"] = 100 * (b["metrics"][key]/a["metrics"][key]-1) if valid else None
        pairs.append(p)
    report = dict(method=campaign["method"], runs=records, pairs=pairs,
                  unique_runs=len(records), recorded_tokens=sum(r["metrics"]["total_tokens"] for r in records),
                  estimated_cost_usd=sum(r["metrics"]["estimated_cost_usd"] for r in records),
                  note="Native crystal verifier uses stdout summary rather than CTRF; derived admission reads its actual 11-test output. Original comparison and all native records remain preserved.")
    (directory / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    lines = ["# 按需加载两题实验：实际结果与曝光核验", "", "晶体和 R2R，每题纯文本／图片条件各一次；使用原 v1 UML 图，OpenCode 1.19.5、DeepSeek Flash，串行且两题组序交替。", "",
             "|题目|组别|原生分数|测试通过|总 token|Agent 秒|估算费用 USD|skill 工具调用数|实际收到图|",
             "|---|---|---:|---|---:|---:|---:|---:|---|"]
    for x in records:
        r=x["metrics"]; t=r["tests"]
        label="晶体" if "crystallographic" in r["task"] else "R2R"
        lines.append(f"|{label}|{r['arm']}|{r['reward']:g}|{t.get('passed',0)}/{t.get('tests',0)}|{r['total_tokens']:,}|{r['agent_seconds']:.1f}|{r['estimated_cost_usd']:.6f}|{len(x['native_skill_calls'])}|{x['any_image_delivered']}|")
    lines += ["", "|题目|分数 文→图|token 变化|Agent 时间变化|估算费用变化|首轮实际请求完全相同|图片曝光|", "|---|---|---:|---:|---:|---|---|"]
    for p in pairs:
        label="晶体" if "crystallographic" in p["task"] else "R2R"
        pct=lambda k:f"{p[k]:+.1f}%" if p[k] is not None else "计量不完整"
        lines.append(f"|{label}|{p['text_score']:g}→{p['image_score']:g}|{pct('total_tokens_change_pct')}|{pct('agent_seconds_change_pct')}|{pct('estimated_cost_usd_change_pct')}|{p['first_requests_exactly_equal']}|{p['image_delivered']}|")
    if not any(r["any_image_delivered"] for r in records):
        lines += ["", "## 这次没有触发图片处理", "", "四次运行都未调用原生 skill 工具，所有已捕获主请求中的图片数均为 0。模型仍能通过普通文件工具直接读取 SKILL.md 或参考文档，或自行完成任务；这些路径不会触发本协议的图片附加。", "",
                  "因此以上文字／图片是预先指定的材料条件，不是已经发生的图像曝光。即使 token 差异很大，也不能归因于图或证明按需图像有效／无效。首轮请求相同且后续未曝光图片的配对，说明采样与自主工具路径足以造成明显波动。", "",
                  "下一步需要先明确是否把直接读取 SKILL.md 也视为激活，或是否要求模型通过 skill 工具加载；本轮没有中途改变规则或追加运行。"]
    lines += ["", "## 轨迹与错误归因", "",
              "晶体文字条件先读取 pymatgen 的完整 SKILL.md，再读取 Wyckoff 参考文档；图片条件直接读取该参考文档。主请求数为 12→9，普通工具调用为 15→11。全文读取造成后续输入重复携带更多正文，是 token 差异的可观察来源之一；仅一次运行不能量化各来源的因果贡献。两组首轮完整请求完全相同。", "",
              "R2R 两组都用普通文件工具读取 skill，未使用原生 skill 工具。图片条件提交的 A/B 与连续时间 Jacobian 完全相同，但原生评分器要求 Euler 离散矩阵 A_d=I+dt·A_c、B_d=dt·B_c；文字条件使用矩阵指数的精确零阶保持离散化，也与评分器要求的 Euler 结果不同。两组均通过控制性能和安全性测试，整体二元分数仍为 0。这里只核对既有提交，没有修正提交或重跑。", "",
              "|R2R 条件|A 与评分器要求的最大误差|B 与评分器要求的最大误差|A 与连续 Jacobian 的最大误差|", "|---|---:|---:|---:|"]
    for x in records:
        if "matrix_diagnostic" in x:
            d=x["matrix_diagnostic"]
            lines.append(f"|{x['metrics']['arm']}|{d['A_error_to_expected_euler']:.6f}|{d['B_error_to_expected_euler']:.6f}|{d['A_error_to_continuous']:.6f}|")
    lines += ["", "R2R 首轮请求不是逐字相同：两项 skill 的发现位置在 /root/.opencode/skills 与 /home/agent/.opencode/skills 之间变化。仅规范化该前缀后，完整请求相同。这是当前原生发现路径的可复现性限制，应在后续新协议中统一；本轮保留原始记录。", "",
              "## token 少但估算费用高", "", "|R2R 条件|缓存输入 token|非缓存输入 token|输出 token|估算费用 USD|", "|---|---:|---:|---:|---:|"]
    for arm in ("text", "image"):
        r=next(x["metrics"] for x in records if x["metrics"]["task"] == "r2r-mpc-control" and x["metrics"]["arm"] == arm)
        lines.append(f"|{arm}|{r['cached_tokens']:,}|{r['input_tokens']-r['cached_tokens']:,}|{r['output_tokens']:,}|{r['estimated_cost_usd']:.6f}|")
    lines += ["", "R2R 图片条件的总 token 少 6.2%，但输出从 19,726 增到 27,436（+39.1%），主要减少的是低价缓存输入。输入、缓存和输出不是同一计价权重，所以框架估算费用增加 26.4%。所有请求都没有图，不能解释成图片计费。", "",
              "后续若继续，应先统一重复发现路径，再在两组加入同一条加载规范（使用 skill 工具而不是直接读 SKILL.md），确认实际曝光后再比较；或另设允许直接文件读取触发的协议。两者都需要作为新协议重新登记，不能将本次零曝光配对当作图效果证据。"]
    lines += ["", "## 证据与范围", "", "初始请求均未预置完整 skill 正文或图。已核验任务 digest、原始用量、材料传递和留存输入文件；不把模型没有激活 skill 的运行删掉。", "",
              "晶体原生评分器不生成 CTRF；本报告读取其原生 stdout 的 11 项测试汇总。原 comparison.json 中通用收集器的 CTRF 限制保留，本报告以派生 analysis_admitted 表达正确计量范围，未改任务、评分器或模型结果。", "",
              f"共 {len(records)} 次唯一运行，记录 {report['recorded_tokens']:,} token，框架估算费用 ${report['estimated_cost_usd']:.6f}。缓存 token 已包含在输入内，费用不是供应商账单。每配置一次，不能推断稳定效应。", ""]
    for x in records:
        r=x["metrics"];trial=ROOT/r["trial"]
        lines += [f"- {r['task']}／{r['arm']}：[原生结果]({trial / 'result.json'}) · [传递审计]({trial / 'skill-delivery.json'}) · [工具轨迹]({trial / 'trajectory/acp_trajectory.jsonl'})"]
    lines += ["", "[机器可读核验、输入哈希与路径记录](analysis.json) · [预登记配置](campaign.json)"]
    (directory / "ANALYSIS.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(dict(runs=len(records), image_exposed_runs=sum(r["any_image_delivered"] for r in records), pairs=pairs), ensure_ascii=False))


if __name__ == "__main__":
    main()
