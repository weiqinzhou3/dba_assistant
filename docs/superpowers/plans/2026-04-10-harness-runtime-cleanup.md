# Harness Runtime Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten DBA Assistant to a stricter Harness Engineering architecture by externalizing the unified prompt, shrinking `application/` to contract-safe normalization, enforcing DOCX artifact fulfillment at runtime, removing skill-layer Python business dependencies, and deleting legacy phase runtime entry points.

**Architecture:** Keep one unified Deep Agent execution path and let the LLM own natural-language business understanding. Preserve only explicit-override handling, hard-fact extraction, and secret scrubbing before agent execution. Move all domain logic ownership under `capabilities/` and make runtime validation enforce artifact completion.

**Tech Stack:** Python, pytest, Deep Agents SDK, LangGraph, python-docx

---

### Task 1: Lock Prompt Loading And DOCX Runtime Contract With Tests

**Files:**
- Modify: `tests/unit/orchestrator/test_agent.py`
- Modify: `tests/e2e/test_phase_3_rdb_analysis.py`
- Modify: `tests/unit/orchestrator/test_tools.py`

- [ ] **Step 1: Write failing tests for prompt loading and DOCX contract**

Add tests that assert:

```python
def test_build_unified_agent_loads_system_prompt_from_file(monkeypatch, tmp_path):
    ...

def test_run_orchestrated_rejects_docx_turn_when_final_output_is_plain_text(monkeypatch):
    ...
```

- [ ] **Step 2: Run targeted tests to verify they fail**

Run: `pytest -q tests/unit/orchestrator/test_agent.py tests/unit/orchestrator/test_tools.py tests/e2e/test_phase_3_rdb_analysis.py`
Expected: FAIL because prompt is still hardcoded and DOCX runtime enforcement does not exist.

- [ ] **Step 3: Update old test expectations to the new architecture**

Replace legacy expectations for:

- `analyze_local_rdb`
- explicit local-path bypass behavior
- fragile fake config objects missing runtime defaults

with expectations aligned to:

- `analyze_local_rdb_stream`
- unified-agent invocation
- full runtime config shape

- [ ] **Step 4: Re-run targeted tests and confirm only intended failures remain**

Run: `pytest -q tests/unit/orchestrator/test_agent.py tests/unit/orchestrator/test_tools.py tests/e2e/test_phase_3_rdb_analysis.py`
Expected: FAIL only on prompt externalization and DOCX enforcement gaps.

### Task 2: Externalize Unified Agent Prompt

**Files:**
- Create: `src/dba_assistant/prompts/unified_system_prompt.md`
- Modify: `src/dba_assistant/orchestrator/agent.py`
- Test: `tests/unit/orchestrator/test_agent.py`

- [ ] **Step 1: Write the failing test for file-backed prompt loading**

Add a test that patches the prompt loader path and asserts `create_deep_agent` receives loaded file text instead of an inline constant.

- [ ] **Step 2: Run the prompt-loading test to verify it fails**

Run: `pytest -q tests/unit/orchestrator/test_agent.py -k prompt`
Expected: FAIL because `agent.py` still uses inline `SYSTEM_PROMPT`.

- [ ] **Step 3: Implement file-backed prompt loading**

Create `src/dba_assistant/prompts/unified_system_prompt.md` and replace the inline constant in `src/dba_assistant/orchestrator/agent.py` with a helper that reads the prompt file and caches or returns the text.

- [ ] **Step 4: Run the prompt-loading tests**

Run: `pytest -q tests/unit/orchestrator/test_agent.py -k prompt`
Expected: PASS

### Task 3: Move DOCX Intent Rule Into Skill And Enforce Artifact Fulfillment At Runtime

**Files:**
- Modify: `skills/redis-rdb-analysis/SKILL.md`
- Modify: `src/dba_assistant/orchestrator/agent.py`
- Test: `tests/unit/orchestrator/test_agent.py`

- [ ] **Step 1: Write failing tests for DOCX artifact fulfillment**

Add tests that assert:

```python
def test_run_orchestrated_accepts_existing_docx_artifact_path(monkeypatch, tmp_path):
    ...

def test_run_orchestrated_rejects_missing_docx_artifact(monkeypatch):
    ...
```

- [ ] **Step 2: Run DOCX fulfillment tests to verify they fail**

Run: `pytest -q tests/unit/orchestrator/test_agent.py -k docx`
Expected: FAIL because `run_orchestrated()` currently returns any assistant text.

- [ ] **Step 3: Update skill and runtime validation**

Change `skills/redis-rdb-analysis/SKILL.md` to state:

- DOCX/Word requests must end in a real DOCX artifact path
- plain-text summaries do not satisfy a DOCX request

Then implement a runtime validator in `src/dba_assistant/orchestrator/agent.py` that:

- inspects whether the request requires DOCX output
- verifies the final result is a `.docx` path
- verifies the file exists
- returns a clear policy error if validation fails

- [ ] **Step 4: Run the DOCX contract tests**

Run: `pytest -q tests/unit/orchestrator/test_agent.py -k docx`
Expected: PASS

### Task 4: Shrink `application/` To Contracts, Hard Facts, And Secrets Only

**Files:**
- Modify: `src/dba_assistant/application/prompt_parser.py`
- Modify: `src/dba_assistant/interface/adapter.py`
- Modify: `src/dba_assistant/application/README.md`
- Test: `tests/unit/application/test_prompt_parser.py`
- Test: `tests/e2e/test_phase_3_rdb_analysis.py`

- [ ] **Step 1: Write failing tests for retained extraction behavior**

Keep tests for:

- password extraction
- explicit path extraction
- explicit host/port extraction

Add or update tests that assert prose-only business hints no longer become structured routing decisions.

- [ ] **Step 2: Run prompt-parser tests to verify current overreach**

Run: `pytest -q tests/unit/application/test_prompt_parser.py`
Expected: FAIL after new assertions because parser still extracts business intent from prose.

- [ ] **Step 3: Remove broad business inference from `prompt_parser.py`**

Refactor so the parser keeps:

- password extraction
- file path extraction
- explicit host/port extraction
- prompt scrubbing

and drops or narrows:

- DOCX/report natural-language inference
- profile inference from prose
- path-mode inference from prose
- broad MySQL route intent inference

Also make adapter runtime-default injection robust when fake config objects omit optional fields.

- [ ] **Step 4: Re-run parser and CLI boundary tests**

Run: `pytest -q tests/unit/application/test_prompt_parser.py tests/e2e/test_phase_3_rdb_analysis.py`
Expected: PASS

### Task 5: Remove Python Business Logic Dependency On `src/dba_assistant/skills/`

**Files:**
- Modify: `src/dba_assistant/capabilities/redis_rdb_analysis/service.py`
- Modify: `src/dba_assistant/capabilities/redis_rdb_analysis/__init__.py`
- Delete or stop importing: `src/dba_assistant/skills/redis_rdb_analysis/*.py` from production paths
- Test: `tests/unit/capabilities/redis_rdb_analysis/test_rdb_analysis_service.py`
- Test: `tests/unit/tools/test_analyze_rdb.py`

- [ ] **Step 1: Write a failing test that capability code no longer imports skill-layer Python**

Add a test that imports the capability service and asserts it resolves without reaching into `dba_assistant.skills.redis_rdb_analysis`.

- [ ] **Step 2: Run the capability tests to verify the current dependency exists**

Run: `pytest -q tests/unit/capabilities/redis_rdb_analysis/test_rdb_analysis_service.py tests/unit/tools/test_analyze_rdb.py`
Expected: FAIL after the new assertion because capability service still delegates to `src/dba_assistant/skills/...`.

- [ ] **Step 3: Move authoritative service implementation fully under `capabilities/`**

Copy only repository-owned production logic into `src/dba_assistant/capabilities/redis_rdb_analysis/service.py`, update imports to capability-local modules, and remove production dependencies on `src/dba_assistant/skills/redis_rdb_analysis/*.py`.

- [ ] **Step 4: Run capability and tool tests**

Run: `pytest -q tests/unit/capabilities/redis_rdb_analysis/test_rdb_analysis_service.py tests/unit/tools/test_analyze_rdb.py`
Expected: PASS

### Task 6: Remove Legacy `phase2` Runtime Entry Points

**Files:**
- Modify or delete: `src/dba_assistant/deep_agent_integration/agent_factory.py`
- Modify or delete: `src/dba_assistant/deep_agent_integration/run.py`
- Modify: `src/dba_assistant/deep_agent_integration/__init__.py`
- Modify: `src/dba_assistant/README.md`
- Test: `tests/unit/deep_agent_integration/test_agent_factory.py`
- Test: `tests/unit/deep_agent_integration/test_run.py`

- [ ] **Step 1: Write failing tests for the desired legacy cleanup shape**

Add tests that assert the production path no longer exposes standalone `phase2` execution helpers.

- [ ] **Step 2: Run deep-agent-integration tests to verify legacy exposure remains**

Run: `pytest -q tests/unit/deep_agent_integration/test_agent_factory.py tests/unit/deep_agent_integration/test_run.py`
Expected: FAIL because `build_phase2_agent` and `run_phase2` still exist.

- [ ] **Step 3: Remove or demote legacy runtime entry points**

Delete or refactor the standalone `phase2` helpers out of the production package exports and update package docs accordingly.

- [ ] **Step 4: Run the deep-agent-integration tests**

Run: `pytest -q tests/unit/deep_agent_integration/test_agent_factory.py tests/unit/deep_agent_integration/test_run.py`
Expected: PASS

### Task 7: Final Verification

**Files:**
- Verify only

- [ ] **Step 1: Run the targeted cleanup suite**

Run: `pytest -q tests/unit/orchestrator/test_agent.py tests/unit/orchestrator/test_tools.py tests/unit/application/test_prompt_parser.py tests/e2e/test_phase_3_rdb_analysis.py tests/unit/capabilities/redis_rdb_analysis/test_rdb_analysis_service.py tests/unit/tools/test_analyze_rdb.py tests/unit/deep_agent_integration/test_agent_factory.py tests/unit/deep_agent_integration/test_run.py`
Expected: PASS

- [ ] **Step 2: Run a broader repository confidence sweep**

Run: `pytest -q`
Expected: PASS, or a documented list of unrelated pre-existing failures.

- [ ] **Step 3: Summarize changed architecture boundaries**

Document in the final handoff:

- what remains in `application/`
- what moved out
- where the unified prompt now lives
- how DOCX fulfillment is enforced
- what legacy `phase2` code was removed
