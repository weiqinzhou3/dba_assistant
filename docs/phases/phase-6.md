# Phase 6: Skill Three — Redis CVE Security Report

## Status

Planning

## Goal

Deliver the `redis_cve_report` skill as a Redis security-intelligence and report-generation capability under the unified Deep Agent architecture.

This phase must follow the repository-wide execution shape:

`CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

The phase is therefore defined by the CVE skill, its collectors, analyzers, and report outputs. It is not defined by a dedicated CLI product flow.

## Architecture Constraints

- The public interaction remains prompt-first.
- Interface surfaces provide normalized requests and optional structured overrides.
- The unified Deep Agent decides when to invoke `redis_cve_report`.
- CVE-source collectors remain internal capability components beneath the skill boundary.
- Report output must reuse the shared report model and shared renderer.

## Input Paths

| Path | Formal meaning | Data source |
|------|----------------|-------------|
| Online multi-source aggregation | Fetch security intelligence at execution time | NVD, MITRE, Redis advisories, GitHub security sources, and other approved sources |
| Offline bundle / cache | Operate in air-gapped or replay mode | Pre-fetched CVE bundles, fixtures, or repository-controlled offline source data |

The Deep Agent should be able to choose this skill from prompt intent such as version-impact checks, Redis security summaries, or time-range CVE reports.

## Delivered Scope

1. Implement multi-source CVE collection.
   - Each source collector must be independently executable.
   - Partial source failure must not collapse the whole skill.
2. Implement the CVE analyzer.
   - merge and deduplicate by CVE identity
   - track source provenance
   - prioritize by severity and relevance
   - support optional version-range impact assessment
3. Implement report assembly and rendering.
   - reuse the shared report pipeline
   - support concise summary output and full report output from the same structured result
4. Preserve source provenance and assessment transparency.
   - record fetch timestamps
   - record source availability
   - distinguish authoritative severity values from LLM-assisted interpretation

## Output Contract

Phase 6 must emit:

- one structured CVE-analysis result
- one shared analysis-report model
- shared-renderer output in summary or full-report form

Expected report contents include:

- executive summary
- CVE table and severity ordering
- optional version-impact assessment
- source provenance and disclaimer sections

## Acceptance Criteria

- `redis_cve_report` exists as a real skill under the unified Deep Agent runtime.
- Multi-source collection works with graceful degradation.
- Version-impact assessment works when the request provides a Redis version or version range.
- The Deep Agent can choose this skill from prompt intent without interface-level phase routing.
- CVE outputs reuse the shared reporting architecture rather than introducing a separate report pipeline.

## Dependency Notes

- Depends on the unified runtime from Phase 2.
- Depends on the shared report architecture matured in earlier phases.
- Depends on the audit and safety baseline from Phase 5 for later security-sensitive extensions.
- Current repository state is tracked separately in `docs/phases/current-scaffold-status.md`.
