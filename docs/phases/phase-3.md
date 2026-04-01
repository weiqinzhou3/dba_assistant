# Phase 3: Skill One — Redis RDB Memory Analysis Report

## Status

Planning

## Goal

Implement the full pipeline for RDB memory analysis, supporting multiple input paths and output modes.

## Input Paths

| Path | Description | Data Flow | Delivery Order |
|------|-------------|-----------|----------------|
| A: Full custom pipeline | Reproduce the current manual workflow | Multiple RDB files → `rdb-tools` parsing → write to MySQL → execute existing SQL analysis → generate report | Deliver first |
| B: Skip parsing and import | Analysis data already exists in MySQL | MySQL query results or pre-exported CSV → generate report | Deliver after Path A |
| C: Pure offline direct analysis | No external tool or database dependency | Multiple RDB files → Python or Node direct parsing → in-memory statistical analysis → generate report | Deliver after Path A |

## Implementation Breakdown

### Phase 3a: Path A — Full Custom Pipeline

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

### Phase 3b: Path B — Generate Report from Existing MySQL Data

1. Implement a MySQL Query Collector that queries existing analysis data from MySQL directly, or reads from pre-exported CSV or JSON.
2. Reuse the Analyzer and Reporter from Phase 3a.
3. Test report generation with MySQL fixture data.

### Phase 3c: Path C — Pure Offline Direct Analysis

1. Implement an RDB Direct Parser Collector using Python or Node libraries, without `rdb-tools` or MySQL.
2. Implement a lightweight Analyzer that performs in-memory statistics and outputs the same `RdbAnalysisResult`.
3. Reuse the Reporter.
4. Test report generation with fixture RDB files and no external dependencies.

## Output Modes

- `--output=report --format=docx`: full Word report
- `--output=report --format=pdf`: full PDF report
- `--output=report --format=html`: full HTML report
- `--output=summary`: stdout summary with risk items, Top Key list, and remediation recommendations

## Acceptance Criteria

- After Phase 3a completion, the current manual workflow is fully reproducible and generates documents of higher quality than historical reports.
- After Phase 3b and Phase 3c completion, all three paths work independently with consistent output structures.

## Dependency Notes

- Depends on shared layers from Phase 1 and runtime assembly from Phase 2.
- Current repository scaffold status is tracked separately in `docs/phases/current-scaffold-status.md`.
