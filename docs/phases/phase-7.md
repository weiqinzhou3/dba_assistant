# Phase 7: Report Template Continuous Optimization

## Status

Ongoing alongside implementation phases

## Goal

Continuously improve report quality across skills while preserving the unified Deep Agent architecture and the shared report-rendering model.

This phase is not a separate user-facing entry surface. It is a continuous improvement phase applied to outputs produced by:

- `redis_rdb_analysis`
- `redis_inspection_report`
- `redis_cve_report`
- future skills that reuse the shared analysis-report architecture

## Architecture Constraints

- Template optimization must improve the shared report model and renderer, not introduce per-surface rendering silos.
- Improvements must remain compatible with prompt-first interaction through the unified Deep Agent.
- GUI / API / WebUI must benefit from the same template and report improvements as CLI users.
- Skill-specific presentation rules may exist, but they should layer on top of the shared report architecture.

## Optimization Scope

1. Shared report structure
   - section ordering
   - summary density
   - readability
   - evidence placement

2. Skill-specific report profiles
   - RDB analysis profiles such as `generic` and `rcs`
   - inspection-specific risk summaries
   - CVE-specific advisory structure

3. Visual and editorial quality
   - terminology consistency
   - table clarity
   - remediation prioritization
   - risk labeling consistency

4. Reusability across surfaces
   - the same report contract should remain consumable by prompt responses, file-backed artifacts, future API payloads, and future WebUI presentation layers

## Delivered Scope

- Establish a repeatable review loop for generated reports.
- Convert recurring improvements into repository-owned template defaults.
- Keep historical samples and real generated artifacts as comparison input.
- Feed quality improvements back into the shared renderer and skill-specific report assembly rules.

## Acceptance Criteria

- Shared report outputs become more consistent across skills over time.
- Skill-specific improvements do not fork the rendering architecture into separate stacks.
- Improvements derived from real generated reports can be applied once and reused across all interface surfaces.

## Dependency Notes

- Runs continuously across Phase 3 and all later skill phases.
- Depends on the shared report architecture remaining central to the repository design.
- Current repository state is tracked separately in `docs/phases/current-scaffold-status.md`.
