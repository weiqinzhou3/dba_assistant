# DBA Assistant Repository Policy

## Purpose

This repository is developed phase by phase from the DBA Assistant master plan.

DBA Assistant is a Deep Agents SDK-based project. Functional delivery happens phase by phase from the master plan.

## Non-Negotiable Rules

- `AGENTS.md` is the repository policy source of truth.
- DBA Assistant uses Deep Agents SDK as its runtime foundation.
- Production code must live under `src/dba_assistant/`.
- `src/claude-code-source-code/` and `src/docs/` are reference-only inputs for design and coding guidance.
- Do not copy runtime implementation code from the reference layer into production modules.
- Do not import production modules from the reference layer, and do not import the reference layer into production modules.
- Follow the master plan when reference material and local preference diverge.
- Phase work must stay scoped. Do not mix unfinished later-phase behavior into an earlier-phase delivery.

## Repository Layout Rules

- `docs/phases/` stores execution-oriented phase notes.
- `templates/reports/` stores repository-owned report template work.
- `references/report-samples/` stores historical report samples for comparison only.
- `tests/` stores repository-native fixtures and verification assets.
- Regarding repository layering, skill/tools/capabilities responsibility boundaries, shared infrastructure reuse rules, and prohibition of anti-patterns, please consistently follow docs/dba_assistant_architecture_constraints_addendum_v1.md; if implementation convenience conflicts with this document, the document shall prevail, unless docs/dba_assistant_master_plan_en.md explicitly overrides it.


## Initialization Rules

- `/init` creates structure, contracts, and documentation only.
- `/init` must not claim runtime completeness.
- Placeholder modules must clearly state `scaffold-only` status.

## Language Direction

- The repository is Python-first.
- TypeScript files under the reference layer do not define the production language choice.

## Redis Connection Information

- Redis server: 192.168.23.54:6379
- SSH server: 192.168.23.54:22
- SSH username: root
- SSH password: root (provided via secure context)
- Remote RDB acquisition mode: fresh_snapshot
