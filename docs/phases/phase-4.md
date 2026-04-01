# Phase 4

## Objective

Implement the Redis inspection report skill in later work, while keeping initialization limited to contracts and paths.

## Scope

- reserve the `redis_inspection_report` production package
- document offline and remote collection paths
- define where inspection analysis and report work will live

## Inputs

- `docs/dba_assistant_master_plan_en.md`
- `docs/phases/phase-1.md`
- `docs/phases/phase-2.md`

## Outputs

- skill scaffold under `src/dba_assistant/skills/redis_inspection_report/`
- contract-oriented `SKILL.md`

## Directories Involved

- `src/dba_assistant/skills/redis_inspection_report/`

## Dependencies

- `docs/phases/phase-1.md`
- `docs/phases/phase-2.md`

## Acceptance Criteria

- skill directory exists
- `SKILL.md` exists
- analyzer and collectors placeholders exist
- no inspection command, parsing, or reporting logic is implemented during initialization

## Non-Goals

- Redis collection
- SSH collection
- inspection report rendering
