# Phase 3 CLI Prompt-First Design

## Summary

This design corrects the current `Phase 3` user surface.

The current repository already has a working `redis_rdb_analysis` implementation, but its public shape still feels too parameter-led for the intended DBA Assistant experience.

The corrected target is:

- the CLI remains `prompt-first`
- a small parameter surface is still preserved
- parameters exist primarily as an override and compatibility layer
- the internal request contract stays structured so future GUI and API surfaces can reuse the same application layer

This design also replaces the code-facing `3a / 3b / 3c` route names with formal route identifiers, while preserving the original phase naming inside phase documentation.

## Goals

1. Keep `dba-assistant ask "<prompt>"` as the primary interaction model for `Phase 3`.
2. Preserve a small explicit parameter surface for file paths, configuration paths, confirmations, and future structured callers.
3. Make prompt parsing responsible for most user-facing analysis intent.
4. Keep one internal normalized request model that CLI, future GUI, and future API can all reuse.
5. Replace route names like `3a` and `3b` in code-facing contracts with formal names.
6. Add user-facing documentation that explains both the parameter contract and the end-to-end data flow.

## Non-Goals

- This design does not replace the `redis_rdb_analysis` business logic delivered in Phase 3.
- This design does not remove all explicit parameters from the CLI.
- This design does not complete a GUI or HTTP API.
- This design does not make free-form prompt parsing the source of truth for every technical input.

## Problem Statement

The current `Phase 3` implementation exposes a CLI that works, but the usage shape still leans too heavily toward technical parameters and internal implementation vocabulary.

Specific problems:

- the CLI does not yet feel like an agent-first surface
- the route vocabulary `3a / 3b / 3c` is phase-document language, not production interface language
- there is no dedicated user document that explains prompt-first usage plus the retained parameter layer
- there is no dedicated flow document that explains how a request such as:

```text
按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx
```

becomes a structured request and then a report artifact

## Key Decisions

### 1. Prompt-first remains the only primary UX

The CLI should continue to be presented and documented as:

```text
dba-assistant ask "<prompt>"
```

The prompt should be the primary place where a user expresses:

- which profile to use
- what to focus on
- whether a docx report is desired
- whether MySQL-style processing is desired
- whether multiple inputs should be merged or split
- where the output should go

Parameters are retained, but prompt remains the first-class interaction mode.

### 2. Parameters remain, but only as an override and compatibility layer

The CLI should preserve a small parameter layer for:

- `--config`
- `--input`
- future explicit confirmation controls
- future output and profile override controls if needed

These parameters are not the primary DBA Assistant user experience. They exist because:

- local files are awkward to represent as pure prompt text
- confirmation flows need reliable machine-readable state
- future GUI and API callers need a structured contract
- debugging and automated testing need deterministic overrides

### 3. Prompt and parameters must converge into one normalized request

The CLI must not implement a separate behavior tree from GUI or API.

Instead:

1. CLI receives raw prompt plus optional explicit parameters
2. prompt parsing extracts user intent
3. explicit parameters override conflicting prompt-derived values
4. the result becomes a single normalized request object
5. the application layer executes from that normalized request

This guarantees that:

- prompt-first UX is preserved
- future GUI/API paths do not duplicate business logic
- testing remains deterministic

### 4. Phase path names and code route names must be separated

`3a / 3b / 3c` should remain in phase documentation, because they refer to master-plan delivery sequencing.

They should not remain the primary code-facing or user-facing route names.

The formal route names will be:

- `3a -> legacy_sql_pipeline`
- `3b -> precomputed_dataset`
- `3c -> direct_memory_analysis`

These names should be used in:

- code
- metadata
- user documentation
- future GUI/API contracts
- logs and debug output

Phase documentation should explicitly show the mapping so the link back to the master plan is never lost.

## CLI Contract

### Primary command shape

The primary command remains:

```text
dba-assistant ask "<prompt>"
```

### Retained parameter layer

The retained explicit parameter layer should be documented as a secondary interface:

- `--config`
- `--input`
- any future confirmation-oriented option
- any future explicit override option that exists for deterministic testing or GUI/API parity

### Precedence

The contract is:

1. prompt is parsed first
2. explicit parameters are applied second
3. explicit parameters override conflicting prompt-derived values
4. final execution always uses the normalized request

This keeps CLI behavior deterministic without changing the user-facing interaction style.

## Data Flow

For a request such as:

```text
按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx
```

the intended data flow is:

1. `cli.py` receives:
   - raw prompt
   - optional `--config`
   - optional `--input`
2. `prompt_parser.py` extracts:
   - `profile_name = rcs`
   - report intent = `docx`
   - output path = `/tmp/rcs.docx`
   - any focus prefixes
   - any TopN overrides
   - any MySQL-routing hint
3. explicit CLI parameters are applied as overrides
4. the result is converted into a normalized request object
5. `application.service` determines this is an RDB analysis request
6. `analyze_rdb` resolves the input source:
   - local RDB
   - precomputed dataset
   - remote Redis
7. route selection chooses the formal route:
   - `legacy_sql_pipeline`
   - `precomputed_dataset`
   - `direct_memory_analysis`
8. `profile_resolver` loads `generic` or `rcs` and merges prompt overrides
9. analyzers produce a structured `AnalysisReport`
10. `generate_analysis_report` renders the requested output
11. the requested artifact is:
   - printed to stdout for summary output
   - written to a file for `docx` and future report formats

## Route Naming Contract

The route mapping must be explicit in documentation and code comments:

| Phase Document Name | Formal Route Name | Meaning |
|---------------------|-------------------|---------|
| `3a` | `legacy_sql_pipeline` | `RDB -> parsing -> MySQL staging / SQL aggregation -> report` |
| `3b` | `precomputed_dataset` | existing `JSON / CSV / exported analysis -> report` |
| `3c` | `direct_memory_analysis` | direct local RDB parsing and in-memory analysis |

The master-plan order is still preserved. Only the interface vocabulary is being improved.

## Documentation to Add or Update

### 1. `docs/phase-3-cli-usage.md`

This document should explain:

- prompt-first usage
- retained parameters
- parameter definitions
- prompt vs parameter precedence
- examples for:
  - generic profile
  - `rcs` profile
  - local RDB input
  - precomputed input
  - remote Redis confirmation flow

### 2. `docs/phase-3-rdb-flow.md`

This document should explain:

- the normalized request model
- route resolution
- profile resolution
- report generation flow
- confirmation-required remote flow
- the exact example flow for:

```text
按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx
```

### 3. `docs/phases/phase-3.md`

This phase document should be updated so that:

- it still preserves `3a / 3b / 3c`
- it explicitly maps those path labels to the formal route names
- the wired entry point section reflects the prompt-first CLI design

## Implementation Scope

The implementation should include:

- prompt parser expansion for `profile`, report format, output path, and routing hints
- CLI/application precedence handling for prompt-derived values vs explicit parameters
- formal route renaming in metadata and route-selection logic
- prompt-first user docs
- flow docs

The implementation should not introduce a broad new CLI subcommand surface.

## Acceptance Criteria

- A user can primarily interact with Phase 3 through prompt-first CLI usage.
- The CLI still retains a small explicit parameter surface for compatibility and overrides.
- Code-facing route names use:
  - `legacy_sql_pipeline`
  - `precomputed_dataset`
  - `direct_memory_analysis`
- Phase documentation clearly maps those names back to `3a / 3b / 3c`.
- Dedicated documentation exists for:
  - CLI usage
  - parameter definitions
  - data flow
  - the example RCS docx request

