# Phase 4: Skill Two — Redis Inspection Report

## Status

Planning

## Goal

Deliver the `redis_inspection_report` skill as a Redis inspection and health-audit capability under the unified Deep Agent architecture.

This phase must follow the repository-wide execution shape:

`CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

That means Phase 4 is not defined by a dedicated CLI workflow. It is defined by a skill, its collectors, analyzers, tools, and report outputs that the unified Deep Agent can select from prompt intent.

## Architecture Constraints

- The public interaction remains prompt-first.
- Interface surfaces normalize requests; they do not hard-route Phase 4 behavior.
- The unified Deep Agent chooses `redis_inspection_report` and the supporting tools.
- Collection remains read-only unless a future phase explicitly introduces approval-gated dangerous operations.
- Report output reuses the shared analysis-report rendering path instead of building a parallel report system.

## Input Paths

| Path | Formal meaning | Data source |
|------|----------------|-------------|
| Offline evidence bundle | Previously collected inspection data is available locally | Local files such as `INFO`, `CONFIG`, `SLOWLOG`, `CLIENT LIST`, host snapshots, and custom evidence bundles |
| Live read-only inspection | Evidence is collected at execution time | Redis read-only inspection plus host-level evidence gathered through allowed read-only adaptors |

These are skill input paths, not separate user-facing products. The unified Deep Agent may choose either path based on the prompt, available runtime inputs, and policy constraints.

## Delivered Scope

### Offline inspection path

1. Implement the offline inspection collector.
   - Accept one local evidence bundle or a directory of collected inspection artifacts.
   - Parse and normalize Redis and host evidence into one shared inspection dataset.
2. Implement the inspection analyzer.
   - Cover instance basics, memory posture, persistence posture, replication, slow query health, connection posture, security posture, and configuration risks.
   - Produce a consistent structured result with findings, evidence, severity, and remediation guidance.
3. Implement report assembly and rendering.
   - Reuse the shared report model and renderer.
   - Support both concise summary output and full report output from the same analysis result.

### Live read-only inspection path

1. Implement the live inspection collector.
   - Collect read-only Redis evidence through repository tools and adaptors.
   - Collect host evidence through approved read-only host access paths when needed.
2. Reuse the same analyzer and reporting pipeline as the offline path.
3. Keep the live path policy-safe.
   - No destructive writes.
   - No implicit dangerous host operations.
   - Any future risky operation must be gated by Deep Agent HITL / `interrupt_on`.

## Output Contract

Phase 4 must support the shared report contract already established by earlier phases:

- one structured analysis result for inspection
- one shared report model
- one shared rendering pipeline

Expected output forms:

- summary output for prompt-first interaction
- full inspection report output through the shared renderer
- reusable artifacts that future GUI / API surfaces can consume without rebuilding inspection logic

## Acceptance Criteria

- `redis_inspection_report` exists as a real skill under the unified Deep Agent runtime.
- Offline evidence can produce a complete inspection result and a report-quality output.
- Live read-only inspection can produce the same output structure as the offline path.
- The Deep Agent can select the inspection capability from prompt intent without CLI-side phase routing.
- Inspection output reuses the shared report architecture rather than introducing a separate reporting stack.

## Dependency Notes

- Depends on shared layers from Phase 1.
- Depends on Deep Agents runtime assembly from Phase 2.
- Depends on the shared report pipeline and prompt-first orchestration shape already established by Phase 3.
- Current repository state is tracked separately in `docs/phases/current-scaffold-status.md`.
