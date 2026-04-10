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

### Small to Medium Files (< 512MB)
- **Path**: Use `analyze_local_rdb_stream`.
- **Workflow**: `inspect` -> `analyze_local_rdb_stream`.

### Large Files (> 512MB)
- **Step A (Proposal)**: Inform the user the file is large and recommend MySQL-backed staging (`stage_local_rdb_to_mysql`).
- **Step B (User Decision)**:
    - **If user agrees**: Proceed with `stage_local_rdb_to_mysql` -> `analyze_staged_rdb`.
    - **If user refuses or insists on direct analysis**: Warn the user about potential memory issues/partial analysis, then **immediately proceed** with `analyze_local_rdb_stream`. **Do not continue asking for permission.**

### Missing Files
- If `inspect` shows the file does not exist, report the exact path and error. Do not guess alternative paths.

## 3. Remote RDB Acquisition
If the user provides a Redis host/port instead of a file:
- **Step A**: Call `discover_remote_rdb`.
- **Step B**: Call `fetch_remote_rdb_via_ssh` (requires approval).
- **Step C**: Once fetched, proceed to Step 1 (Inspect) using the newly downloaded local path.

## Important Constraints
- **Respect User Overrides**: If the user says "just analyze it" or "no MySQL", you must follow that instruction despite the SOP recommendation.
- **HITL Enforcement**: Never ask for approval for `fetch_remote_rdb_via_ssh` or `stage_local_rdb_to_mysql` in plain text. Call the tool; the system handles the confirmation dialog.
