# Phase 3.2: MySQL Access Capability

## Status

Planned

## Goal

Establish MySQL access as a reusable system capability layer that can serve Redis RDB analysis now and other DBA skills later.

Phase 3.2 is not a one-off implementation detail for one RDB route. It is the shared MySQL access foundation for:

- loading preparsed or precomputed datasets
- staging parsed rows for downstream aggregation
- executing read queries for inspection, reporting, reconciliation, and future DBA workflows

## Scope

Phase 3.2 owns:

- the generic MySQL adaptor contract
- MySQL read and staging tools
- separation of read vs write semantics
- approval rules for sensitive write-side behavior
- reusable result-shaping and dataset-loading helpers

Phase 3.2 does not own Redis-RDB-specific route choice. That remains in Phase 3.1.

## Core Layering

### 1. Generic MySQL adaptor

The adaptor is a system-level infrastructure boundary. It should own:

- connection setup
- query execution
- result retrieval
- transaction or write-step boundaries when needed
- error normalization

It must not be coupled to one Redis-RDB-only schema.

### 2. Reusable MySQL tools

The unified Deep Agent should be able to access MySQL capability through a bounded tool surface.

Minimum required tools:

- `mysql_read_query`
  - execute bounded read-only SQL and return a result set
- `load_preparsed_dataset_from_mysql`
  - load a preparsed or precomputed dataset and convert it into the dataset shape needed by `preparsed_dataset_analysis`
- `stage_rdb_rows_to_mysql`
  - write parsed RDB rows into a staging area for downstream database-backed aggregation

Optional helper surfaces may be added later, but Phase 3.2 should not hide all behavior behind one oversized MySQL tool.

## Required Usage Modes

Phase 3.2 must clearly support two distinct MySQL usage modes.

### 1. MySQL as source

This path supports:

- loading an already prepared dataset from MySQL
- then feeding that dataset into Phase 3.1 `preparsed_dataset_analysis`

This is the MySQL-backed entry path for analysis that does not need raw RDB reparsing.

### 2. MySQL as staging and aggregation backend

This path supports:

- parsing RDB rows from local or fetched RDB input
- staging those rows into MySQL
- then continuing into Phase 3.1 `database_backed_analysis`

This is the path behind the canonical `database_backed_analysis` route and can preserve durable intermediate results.

## Unified Deep Agent Relationship

Phase 3.2 capability must be available to the same unified Deep Agent that already orchestrates Redis inspection and RDB analysis.

The agent should be able to combine:

- Redis or RDB input capability
- MySQL dataset loading capability
- MySQL staging capability
- downstream report generation

No caller surface should be forced to hardcode those combinations ahead of time.

## Safety and Approval Model

Read and write capability must not be treated as equivalent.

### Read operations

Examples:

- `mysql_read_query`
- `load_preparsed_dataset_from_mysql`

These are lower-risk than staging writes, but they still require bounded SQL scope and connection policy.

### Write-side operations

Examples:

- `stage_rdb_rows_to_mysql`
- future table creation, overwrite, or cleanup helpers

These may require HITL approval depending on environment policy and requested action. Phase 3.2 should explicitly define that write-like actions are reviewable operations and should not all run as silently approved background steps.

## Reuse Beyond Redis RDB

Phase 3.2 must remain reusable for future DBA skills, such as:

- reading analysis tables
- generating summary statistics
- reconciliation or validation workflows
- reading precomputed result sets for later report generation
- future MySQL-oriented or mixed-database skills

That means:

- adaptor types must stay generic
- tool naming must stay generic
- MySQL capability must not be described as “only for Redis RDB import”

## Relationship to Phase 3.1

Phase 3.2 is the persistence and query capability layer that Phase 3.1 can call when analysis needs durable staging or MySQL-backed dataset loading.

The intended handoff points are:

- `stage_rdb_rows_to_mysql`
  - used by Phase 3.1 `database_backed_analysis`
- `load_preparsed_dataset_from_mysql`
  - used to feed Phase 3.1 `preparsed_dataset_analysis`, including `preparsed_mysql` input sources

This split keeps:

- Phase 3.1 focused on Redis-RDB semantics
- Phase 3.2 focused on MySQL access semantics

## Input and Output Contract Expectations

Phase 3.2 should expose stable tool-level contracts rather than requiring direct adaptor calls from arbitrary callers.

### Input expectations

- connection target or connection profile
- SQL text or staged dataset definition
- operation intent: read vs write
- optional dataset identity and staging metadata

### Output expectations

- normalized result set for reads
- normalized staging result for writes
- explicit metadata that downstream analysis can consume

## Acceptance Criteria

- a reusable MySQL adaptor exists with a generic execution contract
- read and write paths are modeled separately
- the unified Deep Agent can invoke MySQL read and staging tools
- Phase 3.1 can call Phase 3.2 for both:
  - MySQL-backed dataset loading
  - RDB-row staging before database-backed analysis
- MySQL capability docs and tool names remain generic enough for future non-RDB reuse
