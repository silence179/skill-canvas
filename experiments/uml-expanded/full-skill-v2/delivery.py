#!/usr/bin/env python3
"""Versioned bundle selection; reuse the frozen forced-prefix-v1 wire protocol."""
import base64
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LEGACY = ROOT / 'experiments/uml-flowchart'
sys.path.insert(0, str(LEGACY))
sys.path.insert(0, str(ROOT / 'experiments'))
import delivery_runner as legacy
from delivery_protocol import METHOD, SkillDeliveryError, digest, policy_id, validate_policy
from build import check


def load_policy(arm, bundle):
    manifest = check()
    bundle = Path(bundle).resolve()
    study = bundle.parent.parent
    if (arm not in ('text', 'image') or study.parent != HERE / 'tasks'
            or study.name not in manifest['tasks'] or bundle != study / 'bundles' / arm):
        raise SkillDeliveryError('unregistered full-skill-v2 task/arm/bundle')
    # Keep the v1 alphabetical ordering for both arms, despite a new diagram
    # authoring order in v2. Only image content/resources change.
    skills = sorted(manifest['tasks'][study.name]['skills'])
    assets = []
    for skill in skills:
        guide = (bundle / skill / 'GUIDE.md').read_bytes()
        item = {'skill': skill, 'guide_text': guide.decode(), 'guide_sha256': digest(guide)}
        if arm == 'image':
            raw = (bundle / skill / 'assets/flowchart.png').read_bytes()
            item.update(image_data=base64.b64encode(raw).decode(), image_sha256=digest(raw))
        assets.append(item)
    policy = {'method': METHOD, 'arm': arm, 'task': study.name, 'skill_names': skills,
        'study_sha256': digest((HERE / 'manifest.json').read_bytes()), 'assets': assets,
        'adapter_sha256': {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in
            (Path(__file__), LEGACY / 'delivery_runner.py', LEGACY / 'delivery_protocol.py')}}
    policy['id'] = policy_id(policy)
    validate_policy(policy)
    return policy


def main():
    from env_config import load_env
    import shared_opencode
    load_env(ROOT / '.env')
    os.environ.setdefault('DOCKER_CONFIG', str(ROOT / '.runtime/docker'))
    record = shared_opencode.load_record(check_image='--dry-run' not in sys.argv)
    shared_opencode.install_adapter(record)
    print('Shared OpenCode image: ' + record['tag'], flush=True)
    legacy.load_policy = load_policy
    return legacy.main()


if __name__ == '__main__':
    raise SystemExit(main())
