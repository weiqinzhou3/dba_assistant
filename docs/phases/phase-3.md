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

The prompt-first surface uses report-oriented terminology, but the rendered artifact still depends on the selected output mode and format.

| User-facing intent | Normalized mode | Result |
|--------------------|-----------------|--------|
| `summary` | `--output=summary` | Stdout summary with risk items, Top Key list, and remediation recommendations. |
| `report` + `docx` | `--output=report --format=docx` | Full Word report. |
| `report` + `pdf` | `--output=report --format=pdf` | Full PDF report. |
| `report` + `html` | `--output=report --format=html` | Full HTML report. |

## Acceptance Criteria

- After Phase 3a completion, the current manual workflow is fully reproducible and generates documents of higher quality than historical reports.
- After Phase 3b and Phase 3c completion, all three routes work independently with consistent output structures.

## Wired Entry Points

- `dba-assistant ask "<prompt>"` is the primary user entry point.
- The retained CLI flags are `--config`, `--input`, `--profile`, `--report-format`, and `--output`.
- CLI input is normalized before application execution, so prompt-derived intent and explicit overrides converge into one request model.
- `dba_assistant.tools.analyze_rdb.analyze_rdb_tool` remains the public local-RDB analysis entry point.
- `dba_assistant.tools.generate_analysis_report.generate_analysis_report` remains the public generic report renderer export.

## Dependency Notes

- Depends on shared layers from Phase 1 and runtime assembly from Phase 2.
- Current repository scaffold status is tracked separately in `docs/phases/current-scaffold-status.md`.
