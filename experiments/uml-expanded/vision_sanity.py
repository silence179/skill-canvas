#!/usr/bin/env python3
"""Separate image-only transcription check; never part of benchmark scoring."""
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import sys

from study import HERE, ROOT
sys.path.insert(0, str(ROOT / 'experiments'))
from env_config import load_env

async def main():
    load_env(ROOT / '.env')
    os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
    import litellm
    images = [HERE / 'tasks/energy-market-pricing/previews/dc-power-flow.png',
              HERE / 'tasks/manufacturing-fjsp-optimization/previews/fjsp-baseline-repair-with-downtime-and-policy.png']
    prompt = ('Read the two attached flowchart images. No source text is provided. '
        'Return only concise JSON with keys q1, q2, q3. '
        'q1: In image 1, transcribe the rounded rectangle on the right directly below the middle decision diamond. '
        'q2: In image 2, transcribe the half-open overlap inequality in the yellow note at bottom right. '
        'q3: In image 2, transcribe the label on the left exit of the decision about overlap with machine work or downtime.')
    content = [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(p.read_bytes()).decode()}} for p in images]
    content.append({'type': 'text', 'text': prompt})
    record = {'schema': 1, 'scope': 'Image-only spatial transcription sanity, separate from the paired benchmark; does not prove task reasoning benefits.',
        'model': os.environ['EXP_MODEL'], 'prompt': prompt,
        'images': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in images},
        'expected_fragments': ["zero-susceptance handling", 's < b AND a < e', 'earliest feasible start']}
    try:
        response = await litellm.acompletion(model=os.environ['EXP_MODEL'],
            api_key=os.environ['DEEPSEEK_API_KEY'], api_base=os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1'),
            messages=[{'role': 'user', 'content': content}], max_tokens=1024, timeout=60, num_retries=0)
        reply = response.choices[0].message.content or ''
        normalized = ' '.join(reply.lower().split())
        record.update(reply=reply, usage=response.usage.model_dump(),
            matched_fragments=[fragment.lower() in normalized for fragment in record['expected_fragments']])
    except Exception as error:
        record.update(error_type=type(error).__name__, status_code=getattr(error, 'status_code', None))
    target = HERE / 'results/vision-sanity.json'
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: record.get(key) for key in ('reply', 'matched_fragments', 'error_type', 'status_code')}, ensure_ascii=False))

if __name__ == '__main__':
    asyncio.run(main())
