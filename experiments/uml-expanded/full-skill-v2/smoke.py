#!/usr/bin/env python3
"""Check all ten v2 arm payloads on a local HTTP wire, with no paid requests."""
import asyncio
import importlib.util
import json
import sys
from build import HERE, ROOT, check
from delivery import load_policy
from delivery_protocol import prefix_content, validate_delivery, SkillDeliveryError

sys.path.insert(0, str(HERE.parent))
spec = importlib.util.spec_from_file_location('legacy_wire_smoke', HERE.parent / 'smoke.py')
wire = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wire)


def validate_wire(body, policy):
    if policy['arm'] == 'text':
        # DeepSeek's native transform collapses text-only content lists to a
        # string after the strict gateway check. Verify its exact conversion;
        # do not change the frozen gateway/audit protocol or image checks.
        from litellm.litellm_core_utils.prompt_templates.common_utils import convert_content_list_to_str
        first = next(x for x in body['messages'] if x['role'] == 'user')
        expected = convert_content_list_to_str(message={'role': 'user', 'content': prefix_content(policy)})
        if first['content'] != expected:
            raise SkillDeliveryError('text-only wire conversion changed')
    else:
        validate_delivery(body, policy)


wire.validate_delivery = validate_wire


if __name__ == '__main__':
    manifest = check()
    rows = []
    # The old smoke's path is deliberately ignored; the versioned loader
    # resolves only these checked v2 paths. Wire hook/validation stay unchanged.
    for arm in ('text', 'image'):
        for task in manifest['tasks']:
            policy = load_policy(arm, HERE / 'tasks' / task / 'bundles' / arm)
            wire.load_policy = lambda *args, p=policy: p
            row = asyncio.run(wire.check(task, False))
            row['arm'] = arm
            row['image_count'] = len(policy['assets']) if arm == 'image' else 0
            rows.append(row)
    target = ROOT / '.runtime/uml-expanded/full-skill-v2-local-wire.json'
    target.write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps({'valid': all(r['valid'] for r in rows), 'arms': len(rows), 'report': str(target)}))
