#!/usr/bin/env python3
"""New ten-run campaign, with frozen v2 bundles and unchanged native grading."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from build import HERE, ROOT, check, inventory, sha
from delivery import load_policy
sys.path.insert(0, str(HERE.parent))
spec = importlib.util.spec_from_file_location('legacy_campaign_metrics', HERE.parent / 'campaign.py')
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)

PREPARED = ROOT / '.runtime/uml-expanded/prepared-tasks'
PYTHON = ROOT / 'repos/benchflow/.venv/bin/python'


def identity():
    paths = [HERE / name for name in ('campaign.py', 'delivery.py', 'smoke.py')]
    paths += [HERE.parent / 'campaign.py', HERE.parent / 'study.py',
        ROOT / 'experiments/shared_opencode.py', ROOT / 'experiments/env_config.py',
        ROOT / 'experiments/uml-flowchart/delivery_runner.py',
        ROOT / 'experiments/uml-flowchart/delivery_protocol.py']
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def controls():
    return metrics.controls()


def plan(directory):
    from env_config import load_env
    load_env(ROOT / '.env')
    material = check()
    model, agent = os.environ.get('EXP_MODEL'), os.environ.get('EXP_AGENT')
    if not model or agent != 'opencode' or not os.environ.get('DEEPSEEK_API_KEY', '').strip():
        raise ValueError('configured model, opencode and provider key required')
    schedule = []
    task_sources = {}
    for index, task in enumerate(material['tasks']):
        task_sources[task] = {'prepared_files': inventory(PREPARED / task),
            'skill_names': sorted(material['tasks'][task]['skills'])}
        for arm in (('text', 'image') if index % 2 == 0 else ('image', 'text')):
            bundle = HERE / 'tasks' / task / 'bundles' / arm
            policy = load_policy(arm, bundle)
            jobs = directory / task / arm
            command = [str(PYTHON), str(HERE / 'delivery.py'), '--arm', arm,
                '--bundle', str(bundle), '--', 'run', str(PREPARED), '-i', task,
                '--agent', agent, '--sandbox', 'docker', '--trials', '1',
                '--concurrency', '1', '--retry-attempts', '0', '--save-outputs',
                '--jobs-dir', str(jobs), '--model', model, '--skill-mode', 'with-skill',
                '--skills-dir', str(bundle)]
            if os.environ.get('EXP_EFFORT'):
                command += ['--reasoning-effort', os.environ['EXP_EFFORT']]
            schedule.append({'task': task, 'arm': arm, 'jobs_dir': str(jobs),
                'command': command, 'policy_id': policy['id'], 'status': 'planned'})
    return {'schema': 2, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'purpose': 'full-skill-v2; fresh full-text vs PNG-first plus identical full-text pairs',
        'model': model, 'agent': agent, 'trials_per_arm': 1, 'concurrency': 1,
        'effort': os.environ.get('EXP_EFFORT') or None, 'seed': None,
        'order': 'same v1 fixed task order; arm order alternates; alphabetical skill catalog',
        'revision_context': material['revision_context'],
        'material_sha256': sha(HERE / 'manifest.json'), 'code_sha256': identity(),
        'task_sources': task_sources, 'controls': controls(),
        'shared_tool_image': json.loads((ROOT / '.runtime/shared-opencode/image.json').read_text()),
        'sources': {name: {'commit': subprocess.check_output(['git', '-C', str(ROOT / 'repos' / name),
            'rev-parse', 'HEAD'], text=True).strip(), 'status': subprocess.check_output(
            ['git', '-C', str(ROOT / 'repos' / name), 'status', '--short'], text=True)}
            for name in ('skillsbench', 'benchflow')},
        'grading_note': 'Prepared task bytes retained, including prior manufacturing offline dependency bootstrap; native scoring tests unchanged.',
        'schedule': schedule}


def validate(plan):
    from benchflow._utils.task_authoring import task_digest
    check()
    if plan['code_sha256'] != identity() or plan['material_sha256'] != sha(HERE / 'manifest.json'):
        raise ValueError('frozen campaign code/material changed')
    for task, row in plan['task_sources'].items():
        if inventory(PREPARED / task) != row['prepared_files']:
            raise ValueError('prepared task changed: ' + task)
        control = plan['controls'].get(task, {})
        if control.get('reward') != 1 or control.get('error'):
            raise ValueError('healthy oracle required: ' + task)
        if task_digest(PREPARED / task) != control.get('task_digest'):
            raise ValueError('prepared task no longer matches healthy oracle: ' + task)


def summarize(directory):
    plan = json.loads((directory / 'campaign.json').read_text())
    rows = [metrics.collect(slot) for slot in plan['schedule']]
    for row in rows:
        path = ROOT / row.get('trial', '__missing__') / 'verifier/ctrf.json'
        ctrf = json.loads(path.read_text()) if path.exists() else {}
        row['test_summary'] = (ctrf.get('results') or {}).get('summary') or {}
        row['test_execution_confirmed'] = row['test_summary'].get('tests', 0) > 0
        row['matches_healthy_oracle_digest'] = (bool(row.get('task_digest')) and
            row.get('task_digest') == plan['controls'][row['task']].get('task_digest'))
        row['metric_admitted'] &= row['test_execution_confirmed'] and row['matches_healthy_oracle_digest']
        row['ctrf_sha256'] = sha(path) if path.exists() else None
    pairs = []
    for task in plan['task_sources']:
        t, i = [next(r for r in rows if r['task'] == task and r['arm'] == arm) for arm in ('text', 'image')]
        admitted = t['metric_admitted'] and i['metric_admitted'] and t.get('task_digest') == i.get('task_digest')
        pairs.append({'task': task, 'admitted': admitted,
            'token_change_pct': 100 * (i['total_tokens'] / t['total_tokens'] - 1) if admitted and t.get('total_tokens') else None})
    report = {'campaign': str(directory.relative_to(ROOT)), 'rows': rows, 'pairs': pairs,
        'all_slots_recorded_tokens': sum(r.get('total_tokens') or 0 for r in rows),
        'all_slots_estimated_cost_usd': sum(r.get('estimated_cost_usd') or 0 for r in rows),
        'scope': '5 tasks x 2 arms x 1 trial; post-results v2 revision, no causal/stability proof'}
    metrics.write(directory / 'comparison.json', report)
    lines = ['# 完整 skill 文件夹 UML v2 对照', '',
        f"模型 `{plan['model']}`；五任务两组各一次，串行，先后顺序交替。", '',
        '|任务|组别|状态|得分|工具步数|主模型调用|总 token|Agent 秒|图片/原文校验|实际测试执行|',
        '|---|---|---|---:|---:|---:|---:|---:|---|---|']
    for row in rows:
        lines.append('| ' + ' | '.join(str(row.get(k, '—')) for k in
            ('task', 'arm', 'status', 'reward', 'tool_calls', 'main_calls', 'total_tokens',
             'agent_seconds', 'delivery_valid', 'test_execution_confirmed')) + ' |')
    lines += ['', '所有失败和超时保留并计入实际消耗；只有两组完整、评分确实执行、用量一致且任务摘要匹配健康 oracle 的配对，才纳入有效配对 token 对照。', '',
        '两组均强制提供完整原文；图片组先附全部新版 PNG。全部原始资源保留。沿用公共 OpenCode、任务时间上限与评分设置。制造任务沿用此前离线依赖引导修复，评分断言不变。', '',
        '每组仅一次，图像还包含提炼信息；不能将差异直接归因于视觉认知增强。', '',
        f"本批已记录总 token：{report['all_slots_recorded_tokens']:,}；框架估计费用：${report['all_slots_estimated_cost_usd']:.6f}。"]
    (directory / 'comparison.md').write_text('\n'.join(lines) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'run', 'report'))
    parser.add_argument('--campaign', type=Path, default=ROOT / 'jobs/uml-expanded/paired-five-full-skill-v2')
    args = parser.parse_args()
    directory = args.campaign.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / 'campaign.json'
    if args.action == 'report':
        summarize(directory)
        return 0
    if not target.exists():
        metrics.write(target, plan(directory))
    frozen = json.loads(target.read_text())
    validate(frozen)
    if args.action == 'plan':
        print(target)
        return 0
    for slot in frozen['schedule']:
        if slot['status'] != 'planned':
            continue
        validate(frozen)
        if shutil.disk_usage(ROOT).free < 1500 * 1024**2:
            raise RuntimeError('less than 1.5 GiB free; pause before launching another task')
        slot.update(status='launched', started_at_utc=datetime.now(timezone.utc).isoformat())
        metrics.write(target, frozen)
        print(f"START {slot['task']} / {slot['arm']}", flush=True)
        with (directory / f"{slot['task']}-{slot['arm']}.log").open('w') as output:
            completed = subprocess.run(slot['command'], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
        slot.update(status='finished' if completed.returncode == 0 else 'failed',
            exit_code=completed.returncode, finished_at_utc=datetime.now(timezone.utc).isoformat())
        metrics.write(target, frozen)
        summarize(directory)
        print(f"END {slot['task']} / {slot['arm']}: exit {completed.returncode}", flush=True)
    summarize(directory)
    return int(any(s['status'] != 'finished' for s in frozen['schedule']))


if __name__ == '__main__':
    raise SystemExit(main())
