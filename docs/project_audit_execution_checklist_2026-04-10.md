# Project Audit Execution Checklist

> Date: 2026-04-10
> Companion to: `docs/project_audit_preview_2026-04-10.md`
> Purpose: convert the preview audit into a current-state execution checklist aligned with the repository's stricter Harness Engineering direction.

---

## 1. How to Read This Checklist

The preview audit is directionally useful, but parts of it describe an older intermediate state of the codebase.

This checklist therefore splits findings into four buckets:

- `Execute now`: valid findings that still match the current code.
- `Execute after verification`: plausible cleanup items that need one more import or consumer check.
- `Reword, then decide`: the core concern is valid, but the preview wording is too strong or now partially stale.
- `Do not execute as written`: the preview item no longer reflects the current architecture and should not be used as-is.

---

## 2. Execute Now

### 2.1 Split `orchestrator/tools.py`

**Status**

- Started with low-risk extractions for shared helpers, report output rendering, read-only Redis inspection tools, and the config collection tool.
- Full extraction of RDB, remote-RDB, and MySQL staging builders remains a follow-up because those sections share many test-patched dependencies and should be moved in smaller behavior-preserving steps.

**Why this still stands**

- `src/dba_assistant/orchestrator/tools.py` remains the largest and most mixed-responsibility production module.
- It now contains agent-facing tool definitions plus remote acquisition orchestration, MySQL staging helpers, report rendering entry points, approval hooks, and runtime adapter glue.

**Execution target**

- Split by business area while keeping the existing external runtime shape:
  - `src/dba_assistant/orchestrator/tools/rdb_tools.py`
  - `src/dba_assistant/orchestrator/tools/remote_tools.py`
  - `src/dba_assistant/orchestrator/tools/mysql_tools.py`
  - `src/dba_assistant/orchestrator/tools/report_tools.py`
  - `src/dba_assistant/orchestrator/tools/inspection_tools.py`
  - `src/dba_assistant/orchestrator/tools/registry.py`

**Guardrail**

- Do not turn this into a large refactor of business behavior.
- Preserve the current Harness shape: one agent, atomic business tools, explicit non-sensitive tool parameters, secrets in secure context.

### 2.2 Fix reporter dependency direction

**Why this still stands**

- Shared reporter code still depends on capability-local localization logic.
- This violates the repository's layering rule that shared infrastructure should not depend upward on a specific capability package.

**Execution target**

- Move `normalize_report_language()` into a shared reporter-local module such as:
  - `src/dba_assistant/core/reporter/localization.py`
- Update `docx_reporter.py` and any callers to import from the shared reporter layer.

### 2.3 Wire `_build_mysql_staging_interrupt_description()` for real

**Why this still stands**

- The function exists in `src/dba_assistant/orchestrator/agent.py`.
- It should be registered in the active `interrupt_on` mapping for `stage_local_rdb_to_mysql`.

**Execution target**

- Move MySQL staging approval to `interrupt_on` and use the function.
- Preserve the large-file fallback contract: rejecting MySQL staging rejects that route, not the entire analysis request.

**Recommendation**

- Prefer unified `interrupt_on` approval for high-risk remote and MySQL staging actions.

---

## 3. Execute After Verification

### 3.1 Delete obvious scaffold-only files if they truly have zero consumers

**Status**

- Completed after repository-wide consumer checks.

**Candidates**

- `src/dba_assistant/adaptors/filesystem_adaptor.py`
- `src/dba_assistant/capabilities/redis_rdb_analysis/analyzer.py`

**Why this is not auto-delete yet**

- The preview is probably right, but deletion should follow one more repository-wide consumer check and packaging sanity check.

**Execution target**

- Confirm zero imports and zero packaging/runtime references.
- Delete the files and update any package `__init__` exports if needed.

### 3.2 Revisit low-value wrapper exports

**Status**

- Completed for the zero-consumer compatibility wrappers identified in the preview.

**Candidates**

- `src/dba_assistant/core/audit/logger.py`
- `src/dba_assistant/tools/generate_analysis_report.py`

**Important nuance**

- These are likely low-value compatibility wrappers, not necessarily "dead code" in the strongest sense.
- If removed, the cleanup must include:
  - package export updates
  - test updates
  - any downstream imports in docs or examples

**Execution target**

- Treat these as compatibility cleanup, not just dead-code deletion.

---

## 4. Reword, Then Decide

### 4.1 MySQL staging approval

**Preview wording to avoid**

- "MySQL staging writes currently bypass approval."

**Current accurate wording**

- MySQL staging approval should be enforced through `interrupt_on`; rejecting the tool means fallback to direct streaming analysis rather than aborting the whole request.

**Decision needed**

- Keep the fallback semantics documented in the skill and system prompt.
- Keep lower-level write helpers protected when they are called directly outside the high-level staging tool.

### 4.2 `application/` responsibility

**Preview wording to avoid**

- Any wording that still implies `application/` is performing broad prompt-derived connection extraction or business inference.

**Current accurate wording**

- `application/` is now primarily a shared boundary for request models, explicit surface inputs, secret extraction, and prompt scrubbing.
- It should not be treated as a business understanding layer.

### 4.3 Remote acquisition chain

**Preview wording to avoid**

- Any wording that implies remote acquisition still relies on one oversized composite fetch-and-analyze tool.

**Current accurate wording**

- The remote RDB path is now split into atomic business steps:
  - `discover_remote_rdb(...)`
  - `ensure_remote_rdb_snapshot(...)`
  - `fetch_remote_rdb_via_ssh(...)`
- Analysis happens afterward through the normal local-RDB analysis path.

---

## 5. Do Not Execute As Written

### 5.1 Do not re-expand prompt parsing to recover old "hard fact extraction"

The stricter Harness direction now intentionally avoids restoring broad prompt-level parsing of connection semantics from free text.

Do not implement any follow-up task that:

- reintroduces prompt-based SSH/Redis/MySQL host and user extraction from arbitrary prose
- reintroduces prompt-based business routing or profile inference in `application/`
- makes Python the primary interpreter of user intent again

If a future change needs more information, prefer:

- explicit tool parameters selected by the LLM
- secure secret collection through boundary or approval flows
- clearer skill/system-prompt guidance

### 5.2 Do not treat the preview as the source of truth for current architecture

The preview remains useful as a heuristic input, but the source of truth is now:

- current production code under `src/dba_assistant/`
- current root `skills/`
- current architecture docs and handover docs

---

## 6. Recommended Execution Order

1. Split `src/dba_assistant/orchestrator/tools.py` into smaller business-area modules.
2. Move report language normalization into `src/dba_assistant/core/reporter/`.
3. Wire `_build_mysql_staging_interrupt_description()` into `interrupt_on` and document the chosen approval model.
4. Verify candidate dead files and wrapper exports, then delete only the ones that remain truly unused.
5. Run full tests and update architecture docs if any boundary wording changes during the cleanup.

---

## 7. Success Criteria

This checklist is complete when:

- no current architecture doc misstates the role of `application/`
- no preview-derived cleanup item would accidentally reintroduce prompt-heavy Python interpretation
- `orchestrator/tools.py` is no longer a single god module
- shared reporter code no longer imports capability-local code
- approval behavior for MySQL staging is either unified or explicitly documented
- dead-code cleanup is done with verified zero-consumer evidence, not assumption
