---
name: prefix-cache-replay
description: Replay an LLM inference request trace (Mooncake / vLLM / SGLang hash_ids format) against a block-level KV prefix cache and compute hit statistics. Use when given a request trace plus cache configuration and asked for hit rate, hit tokens, or final cache contents. Covers the longest-contiguous-prefix semantics that distinguishes KV prefix caching from full-prompt prompt caching, the policy-specific residency and eviction rules (LRU, LFU, S3FIFO), and the partial-last-block accounting rule.
---

# Skill reading order

1. Read GUIDE.md, the complete original skill, before using its workflow, references, or scripts.

Follow the task's requested outputs. The original examples, code, caveats, and resource paths are preserved in GUIDE.md and the adjacent references/ and scripts/ directories.
