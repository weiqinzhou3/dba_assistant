# Redis Inspection Severity Policy

Deterministic severity is allowed for bounded metric and state checks:

- `cluster_state != ok`: high
- `master_link_status != up`: high
- `rdb_last_bgsave_status=err/fail`: high
- `aof_last_write_status=err/fail`: high
- `maxmemory=0`: medium
- high memory fragmentation: medium
- transparent huge page `always`: medium
- swap used: medium

LLM severity is required for log-derived issues because the same words can mean
routine lifecycle events, background noise, or a real incident depending on
context. The LLM should use:

- critical: active data loss, unavailable cluster, or cascading failure evidence
- high: confirmed OOM, persistence failure, repeated fork failure, or broken replication
- medium: degraded posture with clear recurrence or operational risk
- low/info: background context, isolated warning, or insufficient evidence

When evidence is incomplete, prefer lower confidence and a missing evidence
explanation instead of guessing.
