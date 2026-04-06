# Phase 5 Observability Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a repository-native observability and audit baseline for unified DBA Assistant execution without binding logging or audit behavior to the CLI surface.

**Architecture:** Add a shared `core/observability` layer for bootstrap, sanitization, execution context, structured app logging, and append-only audit JSONL recording. Attach the baseline at the interface adapter, orchestrator/tool execution, HITL approval flow, and shared report generation path so CLI/API/WebUI can reuse the same boundary.

**Tech Stack:** Python dataclasses, `logging`, `contextvars`, JSONL files, pytest.

---

### Task 1: Lock behavior with tests

**Files:**
- Modify: `tests/unit/deep_agent_integration/test_config.py`
- Modify: `tests/unit/test_cli.py`
- Modify: `tests/unit/interface/test_hitl.py`
- Create: `tests/unit/core/observability/test_observability.py`
- Create: `tests/unit/capabilities/redis_rdb_analysis/collectors/test_streaming_aggregate_collector_observability.py`

- [ ] Add config parsing tests for the new observability section, including repo-root relative path resolution and default behavior when the section is omitted.
- [ ] Add execution audit tests that exercise CLI -> adapter -> orchestrator with a temporary config and assert append-only `audit.jsonl` output includes execution lifecycle fields and sanitized request summaries.
- [ ] Add approval audit tests that assert request/decision events are recorded for both approved and denied outcomes.
- [ ] Add sanitizer tests that prove secrets are redacted from audit records and app logs.
- [ ] Add streaming collector tests that assert performance logs still emit and now flow through structured app logging.

### Task 2: Implement shared observability foundation

**Files:**
- Modify: `src/dba_assistant/deep_agent_integration/config.py`
- Modify: `src/dba_assistant/deep_agent_integration/__init__.py`
- Create: `src/dba_assistant/core/observability/__init__.py`
- Create: `src/dba_assistant/core/observability/bootstrap.py`
- Create: `src/dba_assistant/core/observability/context.py`
- Create: `src/dba_assistant/core/observability/sanitizer.py`
- Create: `src/dba_assistant/core/observability/logging.py`
- Create: `src/dba_assistant/core/observability/audit.py`
- Modify: `src/dba_assistant/core/audit/logger.py`

- [ ] Extend app config with an `ObservabilityConfig` dataclass and resolved path helpers without changing `--config` loading semantics.
- [ ] Implement one-process bootstrap for console logging plus JSONL file logging driven entirely by config paths.
- [ ] Implement shared sanitization helpers for mappings, strings, prompts, approval details, and secret-key fields.
- [ ] Implement execution context tracking with `execution_id`, surface, tool sequence, artifact metadata, and final status.
- [ ] Implement append-only audit JSONL recording with a stable event schema and final execution summary event.

### Task 3: Attach instrumentation to unified execution and approvals

**Files:**
- Modify: `src/dba_assistant/interface/types.py`
- Modify: `src/dba_assistant/interface/hitl.py`
- Modify: `src/dba_assistant/interface/adapter.py`
- Modify: `src/dba_assistant/orchestrator/agent.py`
- Modify: `src/dba_assistant/orchestrator/tools.py`
- Modify: `src/dba_assistant/core/reporter/generate_analysis_report.py`

- [ ] Add explicit interface surface typing and execution bootstrap at the shared adapter boundary.
- [ ] Wrap approval handlers so approval requests and outcomes become first-class audit events and printed CLI details are sanitized.
- [ ] Wrap tool callables in the orchestrator tool builder so invocation order, sanitized arguments, duration, and status are recorded once in shared infrastructure.
- [ ] Record denial/failure/success/interruption status transitions in unified execution rather than only in the CLI.
- [ ] Record artifact/output metadata in the shared report generation path.

### Task 4: Wire existing performance logs into the baseline and document the result

**Files:**
- Modify: `src/dba_assistant/capabilities/redis_rdb_analysis/collectors/streaming_aggregate_collector.py`
- Modify: `config/config.yaml`
- Modify: `docs/phase-3-cli-usage.md`
- Create: `docs/phase-5-observability-baseline.md`

- [ ] Convert streaming collector performance logs to structured, sanitized logging while preserving rows/elapsed/throughput signals.
- [ ] Document the new config fields with comments in `config/config.yaml`.
- [ ] Add repository docs showing the audit/app JSONL layout and sample records.
- [ ] Run focused pytest coverage for config, interface, CLI, observability, and streaming collector behavior, then run a broader regression slice if the focused suite passes.
