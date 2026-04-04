# Phase 3: Skill One — Redis RDB Memory Analysis Report

## Status

Delivered

## Goal

Implement the full pipeline for RDB memory analysis, supporting multiple input paths, prompt-first CLI usage, and shared output modes.

## Follow-On Split

The delivered Phase 3 baseline is now treated as the foundation for two follow-on sub-phases:

- `Phase 3.1`: Redis RDB Capability
- `Phase 3.2`: MySQL Access Capability

Those documents define the next architectural evolution for Phase 3 under the unified execution shape:

`CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

This file remains the high-level phase contract for delivered Phase 3 scope. It no longer serves as the sole planning surface for upcoming RDB-routing, MySQL-capability, and interface-contract work.

## Route Mapping

| Delivery stage | Canonical route name | Description | Compatibility alias |
|----------------|----------------------|-------------|---------------------|
| `3a` | `database_backed_analysis` | Reproduce the SQL-backed workflow: RDB parsing, MySQL staging, downstream database aggregation, then report generation. | `legacy_sql_pipeline` |
| `3b` | `preparsed_dataset_analysis` | Analysis data already exists in MySQL or another preparsed form, so the report can be generated without re-parsing the RDB. | `precomputed_dataset` |
| `3c` | `direct_rdb_analysis` | No external tool or database dependency: parse the RDB directly and analyze it in memory. | `direct_memory_analysis` |

Canonical route names are the primary engineering vocabulary. Stage labels and old names remain only as historical or compatibility references.

## Implementation Breakdown

### Phase 3a: `database_backed_analysis`

1. Write `skills/redis-rdb-analysis/SKILL.md` defining input and output contracts.
2. Implement the RDB Offline Collector.
   - Accept RDB file paths, including multiple files and directory scanning.
   - Invoke `rdb-tools` to parse RDB files and produce structured intermediate data.
   - Write parsed results to MySQL through `MySQLAdaptor`.
3. Implement the RDB Analyzer.
   - Execute the existing SQL statement set for aggregation analysis, including Top Keys, memory distribution, TTL distribution, and data type ratios.
   - Output a standardized `RdbAnalysisResult`.
4. Implement report generation.
   - Reference historical report samples to build the standard RDB analysis template.
   - Improve layout consistency, chart readability, and risk grading standardization.
   - Render through the Reporter Layer.
5. Test end to end with fixture RDB files and a MySQL environment.

### Phase 3b: `preparsed_dataset_analysis`

1. Implement a MySQL Query Collector that queries existing analysis data from MySQL directly, or reads from pre-exported CSV or JSON.
2. Reuse the Analyzer and Reporter from Phase 3a.
3. Test report generation with MySQL fixture data.

### Phase 3c: `direct_rdb_analysis`

1. Implement an RDB Direct Parser Collector using Python or Node libraries, without `rdb-tools` or MySQL.
2. Implement a lightweight Analyzer that performs in-memory statistics and outputs the same `RdbAnalysisResult`.
3. Reuse the Reporter.
4. Test report generation with fixture RDB files and no external dependencies.

## Output Modes

The prompt-first surface uses report-oriented terminology, but the currently wired CLI surface is narrower than the full Phase 3 route design.

| User-facing intent | Normalized mode | Result |
|--------------------|-----------------|--------|
| `summary` | prompt says `summary`, or `--report-format summary` | Rendered summary text from the assembled `AnalysisReport`, printed to stdout by default and also written to `--output` when a file target is provided. |
| `report` + `docx` | prompt says `docx`, or `--report-format docx` | Full Word report. A destination path is required in the prompt or via `--output`. |
| `report` + `pdf` | future extension | Reserved for later Phase 3 extension work. |
| `report` + `html` | future extension | Reserved for later Phase 3 extension work. |

## Acceptance Criteria

- After `database_backed_analysis` completion, the SQL-backed workflow is fully reproducible and generates documents of higher quality than historical reports.
- After `preparsed_dataset_analysis` and `direct_rdb_analysis` completion, all three canonical routes work independently with consistent output structures.

## Wired Entry Points

- `dba-assistant ask "<prompt>"` is the primary user entry point.
- The retained CLI flags are `--config`, `--input`, `--profile`, `--report-format`, and `--output`.
- CLI input is normalized through the shared interface adapter, so prompt-derived intent and explicit overrides converge into one request model before Deep Agent execution.
- Runtime shape is now `CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`.
- The unified Deep Agent explicitly loads repository `skills` from `src/dba_assistant/skills/` and chooses tools dynamically instead of relying on CLI or application-service business routing.
- Remote Redis discovery and remote-RDB acquisition now belong to the unified Deep Agent flow. High-risk remote-RDB acquisition is guarded at the tool-call level through Deep Agents `interrupt_on`; it is no longer rejected at the CLI or application boundary.
- `dba_assistant.tools.analyze_rdb.analyze_rdb_tool` remains the public local-RDB analysis tool entry point.
- `dba_assistant.core.reporter.generate_analysis_report.generate_analysis_report` remains the public generic report renderer export.

## Dependency Notes

- Depends on shared layers from Phase 1 and runtime assembly from Phase 2.
- Current repository scaffold status is tracked separately in `docs/phases/current-scaffold-status.md`.
