#!/usr/bin/env python3
"""Derive a bounded paired report without changing native results or scores."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from study import HERE, ROOT, TASKS

LABELS = {"llm-prefix-cache-replay": "前缀缓存回放", "energy-market-pricing": "电价与拥塞分析",
          "r2r-mpc-control": "R2R 控制器", "exam-block-sequencing": "考试排程",
          "manufacturing-fjsp-optimization": "制造排程修复"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, default=ROOT / "jobs/uml-expanded/paired-five-v1")
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    directory = args.campaign.resolve()
    plan = json.loads((directory / "campaign.json").read_text())
    evidence = json.loads((directory / "comparison.json").read_text())
    if args.final and any(slot["status"] not in {"finished", "failed"} for slot in plan["schedule"]):
        parser.error("not all ten slots have reached a terminal state")
    index = {(row["task"], row["arm"]): row for row in evidence["rows"]}
    paired = []
    for task in TASKS:
        text, image = index[(task, "text")], index[(task, "image")]
        for row in (text, image):
            ctrf_path = ROOT / row.get('trial', '__missing__') / 'verifier/ctrf.json'
            ctrf = json.loads(ctrf_path.read_text()) if ctrf_path.is_file() else {}
            summary = (ctrf.get('results') or {}).get('summary') or {}
            row['test_execution_confirmed'] = summary.get('tests', 0) > 0
            row['test_summary'] = summary
            row['ctrf_sha256'] = sha(ctrf_path) if ctrf_path.is_file() else None
            trace_path = ROOT / row.get('trial', '__missing__') / 'trajectory/llm_trajectory.jsonl'
            row['first_successful_main_prompt_tokens'] = None
            if trace_path.is_file():
                for line in trace_path.read_text().splitlines():
                    event = json.loads(line)
                    body = event.get('request', {}).get('body', {})
                    usage = event.get('response', {}).get('body', {}).get('usage') or {}
                    if body.get('tools') and usage:
                        row['first_successful_main_prompt_tokens'] = usage.get('prompt_tokens')
                        break
            row['metric_admitted'] = row.get('metric_admitted', False) and row['test_execution_confirmed']
            if row.get('reward') is not None and not row['test_execution_confirmed']:
                row['derived_grade_exclusion'] = 'Native reward exists but no captured test execution; dependency bootstrap failure must not count as model quality.'
        same_task = bool(text.get("task_digest")) and text.get("task_digest") == image.get("task_digest")
        admitted = text.get("metric_admitted", False) and image.get("metric_admitted", False) and same_task
        row = {"task": task, "label": LABELS[task], "same_task_digest": same_task,
               "paired_metrics_admitted": admitted, "text": text, "image": image}
        if admitted:
            for metric in ("total_tokens", "tool_calls", "main_calls", "agent_seconds", "estimated_cost_usd"):
                before, after = text.get(metric), image.get(metric)
                row[metric + "_change_pct"] = (100 * (after / before - 1)
                    if isinstance(before, (int, float)) and before > 0 and isinstance(after, (int, float)) else None)
        paired.append(row)
    controls = []
    for path in sorted((ROOT / "jobs/uml-expanded").glob("environment-controls*/*/*/result.json")):
        value = json.loads(path.read_text())
        controls.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path),
            "task": value["task_name"], "reward": (value.get("rewards") or {}).get("reward"),
            "error": value.get("error"), "verifier_error": value.get("verifier_error"),
            "verifier_timeout_info": value.get("verifier_timeout_info"),
            "task_digest": value.get("task_digest")})
    healthy = {row["task"]: row for row in controls if row["reward"] == 1 and not row["error"]}
    for row in paired:
        row["matches_healthy_oracle_digest"] = (row["task"] in healthy and row["same_task_digest"]
            and row["text"].get("task_digest") == healthy[row["task"]].get("task_digest"))
        row["paired_metrics_admitted"] &= row["matches_healthy_oracle_digest"]
    admitted = [row for row in paired if row["paired_metrics_admitted"]]
    totals = {}
    for arm in ("text", "image"):
        totals[arm] = {metric: sum(row[arm].get(metric, 0) or 0 for row in admitted)
            for metric in ("total_tokens", "input_tokens", "output_tokens", "cached_tokens", "tool_calls", "main_calls", "agent_seconds", "estimated_cost_usd")}
    selected_totals = {}
    for arm in ('text', 'image'):
        rows = [pair[arm] for pair in paired]
        selected_totals[arm] = {'passed': sum(row.get('reward') == 1 and row['test_execution_confirmed'] for row in rows),
            'graded_tasks': sum(row['test_execution_confirmed'] for row in rows),
            'error_tasks': sum(bool(row.get('error')) for row in rows),
            **{metric: sum(row.get(metric, 0) or 0 for row in rows) for metric in
               ('total_tokens', 'tool_calls', 'main_calls', 'estimated_cost_usd')}}
    unique_attempts = {}
    for campaign in (ROOT / 'jobs/uml-expanded/paired-five-v1', directory):
        comparison = campaign / 'comparison.json'
        if comparison.exists():
            for row in json.loads(comparison.read_text())['rows']:
                if row.get('trial'):
                    unique_attempts[row['trial']] = {key: row.get(key) for key in ('trial', 'task', 'arm', 'reward', 'error', 'total_tokens', 'estimated_cost_usd')}
    completed = sum(slot["status"] == "finished" for slot in plan["schedule"])
    report = {"schema": 1, "final": args.final, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "campaign": str(directory.relative_to(ROOT)), "intended_slots": 10, "finished_slots": completed,
        "failed_slots": sum(slot["status"] == "failed" for slot in plan["schedule"]),
        "admitted_pairs": len(admitted), "pairs": paired, "totals_for_admitted_pairs": totals,
        "all_selected_slots_including_timeout": selected_totals,
        "all_unique_task_attempts": list(unique_attempts.values()),
        "recorded_tokens_all_unique_task_attempts": sum(row.get('total_tokens', 0) or 0 for row in unique_attempts.values()),
        "estimated_cost_usd_all_unique_task_attempts": sum(row.get('estimated_cost_usd', 0) or 0 for row in unique_attempts.values()),
        "control_attempts": controls,
        "bindings": {p.name: sha(p) for p in [directory / "campaign.json", directory / "comparison.json",
            directory / "manufacturing-environment-amendment.json", directory / "manufacturing-bootstrap-amendment.json",
            directory / "manufacturing-amended-files.json", directory / "visible-input-review.json",
            directory / "frozen-source-manifest.json", directory / "recovery-plan.json",
            directory / "manufacturing-offline-recovery-amendment.json",
            directory / "final-validation.json",
            HERE / "results/vision-sanity.json", Path(__file__)] if p.exists()},
        "limits": ["one trial per arm per task; no seed; descriptive pilot only",
            "diagrams add extracted information as well as a visual format; no matched text-summary arm",
            "provider usage includes cached input and helper calls; image tokens are not itemized separately",
            "agent time is observed elapsed time; some oracle controls overlapped early model runs",
            "manufacturing verifier dependency bootstrap adapted before either model arm; scoring tail and Python assertions unchanged",
            "results describe only these selected local task runs"]}
    target = HERE / "results"
    target.mkdir(exist_ok=True)
    stem = directory.name + ("" if args.final else "-progress")
    (target / (stem + ".json")).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    lines = ["# 五任务 UML 辅助 skill 初步对照", "", f"状态：{'全部槽位已结束' if args.final else '进行中'}；正常结束 {completed}/10；可纳入完整配对计量 {len(admitted)}/5。", "",
        f"模型 `{plan['model']}`，OpenCode 1.19.5；每任务每组 1 次。两组均强制全文，image 组额外提供 PNG。13 张图已逐资源核验。", "",
        (f"本轮观察：文字组通过 {selected_totals['text']['passed']}/5，图片组通过 {selected_totals['image']['passed']}/5；没有观察到总体通过率提升。制造任务图片组成功、文字组失败；考试任务图片组超时。token 表现有增有减，样本量不足以证明稳定的认知增强。" if all(selected_totals[arm]['graded_tasks'] == 5 for arm in ('text', 'image')) else '尚在收集可评分结果。'), '',
        "| 任务 | 得分 文/图 | 工具调用 文→图 | 总 token 文→图 | token 变化 | Agent 秒 文→图 |", "|---|---|---|---|---|---|"]
    for pair in paired:
        text, image = pair["text"], pair["image"]
        delta = pair.get("total_tokens_change_pct")
        delta_text = f"{delta:+.1f}%" if pair["paired_metrics_admitted"] and delta is not None else "未纳入"
        text_score = text.get('reward') if text.get('reward') is not None else '未评分'
        image_score = image.get('reward') if image.get('reward') is not None else '未评分'
        if text.get('reward') is not None and not text['test_execution_confirmed']:
            text_score = f'{text_score}（测试未执行）'
        if image.get('reward') is not None and not image['test_execution_confirmed']:
            image_score = f'{image_score}（测试未执行）'
        if '1500s' in (image.get('error') or ''):
            image_score = f'{image_score}（超时）'
        lines.append(f"| {pair['label']} | {text_score}/{image_score} | "
            f"{text.get('tool_calls','—')}→{image.get('tool_calls','—')} | "
            f"{text.get('total_tokens','—')}→{image.get('total_tokens','—')} | {delta_text} | "
            f"{text.get('agent_seconds','—')}→{image.get('agent_seconds','—')} |")
    lines += ["", "总 token 包含辅助标题请求；缓存命中已在输入内，不能再相加。表中变化为图片组相对文字组，负数表示减少。基础设施错误、未完成或证据不完整的行保留，计量纳入条件另列于 JSON。", "",
        "## 实验材料与过程", "", "- [13 张图、UML 与原文索引](../FIGURES.md)",
        "- [准备和运行说明、环境适配](../README.md)",
        "- [独立图片识读检查](vision-sanity.json)：同一路由仅给两张 PNG，不给原文，三个空间定位和文字问题均正确；只验证基本识图能力，不计入 benchmark 成绩。",
        f"- [原始 campaign 与比较结果]({directory}/comparison.md)", "",
        "只有两组都完成评分、传递检查通过、原始 usage 与汇总相符且 task digest 与健康参考解一致的配对才纳入。传递检查核对任务请求中 PNG 与全文的顺序和哈希；通过能证明图片被发送，不能证明模型注意或使用了图片。错误请求保留，不因重试后恢复就被删除。", "",
        "制造任务的在线依赖启动曾超时，因此在该任务两组启动前适配为预装同版本工具与离线缓存。原评分脚本从创建日志目录开始的尾部、测试调用和 reward 分支逐字节一致，Python 评分断言和阈值也逐字节一致。参考解得 1，空输出得 0；具体修订和前后哈希留在 campaign。其余任务预装依赖，评分脚本不变。", "",
        "首轮原始环境失败、后续修复与参考解尝试都保留；它们未计入模型通过率。部分较早模型试验与参考解计算重叠，因此时间数据只作观察，不是严格的性能基准。", "",
        "## 如何解读", "", "每任务只有一次对照，差异可能来自采样、推理和求解路径。通过率相同也可能存在评分上限效应。不能据此证明稳定的认知增强。下一轮应增加重复，并把图中同样的提炼步骤以文字提供给第三组，以区分总结内容与图像形式的作用。", "",
        "详细逐请求/逐结果证据哈希、全部控制实验及限制见同名 JSON。"]
    lines += ["", "## 本轮观察", ""]
    if all(selected_totals[arm]['graded_tasks'] == 5 for arm in ('text', 'image')):
        before, after = selected_totals['text']['total_tokens'], selected_totals['image']['total_tokens']
        lines += [f"最终选定的五个任务，文字组通过 {selected_totals['text']['passed']}/5，图片组通过 {selected_totals['image']['passed']}/5。超时未交付仍作为任务失败计入，不能通过排除超时提高通过率。", '',
            f"含超时任务的已记录总消耗：文字 {before:,} token，图片 {after:,} token（{100*(after/before-1):+.1f}%）；工具调用 {selected_totals['text']['tool_calls']}→{selected_totals['image']['tool_calls']}。这里报告实际记录的资源开销，和下方要求完整试验的配对计量分开。", '']
        manufacture = next(pair for pair in paired if pair['task'] == 'manufacturing-fjsp-optimization')
        exam = next(pair for pair in paired if pair['task'] == 'exam-block-sequencing')
        if manufacture['text']['test_summary'].get('failed') == 1 and manufacture['image']['test_summary'].get('passed') == 15:
            stdout = ROOT / manufacture['text']['trial'] / 'verifier/test-stdout.txt'
            if 'Not locally minimal' in stdout.read_text():
                lines += [f"制造排程是一个值得复验的正面案例：文字组通过 14/15 项，唯一失败为局部最早开始约束，一道工序 start=25 时 start=24 仍可行；图片组通过 15/15。两组报告总工期均为 39。图片组耗时 {manufacture['image']['agent_seconds']} 秒，文字组 {manufacture['text']['agent_seconds']} 秒，因此本次质量差异没有伴随时间节省。[文字组评分记录]({stdout})，[图片组评分记录]({ROOT / manufacture['image']['trial'] / 'verifier/test-stdout.txt'})。", '']
        if '1500s' in (exam['image'].get('error') or ''):
            lines += [f"考试图片组在 1500 秒上限内未交付 schedule.csv，实际评分三项均失败，不能从总体结果删掉。其传递审计已逐个检查 {exam['image']['main_calls']} 次任务请求的两张 PNG 与全文，整次运行 valid=false 的原因是超时/轨迹未正常结束，不能误解为漏传图片。该轨迹还包含额外求解器包下载超时和多轮优化搜索，时间表现受到这些因素影响。文字组正常交付并得 1 分。[超时结果]({ROOT / exam['image']['trial'] / 'result.json'})，[原始传递审计]({ROOT / exam['image']['trial'] / 'skill-delivery.json'})。", '']
    if admitted:
        before, after = totals['text']['total_tokens'], totals['image']['total_tokens']
        lines += [f"可纳入的 {len(admitted)} 个配对合计：文字组 {before:,} token，图片组 {after:,} token（{100*(after/before-1):+.1f}%）。这是这些任务的加权合计，容易受单个长轨迹支配，不代表平均任务或总体效应。", ""]
        lines += ['| 任务 | 任务模型调用 文→图 | 首请求输入 文→图 | 输出 token 文→图 | 缓存输入 文→图 | 估算费用 USD 文→图 |',
                  '|---|---:|---:|---:|---:|---:|']
        for pair in admitted:
            text, image = pair['text'], pair['image']
            lines.append(f"| {pair['label']} | {text['main_calls']}→{image['main_calls']} | {text['first_successful_main_prompt_tokens']}→{image['first_successful_main_prompt_tokens']} | {text['output_tokens']:,}→{image['output_tokens']:,} | {text['cached_tokens']:,}→{image['cached_tokens']:,} | {text.get('estimated_cost_usd')}→{image.get('estimated_cost_usd')} |")
        lines += ['', '工具调用数作为这里的 step 指标；一次工具调用可能执行多个命令。首请求输入是各组第一次成功任务请求的输入量，包含不同入口说明，不能当作服务商单独报告的图片 token。输出 token 包含代码与回答等内容，不能直接视作推理质量。费用为框架记录的估算值，实际账单以服务商为准。强制全文/图片每轮重发可命中缓存，因此总 token 变化不等同费用变化。', '']
    for pair in paired:
        if not pair['paired_metrics_admitted']:
            errors = [f"{arm}: {pair[arm].get('derived_grade_exclusion') or pair[arm].get('error') or pair[arm].get('verifier_error') or pair[arm].get('delivery_errors') or pair[arm].get('reason') or '证据不完整'}" for arm in ('text', 'image') if not pair[arm].get('metric_admitted')]
            lines += [f"- {pair['label']}未纳入完整配对：" + '；'.join(errors)]
    recovery = directory / 'recovery-plan.json'
    if recovery.exists():
        value = json.loads(recovery.read_text())
        lines += ["", f"本报告使用一次预先登记的基础设施补跑。原始十次尝试保留于 `{value['source_campaign']}`，仅补跑 `{', '.join(value['tasks'])}` 的完整两组；其余任务引用原始结果。不得将原始尝试和补跑当作独立重复，也不按得分挑选。补跑方案与原结果路径、哈希见 campaign 内 recovery-plan.json。"]
        lines += ['', f"连同保留的原始故障尝试，共 {len(unique_attempts)} 次不同任务运行；已记录 {report['recorded_tokens_all_unique_task_attempts']:,} token，框架估算费用 ${report['estimated_cost_usd_all_unique_task_attempts']:.4f}。这项累计不包含独立小检查，引用的原始六次只计算一次。"]
    (target / (stem + ".md")).write_text("\n".join(lines) + "\n")
    print(target / (stem + ".md"))


if __name__ == "__main__":
    main()
