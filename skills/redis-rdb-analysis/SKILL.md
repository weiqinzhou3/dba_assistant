---
name: redis-rdb-analysis
description: Specialized instructions for the DBA Assistant to perform Redis RDB memory analysis, prefix analysis, and big-key analysis through the unified Deep Agent.
---

# Redis RDB Analysis SOP

This skill defines the standard operating procedure for analyzing Redis RDB files. You must follow these steps to ensure accuracy and respect the user's environment.

## 1. Context Assessment & Inspection
If a user provides a local path or asks to analyze a file:
- **Rule**: Always call `inspect_local_rdb` first.
- **Goal**: Verify the file exists and check its size.
- **Memory**: Pay close attention to the paths provided in the conversation history. Do not use default paths like `/tmp/dump.rdb` if an explicit path has been mentioned.

## 2. Choosing the Analysis Strategy
Based on the metadata from `inspect_local_rdb`:

### Small to Medium Files (<= 1GB)
- **Path**: Use `analyze_local_rdb_stream`.
- **Workflow**: `inspect` -> `analyze_local_rdb_stream`.

### Large Files (> 1GB)
- **Step A (Proposal)**: Inform the user the file is large and recommend MySQL-backed staging (`stage_local_rdb_to_mysql`).
- **Step B (User Decision)**:
    - **If user agrees**: Proceed with `stage_local_rdb_to_mysql` -> `analyze_staged_rdb`.
    - **If user refuses or insists on direct analysis**: Warn the user about potential memory issues/partial analysis, then **immediately proceed** with `analyze_local_rdb_stream`. **Do not continue asking for permission.**

### Missing Files
- If `inspect` shows the file does not exist, report the exact path and error. Do not guess alternative paths.

## 3. Remote RDB Acquisition
If the user provides a Redis host/port instead of a file:
- **Step A**: Call `discover_remote_rdb(redis_host=..., redis_port=..., redis_db=...)`.
- **Step B**: If the user wants the latest snapshot, call `ensure_remote_rdb_snapshot(redis_host=..., redis_port=..., redis_db=...)` (requires approval).
- **Step C**: Call `fetch_remote_rdb_via_ssh(remote_rdb_path=..., ssh_host=..., ssh_port=..., ssh_username=...)` (requires approval).
- **Step D**: Once fetched, proceed to Step 1 (Inspect) using the newly downloaded local path.

## Important Constraints
- **Respect User Overrides**: If the user says "just analyze it" or "no MySQL", you must follow that instruction despite the SOP recommendation.
- **Parameter Ownership**: Redis / SSH / MySQL hosts, ports, usernames, file paths, and output paths are tool arguments. Do not assume the runtime already parsed them from the prompt.
- **HITL Enforcement**: For large files you may ask the user to choose between MySQL staging and direct streaming analysis. After the user chooses MySQL staging, never ask for separate write approval in plain text; call `stage_local_rdb_to_mysql` and let the system confirmation dialog handle it. The same rule applies to `ensure_remote_rdb_snapshot` and `fetch_remote_rdb_via_ssh`.
- **DOCX Fulfillment**: If the user explicitly asks for Word, DOCX, Doc, 文档, or 报告 output, you must call the chosen analysis tool with `output_mode='report'` and `report_format='docx'`.
- **DOCX Final Response**: After a DOCX tool call succeeds, reply with the generated DOCX artifact path. Do not replace the result with an inline-only prose summary.
