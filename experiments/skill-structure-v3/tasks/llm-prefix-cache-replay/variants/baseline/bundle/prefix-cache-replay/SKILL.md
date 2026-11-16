---
name: prefix-cache-replay
description: Replay an LLM inference request trace (Mooncake / vLLM / SGLang hash_ids format) against a block-level KV prefix cache and compute hit statistics. Use when given a request trace plus cache configuration and asked for hit rate, hit tokens, or final cache contents. Covers the longest-contiguous-prefix semantics that distinguishes KV prefix caching from full-prompt prompt caching, the policy-specific residency and eviction rules (LRU, LFU, S3FIFO), and the partial-last-block accounting rule.
---

# Skill reading order

1. Open assets/flowchart.png with your image-viewing tool and inspect the rendered workflow before applying this skill. Resolve this path relative to this SKILL.md. Reading a filename, image bytes, or alt text is not viewing the image.
2. Then read GUIDE.md, the complete original skill, before using its workflow, references, or scripts.
If the image cannot be viewed, say so and continue with GUIDE.md; do not claim that the visual workflow was inspected.

Follow the task's requested outputs. The original examples, code, caveats, and resource paths are preserved in GUIDE.md and the adjacent references/ and scripts/ directories.
