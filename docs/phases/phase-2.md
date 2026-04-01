# Phase 2

## Objective

Prepare for Deep Agent SDK assembly and remote collection work without implementing it during initialization.

## Scope

- reserve adaptor and tool ownership boundaries
- explicitly document Deep Agent SDK as the future runtime assembly target
- document the read-only remote collection direction
- keep production code separate from the reference layer

## Inputs

- `docs/dba_assistant_master_plan_en.md`
- `AGENTS.md`
- `docs/phases/phase-1.md`

## Outputs

- scaffold adaptor package
- scaffold tool package
- documented phase boundary for later Deep Agent SDK runtime work

## Directories Involved

- `src/dba_assistant/adaptors/`
- `src/dba_assistant/tools/`

## Dependencies

- `docs/phases/phase-1.md`

## Acceptance Criteria

- adaptor module paths exist
- tool package path exists
- phase notes explicitly identify Deep Agent SDK as the runtime foundation
- no runtime registration logic is added during scaffold setup

## Non-Goals

- Deep Agent SDK integration
- live remote connections
- command execution behavior
