---
name: cache-policy-comparison
description: Compare and implement eviction policies (LRU, LFU, FIFO, S3FIFO, ARC) for bounded-capacity caches. Use when choosing or implementing an eviction policy for a buffer pool, page cache, CDN edge, or LLM KV cache, or when writing a replay simulator that supports multiple policies. Clarifies recency vs frequency semantics, queue topology, saturating counters, ghost buffers, and the second-chance rule that distinguishes modern FIFO-family policies from classic LRU.
---

# Skill reading order

1. Read GUIDE.md, the complete original skill, before using its workflow, references, or scripts.

Follow the task's requested outputs. The original examples, code, caveats, and resource paths are preserved in GUIDE.md and the adjacent references/ and scripts/ directories.
