#!/usr/bin/env python3
"""Read-only evidence checks and clearly separated v1/v2 descriptive results."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from campaign import HERE, ROOT, identity, metrics, summarize, validate
from build import sha, inventory
from delivery import load_policy
from delivery_protocol import prefix_content, public_policy, is_helper
from benchflow.trajectories.types import redact_trajectory_obj


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, default=ROOT / 'jobs/uml-expanded/paired-five-full-skill-v2')
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    directory = args.campaign.resolve()
    plan = json.loads((directory / 'campaign.json').read_text())
    validate(plan)
    done = all(s['status'] in ('finished', 'failed') for s in plan['schedule'])
    if args.final and not done:
        parser.error('all ten slots must be terminal')
    evidence = summarize(directory)
    checks = []
    frozen = directory / 'frozen-source'
    checks.append({'check': 'frozen_runtime_sources_match', 'passed': all(
        sha(frozen / rel) == digest for rel, digest in plan['code_sha256'].items())})
    checks.append({'check': 'frozen_prepared_task_sources_match', 'passed': all(
        inventory(frozen / 'prepared-tasks' / task) == row['prepared_files']
        for task, row in plan['task_sources'].items())})
    checks.append({'check': 'material_manifest_binding', 'passed':
        sha(directory / 'material-manifest.json') == plan['material_sha256'] == sha(HERE / 'manifest.json')})
    for slot in plan['schedule']:
        if slot['status'] not in ('finished', 'failed'):
            continue
        found = list(Path(slot['jobs_dir']).glob('*/*/result.json'))
        if len(found) != 1:
            checks.append({'check': 'one_result', 'task': slot['task'], 'arm': slot['arm'], 'passed': False})
            continue
        trial = found[0].parent
        policy = load_policy(slot['arm'], HERE / 'tasks' / slot['task'] / 'bundles' / slot['arm'])
        audit = json.loads((trial / 'skill-delivery.json').read_text())
        messages, captured = [], []
        for line in (trial / 'trajectory/llm_trajectory.jsonl').read_text().splitlines():
            row = json.loads(line)
            body = row['request']['body']
            if not is_helper(body):
                first = next(m for m in body['messages'] if m['role'] == 'user')
                captured.append(first['content'] == prefix_content(policy) or
                    first['content'] == redact_trajectory_obj(prefix_content(policy)))
        receipt_path = trial / 'shared-opencode.json'
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
        checks.append({'check': 'exact_current_material_capture_and_shared_tools', 'task': slot['task'],
            'arm': slot['arm'], 'main_calls_checked': len(captured),
            'passed': bool(captured) and all(captured) and audit['policy'] == public_policy(policy)
                and policy['id'] == slot['policy_id'] and receipt == plan['shared_tool_image']})
    subprocess.run([str(ROOT / 'repos/benchflow/.venv/bin/python'),
        str(HERE.parent / 'review_inputs.py'), '--campaign', str(directory)],
        check=True, stdout=subprocess.DEVNULL)
    inputs = json.loads((directory / 'visible-input-review.json').read_text())
    for row in inputs['rows']:
        if row['state'] == 'checked':
            checks.append({'check': 'visible_inputs_unchanged', 'task': row['task'], 'arm': row['arm'],
                'passed': row['all_declared_visible_inputs_preserved']})
    validation = {'final': done, 'checks': checks, 'all_passed': all(c['passed'] for c in checks),
        'report_script_sha256': sha(Path(__file__)), 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'bindings': {name: sha(directory / name) for name in
            ('campaign.json', 'comparison.json', 'material-manifest.json', 'visible-input-review.json')}}
    metrics.write(directory / ('final-validation.json' if done else 'progress-validation.json'), validation)
    old_path = HERE.parent / 'results/paired-five-v1-recovery.json'
    old = json.loads(old_path.read_text())
    lines = ['# 完整目录 UML v2 与旧版观察', '',
        'v2 ' + ('十次运行已结束。' if done else '仍在运行，下表仅列已结束槽位。'), '',
        '|任务|组别|v1 得分|v2 得分|v1 token|v2 token|v1 工具调用|v2 工具调用|',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for row in evidence['rows']:
        if not row.get('trial'):
            continue
        before = next(p[row['arm']] for p in old['pairs'] if p['task'] == row['task'])
        lines.append('| ' + ' | '.join(str(v) for v in (row['task'], row['arm'], before['reward'],
            row['reward'], before['total_tokens'], row['total_tokens'], before['tool_calls'], row['tool_calls'])) + ' |')
    lines += ['', 'v1、v2 每个槽位仅一次，运行时间与采样不同。v2 图在看过 v1 结果之后重做；不能将跨版本差异当成 UML 质量的因果证明。v1 考试图片组超时，仍保留其实际消耗。', '',
        f"当前 v2 全部槽位记录 token {evidence['all_slots_recorded_tokens']:,}，框架估计费用 ${evidence['all_slots_estimated_cost_usd']:.6f}。", '',
        f"材料、传递、工具镜像与可见输入检查：{len(checks)} 项，{'全部通过' if validation['all_passed'] else '存在未通过项，查看 validation JSON'}。", '',
        'v2 内部文字／图片配对与原始路径见 comparison.md / comparison.json。基础设施失败、超时与不完整运行不进入有效配对比例。正常执行测试得到 0 分的运行仍保留消耗对照；得分不同时，token 下降不能称为完成同等任务的节省。']
    (directory / 'v1-v2-comparison.md').write_text('\n'.join(lines) + '\n')
    index = ['# 本批轨迹索引', '',
        '工具步骤看操作轨迹与 result.json 的 n_tool_calls；模型轮数看主请求计数。一次模型请求可以发起多个工具调用，两者不是同一个计量。', '',
        'token 以模型请求响应 usage 和 comparison.json 对账；包含标题等辅助调用。cached_tokens 已包含在输入 token 内，不能再加一次。超时只统计已记录到的用量，不等于供应商账单。', '',
        '传递报告同时检查图片/全文和运行完整性：超时会使 valid=false。是否实际含图，需要结合本批 final-validation.json 的逐请求材料检查。', '',
        '|任务|组别|操作轨迹|模型请求与用量|评分|传递|测试输出|', '|---|---|---|---|---|---|---|']
    for row in evidence['rows']:
        if not row.get('trial'):
            continue
        trial = ROOT / row['trial']
        links = [f'[{label}]({trial / rel})' for label, rel in (
            ('ACP', 'trajectory/acp_trajectory.jsonl'), ('LLM', 'trajectory/llm_trajectory.jsonl'),
            ('result', 'result.json'), ('delivery', 'skill-delivery.json'), ('stdout', 'verifier/test-stdout.txt'))]
        index.append('| ' + ' | '.join([row['task'], row['arm'], *links]) + ' |')
    (directory / 'TRACE_INDEX.md').write_text('\n'.join(index) + '\n')
    print(json.dumps({'final': done, 'checks': len(checks), 'checks_passed': validation['all_passed'],
        'report': str(directory / 'comparison.md')}))
    return int(not validation['all_passed'])


if __name__ == '__main__':
    raise SystemExit(main())
