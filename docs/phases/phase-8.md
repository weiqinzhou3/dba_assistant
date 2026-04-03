# Phase 8: Future Expansion

## Status

Deferred

## Goal

Record future expansion directions without breaking the repository’s core architectural rule:

`CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

Future scope must extend that architecture. It must not introduce a separate runtime, a separate orchestration layer, or interface-specific business-routing systems.

## Expansion Rules

1. New database capabilities
   - MySQL, MongoDB, or other DBA domains should be introduced as new skills and supporting tools beneath the same Deep Agent.
   - New capability families must reuse the existing interface-adapter and unified-agent boundary.

2. Dangerous operations
   - write-capable or high-risk actions must be approval-gated
   - approval must happen through unified-agent HITL / `interrupt_on`, not through ad hoc interface-specific logic
   - those actions must also fall under the Phase 5 audit baseline

3. Shared report and artifact architecture
   - future skills should continue to reuse the shared analysis-report model and rendering path where possible
   - new domains may add domain-specific sections, but they should not fork the repository into multiple unrelated reporting stacks

4. Shared interface contract
   - future CLI improvements, WebUI, and API endpoints must continue to normalize requests into the same shared application boundary
   - interface surfaces should remain thin, with orchestration centered in the unified Deep Agent

## Deferred Expansion Items

- approval-gated dangerous Redis write tools
- broader DBA domains beyond Redis
- richer remote-execution capabilities built on the same HITL and audit model
- expanded report delivery channels built on the shared renderer
- broader multi-skill planning and cross-domain reasoning inside the same Deep Agent runtime

## Acceptance Criteria

- Any future expansion proposal can be evaluated against the repository’s single-agent architecture.
- No future phase should require replacing the interface-adapter boundary or introducing a second orchestration system.
- Dangerous actions remain impossible to add casually; they must pass through HITL and auditing requirements.

## Dependency Notes

- Intentionally deferred until the Redis-focused phases are mature.
- Must build on the unified Deep Agent, shared interface boundary, shared report system, and audit model from earlier phases.
- Current repository state is tracked separately in `docs/phases/current-scaffold-status.md`.
