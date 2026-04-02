# Phase 2 CLI and Config Correction Design

## Background

Phase 2 delivered the repository-owned Deep Agent SDK assembly layer, provider-capable model configuration, a bounded read-only Redis direct path, and a minimal validation agent.

That foundation is usable for internal wiring validation, but it still has two product-shape defects:

1. Configuration is loader-centric rather than user-centric.
   - The current design makes `config.py` the effective user-facing configuration surface.
   - Model and runtime defaults are loaded from environment variables rather than from a repository-owned configuration file.
   - This makes local validation awkward and hides the supported configuration surface from users.

2. The repository lacks a real prompt-first entry point.
   - `run.py` currently provides only a thin smoke entry.
   - There is no formal CLI shell for a user to type a prompt and have DBA Assistant execute against the Phase 2 runtime.

The correction in this document keeps the project agent-shaped. It does not turn DBA Assistant into a parameter-driven tool. The CLI remains only a thin debug shell, and future GUI/API surfaces must share the same application contract.

## Goals

1. Replace environment-variable-first configuration with repository-owned `config.yaml`.
2. Add a thin prompt-first CLI suitable for local debugging.
3. Allow users to place secrets such as Redis passwords in the raw prompt input while preventing those secrets from remaining ordinary model prompt text after preprocessing.
4. Introduce a normalized internal request contract that future GUI and API entry points can reuse.
5. Keep the correction strictly within Phase 2 scope. No new business-skill implementation is added.

## Non-Goals

- This correction does not make CLI the final product surface.
- This correction does not add GUI implementation.
- This correction does not add HTTP API implementation.
- This correction does not add new Redis analysis or inspection business logic.
- This correction does not expand SSH or MySQL live implementations.

## User-Facing Shape

The intended Phase 2 user shape is:

```bash
dba-assistant ask "Use password abc123 to inspect Redis 10.0.0.8:6379 and give me a summary"
```

The user experience stays prompt-first.

The CLI is only a thin shell that:

1. loads static configuration from `config.yaml`
2. parses the raw request text
3. extracts dynamic target information and secrets
4. builds a normalized application request
5. calls the repository-owned application layer
6. prints the result

The CLI is not the long-term architectural center. It is a temporary debug surface that must remain compatible with future GUI and API entry points.

## Static vs Dynamic Inputs

### Static Configuration: `config.yaml`

`config.yaml` becomes the user-editable configuration surface for stable defaults and application wiring. It should contain:

- provider preset
- model name
- base URL
- API key
- tracing flag
- max turns
- temperature
- default socket timeout
- output defaults
- path defaults for templates, logs, or reports where relevant

It should not contain:

- Redis host
- Redis port
- Redis DB
- Redis password
- per-request file paths
- per-request task targets

These are request-scoped inputs, not application-scoped defaults.

### Dynamic Runtime Inputs

Dynamic inputs belong to the normalized request object, not static configuration. This includes:

- Redis target host and port
- Redis DB
- requested output mode
- report/input file paths for later phases

### Secrets

Users may place secrets in the raw prompt text if that is the desired UX.

However, the system must not continue to treat those secrets as ordinary prompt text after preprocessing.

The system should:

1. accept the raw prompt text
2. parse out secret-like fields needed for runtime execution
3. move them into a dedicated `secrets` section of the normalized request
4. send only the cleaned intent prompt to the agent/model layer

This keeps the UX prompt-first while preserving clean boundaries for future audit, GUI, and API work.

## Normalized Request Contract

Phase 2 should add one repository-owned request contract for all entry points.

Recommended shape:

```python
NormalizedRequest(
    prompt: str,
    runtime_inputs: RuntimeInputs,
    secrets: Secrets,
    output_mode: str,
)
```

Where:

- `prompt` is the cleaned intent text sent to the agent
- `runtime_inputs` contains request-scoped target information
- `secrets` contains extracted sensitive inputs
- `output_mode` controls summary vs later file/report behaviors

This contract must sit above CLI and below presentation layers, so that:

- CLI can create it now
- GUI can create it later
- API can create it later

without duplicating parsing or routing logic.

## Application Layer Boundary

The repository should have one application-level entry that all presentation surfaces call.

The boundary should be:

- CLI -> request normalization -> application service -> Deep Agent SDK assembly
- GUI -> request normalization -> application service -> Deep Agent SDK assembly
- API -> request normalization -> application service -> Deep Agent SDK assembly

The current `deep_agent_integration/` layer remains responsible for:

- configuration loading
- model construction
- tool registration
- agent construction
- runner invocation

But the new presentation-facing orchestration should sit just above it, so future GUI/API work does not depend on CLI code.

## CLI Scope

Phase 2 should add one thin official CLI command:

```bash
dba-assistant ask "<raw prompt>"
```

Optional debug-friendly flags may be added only if they do not change the prompt-first shape. For example:

- `--config <path>`
- `--output summary`

The CLI should not require users to pass Redis host/port/password as primary flags for ordinary usage.

If explicit flags are later added, they must be secondary overrides, not the main interaction model.

## Parsing Strategy

Phase 2 should keep prompt parsing deliberately narrow and debug-oriented.

It is enough to support a small, explicit extraction contract for the current Redis validation flow, such as:

- password
- host
- port
- db
- output mode

This parser should be deterministic and local, not LLM-dependent.

The goal is not to solve general natural-language extraction for all future skills. The goal is only to support a clean prompt-first debugging flow in Phase 2.

## File-Level Direction

### New Files

- `config/config.yaml`
- `config/config.example.yaml`
- a thin CLI module
- a request-normalization module

### Modified Files

- `src/dba_assistant/deep_agent_integration/config.py`
  - becomes a YAML-backed loader instead of an environment-variable-first loader
- `src/dba_assistant/deep_agent_integration/run.py`
  - should call through the normalized application path rather than acting as the only entry
- docs that currently describe the Phase 2 runtime surface

## Compatibility Constraint

This correction must preserve forward compatibility with GUI and API work.

That means:

- no CLI-only business logic
- no secrets stored as plain model prompt text after preprocessing
- no environment-variable-only configuration dependency
- no direct presentation-layer coupling to adaptors or tools

If a future GUI sends the same raw request text, it should be able to reuse the same normalization and application layers without semantic drift.

## Acceptance Criteria

1. A user can edit `config/config.yaml` without modifying Python code.
2. A user can execute a thin prompt-first CLI command for Phase 2 validation.
3. The system extracts Redis password and other runtime-scoped fields from the raw request before agent execution.
4. The cleaned prompt and structured runtime inputs are separated internally.
5. The implementation remains compatible with future GUI/API entry points.
6. The correction does not expand business scope beyond Phase 2 runtime and validation behavior.
