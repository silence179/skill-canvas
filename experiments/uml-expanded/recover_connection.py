#!/usr/bin/env python3
"""One registered paired recovery of connection failures; never select by score."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from campaign import ROOT, source_identity, write

source = ROOT / 'jobs/uml-expanded/paired-five-v1'
target = ROOT / 'jobs/uml-expanded/paired-five-v1-recovery'
tasks = ['exam-block-sequencing', 'manufacturing-fjsp-optimization']
target.mkdir(parents=True, exist_ok=True)
registration = target / 'recovery-plan.json'
if registration.exists():
    raise SystemExit('Recovery already registered; refuse duplicate dispatch.')
observed = []
for task in tasks:
    found = []
    for trace in (source / task).glob('*/*/*/trajectory/llm_trajectory.jsonl'):
        events = [json.loads(line) for line in trace.read_text().splitlines()]
        errors = [event.get('response', {}).get('status_code') for event in events
                  if event.get('response', {}).get('status_code') != 200]
        if errors:
            found.append({'trace': str(trace.relative_to(ROOT)), 'failed_statuses': errors})
    if not found:
        raise SystemExit(f'No observed connection failure: {task}')
    observed.extend(found)
write(registration, {'schema': 1, 'registered_at_utc': datetime.now(timezone.utc).isoformat(),
    'source_campaign': str(source.relative_to(ROOT)), 'tasks': tasks,
    'reason': 'Both selected task pairs encountered upstream connection-reset HTTP 500 errors; no selection by score.',
    'observed_failures_at_registration': observed,
    'rule': 'At most one fresh complete pair per selected task, same order and immutable task/diagram/harness/model settings; keep all originals and report every attempt. No further automatic retries.',
    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
print('Registered one recovery pair each for exam and manufacturing; waiting for original campaign.', flush=True)
while True:
    original = json.loads((source / 'campaign.json').read_text())
    if all(slot['status'] in {'finished', 'failed'} for slot in original['schedule']):
        break
    time.sleep(10)
if original['code_sha256'] != source_identity():
    raise SystemExit('Frozen implementation changed; recovery refused.')
original['created_at_utc'] = datetime.now(timezone.utc).isoformat()
original['purpose'] = 'One connection-failure recovery; original six healthy runs referenced, two complete pairs rerun.'
original['recovery_registration'] = str(registration.relative_to(ROOT))
for slot in original['schedule']:
    if slot['task'] not in tasks:
        if slot['status'] != 'finished':
            raise SystemExit('An unexpected original task failed; manual audit needed.')
        continue
    old = slot['jobs_dir']
    new = str(target / slot['task'] / slot['arm'])
    slot['original_jobs_dir'] = old
    slot['jobs_dir'] = new
    slot['command'] = [new if arg == old else arg for arg in slot['command']]
    slot['status'] = 'planned'
    for key in ('exit_code', 'started_at_utc', 'finished_at_utc'):
        slot.pop(key, None)
for name in ('manufacturing-environment-amendment.json', 'manufacturing-bootstrap-amendment.json',
             'manufacturing-amended-files.json', 'frozen-source-manifest.json'):
    (target / name).write_bytes((source / name).read_bytes())
value = json.loads(registration.read_text())
value['source_final_manifest_sha256'] = hashlib.sha256((source / 'campaign.json').read_bytes()).hexdigest()
value['launched_at_utc'] = datetime.now(timezone.utc).isoformat()
write(registration, value)
write(target / 'campaign.json', original)
print('Original campaign terminal; launching four recovery trials.', flush=True)
result = subprocess.run([sys.executable, str(Path(__file__).with_name('campaign.py')), 'run', '--campaign', str(target)], cwd=ROOT)
raise SystemExit(result.returncode)
