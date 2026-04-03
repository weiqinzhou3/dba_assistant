# Phase 3 RDB Flow

This document describes the current Phase 3 runtime shape:

`CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

The important point is that the CLI no longer performs business routing. It only hands one normalized request into the shared boundary. From there, the unified Deep Agent decides which `skill` or `tool` to invoke.

## 1. End-to-End Data Flow

For a request such as:

```text
按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx
```

the runtime flow is:

1. `dba-assistant ask "<prompt>"` receives the prompt and any retained flags such as `--input`.
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
| `runtime_inputs` | Structured runtime values such as `redis_host`, `redis_port`, `input_paths`, `output_mode`, `report_format`, and `output_path` |
| `secrets` | Extracted secrets such as Redis password |
| `rdb_overrides` | Prompt-derived Phase 3 hints such as `profile_name`, `focus_prefixes`, `top_n`, and route hints |

This object exists so that:

- CLI can stay thin
- API / WebUI can reuse the same boundary
- the Deep Agent receives consistent context regardless of caller surface

## 3. Unified Agent Assembly

The unified agent is built in `src/dba_assistant/orchestrator/agent.py`.

It now explicitly includes:

- `memory` from repository `AGENTS.md`
- `skills` from `src/dba_assistant/skills/`
- the full tool list from `src/dba_assistant/orchestrator/tools.py`

That means the runtime is no longer “CLI routes to Phase 2 or Phase 3.” The real shape is:

- one Deep Agent
- one shared interface adapter
- one tool registry
- one repository skill source

## 4. Phase 3 Route Semantics

Phase 3 still keeps the formal route semantics:

- `legacy_sql_pipeline`
- `precomputed_dataset`
- `direct_memory_analysis`

These remain Phase 3 domain route names, not public CLI commands.

They are consumed inside the RDB-analysis domain, mainly through:

- prompt-derived route hints
- input type
- downstream Phase 3 request construction

The user should not have to think in “3a / 3b / 3c” terms when using the main CLI.

## 5. Remote Redis Approval Flow

Remote Redis is now part of the unified Deep Agent flow.

The runtime sequence is:

1. prompt includes a Redis target such as `redis.example:6379`
2. the unified agent may call read-only discovery tools first
3. if it chooses the remote-RDB acquisition tool, that tool call is guarded by Deep Agents `interrupt_on`
4. the CLI asks for approval
5. if approved, the tool call resumes
6. if denied, the orchestrator returns a denial result and the high-risk action is not performed

The important correction is:

- remote-RDB prompts are not rejected at the CLI or application-service layer anymore
- approval is attached to the high-risk tool call itself
- this keeps the control point inside the Deep Agent execution path

## 6. Current Tool Roles

At the unified-agent level, the relevant Phase 3 tools are:

- `analyze_local_rdb`
  - local `.rdb` analysis plus report rendering
- `discover_remote_rdb`
  - read-only remote Redis persistence discovery
- `fetch_and_analyze_remote_rdb`
  - approval-gated remote RDB acquisition intent

And the Phase 2 live inspection tools remain available alongside them:

- `redis_ping`
- `redis_info`
- `redis_config_get`
- `redis_slowlog_get`
- `redis_client_list`

That mixed tool set is intentional. It supports the target architecture:

`一个总 Deep Agent -> skills/tools 自由编排`

## 7. Exact Example

Request:

```text
按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx
```

With:

```text
--input ./dump.rdb
```

the actual flow is:

1. prompt parser extracts `rcs`, `docx`, and `/tmp/rcs.docx`
2. `--input` provides the concrete local file path
3. interface adapter merges prompt intent and any explicit CLI overrides
4. unified Deep Agent receives one final user message with the normalized context
5. the agent selects the local-RDB analysis tool
6. Phase 3 analysis resolves its internal route and profile
7. generic report generation renders the final artifact
8. `/tmp/rcs.docx` is written as the final result

That is the current architectural contract for Phase 3.
