# Phase 3.1: Redis RDB Capability

## Status

Planned

## Goal

Turn Redis RDB analysis into a single agent-callable capability chain that:

- accepts multiple input source kinds through one shared interface contract
- remains prompt-first at the user surface
- stays adapter-agnostic for future CLI, Web, and API callers
- can continue through remote discovery, approval, fetch, and analysis without CLI-side business rejection
- can compose naturally with Phase 3.2 MySQL capability when database-backed analysis is the better route

The target execution shape remains:

`CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

## Scope

Phase 3.1 owns the Redis-RDB-specific capability layer:

- input-source normalization for Redis RDB work
- route normalization for RDB analysis modes
- profile resolution and prompt-driven analysis overrides
- local, remote, and precomputed RDB-oriented analysis entry
- remote discovery and approval-gated acquisition flow
- the domain decision of which RDB analysis route to use

Phase 3.1 does not own generic MySQL infrastructure. When database-backed work is needed, it must call Phase 3.2 capability surfaces instead of embedding one-off MySQL logic.

## Unified Input Contract

Phase 3.1 requires the shared interface contract to represent RDB-oriented input explicitly.

### Required fields

- `input_kind`
  - `local_rdb`
  - `precomputed`
  - `remote_redis`
- `path_mode`
  - `auto`
  - `database_backed_analysis`
  - `preparsed_dataset_analysis`
  - `direct_rdb_analysis`

These are contract-level fields, not CLI-only fields. CLI may expose them as optional overrides, but Web and API must be able to send the same information without inventing a parallel schema.

### Input semantics

- `local_rdb`
  - one or more local RDB files supplied as structured inputs
- `precomputed`
  - one or more precomputed datasets supplied as JSON, CSV, or future external dataset references
- `preparsed_mysql`
  - a preparsed dataset loaded from MySQL and then treated as `preparsed_dataset_analysis`
- `remote_redis`
  - a live Redis target whose persistence state must be discovered before acquisition

MySQL-backed dataset input uses the same shared contract rather than a separate caller-specific surface.

## Unified Analysis Modes

The formal, engineering-facing route names are:

- `database_backed_analysis`
- `preparsed_dataset_analysis`
- `direct_rdb_analysis`

These replace older compatibility aliases:

- `3a`
- `3b`
- `3c`
- `legacy_sql_pipeline`
- `precomputed_dataset`
- `direct_memory_analysis`

### Compatibility requirement

Old names remain compatibility aliases and must be normalized by `normalize_route_name`.

The normalized mapping is:

- `3a` -> `database_backed_analysis`
- `legacy_sql_pipeline` -> `database_backed_analysis`
- `3b` -> `preparsed_dataset_analysis`
- `precomputed_dataset` -> `preparsed_dataset_analysis`
- `3c` -> `direct_rdb_analysis`
- `direct_memory_analysis` -> `direct_rdb_analysis`

New code, new docs, new logs, and new tool responses should prefer the canonical names.

## Redis RDB Capability Scenarios

Phase 3.1 must support these scenarios through the unified Deep Agent path.

### 1. Local RDB to direct analysis

- input source: one or more local RDB files
- selected route: `direct_rdb_analysis`
- outcome: direct parsing, in-memory analysis, shared report generation

### 2. Local RDB to database-backed analysis

- input source: one or more local RDB files
- selected route: `database_backed_analysis`
- outcome: parse RDB rows, stage them through Phase 3.2 MySQL capability, run database-backed aggregation, then render reports

### 3. Preparsed dataset to analysis

- input source: precomputed dataset or MySQL-backed preparsed dataset
- selected route: `preparsed_dataset_analysis`
- outcome: skip raw RDB parsing and move directly into normalized analysis plus report generation

### 4. Remote Redis to approval-gated acquisition

- input source: remote Redis target
- flow:
  - `remote discovery`
  - `approval_required`
  - `fetch`
  - return to unified `analyze_rdb`
- after acquisition, the same request can continue through either:
  - `direct_rdb_analysis`
  - `database_backed_analysis`

The remote branch must not be rejected at CLI or service level simply because the target is remote.

## Remote Redis Branch

Remote Redis support in Phase 3.1 must be modeled as one upstream acquisition branch feeding the same downstream analysis chain.

### Required stages

1. `remote discovery`
   - read-only discovery of persistence information
   - returns target metadata and an `approval_required` state when acquisition is needed
2. `approval_required`
   - approval must be attached to the high-risk acquisition step
   - approval belongs inside Deep Agent execution, not in CLI-side routing logic
3. `fetch`
   - once approved, the system fetches the RDB or otherwise materializes the analysis input
4. `continue analyze_rdb`
   - the fetched artifact is routed back into the normal analysis capability

### Approval boundary

The sensitive action is not discovery. The sensitive action is acquisition and any action that may create, overwrite, or trigger remote snapshot state. HITL must therefore guard the acquisition step, not the general request.

## Profile and Analysis Override Model

Profile is a default analysis/report template, not a hardcoded parser branch.

### Required behavior

- default profile: `generic`
- explicit prompt profile selection takes priority
- additional prompt requests become bounded overrides, not free-form SQL generation

### Valid override categories

- key prefixes
- top N overrides
- data-type focus
- section or dimension selection

These values must be resolved by a profile registry / resolver layer. Profile name validation, loading, defaulting, and aliasing should not remain hardcoded inside the prompt parser.

## Relationship to Phase 3.2

Phase 3.1 depends on Phase 3.2 whenever MySQL-backed storage or retrieval is part of the analysis path.

### Required connection points

- `database_backed_analysis`
  - calls Phase 3.2 staging and query capabilities instead of embedding ad hoc MySQL behavior
- `preparsed_dataset_analysis`
  - must be able to accept datasets that Phase 3.2 loads from MySQL

Phase 3.1 owns route choice and analysis semantics. Phase 3.2 owns reusable MySQL infrastructure and MySQL-oriented tool surfaces.

## Unified Deep Agent Relationship

The unified Deep Agent remains the orchestrator of capability choice.

Phase 3.1 is not a standalone CLI feature. It is a skill-and-tool capability group available to the one Deep Agent. The agent should be able to choose among:

- direct local RDB analysis
- precomputed dataset analysis
- remote discovery and later acquisition
- database-backed analysis that composes with Phase 3.2 MySQL tools

The interface adapter remains responsible only for normalizing hard input facts and applying explicit overrides.

## Acceptance Criteria

- the interface contract can represent `local_rdb`, `precomputed`, and `remote_redis` as first-class inputs
- `analyze_rdb` accepts the new formal route names and compatibility aliases
- remote Redis requests flow through discovery -> approval -> fetch -> analyze
- fetched remote RDB input can continue through either `direct_rdb_analysis` or `database_backed_analysis`
- profile selection and validation are registry/resolver-driven
- new logs, docs, and interface responses prefer the new route names
