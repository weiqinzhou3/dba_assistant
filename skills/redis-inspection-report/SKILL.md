---
name: redis-inspection-report
description: Describe the Phase 4 Redis inspection reporting scope and the current boundaries of the unified-agent runtime.
---

# Redis Inspection Report

Use this skill for Redis inspection report requests that are based on live read-only inspection data or offline inspection bundles.

Current boundary:

- The repository already exposes read-only Redis inspection tools such as `redis_ping`, `redis_info`, `redis_config_get`, `redis_slowlog_get`, and `redis_client_list`.
- Full Phase 4 inspection report assembly is still narrower than the RDB analysis path and should be treated as incremental work, not as a completed end-to-end reporting pipeline.

Guidance:

- Stay within read-only Redis inspection capabilities.
- Do not claim remote write, remediation, or mutation capabilities.
- If the user asks for a rich inspection report beyond the currently wired runtime, explain the available read-only inspection data first.
