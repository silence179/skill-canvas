#!/usr/bin/env python3
"""Versioned full-skill-folder UML materials; never edits/runs the old campaign."""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
from datetime import datetime, timezone

from diagrams import DIAGRAMS, STYLE

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
UPSTREAM = ROOT / 'repos/skillsbench'
spec = importlib.util.spec_from_file_location('full_folder_renderer', HERE.parent.parent / 'uml-flowchart/prepare.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

# Full local resource closure. S1 is always the complete original SKILL.md.
EXTRA = {
 ('llm-prefix-cache-replay', 'prefix-cache-replay'): [('S2', 'cache-policy-comparison/SKILL.md', 'Companion policy specification: do not follow S3FIFO transitions when a different eviction policy is declared.')],
 ('llm-prefix-cache-replay', 'cache-policy-comparison'): [('S2', 'prefix-cache-replay/SKILL.md', 'Explicitly linked sibling: full S3FIFO transitions and prefix-hit accounting.')],
 ('energy-market-pricing', 'dc-power-flow'): [('S2', 'dc-power-flow/scripts/build_b_matrix.py', 'Both callable helpers, their return contracts, zero-X/zero-rating behavior and diagnostic CLI.')],
 ('energy-market-pricing', 'economic-dispatch'): [('S2', 'economic-dispatch/references/cost-functions.md', 'Polynomial and piecewise-linear formats, coefficient units, marginal-cost formula; examples and bibliography context reviewed.')],
 ('manufacturing-fjsp-optimization', 'fjsp-baseline-repair-with-downtime-and-policy'): [('S2', 'reference.md', 'Shared skills-root resource: baseline-repair commitments, FJSPLib provenance, difficulty taxonomy and literature. No instance-specific solution is supplied.')],
}
REVIEW = {
 'prefix-cache-replay': 'Keep pre-access hit accounting distinct from all-hash mutation; show M/G helper transitions, preserved promotion frequency, rounding and ghost exclusion.',
 'cache-policy-comparison': 'Include LFU initial frequency=1 and insertion-order ties; follow the linked full S3FIFO skill. ARC is named but no algorithm is supplied.',
 'power-flow-data': 'Preserve MATPOWER columns, non-contiguous bus labels, MW/per-unit conversion, reserve fields and large-JSON reading advice.',
 'dc-power-flow': 'Add executable-resource contract: build_susceptance_matrix returns three objects; calculate_line_flows reuses saved susceptances, keeps original IDs and uses zero loading when rating<=0. CLI only prints matrix diagnostics.',
 'economic-dispatch': 'Add reference-only MODEL=1 breakpoint costs and marginal costs. Flag general-polynomial layout versus the GUIDE example treating NCOST>=3 as quadratic; do not invent an unprovided piecewise optimization implementation.',
 'locational-marginal-prices': 'Preserve source extraction and counterfactual workflow. Mark source dual*baseMVA scaling / sign as requiring review of the actual equation; do not inject a formula learned from previous verifier outcomes. Distinguish None->0 source fallback from an available market dual.',
 'state-space-linearization': 'Include all four stated R2R partial derivatives and both discretization choices. Invertibility is an explicit mathematical precondition of the supplied inverse expression, not a new discretization algorithm.',
 'finite-horizon-lqr': 'Preserve P-next versus P-current order, gain storage and first-action-only receding horizon. Returned/logged states are an interface summary, not a new controller.',
 'mpc-horizon-tuning': 'Separate parameter selection and evaluation. Show both horizon guidelines without making them simultaneous hard limits; flag continuous ARE example versus discrete-model conventions.',
 'integral-action-design': 'Separate timestep integration/clipping from post-trial tuning advice. This is an editorial clarification: the source gives tuning advice but does not mandate online gain adaptation.',
 'mip-solver-and-solution-audit': 'Preserve installed-solver discovery, solver-required method, incumbent extraction, truthful certificates, exact disk reload before metrics, objective consistency and explicit formulation contents.',
 'ordered-window-sequencing-mip': 'Retain both representations, all linearization bounds, ordered keys, successor labels, masks, boundary conditions, active-pattern overlap and full optimized objective.',
 'fjsp-baseline-repair-with-downtime-and-policy': 'Incorporate the shared baseline-repair context. Keep integer scan and same-order commitment explicit. Flag conflicting heuristic priorities and the sample safety-bound return not proving feasibility; preserve all original guidance/resources.',
}

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def inventory(folder):
    return {str(p.relative_to(folder)): sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}

def resources(task, skill):
    rows = [('S1', f'{skill}/SKILL.md', REVIEW[skill])]
    return rows + EXTRA.get((task, skill), [])

def source_record(path, role):
    text = path.read_text(encoding='utf-8')
    record = {'sha256': sha(path), 'bytes': path.stat().st_size, 'lines': len(text.splitlines()), 'review': role,
              'headings': [{'line': i, 'heading': line} for i, line in enumerate(text.splitlines(), 1) if re.match(r'^#{1,6} ', line)]}
    if path.suffix == '.py':
        tree = ast.parse(text)
        record['functions'] = [{'name': node.name, 'line': node.lineno,
            'arguments': [a.arg for a in node.args.args]} for node in tree.body if isinstance(node, ast.FunctionDef)]
    return record

def identities():
    return {p.name: sha(p) for p in (Path(__file__), HERE / 'diagrams.py') } | {'renderer_helper': sha(Path(base.__file__))}

def check():
    manifest = json.loads((HERE / 'manifest.json').read_text())
    if identities() != manifest['generator_sha256'] or sha(base.JAR) != manifest['renderer']['sha256']:
        raise ValueError('generator or renderer changed; use a new version directory')
    commit = subprocess.check_output(['git','-C',str(UPSTREAM),'rev-parse','HEAD'],text=True).strip()
    if commit != manifest['skillsbench_commit']:
        raise ValueError('upstream source revision changed')
    for task, details in manifest['tasks'].items():
        source = UPSTREAM / 'tasks' / task / 'environment/skills'
        target = HERE / 'tasks' / task
        if inventory(source) != details['source_files'] or inventory(target / 'source') != details['source_files']:
            raise ValueError(f'{task}: full source tree changed')
        if sha(target / 'source-map.json') != details['source_map_sha256']:
            raise ValueError('source map changed')
        for skill, row in details['skills'].items():
            for rel, digest in row['artifacts'].items():
                if sha(target / rel) != digest:
                    raise ValueError(f'{task}/{skill}: artifact changed: {rel}')
            raw = (target / f'previews/{skill}.png').read_bytes()
            if not raw.startswith(b'\x89PNG\r\n\x1a\n') or list(struct.unpack('>II', raw[16:24])) != row['png_dimensions']:
                raise ValueError('invalid PNG')
            for arm in ('text', 'image'):
                bundle = target / 'bundles' / arm
                if (bundle / skill / 'GUIDE.md').read_bytes() != (source / skill / 'SKILL.md').read_bytes():
                    raise ValueError('original full text changed')
                for original in (source / skill).rglob('*'):
                    if original.is_file() and original.name != 'SKILL.md':
                        if original.read_bytes() != (bundle / original.relative_to(source)).read_bytes():
                            raise ValueError('original resource changed')
        for arm in ('text', 'image'):
            if inventory(target / 'bundles' / arm) != details['bundles'][arm]:
                raise ValueError('bundle changed')
        # Whole folder, including siblings/shared files, is retained identically.
        for rel in details['source_files']:
            for arm in ('text', 'image'):
                dest = target / 'bundles' / arm / rel
                if Path(rel).name != 'SKILL.md' and sha(dest) != details['source_files'][rel]:
                    raise ValueError('shared resource changed')
    print('Verified 5 whole skill trees, 16 unique source files, 13 UML/PNG/SVG sets and matched full-resource bundles.')
    return manifest

def build():
    if (HERE / 'manifest.json').exists():
        return check()
    if sha(base.JAR) != base.JAR_SHA256:
        raise ValueError('renderer pin mismatch')
    manifest = {'schema': 2, 'version': 'full-skill-v2', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'skillsbench_commit': subprocess.check_output(['git','-C',str(UPSTREAM),'rev-parse','HEAD'],text=True).strip(),
        'basis': 'Complete local skill folders, explicitly linked sibling skills, and shared skills-root resources.',
        'revision_context': 'Post-results material revision requested by user; not a blinded pre-results generation and no new model evaluation.',
        'renderer': {'name': 'PlantUML MIT', 'version': '1.2026.10', 'sha256': base.JAR_SHA256},
        'generator_sha256': identities(), 'tasks': {}}
    index = ['# 完整 skill 文件夹版 UML（v2）', '', '13 张图均重新提炼、渲染；完整来源见 [SOURCE_REVIEW.md](SOURCE_REVIEW.md)。旧版实验未改写，本版尚未运行模型对照。', '',
             '| Task / skill | PNG | SVG | UML | 来源 |', '|---|---|---|---|---|']
    review = ['# 完整来源与语义复核', '',
        '本版先阅读五个任务全部本地 skills 目录，再重写 13 张图。共 16 个不同源文件：13 份 SKILL.md、1 个 Python 脚本、1 份子目录参考、1 份 skills 根目录共享参考。显式引用的兄弟 skill 也纳入来源闭包。', '',
        '这不是新增知识检索：外部网站/论文链接作为本地文献索引记录，不把其未附带内容假装读入。没有用 task.md、实例、oracle、verifier 或历史模型代码来补写算法。材料重建发生在旧结果之后，后续评测需单独登记。', '',
        '原文与资源保留逐字节副本。图是完整资源的流程提炼，不是每句文字的逐字转换；背景、文献和示例中不构成流程的部分单独说明。来源中的歧义被标记，没有按旧实验评分静默修正原文。', '']
    reviewed_files = 0
    for task, diagrams in DIAGRAMS.items():
        source = UPSTREAM / 'tasks' / task / 'environment/skills'
        target = HERE / 'tasks' / task
        source_files = inventory(source)
        actual_names = {p.parent.name for p in source.glob('*/SKILL.md')}
        if actual_names != set(diagrams):
            raise ValueError('skill catalog does not match full source')
        for p in source.rglob('*'):
            if p.is_symlink():
                raise ValueError('symlink source not supported')
        declared = {rel for skill in diagrams for _,rel,_ in resources(task, skill)}
        if declared != set(source_files):
            raise ValueError(f'{task}: unreviewed or missing full-folder resources: {declared ^ set(source_files)}')
        reviewed_files += len(source_files)
        target.mkdir(parents=True, exist_ok=True)
        if not (target / 'source').exists():
            shutil.copytree(source, target / 'source')
        details = {'source_files': source_files, 'skills': {}, 'bundles': {}}
        source_map = {}
        for arm in ('text', 'image'):
            bundle = target / 'bundles' / arm
            if bundle.exists():
                shutil.rmtree(bundle)  # Only this new, not-yet-frozen material build.
            shutil.copytree(source, bundle)
        review += [f'## {task}', '']
        for skill, body in diagrams.items():
            refs = resources(task, skill)
            source_map[skill] = {sid: {'path': rel, **source_record(source / rel, role)} for sid,rel,role in refs}
            if not all(sid in body for sid,_,_ in refs):
                raise ValueError('diagram must mark every source ID')
            footer = 'footer Full-skill v2 | ' + ' | '.join(f'{sid}: {Path(rel).name}' for sid,rel,_ in refs) + '\n'
            uml = target / 'diagrams' / (skill + '.puml')
            uml.parent.mkdir(exist_ok=True)
            uml.write_text(STYLE + body.strip() + '\n' + footer + '@enduml\n')
            preview = target / 'previews'
            preview.mkdir(exist_ok=True)
            png, svg = base.render(uml, 'png'), base.render(uml, 'svg')
            if not png.startswith(b'\x89PNG\r\n\x1a\n') or b'<svg' not in svg or b'Syntax Error' in svg:
                raise ValueError('render failed')
            (preview / (skill + '.png')).write_bytes(png)
            (preview / (skill + '.svg')).write_bytes(svg)
            original = (source / skill / 'SKILL.md').read_bytes()
            front = re.match(r'\A---\n.*?\n---\n', original.decode(), re.S)
            if not front:
                raise ValueError('skill frontmatter missing')
            for arm in ('text', 'image'):
                destination = target / 'bundles' / arm / skill
                if (destination / 'GUIDE.md').exists():
                    raise ValueError('GUIDE.md source collision')
                (destination / 'GUIDE.md').write_bytes(original)
                (destination / 'SKILL.md').write_text(base.entrypoint(front.group(), arm == 'image'))
                if arm == 'image':
                    asset = destination / 'assets/flowchart.png'
                    if asset.exists():
                        raise ValueError('PNG source collision')
                    asset.parent.mkdir(exist_ok=True)
                    asset.write_bytes(png)
            artifact_paths = [uml, preview / (skill+'.png'), preview / (skill+'.svg')]
            details['skills'][skill] = {'sources': source_map[skill], 'review': REVIEW[skill],
                'png_dimensions': list(struct.unpack('>II',png[16:24])),
                'artifacts': {str(p.relative_to(target)): sha(p) for p in artifact_paths}}
            prefix = f'tasks/{task}'
            index += [f'| {task} / {skill} | [PNG]({prefix}/previews/{skill}.png) | [SVG]({prefix}/previews/{skill}.svg) | [UML]({prefix}/diagrams/{skill}.puml) | [来源]({prefix}/source-map.json) |']
            review += [f'### {skill}', '', REVIEW[skill], '']
            for sid,rel,role in refs:
                review += [f'- {sid}: [{rel}](tasks/{task}/source/{rel}) — {role}']
            review += ['']
            print(f'{task}/{skill}: rendered {details["skills"][skill]["png_dimensions"]}',flush=True)
        (target / 'source-map.json').write_text(json.dumps(source_map,indent=2,ensure_ascii=False)+'\n')
        details['source_map_sha256'] = sha(target / 'source-map.json')
        for arm in ('text', 'image'):
            details['bundles'][arm] = inventory(target / 'bundles' / arm)
        manifest['tasks'][task] = details
    if reviewed_files != 16:
        raise ValueError('full-folder inventory differs; review newly discovered files')
    (HERE / 'FIGURES.md').write_text('\n'.join(index)+'\n')
    (HERE / 'SOURCE_REVIEW.md').write_text('\n'.join(review)+'\n')
    (HERE / 'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    check()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    check() if args.check else build()
