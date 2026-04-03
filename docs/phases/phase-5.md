# Phase 5: Audit & Security Baseline

## Status

Planning

## Goal

Add repository-native execution audit and safety-baseline capabilities that match the unified Deep Agent runtime rather than a single CLI workflow.

This phase must also follow the repository-wide execution shape:

`CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

Phase 5 therefore audits the shared execution boundary, the unified Deep Agent, tool usage, approvals, and artifacts. It is not limited to terminal command logging.

## Architecture Constraints

- Auditing must attach to normalized requests and unified agent execution, not only to CLI commands.
- No raw secrets may be written into audit records.
- HITL / approval events must be auditable as first-class execution events.
- Audit capability must be reusable across all current and future skills.

## Audit Scope

The audit baseline must cover:

1. Interface boundary
   - normalized request summary
   - caller surface classification such as CLI, API, or WebUI
   - input source summary without leaking raw secrets

2. Unified Deep Agent execution
   - selected skill or dominant capability path
   - tool invocation sequence
   - start / end timestamps
   - success, failure, interruption, denial, or partial completion status

3. Approval and safety events
   - human approval requests triggered by `interrupt_on`
   - approval decision outcome
   - rejection reason when available

4. Artifact and output records
   - output mode
   - output path or artifact identifier
   - generated report metadata

## Delivered Scope

1. Implement repository-native audit logging.
   - Write structured JSONL or equivalent append-only execution records.
   - Keep the logging format stable enough for later tooling and review.
2. Instrument existing delivered skills and tools.
   - Phase 3 RDB analysis flow
   - Phase 4 inspection flow once delivered
   - shared report rendering path
3. Instrument unified-agent approval checkpoints.
   - Record approval-required actions
   - Record approve / reject outcomes
4. Define the minimum security baseline for future risky operations.
   - dangerous operations must not bypass the approval model
   - auditability is mandatory for any future write-capable tool

## Acceptance Criteria

- Each unified-agent execution can produce a complete audit record.
- Records capture request summary, selected capability path, tool usage, outputs, and approval events.
- Secrets are sanitized before persistence.
- Audit instrumentation is shared across skills instead of duplicated per interface surface.

## Dependency Notes

- Depends on the unified Deep Agent architecture established by earlier phases.
- Depends on delivered skills from earlier phases to attach real audit events.
- Current repository state is tracked separately in `docs/phases/current-scaffold-status.md`.
