# Deep Agents Runtime Correction Design

## Summary

This design corrects a runtime foundation mistake in the DBA Assistant repository.

The repository documentation, master plan, and `AGENTS.md` consistently define DBA Assistant as a `Deep Agents SDK` project. The current implementation under `src/dba_assistant/deep_agent_integration/` does not satisfy that requirement. It is wired to `openai-agents`, which is a different SDK.

This correction replaces the repository-owned runtime glue with a true `deepagents` integration while preserving the existing DBA Assistant application boundaries:

- `config.yaml` remains the static configuration source
- the CLI remains prompt-first
- the application layer remains the stable contract for future CLI, GUI, and API surfaces
- Phase 2 and Phase 3 business boundaries remain unchanged

The correction is intentionally narrow. It fixes the runtime foundation and the surrounding documentation/tests. It does not redesign the assistant’s business workflows.

## Problem Statement

The current runtime implementation is inconsistent with the project contract in three ways:

1. Dependency mismatch
   - `pyproject.toml` declares `openai-agents` instead of `deepagents`.

2. Integration mismatch
   - `deep_agent_integration/model_provider.py`, `agent_factory.py`, `tool_registry.py`, and `run.py` import and use `agents` package constructs such as `Agent`, `Runner`, `function_tool`, `AsyncOpenAI`, and `OpenAIChatCompletionsModel`.

3. Documentation mismatch
   - the repository says “Deep Agent SDK”, but the actual runtime is an OpenAI Agents SDK wiring.

This is not a cosmetic issue. It means the repository currently violates its own master plan and architecture policy.

## Scope

### In Scope

- Remove `openai-agents` as the runtime dependency
- Add and wire the Python `deepagents` SDK as the runtime foundation
- Replace the current `agents`-based model/agent/tool invocation path inside `src/dba_assistant/deep_agent_integration/`
- Keep `config/config.yaml` as the configuration source
- Keep prompt-first CLI behavior intact
- Keep the application-layer request contract intact
- Rework runtime tests so they verify `deepagents` behavior rather than `openai-agents` behavior
- Correct the relevant Phase 2 docs, runtime docs, and repository-level wording where they currently imply or mention OpenAI Agents SDK

### Out of Scope

- No redesign of the CLI UX
- No redesign of Phase 2 Redis tool scope
- No redesign of Phase 3 RDB analysis paths or profiles
- No introduction of full Deep Agents CLI storage conventions as a required runtime dependency
- No new GUI or API surface
- No long-lived durable orchestration beyond what is needed for the repository-owned runtime glue

## Design Principles

### 1. Keep the repository-owned glue layer, but make it real

The directory name `src/dba_assistant/deep_agent_integration/` is still appropriate. It communicates that this package is project-owned integration code around the runtime SDK, not the SDK itself.

What changes is the implementation inside it:

- before: glue around `openai-agents`
- after: glue around `deepagents`

### 2. Preserve the application contract

The runtime correction must not force a new top-level application shape.

The existing layering remains valid:

- `cli.py` parses the user entry
- `application/` normalizes requests
- `deep_agent_integration/` assembles the runtime-facing agent
- `tools/`, `skills/`, `collectors/`, and `adaptors/` keep their current responsibilities

This keeps the future GUI/API path stable while fixing the underlying runtime.

### 3. Prefer LangChain chat model objects over SDK-specific OpenAI clients

`deepagents` works with any LangChain chat model that supports tool calling, and `create_deep_agent(...)` accepts either a model string or a model object.

For DBA Assistant, the safer repository-owned path is to construct a provider-compatible LangChain chat model object from `config.yaml` and pass that model object into `create_deep_agent(...)`.

This avoids recreating the current mistake of binding the runtime layer to an OpenAI Agents-specific client abstraction.

### 4. Keep configuration static, targets dynamic

This correction does not revisit the already-correct direction that:

- static model/runtime configuration lives in `config/config.yaml`
- request-scoped targets and secrets are normalized separately by the application layer

The runtime migration must preserve that separation.

### 5. Use project memory explicitly

The repository already has a root `AGENTS.md`. The corrected runtime should explicitly load that repository policy into the `deepagents` agent instead of merely documenting its existence.

The runtime glue should not assume Deep Agents CLI auto-discovery behavior. SDK code should pass memory paths explicitly.

## External Constraints

### Deep Agents SDK constraint

The official Deep Agents Python docs state that:

- `create_deep_agent(...)` is the main runtime entry point
- deep agents work with any LangChain chat model that supports tool calling
- skills and memory are passed explicitly to the SDK in code

That means the repository should build a `deepagents` agent directly and should stop using OpenAI Agents SDK constructs.

### Memory and skills constraint

Deep Agents SDK code does not automatically scan project directories the way the Deep Agents CLI does. When using the SDK directly, the repository must explicitly pass:

- memory sources such as root `AGENTS.md`
- any project skill directories it wants the agent to use

That means the runtime glue should be explicit about what memory and skill paths are loaded.

## Repository Changes

The runtime correction affects the following files and areas:

```text
pyproject.toml
src/dba_assistant/deep_agent_integration/
  README.md
  config.py
  model_provider.py
  agent_factory.py
  tool_registry.py
  run.py
tests/unit/deep_agent_integration/
docs/phases/phase-2.md
docs/superpowers/specs/2026-04-01-phase-2-runtime-assembly-design.md
```

It may also require a small helper module if the runtime wiring needs isolated logic for:

- memory source resolution
- skill source resolution
- agent invocation payload shaping

If that helper is needed, it should remain small and local to `deep_agent_integration/`.

## Component Design

### `deep_agent_integration/config.py`

Responsibilities remain mostly unchanged:

- read `config/config.yaml`
- validate model and runtime settings
- normalize supported provider presets

What changes:

- configuration objects should no longer be typed around `openai-agents` assumptions
- naming and comments must reflect `deepagents` and LangChain chat model construction

### `deep_agent_integration/model_provider.py`

Before:

- built an `AsyncOpenAI` client
- built an `OpenAIChatCompletionsModel`
- toggled tracing through `openai-agents`

After:

- build a LangChain chat model instance compatible with `deepagents`
- use configuration values from `config.yaml`
- support the current provider presets:
  - DashScope China
  - DashScope International
  - Ollama local
  - custom OpenAI-compatible endpoint

Implementation direction:

- construct a provider-compatible LangChain model object
- pass that model object to `create_deep_agent(...)`

### `deep_agent_integration/tool_registry.py`

Before:

- wrapped Python callables using `function_tool(...)`

After:

- expose plain tool callables or the tool object shape expected by `deepagents`
- keep the same bounded tool surface:
  - Phase 2 read-only Redis tools
  - Phase 3 `analyze_rdb` tool

This migration must not expand tool scope.

### `deep_agent_integration/agent_factory.py`

Before:

- created an `Agent(...)`
- attached `ModelSettings(...)`

After:

- create a `deepagents` agent via `create_deep_agent(...)`
- attach:
  - the configured model
  - the bounded tool list
  - explicit memory sources
  - explicit skill sources if needed for the repository-owned runtime path

The produced agent remains a repository-owned integration-validation / execution agent. It does not become a Deep Agents CLI clone.

### `deep_agent_integration/run.py`

Before:

- called `Runner.run_sync(...)`

After:

- invoke the `deepagents` agent directly
- map the repository’s normalized request into the invocation shape required by `deepagents`
- preserve the existing repository entry points:
  - `run_phase2_request(...)`
  - `run_phase2(...)`
  - the application-layer call chain used by the prompt-first CLI

### `deep_agent_integration/README.md`

This file must stop referring to `Runner` or OpenAI Agents SDK semantics.

It should clearly say:

- this package is repository-owned `deepagents` assembly code
- it explicitly loads repository policy from `AGENTS.md`
- it is not a custom framework and not the presentation layer

## Memory and Skills Loading

The corrected runtime should explicitly load repository memory from the root `AGENTS.md`.

Initial runtime requirement:

- load root `AGENTS.md` as a memory source

Optional but preferred runtime behavior:

- explicitly pass project skill directories only when they are needed by the SDK-facing agent behavior

This migration should not silently invent a `.deepagents/` project tree. The current repository contract already uses root `AGENTS.md`, and the runtime should respect that.

## Testing Strategy

### Unit Tests

Replace the current `openai-agents`-shaped tests with `deepagents`-shaped tests that verify:

- model provider returns the expected LangChain-compatible model object or constructor path
- agent factory calls `create_deep_agent(...)` with the expected arguments
- memory source resolution includes root `AGENTS.md`
- run entry invokes the deep agent and returns a final string payload
- tool registry exports the expected bounded tools

### Regression Tests

The migration must not break:

- the prompt-first CLI contract
- Phase 2 Redis request execution path
- Phase 3 local RDB analysis path

Existing tests outside `deep_agent_integration/` should continue to pass unchanged unless they asserted `openai-agents` internals directly.

## Documentation Changes

The following wording corrections are required:

- replace “OpenAI Agents SDK” with “Deep Agents SDK” where runtime foundation is described
- remove OpenAI Agents-specific architectural claims from the Phase 2 spec and plan docs where they currently describe implementation details
- update runtime docs so they describe `deepagents` invocation rather than `Runner.run_sync(...)`

This correction should also be reflected in user-facing usage notes if they currently imply the wrong runtime foundation.

## Acceptance Criteria

- `pyproject.toml` no longer depends on `openai-agents`
- repository runtime code under `src/dba_assistant/deep_agent_integration/` no longer imports from `agents`
- runtime assembly uses `deepagents`
- root `AGENTS.md` is explicitly wired into runtime memory loading
- runtime tests validate the `deepagents` integration path
- prompt-first CLI behavior still works after the migration
- repository docs no longer misdescribe the runtime foundation

## Risks

### 1. API mismatch risk

`deepagents` is a different SDK and may require different invocation payloads or model abstractions than the current code assumes.

Mitigation:

- keep the migration localized to `deep_agent_integration/`
- verify against official `deepagents` docs and package APIs before finalizing implementation

### 2. Overcorrection risk

It would be easy to use this correction as an excuse to redesign the application layer.

Mitigation:

- keep CLI, application request normalization, and Phase 3 report flow intact
- change only the runtime foundation and its directly affected tests/docs

### 3. Memory/skills loading confusion

The Deep Agents CLI auto-discovers data from standard locations, but the SDK does not do that automatically.

Mitigation:

- explicitly pass root `AGENTS.md`
- document any explicit skill-path loading used by the repository runtime

## Recommended Implementation Sequence

1. Replace runtime dependency and add required `deepagents`/LangChain provider packages
2. Rewrite `model_provider.py` around LangChain chat model construction
3. Rewrite `tool_registry.py` and `agent_factory.py` around `create_deep_agent(...)`
4. Rewrite `run.py` invocation path
5. Rewrite runtime unit tests
6. Correct runtime-facing docs and Phase 2 wording
7. Run full repository verification
