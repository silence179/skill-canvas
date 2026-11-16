#!/usr/bin/env python3
"""Read-only check of captured visible inputs; not a full integrity certification."""

import hashlib
import json
import argparse
from pathlib import Path

from study import ROOT, TASKS

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--campaign', type=Path, default=ROOT / 'jobs/uml-expanded/paired-five-v1')
args = parser.parse_args()
campaign = args.campaign.resolve()
plan = json.loads((campaign / 'campaign.json').read_text())
slots = {(slot['task'], slot['arm']): slot for slot in plan['schedule']}
groups = {
    "llm-prefix-cache-replay": ("trace.jsonl", "config.json"),
    "energy-market-pricing": ("network.json",),
    "r2r-mpc-control": ("r2r_simulator.py", "system_config.json"),
    "exam-block-sequencing": ("data",),
    "manufacturing-fjsp-optimization": ("data",),
}
rows = []
for task in TASKS:
    source = ROOT / "repos/skillsbench/tasks" / task / "environment"
    inputs = []
    for name in groups[task]:
        path = source / name
        inputs.extend(path.rglob("*") if path.is_dir() else [path])
    inputs = [path for path in inputs if path.is_file()]
    for arm in ("text", "image"):
        results = list(Path(slots[(task, arm)]['jobs_dir']).glob("*/*/result.json"))
        if len(results) != 1:
            rows.append({"task": task, "arm": arm, "state": "pending"})
            continue
        trial = results[0].parent
        missing, changed, matched = [], [], []
        for path in inputs:
            relative = path.relative_to(source)
            captured = trial / "evidence/workspace" / relative
            if not captured.is_file():
                missing.append(relative.as_posix())
            elif captured.read_bytes() != path.read_bytes():
                changed.append(relative.as_posix())
            else:
                matched.append(relative.as_posix())
        rows.append({"task": task, "arm": arm, "trial": str(trial.relative_to(ROOT)),
            "state": "checked", "matched": matched, "changed": changed, "missing": missing,
            "all_declared_visible_inputs_preserved": not missing and not changed})
report = {"schema": 1, "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "scope": "captured visible input bytes, including R2R simulator; no full grader-gaming certification", "rows": rows}
(campaign / "visible-input-review.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps([{k: v for k, v in row.items() if k in
    {"task", "arm", "state", "all_declared_visible_inputs_preserved", "changed", "missing"}} for row in rows]))
