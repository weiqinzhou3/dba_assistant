# Phase 3: Skill One — Redis RDB Memory Analysis Report

## Status

Delivered

## Goal

Implement the full pipeline for RDB memory analysis, supporting multiple input paths, prompt-first CLI usage, and shared output modes.

## Stage Mapping

| Phase stage | Formal route name | Description | Delivery order |
|-------------|-------------------|-------------|----------------|
| `3a` | `legacy_sql_pipeline` | Reproduce the current manual workflow: RDB parsing, MySQL staging, SQL aggregation, then report generation. | Deliver first |
| `3b` | `precomputed_dataset` | Analysis data already exists in MySQL or another precomputed form, so the report can be generated without re-parsing the RDB. | Deliver after `3a` |
| `3c` | `direct_memory_analysis` | No external tool or database dependency: parse the RDB directly and analyze it in memory. | Deliver after `3a` |

The table above defines the intended semantics of each formal route name. In the current local debug wiring, `legacy_sql_pipeline` still falls back to the default direct-parser collector unless a dedicated path-A collector is injected.

## Implementation Breakdown

### Phase 3a: `legacy_sql_pipeline`

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

### Phase 3b: `precomputed_dataset`

1. Implement a MySQL Query Collector that queries existing analysis data from MySQL directly, or reads from pre-exported CSV or JSON.
2. Reuse the Analyzer and Reporter from Phase 3a.
3. Test report generation with MySQL fixture data.

### Phase 3c: `direct_memory_analysis`

1. Implement an RDB Direct Parser Collector using Python or Node libraries, without `rdb-tools` or MySQL.
2. Implement a lightweight Analyzer that performs in-memory statistics and outputs the same `RdbAnalysisResult`.
3. Reuse the Reporter.
4. Test report generation with fixture RDB files and no external dependencies.

## Output Modes

The prompt-first surface uses report-oriented terminology, but the currently wired CLI surface is narrower than the full Phase 3 route design.

| User-facing intent | Normalized mode | Result |
|--------------------|-----------------|--------|
| `summary` | prompt says `summary`, or `--report-format summary` | Rendered summary text from the assembled `AnalysisReport`, printed to stdout by default or written to `--output` when a file target is provided. |
| `report` + `docx` | prompt says `docx`, or `--report-format docx` | Full Word report. |
| `report` + `pdf` | future extension | Reserved for later Phase 3 extension work. |
| `report` + `html` | future extension | Reserved for later Phase 3 extension work. |

## Acceptance Criteria

- After Phase 3a completion, the current manual workflow is fully reproducible and generates documents of higher quality than historical reports.
- After Phase 3b and Phase 3c completion, all three routes work independently with consistent output structures.

## Wired Entry Points

- `dba-assistant ask "<prompt>"` is the primary user entry point.
- The retained CLI flags are `--config`, `--input`, `--profile`, `--report-format`, and `--output`.
- CLI input is normalized before application execution, so prompt-derived intent and explicit overrides converge into one request model.
- The current CLI debug shell routes local file inputs through Phase 3. `precomputed_dataset` and remote confirmation flows remain part of the Phase 3 service contract but are not yet first-class CLI modes.
- `dba_assistant.tools.analyze_rdb.analyze_rdb_tool` remains the public local-RDB analysis entry point.
- `dba_assistant.tools.generate_analysis_report.generate_analysis_report` remains the public generic report renderer export.

## Dependency Notes

- Depends on shared layers from Phase 1 and runtime assembly from Phase 2.
- Current repository scaffold status is tracked separately in `docs/phases/current-scaffold-status.md`.
