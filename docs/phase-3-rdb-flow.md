# Phase 3 RDB Flow

This document describes the current Phase 3 runtime shape:

`CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

The important point is that the CLI no longer performs business routing. It only hands one normalized request into the shared boundary. From there, the unified Deep Agent decides which `skill` or `tool` to invoke.

## 1. End-to-End Data Flow

For a request such as:

```text
分析 /data/a.rdb 和 /data/b.rdb，按 rcs profile 输出 docx，到 /tmp/rcs.docx
```

the runtime flow is:

1. `dba-assistant ask "<prompt>"` receives the prompt and any retained override flags.
2. `src/dba_assistant/interface/adapter.py` loads config and normalizes the raw request.
3. The interface adapter applies explicit overrides such as `--profile`, `--report-format`, or `--output`.
4. `src/dba_assistant/orchestrator/agent.py` builds one unified Deep Agent with:
   - repository `memory`
   - repository `skills`
   - all currently available DBA tools
5. The orchestrator sends one user message to that unified agent.
6. The Deep Agent decides whether to use:
   - a local RDB analysis tool
   - a live Redis inspection tool
   - remote RDB discovery
   - a report-generation path
7. The final assistant output is returned back through the interface adapter to the CLI.

The same interface boundary is intended for future API and WebUI callers.

## 2. Normalized Request Boundary

The shared request model still matters, but it is now an application boundary, not a business router.

The normalized request carries:

| Field | Meaning |
|------|---------|
| `raw_prompt` | Original prompt text |
| `prompt` | Normalized prompt after secret stripping and cleanup |
| `runtime_inputs` | Explicit surface values such as CLI `input_paths`, explicit overrides, and config-backed runtime defaults |
| `secrets` | Extracted secrets such as Redis / SSH / MySQL passwords |
| `rdb_overrides` | Bounded interface overrides such as explicit `profile_name` |

This object exists so that:

- CLI can stay thin
- secrets can be extracted once at the shared boundary
- API / WebUI can reuse the same boundary
- explicit interface overrides can stay secondary without breaking the shared contract
- the Deep Agent receives consistent context regardless of caller surface

Non-sensitive parameters such as Redis host, SSH username, MySQL database, remote RDB path, and output path are now expected to flow through tool arguments or explicit interface fields, not prompt parsing.

## 3. Unified Agent Assembly

The unified agent is built in `src/dba_assistant/orchestrator/agent.py`.

It now explicitly includes:

- `memory` from repository `AGENTS.md`
- `skills` from repository-root `skills/`
- the full tool list from `src/dba_assistant/orchestrator/tools.py`

That means the runtime is no longer “CLI routes to Phase 2 or Phase 3.” The real shape is:

- one Deep Agent
- one shared interface adapter
- one repository tool set
- one repository skill source

## 4. Phase 3 Route Semantics

Phase 3 now uses these canonical route names:

- `database_backed_analysis`
- `preparsed_dataset_analysis`
- `direct_rdb_analysis`

These are Phase 3 domain route names, not public CLI commands.

Compatibility aliases still normalize correctly:

- `legacy_sql_pipeline` -> `database_backed_analysis`
- `precomputed_dataset` -> `preparsed_dataset_analysis`
- `direct_memory_analysis` -> `direct_rdb_analysis`
- `3a` -> `database_backed_analysis`
- `3b` -> `preparsed_dataset_analysis`
- `3c` -> `direct_rdb_analysis`

They are consumed inside the RDB-analysis domain, mainly through:

- explicit route overrides when present
- input type
- downstream Phase 3 request construction

The user should not have to think in stage labels or legacy route names when using the main CLI.

## 5. Remote Redis Approval Flow

Remote Redis is now part of the unified Deep Agent flow.

The runtime sequence is:

1. the prompt includes a Redis target such as `redis.example:6379`
2. the unified agent calls `discover_remote_rdb(redis_host=..., redis_port=..., redis_db=...)`
3. if the user wants the latest snapshot, the agent calls `ensure_remote_rdb_snapshot(...)` and runtime gates that call with approval
4. the agent calls `fetch_remote_rdb_via_ssh(remote_rdb_path=..., ssh_host=..., ssh_port=..., ssh_username=...)` and runtime gates that call with approval
5. after fetch succeeds, the agent calls `inspect_local_rdb` on the downloaded local artifact
6. the agent chooses direct analysis or MySQL-backed staging based on inspection and user intent; if MySQL staging is rejected, the agent continues with direct streaming analysis

The important correction is:

- remote-RDB prompts are not rejected at the CLI or application layer anymore
- approval is attached to the high-risk tool call itself; rejecting MySQL staging rejects that route, not the entire analysis request
- this keeps the control point inside the Deep Agent execution path

## 6. Current Tool Roles

At the unified-agent level, the relevant Phase 3 tools are:

- `inspect_local_rdb`
  - local `.rdb` file existence and size inspection before strategy selection
- `analyze_local_rdb_stream`
  - direct local `.rdb` analysis plus report rendering for streaming-friendly files
- `stage_local_rdb_to_mysql`
  - approval-gated local `.rdb` staging into MySQL for files larger than 1GB
- `analyze_staged_rdb`
  - analysis and report generation from previously staged MySQL data
- `analyze_preparsed_dataset`
  - analysis from preparsed local or MySQL-backed datasets
- `discover_remote_rdb`
  - read-only remote Redis persistence discovery
- `ensure_remote_rdb_snapshot`
  - approval-gated fresh remote snapshot generation via Redis `BGSAVE`
- `fetch_remote_rdb_via_ssh`
  - approval-gated remote RDB acquisition over SSH only; analysis continues in later tool calls

And the Phase 2 live inspection tools remain available alongside them:

- `redis_ping`
- `redis_info`
- `redis_config_get`
- `redis_slowlog_get`
- `redis_client_list`

That mixed tool set is intentional. It supports the target architecture:

`一个总 Deep Agent -> skills/tools 自由编排`

## 7. RDB Parser Runtime

Phase 3 RDB parsing now prefers `HDT3213/rdb` through `src/dba_assistant/parsers/rdb_parser_strategy.py`.

- default order is `HdtRdbCliStrategy` first, then `LegacyRdbtoolsStrategy` as fallback
- the selected parser strategy is written into analysis metadata as `parser_strategy`
- if the HDT CLI is selected, the resolved binary path is written as `parser_binary`

Binary discovery order is:

1. `DBA_ASSISTANT_HDT_RDB_BIN`
2. repository-local `.tools/bin/rdb`
3. `rdb` from `PATH`

Bootstrap for local development and CI:

```bash
./scripts/install_hdt_rdb.sh
```

That script installs `github.com/hdt3213/rdb` into `.tools/bin/rdb`, which is the repository-local default path.

## 8. Exact Example

Request:

```text
按 rcs profile 分析 /data/a.rdb 和 /data/b.rdb，输出 docx，到 /tmp/rcs.docx
```

the actual flow is:

1. the shared boundary strips secrets and preserves explicit interface inputs such as CLI `--input`
2. interface adapter merges any explicit CLI overrides
3. the unified Deep Agent receives one final user message with the free-form prompt plus explicit surface context
4. the agent selects the appropriate local-RDB analysis path and passes `profile_name='rcs'`, `output_mode='report'`, `report_format='docx'`, and `output_path='/tmp/rcs.docx'` as tool arguments
5. generic report generation renders the final artifact
6. runtime only accepts the run as successful if a real `.docx` artifact path exists
7. `/tmp/rcs.docx` is returned as the final result

That is the current architectural contract for Phase 3.

## 9. Prompt-First Secret Extraction

Prompt parsing is now expected to extract only scoped secrets directly into the shared contract:

- Redis password
- SSH password
- MySQL password

Retained CLI flags remain useful, but only as:

- explicit overrides
- debugging fallbacks
- deterministic reproduction of a previous run

Profile choice, route choice, connection targets, output paths, and analysis strategy remain LLM responsibilities unless the caller supplies explicit structured fields.

That keeps the user-facing entry prompt-first while preserving the structured request boundary required for future API and WebUI callers.
