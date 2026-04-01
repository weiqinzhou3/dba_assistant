# Phase 4: Skill Two — Redis Inspection Report

## Status

Planning

## Goal

Implement the full pipeline for Redis inspection reports, supporting offline source data and remote real-time collection, with multiple output modes.

## Input Paths

| Path | Description | Data Flow | Delivery Order |
|------|-------------|-----------|----------------|
| A: Offline source data | Multiple source data files already collected locally | Local file directory → parse and normalize → analyze → generate report | Deliver first |
| B: Remote real-time collection | Connect to Redis or SSH for live collection | Redis `INFO`, `CONFIG`, `SLOWLOG`, `CLIENT LIST`, system commands, and related data → analyze → generate report | Deliver after Path A |

## Implementation Breakdown

### Phase 4a: Offline Source Data Path

1. Write `skills/redis-inspection-report/SKILL.md` defining inspection scope, data contract, and output contract.
2. Implement the Inspection Offline Collector.
   - Accept a local source data directory path.
   - Auto-detect and parse multiple source data formats, including `INFO`, `CONFIG`, `SLOWLOG`, and custom collection outputs.
   - Output a normalized `InspectionRawData`.
3. Implement the Inspection Analyzer.
   - Cover basic information, configuration audit, persistence status, replication topology, memory usage, slow query analysis, connection status, security configuration, and known risk items.
   - For each inspection item, output current value, expected value or threshold, risk level, and remediation recommendation.
   - Output a standardized `InspectionAnalysisResult`.
4. Implement report generation.
   - Reference historical inspection reports to build a standard inspection template.
   - Standardize cover page information, executive summary, inspection detail tables, risk visualization, remediation prioritization, and evidence appendix structure.
   - Render through the Reporter Layer.
5. Test end to end with fixture offline source data, including full report output and summary output.

### Phase 4b: Remote Real-Time Collection Path

1. Implement the Inspection Remote Collector.
   - Execute the inspection command sequence through `RedisAdaptor`.
   - Collect system-level information through `SSHAdaptor` where needed.
   - Output the same `InspectionRawData`.
2. Reuse the Analyzer and Reporter from Phase 4a.
3. Keep all remote collection strictly read-only.
4. Test end to end against a test Redis instance.

## Output Modes

- `--output=report --format=docx`: full Word inspection report
- `--output=report --format=pdf`: full PDF inspection report
- `--output=report --format=html`: full HTML inspection report
- `--output=summary`: stdout summary with risk items, level statistics, and remediation priority ranking

## Acceptance Criteria

- After Phase 4a completion, offline source data can produce a standardized, clearly structured document of higher quality than historical reports.
- After Phase 4b completion, the remote collection pipeline is functional and its output structures remain consistent with the offline path.
- Summary mode provides conclusions directly in the terminal without opening a file.

## Dependency Notes

- Depends on shared layers from Phase 1 and remote/runtime foundations from Phase 2.
- Current repository scaffold status is tracked separately in `docs/phases/current-scaffold-status.md`.
