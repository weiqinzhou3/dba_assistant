---
name: redis-inspection-report
description: Generate Redis inspection summaries or formal DOCX reports from offline evidence bundles or live read-only Redis probes.
---

# Redis Inspection Report Contract

Use this skill for Redis 巡检, health checks, cluster inspection, risk checks,
offline evidence package analysis, live read-only inspection, Redis error log
analysis, and formal Redis inspection reports.

Do not use this skill for Redis RDB keyspace, memory distribution, prefix, TTL,
or big-key analysis. Use `redis-rdb-analysis` for RDB dump analysis.

## Trigger Conditions

Use this skill when the user asks for any of the following:

- Redis 巡检 or health inspection
- health check, cluster inspection, or risk check
- offline evidence bundle, evidence directory, mixed evidence files, or
  historical inspection package analysis
- online / live read-only inspection of a Redis target
- Redis error log, warning log, slow log, topology, configuration, client, host,
  memory posture, or persistence posture review
- Word, DOCX, Doc, 文档, 报告, or formal report output for inspection findings

## Two Main Paths

### Offline Evidence Inspection

Use `redis_inspection_report` with `input_paths` for local files, directories,
mixed inputs, or `.tar.gz` evidence bundles. Supported evidence includes Redis
INFO output, cluster nodes output, config snippets, host evidence, slowlog
captures, and Redis log files.

If the input evidence is missing or unsupported, return a missing evidence
explanation. Do not guess topology, host facts, ports, or findings without
evidence.

When the user asks to analyze Redis logs, use a two-stage log path:

1. Deterministic evidence reduction: call `redis_inspection_log_candidates` to
   collect neutral `log_candidates`. This stage may parse timestamps, apply the
   time window, deduplicate repeated lines, count frequencies, sample bounded
   evidence, and bucket candidates by node and cluster.
2. LLM semantic review: inspect the candidate JSON and produce structured
   `reviewed_log_issues` with `issue_name`, `is_anomalous`, `severity`, `why`,
   `affected_nodes`, `supporting_samples`, `recommendation`, `merge_key`,
   `category`, and `confidence`.

The deterministic stage must not decide whether a log candidate is abnormal.
Normal persistence events, including successful AOF rewrite and normal RDB
copy-on-write statistics, must not be treated as anomalies unless LLM semantic
review explicitly identifies a real risk with evidence.

### Live Read-Only Inspection

Use `redis_inspection_report` without `input_paths` and pass explicit Redis
connection target fields when the user provides them:

- `redis_host`
- `redis_port`
- `redis_db`

Live inspection is read-only. It may use Redis read probes such as ping, INFO,
CONFIG GET, SLOWLOG GET, CLIENT LIST, CLUSTER INFO, and CLUSTER NODES. It must
not run writes, remediation, failover, resize, config mutation, or destructive
commands.

## Parameter Ownership

The LLM should understand these from the prompt or prior tool results and pass
them to tools when relevant:

- whether the user wants DOCX / Word / formal report output
- whether the user wants summary output
- whether the user wants log analysis
- the user's explicit log time range
- `log_time_window_days`
- `log_start_time`
- `log_end_time`
- input source type: offline evidence or live read-only inspection
- Redis connection target
- SSH target only if the user provides it and an approval-aware read-only SSH log
  collection path exists

The LLM must not invent these:

- `output_path`
- temporary directories
- project repository paths
- generated table names or temporary file names
- hosts, credentials, Redis ports, SSH ports, or usernames not supplied by the
  user or runtime context

Do not invent missing inspection evidence or replacement paths.

Secrets must come only from secure runtime context. Do not pass passwords as
tool arguments.

## Default Policies

- If the user asks to analyze logs and gives no time range, default to the last 30 days.
- If the user explicitly asks for recent 7 days, recent 1 month, recent 90 days,
  or another time window, pass that user-provided window.
- If the user explicitly gives `log_start_time` or `log_end_time`, pass those
  values exactly.
- If the user asks for Word, DOCX, Doc, 正式报告, 文档, or 报告 and gives no output
  path, do not require the user to provide output_path. Omit `output_path` and
  let runtime/tool default to
  `/tmp/dba_assistant_redis_inspection_<timestamp>.docx`.

## Output Contract

- Summary mode returns an inline summary.
- DOCX mode must generate a DOCX artifact.
- On success, the final response must include the generated artifact path.
- Do not provide only an inline summary as a substitute for DOCX output.
- Chapter 3 uses cluster-level merged issues. For log-derived problems, merge by
  `merge_key` first, then by cluster, issue name, severity, impact, and
  recommendation.
- Chapter 9 shows the detailed risk items from the same reviewed issue set. It
  must not run a second programmatic log-anomaly rule.

## Risk and Approval Constraints

- Inspection is read-only by default.
- SSH log collection must use an approval-aware read-only path if such a tool is
  available. Do not ask for approval in plain text.
- If evidence is missing, stale, incomplete, or unparseable, state the missing
  evidence explanation and avoid guessing.

## Log Timestamp Filtering

When a time window is active, only log lines with parseable timestamps inside
the window should be counted as time-scoped log findings. Supported timestamp
forms include:

- `YYYY-MM-DD HH:MM:SS`
- ISO-like date/time forms
- `26 May 2023 15:22:16.830`
- `17 Dec 15:01:30.642` interpreted against the active window year

Lines without parseable timestamps must not silently bypass the time window.
They may be retained only when no time filtering is active.

## Log Issue Ownership

Programs may keep deterministic rules for THP always, used swap, maxmemory=0,
high memory fragmentation, failed `rdb_last_bgsave_status`, failed
`aof_last_write_status`, `master_link_status != up`, and `cluster_state != ok`.

For log semantics, the LLM owns:

- deciding whether a candidate represents an anomaly
- distinguishing normal operating events from incidents
- merging similar log problems across nodes in a cluster
- naming the issue
- assigning severity for log-derived problems
- writing the why/recommendation fields

Only `reviewed_log_issues` with `is_anomalous=true` may become findings.
