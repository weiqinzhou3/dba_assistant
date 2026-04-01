# Phase 1: Architecture Foundation & Shared Layers

## Status

Planning

## Goal

Establish the repository structure and deliver the interface definitions and offline implementations for the Collector, Reporter, and Template shared layers.

## Tasks

1. Establish repository directory structure and create `AGENTS.md`.
2. Define Collector interfaces and types.
   - Declare `ICollector<TInput, TOutput>`.
   - Implement an `OfflineCollector` base class that reads local files or directories, validates format, and outputs structured data.
   - Keep the Remote Collector at interface-definition level only.
3. Define Reporter interfaces and types.
   - Declare `IReporter<TAnalysis>`.
   - Implement `DocxReporter` to render analysis results into Word documents based on templates.
   - Implement `SummaryReporter` to format analysis results into terminal-readable structured output.
   - Keep PDF and HTML Reporters at interface-definition level only.
4. Establish the report template system.
   - Create `templates/reports/shared/` and implement shared components such as cover page, risk level styles, disclaimer, and related shared template elements.
   - Analyze historical report samples in `references/report-samples/`, extract content structure, and identify improvement areas.
   - Build initial standard template skeletons for RDB analysis and inspection reports.
5. Establish the reference file isolation directory and create usage-constraint documentation for it.
6. Set up the base testing framework and write unit tests for Collector and Reporter interfaces.

## Acceptance Criteria

- The Collector interface can be called by Skills, and the offline path can read local files and output structured data.
- The Reporter interface can be called by Skills, and at minimum `DocxReporter` and `SummaryReporter` are functional.
- Template skeletons are ready and can render a minimal Word document with a cover page, headings, and tables.
- Tests pass.

## Dependency Notes

- This is the foundation phase for later runtime, skill, and audit work.
- Current repository scaffold status is tracked separately in `docs/phases/current-scaffold-status.md`.
