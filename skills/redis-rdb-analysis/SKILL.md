---
name: redis-rdb-analysis
description: Specialized contract for Redis RDB memory analysis, prefix analysis, big-key analysis, and DOCX artifact generation through DBA Assistant tools.
---

# Redis RDB Analysis Contract

Use this skill when the user asks to analyze Redis RDB dumps, memory distribution,
key prefixes, key types, TTL posture, big keys, focused prefixes, or a formal RDB
analysis report. Do not use this skill for Redis 巡检, health inspection, or
runtime log review; use `redis-inspection-report` for those tasks.

Keep this file as the task contract and SOP index. Use the supporting package
files for heavier policy details:

- `references/strategy_policy.md` for local direct stream, remote acquisition, and route selection.
- `references/mysql_staging_policy.md` for MySQL-backed staging wording and refusal handling.
- `references/docx_contract.md` for DOCX artifact and output_path ownership.
- `assets/report_outline.md` and `assets/output_contract.json` for report and artifact structure.
- `scripts/mysql_queries.sql` for example read queries against staged data.

## Trigger Conditions

- The user provides a local `.rdb` file path or interface input file and asks for
  keyspace, memory, prefix, expiration, or big-key analysis.
- The user provides a remote Redis target and asks to acquire or analyze its RDB.
- The user provides a precomputed or MySQL-staged RDB dataset and asks for RDB
  analysis.
- The user asks for Word, DOCX, Doc, 文档, 报告, or a formal report for RDB
  analysis.

## Local RDB Path

Always inspect local files before analysis:

1. Call `inspect_local_rdb(input_paths=...)` for the exact file paths supplied by
   the user, interface, or prior tool result.
2. If any inspected file is missing, report that exact path and stop. Do not
   invent fallback input paths such as `/tmp/dump.rdb`.
3. If every file is small or medium (size is at most 1 GB), call
   `analyze_local_rdb_stream`.
4. If any file is larger than 1 GB, recommend MySQL-backed staging for full
   analysis.

## Large RDB Strategy

For files larger than 1 GB:

- Explain that MySQL-backed staging is recommended because it is safer for
  full analysis of large dumps.
- If the user agrees, gather missing MySQL settings with `ask_user_for_config`
  when needed, then call `stage_local_rdb_to_mysql`, followed by
  `analyze_staged_rdb`.
- If the user refuses MySQL or says direct analysis / just analyze it / no
  MySQL, warn once about memory or partial-analysis risk, then immediately proceed
  with `analyze_local_rdb_stream`. Do not repeat negotiation.
- MySQL staging consent is not a substitute for runtime approval. After the user
  chooses staging, call the approval-gated tool and let the runtime interrupt
  collect approval.

## Remote RDB Acquisition

If the user provides a Redis target instead of a local RDB file, use the remote
tool chain explicitly:

1. Call `discover_remote_rdb(redis_host=..., redis_port=..., redis_db=...)`.
2. If the user asks for the latest snapshot or the runtime context says fresh
   snapshot, call `ensure_remote_rdb_snapshot(redis_host=..., redis_port=...,
   redis_db=...)`.
3. Call `fetch_remote_rdb_via_ssh(remote_rdb_path=..., ssh_host=...,
   ssh_port=..., ssh_username=...)`.
4. Use the fetched local path returned by the SSH tool and continue with
   `inspect_local_rdb`.

`ensure_remote_rdb_snapshot` and `fetch_remote_rdb_via_ssh` are approval-gated.
Do not ask for approval in plain text; call the tool so the runtime interrupt can
handle HITL.

## Parameter Ownership

The LLM must pass explicit, non-sensitive tool arguments that it understands
from the prompt or tool results:

- local RDB file paths
- Redis host, port, and DB
- SSH host, port, and username
- MySQL host, port, user, database, table, and query when provided
- report language, output mode, report format, profile name, and focus prefixes

Secrets must not be passed as tool parameters. Redis, SSH, and MySQL passwords
come only from secure runtime context or a secure `ask_user_for_config` flow.

Do not invent hosts, credentials, file paths, table names, output paths, or
temporary directories. If required evidence is absent, explain what is missing.

## DOCX Artifact Contract

If the user asks for Word, DOCX, Doc, 文档, 报告, or a formal RDB report:

- Call the chosen analysis tool with `output_mode='report'` and
  `report_format='docx'`.
- If the user supplied an output path, pass it exactly.
- If no output path is supplied, omit `output_path` and let the runtime/tool
  apply the repository output-path policy.
- After the tool succeeds, the final response must include the generated DOCX
  artifact path. Do not replace DOCX output with an inline-only summary.

## Success Criteria

- Small local RDB files follow `inspect_local_rdb` -> `analyze_local_rdb_stream`.
- Large local RDB files recommend MySQL-backed staging.
- Large-file direct fallback is honored immediately when the user refuses MySQL.
- Remote RDB analysis follows discover -> optional fresh snapshot -> SSH fetch
  -> local inspect -> analysis.
- DOCX requests produce a generated DOCX artifact path.
