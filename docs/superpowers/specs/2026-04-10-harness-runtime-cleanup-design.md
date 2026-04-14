# Harness Runtime Cleanup Design

## Scope

This design tightens DBA Assistant toward a stricter Harness Engineering shape without expanding product scope.

The cleanup targets five concrete problems:

1. The unified agent system prompt is hardcoded in Python.
2. `application/prompt_parser.py` performs broad natural-language business inference that should belong to the LLM.
3. DOCX intent is treated as best-effort model behavior instead of a runtime-enforced artifact contract.
4. `src/dba_assistant/skills/` still contains Python business implementation code and capability code depends on it.
5. Legacy `phase2` runtime entry points remain in production code and documentation.

## Goal

Preserve the repository-wide execution shape:

`CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

while making the boundaries stricter:

- `application/` keeps shared request contracts and security-oriented extraction only
- `skills/` becomes agent-facing document content only
- `capabilities/` becomes the home of domain logic
- runtime, not the model, becomes the final authority on artifact fulfillment

## Boundary Decisions

### 1. System Prompt Handling

The system prompt should remain a runtime concern, but the prompt content should be externalized from Python source.

The code will load the unified agent prompt from a repository-owned prompt file under production code or repository docs/prompts. Python remains responsible for:

- loading the prompt text
- passing it into `create_deep_agent(...)`
- failing fast if the prompt file is missing

This keeps runtime assembly explicit without forcing prompt edits to require Python source changes.

### 2. What `application/` Keeps

`application/` stays, but only as a thin contract and sanitization layer.

Allowed responsibilities:

- shared request dataclasses
- CLI/API/Web explicit override merging
- secret extraction and prompt scrubbing
- deterministic extraction of hard facts when they are syntactically explicit
  - file paths
  - host:port
  - password tokens

Disallowed responsibilities:

- broad natural-language intent inference
- business routing
- profile selection from prose
- report mode selection from prose
- path-mode selection from prose
- analysis strategy decisions

### 3. DOCX Fulfillment Rule

DOCX intent recognition should primarily come from the LLM through the system prompt and `skills/redis-rdb-analysis/SKILL.md`.

However, fulfillment cannot be left to model compliance alone.

The runtime contract becomes:

- if the agent selects DOCX output for a turn, the final result returned to the interface must be a real `.docx` artifact path
- if the agent replies with plain text or a non-existent path after choosing DOCX, the turn fails with a clear policy error

This is not prompt parsing. It is output validation.

### 4. Skill / Capability Separation

Python implementation under `src/dba_assistant/skills/` must be removed from the production dependency graph.

`skills/` at the repository root continues to hold `SKILL.md` documents for Deep Agents.

`src/dba_assistant/capabilities/redis_rdb_analysis/` becomes the authoritative home for:

- analysis service
- path routing
- profile resolution
- collectors
- report assembly

No production module may import business logic from `src/dba_assistant/skills/`.

### 5. Phase Legacy Cleanup

The standalone `phase2` runtime entry points are legacy validation leftovers and conflict with the unified-agent direction.

The production package should converge on one entry path:

- interface adapter
- unified orchestrator
- one Deep Agent

Legacy phase-named entry points should be deleted or moved out of the production path.

## Execution Strategy

The cleanup should proceed in this order:

1. Lock current target behavior with tests.
2. Externalize prompt loading and update skill wording.
3. Add runtime artifact validation for DOCX turns.
4. Shrink `application/prompt_parser.py` to contract-safe extraction only.
5. Move remaining capability logic ownership fully under `capabilities/`.
6. Remove `phase2` runtime entry points and update tests/docs.

## Acceptance Criteria

The cleanup is complete when all of the following are true:

- unified agent prompt text is loaded from a file, not hardcoded in Python
- `application/` no longer performs broad natural-language business inference
- password and explicit hard-fact extraction still work
- `skills/redis-rdb-analysis/SKILL.md` explicitly states DOCX artifact behavior
- runtime rejects DOCX turns that do not produce a real `.docx` artifact
- no production capability imports Python business logic from `src/dba_assistant/skills/`
- legacy `phase2` production entry points are removed from the active production path
- affected tests pass and are aligned with the new architecture
