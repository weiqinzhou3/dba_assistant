# DBA Assistant

DBA Assistant is a phase-oriented repository for building Redis-focused DBA analysis and reporting workflows on top of a Python implementation path.

## Runtime Foundation

DBA Assistant runs on Deep Agents SDK.

The repository-owned runtime glue lives under `src/dba_assistant/deep_agent_integration/` and is implemented with `deepagents`. The rest of the repository continues to evolve phase by phase on top of that runtime foundation.

## Current Status

This repository now contains:

- explicit documentation that the project is built on Deep Agents SDK
- the master plan
- reference materials under `src/`
- phase documents under `docs/phases/`
- production code under `src/dba_assistant/`
- template and test assets

It includes working runtime assembly, Redis-oriented collection/reporting paths delivered so far, and the remaining later-phase work tracked in `docs/phases/`.

## Repository Boundaries

- Production code: `src/dba_assistant/`
- Reference-only content: `src/claude-code-source-code/`, `src/docs/`
- Report templates: `templates/reports/`
- Historical report samples: `references/report-samples/`

## Development Model

Work is expected to proceed phase by phase:

1. establish shared foundations
2. add Deep Agents SDK runtime and collection infrastructure
3. implement skills incrementally
4. expand audit, templates, and future safety controls
