---
name: redis-rdb-analysis
description: Analyze local RDB files, MySQL-backed preparsed datasets, or approval-gated remote Redis dumps through the unified Deep Agent.
---

# Redis RDB Analysis

Use this skill when the user needs Redis RDB memory analysis, prefix analysis, big-key analysis, or report generation from:

- local `.rdb` files
- remote Redis targets that require discovery plus approval-gated fetch
- preparsed datasets from local exports or MySQL

Current runtime shape:

- The unified Deep Agent chooses between `direct_rdb_analysis`, `database_backed_analysis`, and `preparsed_dataset_analysis`.
- Remote Redis retrieval stays inside the tool flow: `discover_remote_rdb` then `fetch_remote_rdb_via_ssh`.
- MySQL-backed analysis can read preparsed datasets or stage parsed rows into MySQL when the write step is approved.

Important boundaries:

- This skill is active and invokable in the current unified-agent runtime.
- Remote fetch and MySQL staging are approval-gated operations.
- Output may be summary text or a generated report artifact depending on the request.
