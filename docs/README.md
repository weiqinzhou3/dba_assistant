# Documentation Guide

Use this directory with two levels of trust:

## Current-State Documents

These documents should describe the active production architecture and repository policy:

- `../AGENTS.md`
- `dba_assistant_master_plan_en.md`
- `dba_assistant_architecture_constraints_addendum_v1.md`
- `dba_assistant_architecture_investigation_report_v2.md`
- `dba_assistant_codex_handover.md`
- `phase-3-cli-usage.md`
- `phase-3-rdb-flow.md`
- `phases/phase-3.md`

When these documents disagree with historical design notes, current production code and the documents above win.

## Historical Design And Execution Notes

The following are planning records, migration notes, or execution logs. They are useful for context, but they are not the current runtime contract:

- `dba_assistant_agent_refactor_plan.md`
- `superpowers/`

Read them as historical evidence of how the repository evolved, not as the source of truth for today's production boundaries.
