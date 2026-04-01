# Phase 6: Skill Three — Redis CVE Security Report

## Status

Planning

## Goal

Implement Redis CVE intelligence collection and report generation, supporting multi-source aggregation and version impact assessment.

## Input Paths

- Online fetching from NVD, MITRE, Redis official advisories, and GitHub Security Advisories
- Offline data bundles for air-gapped environments or testing

## Tasks

1. Write `skills/redis-cve-report/SKILL.md` defining the input contract.
   - Required: time range, including natural-language forms such as "last three months"
   - Optional: Redis version range for impact assessment
   - Optional: data source priority configuration
2. Implement individual data source Collectors.
   - NIST NVD CVE API
   - MITRE/CVE
   - Redis official security advisory page
   - GitHub Security Advisories API for `redis/redis`
   - Each Collector must run independently so one source failure does not block the pipeline
3. Implement the CVE Analyzer.
   - Merge and deduplicate by CVE ID
   - Treat NVD CVSS as authoritative
   - Sort by CVSS descending
   - When a version range is provided, invoke the LLM to assess impact status
   - When no version range is provided, mark entries as requiring manual version assessment
   - Record each data source's availability status and fetch timestamp
4. Implement report generation through the Reporter Layer, reusing shared template components.
   - Include cover page, executive summary, CVE detail table, impact assessment results where applicable, data source notes, and disclaimer
5. Test end to end with mock Collector responses and fixture data.

## Output Modes

- `report` in `docx`, `pdf`, or `html`
- `summary` in stdout

## Acceptance Criteria

- Multi-source aggregation is functional with graceful degradation when some sources fail.
- LLM impact assessment works when a version range is provided.
- Reports include complete data source provenance information.

## Dependency Notes

- Depends on Reporter Layer capability and LLM configuration from earlier phases.
- Current repository scaffold status is tracked separately in `docs/phases/current-scaffold-status.md`.
