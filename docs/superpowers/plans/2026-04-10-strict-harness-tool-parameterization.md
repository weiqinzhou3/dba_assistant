# Strict Harness Tool Parameterization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans when splitting execution across workers. Steps use checkbox syntax for tracking.

**Goal:** Remove prompt-derived connection orchestration from Python and make all agent-facing business tools accept explicit non-sensitive parameters, while keeping secrets in runtime-only secure context.

**Architecture:** `interface adapter -> unified Deep Agent -> business tools`. The boundary sanitizes secrets and merges explicit surface fields only. Tools resolve connections from explicit tool args plus secure runtime context. Sensitive actions use runtime approval.

**Tech Stack:** Python, pytest, Deep Agents SDK, LangGraph

---

### Task 1: Lock The New Boundary Contract With Tests

**Files:**
- Modify: `tests/unit/application/test_prompt_parser.py`
- Modify: `tests/unit/interface/test_adapter.py`
- Modify: `tests/e2e/test_phase_3_rdb_analysis.py`

- [ ] Replace prompt-parser expectations that currently require Redis / SSH / MySQL endpoint extraction from prose.
- [ ] Keep tests for password extraction, prompt scrubbing, and explicit interface overrides.
- [ ] Add assertions that prompt-only DOCX path and prompt-only SSH host/user are no longer materialized into runtime inputs.

### Task 2: Shrink `application/` To Secrets And Explicit Inputs

**Files:**
- Modify: `src/dba_assistant/application/prompt_parser.py`
- Modify: `src/dba_assistant/interface/adapter.py`
- Modify: `src/dba_assistant/application/README.md`

- [ ] Refactor `normalize_raw_request(...)` so it keeps password extraction and prompt scrubbing only.
- [ ] Preserve interface-level overrides and config defaults where they originate from CLI/API, not prose.
- [ ] Remove prompt-derived host/port/user/path/acquisition-mode extraction.

### Task 3: Refactor Tool Registration And Tool Signatures

**Files:**
- Modify: `src/dba_assistant/orchestrator/tools.py`
- Modify: `src/dba_assistant/orchestrator/agent.py`
- Modify: `tests/unit/orchestrator/test_tools.py`
- Modify: `tests/unit/orchestrator/test_agent.py`

- [ ] Remove prebuilt Redis/MySQL connection gating from `build_all_tools(...)`.
- [ ] Introduce internal helpers to resolve Redis / SSH / MySQL configs from explicit tool args plus secure request secrets.
- [ ] Update all Redis, remote-RDB, and MySQL tools to accept explicit non-sensitive parameters.
- [ ] Make `ensure_remote_rdb_snapshot` an agent-facing tool.
- [ ] Change `fetch_remote_rdb_via_ssh` into a fetch-only tool that returns a local file path.

### Task 4: Split Remote Acquisition Into Atomic Business Steps

**Files:**
- Modify: `src/dba_assistant/orchestrator/tools.py`
- Modify: `src/dba_assistant/prompts/unified_system_prompt.md`
- Modify: `skills/redis-rdb-analysis/SKILL.md`
- Modify: `tests/integration/test_remote_rdb_discovery_failures.py`

- [ ] Ensure remote SOP is `discover -> ensure snapshot if needed -> fetch -> inspect -> analyze`.
- [ ] Remove composite auto-analysis behavior from the remote fetch tool.
- [ ] Keep approval enforced for snapshot generation and SSH fetch.

### Task 5: Reduce Hidden Python Route Selection In Capability Calls

**Files:**
- Modify: `src/dba_assistant/capabilities/redis_rdb_analysis/path_router.py`
- Modify: `src/dba_assistant/capabilities/redis_rdb_analysis/service.py`
- Modify: relevant unit tests under `tests/unit/capabilities/redis_rdb_analysis/`

- [ ] Stop selecting MySQL-backed analysis from prompt text hints such as `mysql`.
- [ ] Keep route selection based on explicit `path_mode` or input kind only.
- [ ] Leave tool-level path decisions to the agent and SOP, not prompt heuristics in Python.

### Task 6: Final Verification

**Files:**
- Verify only

- [ ] Run targeted suites covering prompt parsing, adapter wiring, orchestrator tools, agent runtime, remote discovery, and E2E CLI flow.
- [ ] Run a broader pytest sweep if the targeted suites pass.
- [ ] Summarize what remains in `application/`, how tool signatures changed, and which runtime approvals now gate sensitive actions.
