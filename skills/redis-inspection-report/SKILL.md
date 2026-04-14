---
name: redis-inspection-report
description: Generate Redis inspection summaries or formal DOCX reports from offline evidence bundles or live read-only Redis probes.
---

# Redis Inspection Report

Use this skill when the user asks for Redis 巡检, health inspection, risk review,
cluster inspection, offline evidence package analysis, or a formal Redis
inspection report.

## Trigger Conditions

- The prompt asks to inspect Redis runtime health, topology, configuration,
  host evidence, slow logs, client posture, or Redis error logs.
- The prompt provides an offline inspection bundle, directory, or mixed evidence
  files and asks for a report.
- The prompt provides Redis connection information and asks for a live read-only
  inspection summary or DOCX report.

Do not use this skill for RDB keyspace/memory-distribution analysis. Use
`redis-rdb-analysis` for RDB dump analysis.

## Tool Usage

Use `redis_inspection_report` for the end-to-end Phase 4 path.

- Offline evidence: pass `input_paths` as comma-separated files, directories, or
  `.tar.gz` bundles.
- Live read-only inspection: omit `input_paths` and provide `redis_host`,
  `redis_port`, and `redis_db` when needed. Passwords must come from secure
  runtime context, not from tool parameters.
- Summary output: use `output_mode="summary"` and `report_format="summary"`.
- Formal DOCX output: use `output_mode="report"`, `report_format="docx"`, and an
  `output_path` when the runtime has not already supplied one.

The following lower-level read-only probes are available for evidence checks or
stepwise debugging: `redis_ping`, `redis_info`, `redis_config_get`,
`redis_slowlog_get`, `redis_client_list`, `redis_cluster_info`, and
`redis_cluster_nodes`.

## Risk and Approval Notes

- This skill is read-only. It must not run Redis write commands, remediation,
  failover, resize, or configuration mutation.
- SSH error-log collection is not part of this first vertical slice unless a
  repository tool explicitly provides an approval-aware read-only SSH path.
- If required evidence is missing, return a clear missing-evidence explanation
  instead of guessing.

## Output Contract

The skill produces a shared `AnalysisReport` compatible with repository summary
and DOCX renderers. The report is organized by system, cluster, and node, and
contains risk items with severity, target, evidence, impact, and remediation.
