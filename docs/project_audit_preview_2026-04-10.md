# DBA Assistant Project Audit Preview

> Audit Date: 2026-04-10
> Scope: Dead code, harness engineering compliance, optimization recommendations
> Codebase: ~10,776 lines production Python / ~8,136 lines test code

---

## 1. Dead Code & Unused Module Inventory

### 1.1 Empty Scaffold Files (No Functional Code)

| File | Content | Verdict |
|------|---------|---------|
| `src/dba_assistant/adaptors/filesystem_adaptor.py` | Single docstring `"""Filesystem adaptor scaffold."""` | **Dead code** -- not imported anywhere. Either implement or delete. |
| `src/dba_assistant/capabilities/redis_rdb_analysis/analyzer.py` | Single docstring `"""Analyzer scaffold..."""` | **Dead code** -- all analysis logic lives in `analyzers/` subpackage. This top-level `analyzer.py` is never imported. Remove it. |
| `src/dba_assistant/capabilities/redis_inspection_report/analyzer.py` | Single docstring | **Scaffold placeholder** -- acceptable as Phase 4 marker, but no code depends on it. |
| `src/dba_assistant/capabilities/redis_cve_report/analyzer.py` | Single docstring | **Scaffold placeholder** -- acceptable as Phase 6 marker. |

### 1.2 Unused Functions

| Location | Function | Issue |
|----------|----------|-------|
| `orchestrator/agent.py:464` | `_build_mysql_staging_interrupt_description()` | **Defined but never called.** Not registered in `interrupt_on` dict at line 72-81. Was likely intended for MySQL staging approval gates but was not wired in. |

### 1.3 Re-export-Only Wrappers with Zero Consumers

| File | Content | Issue |
|------|---------|-------|
| `core/audit/logger.py` | Re-exports `AuditRecorder` and `get_audit_recorder` from `core.observability` | **Zero imports** found from anywhere in the codebase. This wrapper adds no value -- all callers import from `core.observability` directly. Can be removed along with the `core/audit/` directory. |
| `tools/generate_analysis_report.py` | Re-exports `generate_analysis_report` from `core.reporter` | Only imported by `tools/__init__.py`. No external consumer imports from `tools/__init__`. The `orchestrator/tools.py` imports `generate_analysis_report` directly from `core.reporter`. This is a dead re-export chain. |

### 1.4 Placeholder Reporters (Intentional)

| File | Status |
|------|--------|
| `core/reporter/html_reporter.py` | `raise NotImplementedError` -- Phase 1 placeholder |
| `core/reporter/pdf_reporter.py` | `raise NotImplementedError` -- Phase 1 placeholder |

These are registered in `core/reporter/__init__.py` via lazy imports. They are intentional interface stubs per the master plan, not dead code. However, they've remained unchanged since Phase 1 while the project is now in Phase 3 -- worth tracking.

### 1.5 Empty `skills/` Directory Under `src/dba_assistant/`

The master plan defines `skills/` at repository root for SKILL.md documents (which correctly exist at `/skills/redis-rdb-analysis/SKILL.md` etc.). A separate `src/dba_assistant/skills/` directory was apparently planned but contains **zero files** (the glob returns nothing). This empty package tree should be removed to avoid confusion with the root-level `skills/` directory.

---

## 2. Deep Agents SDK Harness Engineering Assessment

### 2.1 SDK Integration Pattern

The project uses Deep Agents SDK through `deep_agent_integration/`:

```
deep_agent_integration/
  config.py        -- AppConfig, ModelConfig, RuntimeConfig, ObservabilityConfig
  model_provider.py -- build_model() via ChatOpenAI (LangChain)
  runtime_support.py -- FilesystemBackend, InMemorySaver, memory/skill sources
```

**Assessment: Compliant with harness pattern.**

- `create_deep_agent()` is called correctly with model, tools, backend, checkpointer, skills, memory, interrupt_on, system_prompt.
- The agent is stateful with `InMemorySaver` checkpointer.
- `FilesystemBackend(virtual_mode=True)` properly provides filesystem access.
- Memory sources correctly point to `AGENTS.md`.
- Skill sources correctly point to `/skills`.

### 2.2 Execution Shape Compliance

Master plan mandates: `CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

**Actual flow:**

```
cli.py (thin CLI)
  -> interface/adapter.py (handle_request)
    -> application/prompt_parser.py (normalize_raw_request)
    -> orchestrator/agent.py (run_orchestrated)
      -> create_deep_agent() with all tools
        -> LLM selects tools based on prompt intent
```

**Assessment: Fully compliant.**

- CLI is thin (197 lines), no business routing.
- Interface adapter handles normalization, config loading, observability bootstrap.
- Single unified agent with all tools -- LLM-driven capability selection.
- No parallel runtimes or surface-specific routers.

### 2.3 HITL / Approval Integration

- `interrupt_on` is properly configured for `ensure_remote_rdb_snapshot` and `fetch_remote_rdb_via_ssh`.
- `_should_force_runtime_approval()` catches LLM-level plain-text approval attempts and forces proper tool-based approval.
- `AuditedApprovalHandler` wraps approvals with audit logging.

**Assessment: Well-implemented.** One gap: `_build_mysql_staging_interrupt_description` exists but is not wired into the interrupt chain, meaning MySQL staging writes currently bypass approval. If MySQL write approval was intended for the current phase, this is a bug; if deferred, it should be documented.

### 2.4 Tool Registration

`orchestrator/tools.py` (~1750 lines) is the largest file in the codebase. All tools are registered through `build_all_tools()` and wrapped with `_instrument_tool()` for observability.

**Tool categories:**
- Local RDB inspection & analysis (inspect, analyze_stream, analyze_staged)
- MySQL staging (stage, create_database, create_table, insert, load_dataset, read_query)
- Remote Redis (discover, ensure_snapshot, fetch_via_ssh)
- Redis inspection probes (ping, info, config_get, slowlog, client_list)
- Report generation (generate_analysis_report)
- Config collection (ask_user_for_config)

**Assessment: Functionally complete for Phase 3.** However, this file is a "god module" -- see optimization recommendations.

### 2.5 Observability

- Execution session tracking via context vars (`ExecutionSession`).
- JSONL audit log with sanitization.
- Tool invocation sequence recording.
- Artifact registration for generated files.
- Secret redaction at multiple layers (prompt parser, sanitizer, audit).

**Assessment: Comprehensive and well-layered.**

---

## 3. Architecture Constraints Compliance

Checking against `docs/dba_assistant_architecture_constraints_addendum_v1.md`:

| Constraint | Status | Notes |
|------------|--------|-------|
| `skills/` contains skill docs only | **Pass** | Root `skills/` has only SKILL.md files |
| Business code under `capabilities/` | **Pass** | All domain logic in `capabilities/redis_rdb_analysis/` |
| Tools call capabilities, not skills | **Pass** | `tools/analyze_rdb.py` imports from `capabilities.redis_rdb_analysis.service` |
| Shared adaptors not rebuilt per capability | **Pass** | Single `adaptors/` package shared across all capabilities |
| Profiles in capability layer | **Pass** | `capabilities/redis_rdb_analysis/profiles/*.yaml` |
| CLI thin and prompt-first | **Pass** | `cli.py` is 197 lines, no routing |
| No reference layer imports | **Pass** | No imports from `claude-code-source-code` or `src/docs` |

**One minor violation:** `core/reporter/docx_reporter.py` imports from `capabilities/redis_rdb_analysis/reports/localization.py` (line 11). The shared reporter layer should not depend on a specific capability's module. The `normalize_report_language()` function should be elevated to the shared reporter layer.

---

## 4. Optimization Recommendations

### 4.1 HIGH PRIORITY -- Structural

#### H1: Split `orchestrator/tools.py` (~1750 lines)

This file is a "god module" containing every tool definition, helper, and MySQL/Redis/SSH interaction logic. It violates the architecture's own principle that "tools should not become the main home of large business logic."

**Recommendation:** Split into:
- `orchestrator/tools/rdb_tools.py` -- local RDB analysis tools
- `orchestrator/tools/mysql_tools.py` -- MySQL staging tools
- `orchestrator/tools/remote_tools.py` -- remote Redis/SSH tools
- `orchestrator/tools/redis_inspection_tools.py` -- Redis probe tools
- `orchestrator/tools/report_tools.py` -- report generation tools
- `orchestrator/tools/registry.py` -- `build_all_tools()` assembles from above

#### H2: Remove `core/reporter/docx_reporter.py` dependency on capability layer

`docx_reporter.py:11` imports `capabilities.redis_rdb_analysis.reports.localization.normalize_report_language`. This creates an upward dependency from shared infrastructure to a specific capability. Move `normalize_report_language()` to `core/reporter/localization.py`.

#### H3: Wire or document MySQL staging approval

`_build_mysql_staging_interrupt_description()` is defined but not registered in `interrupt_on`. Either:
- Wire it into the approval chain if MySQL write approval is required
- Remove it and document that MySQL staging is auto-approved in Phase 3
- Add a TODO with phase reference

### 4.2 MEDIUM PRIORITY -- Clean Up

#### M1: Remove dead code

- Delete `src/dba_assistant/adaptors/filesystem_adaptor.py`
- Delete `src/dba_assistant/capabilities/redis_rdb_analysis/analyzer.py`
- Delete `src/dba_assistant/core/audit/logger.py` and `core/audit/__init__.py`
- Delete `src/dba_assistant/tools/generate_analysis_report.py` (the re-export wrapper)
- Clean up `tools/__init__.py` to remove the dead import
- Remove `src/dba_assistant/skills/` empty directory tree (if it exists as empty dirs)

#### M2: Address `_build_all_tools_compatible()` defensive wrapper

`orchestrator/agent.py:161-174` has a `try/except TypeError` wrapper that silently drops `approval_handler` and `config` kwargs if `build_all_tools()` doesn't accept them. This suggests an API instability concern that should be resolved, not worked around.

#### M3: Reduce `setattr` hack on agent object

`orchestrator/agent.py:94-96` uses `setattr(agent, "_dba_remote_rdb_state", remote_rdb_state)` to carry state through the agent. This is fragile. Consider passing state through the tool runtime context instead.

### 4.3 LOW PRIORITY -- Quality

#### L1: Standardize error handling patterns

Tools in `orchestrator/tools.py` have inconsistent error handling:
- Some return `f"Error: {exc}"`
- Some catch `ValueError`, others catch `Exception`
- Some log errors, others don't

Consider a shared `_tool_error_response()` helper.

#### L2: Test coverage assessment

Test directory has 8,136 lines, but many test files may be scaffolds. Actual runtime coverage should be verified with `pytest --cov`.

#### L3: PDF/HTML reporters still at Phase 1 stub

The project is in Phase 3 but PDF and HTML reporters remain `NotImplementedError`. The master plan says "Implement PDF Reporter and HTML Reporter if complexity is manageable; otherwise defer them" for Phase 2. Should be explicitly tracked if still deferred.

---

## 5. Summary Scorecard

| Dimension | Score | Comment |
|-----------|-------|---------|
| Dead code | 7/10 | Small amount -- a few scaffolds, one unused function, two dead re-export wrappers |
| Harness engineering compliance | 9/10 | Proper Deep Agents SDK usage, correct execution shape, good HITL integration |
| Architecture constraint compliance | 8/10 | One shared->capability upward dependency, otherwise clean layering |
| Code organization | 6/10 | `orchestrator/tools.py` is too large; needs splitting |
| Observability | 9/10 | Comprehensive execution tracking, audit logging, secret redaction |
| Extensibility | 8/10 | Clean collector/reporter abstractions; capability pattern is replicable |
| Test coverage | 5/10 | Tests exist but coverage depth is unclear; needs `pytest --cov` verification |

**Overall: The project is well-architected and correctly follows the Deep Agents SDK harness pattern. The main areas for improvement are splitting the oversized tools module, cleaning up ~6 dead code files/functions, and fixing one dependency direction violation.**

---

## Appendix: File Size Rankings (Production Code)

| File | Lines (approx) |
|------|----------------|
| `orchestrator/tools.py` | ~1750 |
| `orchestrator/agent.py` | ~515 |
| `adaptors/mysql_adaptor.py` | ~340 |
| `application/prompt_parser.py` | ~235 |
| `core/reporter/docx_reporter.py` | ~246 |
| `core/reporter/docx_styles.py` | ~230+ |
| `adaptors/redis_adaptor.py` | ~229 |
| `interface/adapter.py` | ~207 |
| `cli.py` | ~197 |
| `tools/mysql_tools.py` | ~150+ |
| `parsers/rdb_parser_strategy.py` | ~150+ |
