#!/usr/bin/env python3
"""Use the exact preinstalled test toolchain; preserve the entire scoring tail."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from prepare_environments import ROOT, COPIES
from study import inventory

task = "manufacturing-fjsp-optimization"
campaign = ROOT / "jobs/uml-expanded/paired-five-v1"
plan = json.loads((campaign / "campaign.json").read_text())
assert all(s["status"] == "planned" for s in plan["schedule"] if s["task"] == task)
original = ROOT / "repos/skillsbench/tasks" / task
prepared = COPIES / task
old = (original / "verifier/test.sh").read_text()
tail = old[old.index("mkdir -p /logs/verifier"):]
new = ("#!/bin/bash\nset -euo pipefail\n"
       "# SkillCanvas: bootstrap only; same uv version and unchanged test command.\n"
       "test \"$(uv --version)\" = 'uv 0.9.7'\n"
       "export UV_NO_INDEX=1\n" + tail)
assert new[new.index("mkdir -p /logs/verifier"):] == tail
assert (original / "verifier/test_outputs.py").read_bytes() == (prepared / "verifier/test_outputs.py").read_bytes()
(prepared / "verifier/test.sh").write_text(new)
sha = lambda data: hashlib.sha256(data).hexdigest()
amendment = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "task": task,
    "before_first_model_trial_for_this_task": True,
    "reason": "the pinned online uv installer endpoint fails; use preinstalled uv 0.9.7 and its exact cached pytest dependencies",
    "changes": ["verifier/test.sh dependency bootstrap only"],
    "scoring_tail_byte_identical": True, "test_outputs_py_byte_identical": True,
    "oracle_prompt_data_skills_unchanged": True,
    "original_test_sh_sha256": sha(old.encode()), "adapted_test_sh_sha256": sha(new.encode()),
    "scoring_tail_sha256": sha(tail.encode()),
    "test_outputs_py_sha256": sha((original / "verifier/test_outputs.py").read_bytes()),
    "script_sha256": sha(Path(__file__).read_bytes())}
(campaign / "manufacturing-bootstrap-amendment.json").write_text(json.dumps(amendment, indent=2) + "\n")
(campaign / "manufacturing-amended-files.json").write_text(json.dumps(inventory(prepared), indent=2) + "\n")
print("Adapted dependency bootstrap; grading tail and Python assertions unchanged")
