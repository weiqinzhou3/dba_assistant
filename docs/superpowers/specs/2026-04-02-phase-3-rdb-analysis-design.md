# Phase 3 Redis RDB Analysis Design

## Summary

This design defines `Phase 3` of the DBA Assistant project: the first full business skill, `redis_rdb_analysis`.

`Phase 3` must satisfy two requirements at the same time:

- reproduce the current RCS-oriented Redis RDB analysis workflow and report quality
- keep the skill generic enough to support non-RCS Redis systems in the future

The resulting design is therefore not "one hardcoded RCS report pipeline" and not "free-form prompt-to-SQL generation." It is a generic RDB analysis skill with:

- three input paths aligned to the master plan
- one unified analysis contract
- profile-driven analysis and report shaping
- prompt-driven, bounded overrides
- a generic report output layer that can be reused by future database report skills

As of April 2, 2026, this design remains intentionally bounded to `Phase 3`. It does not attempt to finish `Phase 4`, `Phase 5`, or future multi-database reporting in the same implementation pass.

## Goals

1. Implement the `redis_rdb_analysis` skill as a real end-to-end Phase 3 skill.
2. Preserve the master-plan delivery order of `3a -> 3b -> 3c`.
3. Reproduce the current manual RCS reporting workflow with higher-quality output.
4. Introduce a generic profile model so future non-RCS Redis systems can reuse the same skill.
5. Support single or multiple RDB inputs, with merged reporting by default.
6. Support remote Redis as an input source when the user asks for the latest RDB, with an explicit human confirmation gate before file acquisition.
7. Keep prompt-first usage while preventing prompt text from becoming unbounded executable analysis logic.

## Non-Goals

- This phase does not promise free-form natural-language SQL generation.
- This phase does not create one tool per profile.
- This phase does not make MySQL staging the default path.
- This phase does not complete generic cross-database analysis skills.
- This phase does not complete GUI or API surfaces.
- This phase does not implement dangerous unattended remote actions.

## Master Plan Alignment

The master plan remains authoritative for Phase 3 path ordering:

- `3a`: full custom pipeline, reproducing the current manual workflow
- `3b`: generate the report from precomputed MySQL or exported analysis data
- `3c`: pure offline direct analysis with no external database dependency

This design preserves those three paths exactly. The design only adds a cleaner internal model so all three paths converge on the same analysis and reporting contracts.

## Key Decisions

### 1. One generic skill, not one skill per customer workflow

`redis_rdb_analysis` remains the single Phase 3 skill.

RCS-specific behavior is expressed as a built-in `profile`, not as a separate skill. This allows:

- current daily RCS work to be delivered
- future non-RCS Redis systems to reuse the same skill
- prompt-first selection of a profile without multiplying skills

### 2. Profiles are analysis/report rules, not runtime config

Profiles are not model settings and not environment/runtime wiring.

Profiles define:

- which sections should appear in the report by default
- which prefix groups matter
- which custom breakdowns should be produced
- which TopN defaults should be applied
- which report title and section ordering should be used

Profiles do not define:

- LLM provider settings
- Deep Agent SDK model wiring
- transport credentials
- Redis connection lifecycle behavior

### 3. Prompt can override focus, but not invent arbitrary analysis logic

Prompt input may:

- choose a profile
- add focus prefixes
- request specific sections
- change `top_n`
- request merged or split reporting
- emphasize expiration vs non-expiration views

Prompt input may not:

- generate arbitrary SQL that becomes the formal analysis basis
- define unverifiable ad hoc statistics
- bypass the profile/analyzer contract

### 4. Default execution should not depend on MySQL

If the prompt does not explicitly request MySQL staging or historical SQL-style reproduction, the default execution path should avoid MySQL.

Default preference:

- local RDB -> direct analysis path when possible
- remote Redis -> acquire RDB, then direct analysis path when possible
- existing MySQL/CSV/JSON -> query/read precomputed data path

MySQL staging remains important for:

- reproducing the current RCS SQL-driven workflow
- preserving queryable intermediate results
- handling heavy multi-sample slicing when explicitly requested

But it is not the default path for ordinary prompt-first analysis.

### 5. Remote RDB acquisition is part of input acquisition, not profile behavior

If the user asks to analyze the latest RDB from a remote Redis instance, the skill must support that.

However:

- discovering remote RDB state is read-only
- acquiring an RDB file, or triggering a new snapshot, is operationally sensitive
- the actual acquisition step must require explicit human confirmation

This behavior belongs inside the unified `analyze_rdb` flow, not in a separate profile.

### 6. Reporting should be generic at the output layer

The RDB-specific analysis tool should remain RDB-specific.

The report output layer should be generic:

- `analyze_rdb` produces structured analysis results
- `generate_analysis_report` renders those results

This allows later database skills to reuse the same report-generation surface without renaming or duplicating the reporter layer.

## Reference Inputs

This design is informed by repository-local reference material only:

- the historical RCS Word report sample under `references/report-samples/rdb/`
- the legacy shell and SQL workflow under `references/legacy-workflows/rdb-analysis/scripts/`

These references define expected reporting content and workflow semantics. They are implementation references only. Their code must not be copied directly into production code.

## User-Facing Shape

Phase 3 should remain prompt-first.

Examples of expected usage:

```text
Analyze this RDB with the generic profile and focus on key types, expiration, and prefix top 30.
```

```text
Analyze the latest RDB from 10.0.0.8:6379 with the RCS profile and generate a detailed report.
```

```text
Analyze these three RDB files, merge them into one report, and focus on loan:* plus non-expiring keys.
```

The user should not need to create a new profile just to investigate a new prefix once. Long-lived recurring business views should later become named profiles.

## Path Model

### Path 3a: Full Custom Pipeline

Data flow:

`RDB files -> rdb-tools parsing -> MySQL staging -> SQL aggregation -> normalized analysis result -> report`

Primary purpose:

- reproduce and improve the current manual RCS workflow

### Path 3b: Precomputed Analysis Path

Data flow:

`existing MySQL results / CSV / JSON -> normalized analysis result -> report`

Primary purpose:

- generate reports from existing analysis data without repeating parsing/import

### Path 3c: Pure Offline Direct Analysis

Data flow:

`RDB files -> direct parser -> in-memory statistics -> normalized analysis result -> report`

Primary purpose:

- enable lightweight analysis with no `rdb-tools` or MySQL dependency

### Path Selection

Requested path may be explicit.

If not explicit, path selection should follow these rules:

- use `3b` when the user provides precomputed analysis inputs
- use `3a` when the user explicitly requests historical SQL-style reproduction or MySQL staging
- otherwise prefer `3c` for ordinary local or remotely acquired RDB analysis

## Remote Redis Input Acquisition

Remote Redis must be supported as an input source for `analyze_rdb`.

### Read-Only Discovery Stage

When the input source is remote Redis, `analyze_rdb` first performs a read-only discovery stage, such as:

- `INFO persistence`
- `LASTSAVE`
- `CONFIG GET dir`
- `CONFIG GET dbfilename`

This stage may infer:

- likely RDB file path
- last successful save time
- whether a background save is in progress
- whether an existing snapshot appears available

### Confirmation Gate

If analysis requires actual RDB acquisition, `analyze_rdb` must stop and surface a structured confirmation-required response before:

- copying the current RDB file
- triggering a new `BGSAVE`
- performing any file-transfer operation

This is required even if the user originally asked for "the latest RDB."

### Acquisition Modes

After confirmation, the implementation may proceed with one of these modes:

- `fetch_existing`
- `trigger_bgsave_and_fetch`

The implementation must treat `trigger_bgsave_and_fetch` as a higher-risk path than `fetch_existing`.

## Profile System

### Profile Locations

Built-in profiles should live under:

`src/dba_assistant/skills/redis_rdb_analysis/profiles/`

User- or customer-local profiles should be discoverable under:

`config/profiles/`

### Default Profiles

Phase 3 should define at least:

- `generic`
- `rcs`

### `generic` Profile

The `generic` profile is the default general-purpose Redis RDB analysis profile.

It should default to the following sections:

- executive summary
- sample overview
- overall dataset analysis
- key type distribution
- key type memory distribution
- expiration vs non-expiration analysis
- prefix analysis
- top big keys
- top keys by type
- conclusions and recommendations

It should explicitly support:

- key type count analysis
- key type memory share analysis
- expiration vs non-expiration analysis
- automatic prefix top analysis
- prefix-level expiration breakdown
- type-specific TopN analysis

### `rcs` Profile

The `rcs` profile is the first built-in customer-style profile.

It should preserve the business-relevant analytical content of the historical RCS report while allowing:

- better section ordering
- more consistent table titles
- clearer narrative structure
- standardized report formatting

It should remain a specialization of the generic analysis model, not a completely separate pipeline.

## Prompt-Driven Overrides

Prompt parsing may produce bounded overrides such as:

- `focus_prefixes`
- `include_sections`
- `exclude_sections`
- `top_n`
- `merge_multiple_inputs`
- `split_reports`
- `profile`

Examples of allowed prompt intent:

- focus on `loan:*`
- show non-expiring keys separately
- only expand list and hash top keys
- set prefix top to 30
- merge multiple inputs into one report

Examples of disallowed prompt intent:

- "generate a brand new SQL template set"
- "invent a new scoring model and use it as the report basis"

## Multi-Input Behavior

The skill must support one or multiple inputs.

Default output behavior:

- merge multiple inputs into one report

Split behavior:

- only split into separate reports when the user explicitly requests it

Labeling rules:

- explicit input labels win
- otherwise infer from filename or available metadata
- otherwise fall back to stable generated sample labels

The report model must preserve per-sample and per-host visibility when multiple inputs are merged.

## Internal Component Model

### Collectors

Collectors are responsible for acquiring or loading raw analysis inputs:

- `path_a_rdb_toolchain_collector`
- `path_b_precomputed_collector`
- `path_c_direct_parser_collector`

### Normalizer

The normalizer converts heterogeneous path outputs into one common dataset model.

### Profile Resolver

The profile resolver merges:

- named profile defaults
- prompt-driven overrides
- request defaults

into one effective analysis profile.

### Analyzers

Analyzers must remain deterministic and structured. Suggested analyzer families:

- overall analyzer
- key type analyzer
- expiration analyzer
- prefix analyzer
- big key analyzer
- profile custom analyzer

### Report Assembler

The report assembler converts analysis results into a generic report model with:

- title
- metadata
- sections
- structured blocks
- summary findings

### Report Renderer

The generic report renderer, reached through `generate_analysis_report`, is responsible for final output formatting such as:

- summary
- docx
- later html
- later pdf

## Core Contracts

### `RdbAnalysisRequest`

Recommended request shape:

- `prompt`
- `input_paths`
- `input_labels`
- `path_mode`
- `profile`
- `profile_overrides`
- `output_mode`
- `split_reports`
- `extra_context`

The request should also support a remote Redis source description when applicable.

### `NormalizedRdbDataset`

Recommended normalized dataset shape:

- `samples`
  - `sample_id`
  - `label`
  - `host_guess`
  - `source_path`
- `records`
  - `sample_id`
  - `key_name`
  - `key_type`
  - `size_bytes`
  - `has_expiration`
  - `ttl_seconds`
  - `prefix_segments`

### `RdbAnalysisResult`

Recommended analysis result families:

- `overall_summary`
- `key_type_summary`
- `key_type_memory_breakdown`
- `expiration_summary`
- `expiration_by_type`
- `prefix_top_summary`
- `prefix_expiration_breakdown`
- `top_big_keys`
- `top_keys_by_type`
- `custom_sections`

### Generic Report Model

The report output contract should be database-agnostic so future skills can reuse it.

It should support:

- report title
- report metadata
- ordered sections
- paragraphs
- tables
- findings lists
- charts or chart placeholders

## Tool Surface

Phase 3 should keep the public tool surface small.

Recommended tools:

- `analyze_rdb`
- `generate_analysis_report`

`analyze_rdb` is the unified analysis entry point and must internally support:

- local RDB inputs
- existing MySQL/CSV/JSON analysis inputs
- remote Redis discovery
- confirmation-required remote RDB acquisition
- path routing across `3a`, `3b`, and `3c`

`generate_analysis_report` is the generic renderer entry point and must not be hardcoded to Redis RDB naming.

Profiles are not tools.

## Required RCS Content Preservation

The following analytical content from the historical RCS report must be preserved in Phase 3 output:

- multi-host or multi-sample consolidated perspective
- host-dimension tables
- key count share and total space usage
- expiring key analysis
- non-expiring key analysis
- prefix-level breakdown
- `loan:*` detailed breakdown
- overall top 20 big keys
- top 10 list keys
- top 10 set keys
- top 10 hash keys

The following do not need to be preserved exactly:

- old version-control table layout
- historical wording
- exact table styling

These may be standardized and improved.

## Acceptance Direction

The eventual implementation should satisfy these outcomes:

- `3a` fully reproduces the current manual workflow with better output quality
- `3b` can generate reports from existing analysis data without reparsing RDB files
- `3c` can generate reports without `rdb-tools` or MySQL
- all three paths converge on compatible analysis and reporting structures
- prompt-driven profile selection and bounded overrides work without requiring new skills
- remote Redis analysis can pause for explicit confirmation before any RDB acquisition step

## Risks and Guardrails

- Do not let prompt overrides become an unbounded mini-language.
- Do not make MySQL staging implicit for all RDB analysis.
- Do not couple profile definitions to tool names.
- Do not copy legacy shell or SQL code directly into production.
- Do not hide remote file acquisition behind a silent automatic step.
- Do not hardcode RCS-only prefixes into the generic profile.
