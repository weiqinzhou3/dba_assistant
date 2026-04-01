# DBA Assistant Master Plan v2

## Rules

- Deep Agent SDK is the runtime foundation.
- AGENTS.md is the global policy and security boundary layer.
- Skill is the basic unit for a single DBA scenario.
- Tool is a business action exposed to the Agent.
- Adaptor is the integration boundary for external systems.
- Abstractions are introduced on demand, but when multiple Skills exhibit the same pattern, it must be extracted into a shared layer.
- Phase 1 remains offline, read-only, report-generation only.
- No custom runtime framework is introduced until proven necessary by real complexity.
- Dangerous write operations must integrate a human confirmation mechanism in later phases.

## Reference File Constraints

- This project downloads `claude-code-source-code` locally as a design reference input.
- The following 3 documents are placed under `src` as reference materials:
  - Claude Code Prompt System Overview
  - Claude Code Skill Mechanism & Built-in Skills Overview
  - Claude Code Built-in Tools & External Invocation System Overview
- The role of the above source code and documents is "reference layer", not a runtime dependency of this project.
- Direct copying of runtime frameworks from `claude-code-source-code` as the basis for this project's implementation is not allowed.
- Design concepts such as prompt organization, skill mechanism, tool layering, permission boundaries, dynamic discovery, and context governance may be referenced.
- The existence of reference files must not alter this project's architectural direction; this project remains built on Deep Agent SDK as the runtime foundation.
- When reference files conflict with this master plan, this master plan takes precedence.
- Reference files under `src` must be isolated from business implementation directories to prevent accidental import as production modules.
- Reference files are primarily used to:
  - Help Codex / Claude Code understand the organizational patterns of skills, tools, and prompts.
  - Serve as architecture design samples rather than direct implementation reuse.
  - Provide reference for this project's subsequent skill mechanism, tool layering, permission, and audit design.
- The production code, directory structure, naming conventions, and execution flows output by this project must follow the repository's own standards and must not be reverse-dominated by the reference repository.

---

## Core Architecture Concepts

### Collector Layer

All Skills share a unified data collection abstraction. The Collector Layer is responsible for hiding data source differences and providing normalized structured data to Skills.

**Two collection paths:**

| Path | Description | Phase |
|------|-------------|-------|
| Offline | Read existing source data from local files/directories (RDB files, inspection bundles, CSV/JSON, etc.) | Available from Phase 1 |
| Remote | Collect data in real-time via Redis connections, SSH tunnels, API calls, etc. | Gradually introduced from Phase 2 |

**Design principles:**

- Each Skill declares the **data contract** it requires (which fields/structures), without concern for data origin.
- Collectors implement specific collection logic and output a unified intermediate data structure.
- Offline Collectors and Remote Collectors implement the same interface, enabling transparent switching at the Skill layer.
- Remote collection involves connection credentials, which must be managed through Adaptors, never hardcoded.

### Reporter Layer

All Skills share a unified output abstraction. The Reporter Layer is responsible for rendering Skill analysis results into different formats.

**Supported output modes:**

| Mode | Format | Description |
|------|--------|-------------|
| report | `.docx` | Full Word report with cover page, table of contents, charts, and risk grading |
| report | `.pdf` | Full PDF report (converted from Word or generated directly) |
| report | `.html` | Full HTML report, viewable and shareable in browsers |
| summary | stdout | Structured conclusion summary only, no file generated, suitable for quick review and pipeline chaining |

**Design principles:**

- Each Skill's core logic is only responsible for producing an **analysis result data structure** (format-agnostic).
- The Reporter receives the analysis result and renders it into the target format based on `output_mode` and `output_format`.
- Report templates are separated from Skill logic, stored in an independent directory, and support iterative optimization.
- Word/PDF/HTML reports share the same content structure definition, avoiding separate logic for each format.

### Report Template System

Historical reports serve as **reference samples** for input, but are not used directly as templates. The project needs to establish its own standardized report template system.

**Design principles:**

- Historical reports are stored in `references/report-samples/` for analyzing content structure and formatting style.
- The project maintains its own standard report templates in `templates/reports/`.
- Templates define the report skeleton (section order, heading hierarchy, table styles, cover layout, etc.) without containing specific data.
- Initial templates reference historical reports but incorporate standardization improvements (layout consistency, risk grading normalization, readability optimization, etc.).
- Templates are independent of Skills; multiple Skills can share base template components (e.g., cover template, risk level styles, disclaimer blocks).

---

## Skill Universal Contract

Each Skill must declare the following in its `SKILL.md`:

```yaml
skill:
  name: skill name
  description: one-line description

input_contract:
  required_data:          # Data fields/structures the Skill requires
    - name: field name
      type: type
      description: description
  supported_collectors:   # Supported collection paths
    - offline             # Offline file input
    - remote-redis        # Direct Redis connection
    - remote-ssh          # SSH collection
    - remote-mysql        # MySQL query
  parameters:             # User-configurable parameters
    - name: parameter name
      type: type
      default: default value
      description: description

output_contract:
  analysis_schema:        # Data structure definition for analysis results
  supported_modes:
    - report              # Full report
    - summary             # Summary conclusion
  supported_formats:      # Supported formats in report mode
    - docx
    - pdf
    - html
  default_mode: report
  default_format: docx
```

---

## Directory Structure

```
dba-assistant/
├── AGENTS.md                          # Global policy and security boundaries
├── master-plan.md                     # This file
├── src/
│   ├── core/                          # Core shared layer
│   │   ├── collector/                 # Collector Layer
│   │   │   ├── types.py               # Collection interfaces and data contract types
│   │   │   ├── offline-collector.py   # Offline file collection base class
│   │   │   └── remote-collector.py    # Remote collection base class (Phase 2+)
│   │   ├── reporter/                  # Reporter Layer
│   │   │   ├── types.py               # Output interfaces and config types
│   │   │   ├── docx-reporter.py       # Word report renderer
│   │   │   ├── pdf-reporter.py        # PDF report renderer
│   │   │   ├── html-reporter.py       # HTML report renderer
│   │   │   └── summary-reporter.py    # Stdout summary renderer
│   │   ├── analyzer/                  # Analysis infrastructure
│   │   │   └── types.py               # Common analysis result types
│   │   └── audit/                     # Audit logging (Phase 5)
│   │       └── logger.py
│   ├── adaptors/                      # External system integrations
│   │   ├── redis-adaptor.py           # Redis connection management
│   │   ├── ssh-adaptor.py             # SSH connection management
│   │   ├── mysql-adaptor.py           # MySQL connection management
│   │   └── filesystem-adaptor.py      # Local filesystem access
│   ├── skills/                        # Business skills
│   │   ├── redis-rdb-analysis/
│   │   │   ├── SKILL.md
│   │   │   ├── collectors/            # Skill-specific collector implementations
│   │   │   ├── analyzer.py            # Analysis logic
│   │   │   └── index.py
│   │   ├── redis-inspection-report/
│   │   │   ├── SKILL.md
│   │   │   ├── collectors/
│   │   │   ├── analyzer.py
│   │   │   └── index.py
│   │   └── redis-cve-report/
│   │       ├── SKILL.md
│   │       ├── collectors/
│   │       ├── analyzer.py
│   │       └── index.py
│   ├── tools/                         # Tool registrations for the Agent
│   └── references/                    # Reference docs (isolated, not importable)
│       ├── claude-code-source-code/
│       └── docs/
├── templates/                         # Report templates
│   └── reports/
│       ├── shared/                    # Shared template components
│       │   ├── cover.py               # Cover page template
│       │   ├── risk-level-styles.py   # Risk level styling
│       │   ├── disclaimer.py          # Disclaimer block
│       │   └── table-styles.py        # Table styles
│       ├── rdb-analysis/              # RDB analysis report template
│       ├── inspection/                # Inspection report template
│       └── cve/                       # CVE report template
├── references/
│   └── report-samples/                # Historical report samples (reference only)
│       ├── README.md                  # Note: reference samples only
│       ├── rdb-sample-*.docx
│       └── inspection-sample-*.docx
├── tests/
│   ├── fixtures/                      # Test data
│   ├── unit/
│   └── e2e/
└── package.json
```

---

## Phased Plan

### Phase 1: Architecture Foundation & Shared Layers

- Status: Planning
- **Goal:** Establish the repository structure and deliver the interface definitions and offline implementations for the Collector / Reporter / Template shared layers.

**Tasks:**

1. Establish repository directory structure and create AGENTS.md.
2. Define Collector interfaces and types (`core/collector/types.py`).
   - Declare `ICollector<TInput, TOutput>` interface.
   - Implement `OfflineCollector` base class: read data from local files/directories, validate format, output structured data.
   - Remote Collector: interface definition only, no implementation.
3. Define Reporter interfaces and types (`core/reporter/types.py`).
   - Declare `IReporter<TAnalysis>` interface: receive analysis result data structure, output target format.
   - Implement `DocxReporter` base class: render analysis results into Word documents based on templates.
   - Implement `SummaryReporter`: format analysis results into terminal-readable structured text output.
   - PDF and HTML Reporters: interface definition only, no implementation.
4. Establish the report template system.
   - Create `templates/reports/shared/` and implement shared components: cover page, risk level styles, disclaimer, etc.
   - Analyze historical report samples (placed in `references/report-samples/`), extract content structure, and identify areas for improvement.
   - Build initial standard template skeletons for the RDB analysis and inspection reports.
5. Establish the reference file isolation directory (`src/references/`) and create a README explaining usage constraints.
6. Set up the base testing framework and write unit tests for the Collector and Reporter interfaces.

**Acceptance criteria:**
- The Collector interface can be called by Skills; the offline path can read local files and output structured data.
- The Reporter interface can be called by Skills; at minimum DocxReporter and SummaryReporter are functional.
- Template skeletons are ready and can render a minimal Word document with a cover page, headings, and tables.
- Tests pass.

---

### Phase 2: Runtime Assembly & Remote Collection Foundation

- Status: Planning
- **Goal:** Register skills and tools via the SDK, configure the LLM, and implement the remote collection path.

**Tasks:**

1. Register skills and tools through Deep Agent SDK to complete runtime assembly.
2. Configure a working LLM setup (model selection, token limits, retry strategy).
3. Implement Remote Collector infrastructure:
   - `RedisAdaptor`: manage Redis connections (supporting direct connections and SSH tunnels), wrapping INFO, CONFIG GET, SLOWLOG, CLIENT LIST, and other commands.
   - `SSHAdaptor`: manage SSH connections, supporting remote command execution and file transfer.
   - `MySQLAdaptor`: manage MySQL connections, supporting SQL query execution and result export.
4. All remote collection paths are marked as **read-only**; no write operations are executed.
5. Implement PDF Reporter and HTML Reporter (if complexity is manageable; otherwise defer to post-Phase 4).

**Acceptance criteria:**
- The Agent can invoke registered skills through the SDK.
- At least one remote Adaptor (Redis direct connection) is functional.
- The runtime remains lightweight with no custom framework.

---

### Phase 3: Skill One — Redis RDB Memory Analysis Report

- Status: Planning
- **Goal:** Implement the full pipeline for RDB memory analysis, supporting multiple input paths and output modes.

**Input paths (by priority):**

| Path | Description | Data Flow | Phase |
|------|-------------|-----------|-------|
| A: Full custom pipeline | Reproduce the current manual workflow | Multiple RDB files → rdb-tools parsing → Write to MySQL → Execute existing SQL analysis → Generate report | 3a |
| B: Skip parsing & import | Analysis data already exists in MySQL | MySQL query results / Pre-exported CSV → Generate report | 3b |
| C: Pure offline direct analysis | No external tool or database dependency | Multiple RDB files → Python/Node direct parsing → In-memory statistical analysis → Generate report | 3c |

**Implementation breakdown:**

#### Phase 3a: Path A — Full Custom Pipeline (Deliver First)

1. Write `skills/redis-rdb-analysis/SKILL.md` defining input/output contracts.
2. Implement RDB Offline Collector:
   - Accept RDB file paths (supporting multiple files and directory scanning).
   - Invoke rdb-tools to parse RDB files, outputting structured intermediate data.
   - Write parsed results to MySQL (via MySQLAdaptor).
3. Implement RDB Analyzer:
   - Execute the existing SQL statement set for aggregation analysis (Top Keys, memory distribution, TTL distribution, data type ratios, etc.).
   - Output a standardized `RdbAnalysisResult` data structure.
4. Implement report generation:
   - Reference historical report samples to build the RDB analysis report standard template.
   - Improve known issues in historical reports: layout consistency, chart readability, risk grading standardization.
   - Render into the target format via the Reporter Layer.
5. Testing: given fixture RDB files + MySQL environment, end-to-end generation of a complete report.

#### Phase 3b: Path B — Generate Report from Existing MySQL Data

1. Implement MySQL Query Collector: query existing analysis data from MySQL directly, or read from pre-exported CSV/JSON.
2. Reuse the Analyzer and Reporter from Phase 3a.
3. Testing: given MySQL fixture data, generate a report.

#### Phase 3c: Path C — Pure Offline Direct Analysis

1. Implement RDB Direct Parser Collector: parse RDB files directly using Python/Node libraries, without rdb-tools or MySQL.
2. Implement a lightweight Analyzer: perform statistics in memory, outputting the same `RdbAnalysisResult`.
3. Reuse the Reporter.
4. Testing: given fixture RDB files, generate a report with no external dependencies.

**Output modes (shared across all paths):**

| Mode | Description |
|------|-------------|
| `--output=report --format=docx` | Full Word report |
| `--output=report --format=pdf` | Full PDF report |
| `--output=report --format=html` | Full HTML report |
| `--output=summary` | Stdout: risk item summary + Top Key list + remediation recommendations, no file generated |

**Acceptance criteria:**
- After Phase 3a completion, the current manual workflow is fully reproducible, generating documents of higher quality than historical reports.
- After Phase 3b/3c completion, all three paths work independently with consistent output structures.

---

### Phase 4: Skill Two — Redis Inspection Report

- Status: Planning
- **Goal:** Implement the full pipeline for Redis inspection reports, supporting offline source data and remote real-time collection, with multiple output modes.

**Input paths:**

| Path | Description | Data Flow | Phase |
|------|-------------|-----------|-------|
| A: Offline source data | Multiple source data files already collected locally | Local file directory → Parse & normalize → Analyze → Generate report | 4a |
| B: Remote real-time collection | Connect to Redis / SSH for live collection | Redis INFO + CONFIG + SLOWLOG + CLIENT LIST + ... → Analyze → Generate report | 4b |

#### Phase 4a: Offline Source Data Path (Deliver First)

1. Write `skills/redis-inspection-report/SKILL.md` defining inspection scope, data contract, and output contract.
2. Implement Inspection Offline Collector:
   - Accept a local source data directory path.
   - Auto-detect and parse source data files in multiple formats (INFO output, CONFIG output, SLOWLOG export, custom collection script output, etc.).
   - Output a normalized `InspectionRawData` structure.
3. Implement Inspection Analyzer:
   - Inspection coverage: basic information, configuration audit, persistence status, replication topology, memory usage, slow query analysis, connection status, security configuration, known risk items.
   - Each inspection item produces: current value, expected value/threshold, risk level (Normal / Warning / Critical / Urgent), remediation recommendation.
   - Output a standardized `InspectionAnalysisResult`.
4. Implement report generation:
   - Reference historical inspection report samples to build the standard inspection report template.
   - **Template standardization improvements:**
     - Unified cover page information (client, environment, inspection date, inspector).
     - Executive summary added (single-page overview: total inspection items, risk count by level, core conclusions).
     - Unified inspection item detail table format (Check Item / Current Value / Recommended Value / Risk Level / Recommendation).
     - Risk grading uses a unified color and icon system.
     - Remediation recommendations sorted by priority with action steps.
     - Evidence appendix added (raw output of key commands).
   - Render into the target format via the Reporter Layer.
5. Testing: given fixture offline source data, end-to-end generation of both a complete report and summary output.

#### Phase 4b: Remote Real-time Collection Path

1. Implement Inspection Remote Collector:
   - Execute the inspection command sequence via RedisAdaptor.
   - Collect system-level information via SSHAdaptor (if needed).
   - Output the same `InspectionRawData` structure.
2. Reuse the Analyzer and Reporter from Phase 4a.
3. All remote collection is strictly read-only; no configuration modifications are executed.
4. Testing: connect to a test Redis instance, complete end-to-end collection and report generation.

**Output modes (same as Phase 3):**

| Mode | Description |
|------|-------------|
| `--output=report --format=docx` | Full Word inspection report |
| `--output=report --format=pdf` | Full PDF inspection report |
| `--output=report --format=html` | Full HTML inspection report |
| `--output=summary` | Stdout: risk item list + level statistics + remediation priority ranking, no file generated |

**Acceptance criteria:**
- After Phase 4a completion, offline source data can produce a standardized, clearly structured document of higher quality than historical reports.
- After Phase 4b completion, the remote collection pipeline is functional with output structures consistent with the offline path.
- Summary mode provides conclusions directly in the terminal without opening a file.

---

### Phase 5: Audit & Security Baseline

- Status: Planning
- **Goal:** Add execution audit capabilities in preparation for future dangerous operations.

**Tasks:**

1. Implement lightweight JSONL execution logging (`core/audit/logger.py`).
2. Recorded content:
   - Skill name and version.
   - Input summary (data source, file list, connection target — sanitized).
   - Tool invocation sequence and duration.
   - Output path and output mode.
   - Execution result (success / failure / partial failure).
   - Error messages and stack traces (if any).
3. Retroactively add audit instrumentation to Phase 3 and Phase 4 Skills.
4. Document the future interrupt-based human confirmation strategy (design doc only, no implementation).

**Acceptance criteria:**
- Each Skill execution generates a complete JSONL audit record in the `logs/` directory.
- Audit logging does not impact Skill execution performance.

---

### Phase 6: Skill Three — Redis CVE Security Report

- Status: Planning
- **Goal:** Implement Redis CVE intelligence collection and report generation, supporting multi-source aggregation and version impact assessment.

**Input paths:**

| Path | Description |
|------|-------------|
| Online fetching | Real-time fetching from NVD, MITRE, Redis official advisories, GitHub Security Advisories |
| Offline data bundle | Generate report from pre-downloaded CVE data files (for air-gapped environments or testing) |

**Tasks:**

1. Write `skills/redis-cve-report/SKILL.md` defining the input contract:
   - Required: time range (supports natural language parsing, e.g., "last three months").
   - Optional: Redis version range (e.g., `6.2.0-7.0.15`) for impact assessment.
   - Optional: data source priority configuration.
2. Implement individual data source Collectors:
   - NIST NVD CVE API: fetch Redis-related CVEs by time range with exponential backoff retry.
   - MITRE/CVE: query Redis-related entries.
   - Redis official security advisory page: scrape advisory content.
   - GitHub Security Advisories API: query the `redis/redis` repository.
   - Each Collector runs independently; a single failure does not block the overall pipeline.
3. Implement CVE Analyzer:
   - Merge and deduplicate using CVE ID as the primary key; CVSS scores use NVD as the authoritative source.
   - Sort by CVSS score descending.
   - When a version range is provided, invoke the LLM to assess impact status per entry (Affected / Not Affected / To Be Confirmed).
   - When no version range is provided, uniformly annotate all entries as "Requires manual assessment against actual version".
   - Record each data source's availability status and fetch timestamp.
4. Implement report generation:
   - Render via the Reporter Layer, reusing shared template components.
   - Report content: cover page, executive summary, CVE detail table, impact assessment results (if applicable), data source notes (with fetch timestamps and availability status), disclaimer.
5. Testing: given mock Collector responses as fixtures, end-to-end generation of a complete report.

**Output modes (same as above):**
- `report` (docx / pdf / html)
- `summary` (stdout)

**Acceptance criteria:**
- Multi-source aggregation is functional with graceful degradation and logging for source failures.
- LLM impact assessment works when a version range is provided.
- Reports include complete data source provenance information.

---

### Phase 7: Report Template Continuous Optimization

- Status: Ongoing alongside each Phase
- **Goal:** Continuously improve template quality based on actual generated reports.

**Ongoing tasks:**
- After each Skill's first report is generated, review output quality, compare against historical reports, and identify areas for improvement.
- Optimization focus: layout professionalism, information density, readability, risk visualization, remediation recommendation actionability.
- Collect usage feedback and solidify high-frequency adjustments into template defaults.

---

### Phase 8: Future Expansion

- Status: Deferred
- Integrate dangerous write operations requiring approval (e.g., CONFIG SET, SLAVEOF) through an interrupt mechanism for human confirmation.
- Only introduce a general-purpose framework when complexity has been proven.
- Expand to additional DBA skills (MySQL, MongoDB, etc.) after the Redis scope is stabilized.

---

## Cross-Phase Dependencies

```
Phase 1 (Shared layer interfaces + Offline Collector + DocxReporter + SummaryReporter + Template skeletons)
  │
  ├─→ Phase 2 (Runtime assembly + Remote Adaptors + Additional Reporter formats)
  │     │
  │     ├─→ Phase 3a (RDB full pipeline: rdb-tools → MySQL → SQL → Report)
  │     │     ├─→ Phase 3b (Generate report from existing MySQL data)
  │     │     └─→ Phase 3c (Pure offline direct RDB parsing)
  │     │
  │     └─→ Phase 4a (Inspection offline source data → Report)
  │           └─→ Phase 4b (Inspection remote collection → Report)
  │
  ├─→ Phase 5 (Audit logging, retroactively instrument Phase 3/4)
  │
  └─→ Phase 6 (CVE report, depends on Reporter Layer + LLM config)

Phase 7 (Template optimization) runs continuously across Phase 3 ~ Phase 6.
```

---

## Execution Sequence

1. Complete phase design review.
2. Complete phase code implementation.
3. Run unit tests, end-to-end tests, and smoke checks.
4. Review output quality (especially for report-generating Skills — compare against historical reports to confirm improvement).
5. Update phase documentation, clearly stating outputs and next-phase entry criteria.

## Key Design Decision Log

| Decision | Rationale |
|----------|-----------|
| Extract Collector / Reporter as shared layers | All 3 Skills share "multiple input sources + multiple output formats" requirements; without extraction, significant code duplication would result |
| Deliver offline paths first | Offline is the current real-world workflow; enables immediate end-to-end validation without network dependencies |
| Historical reports as reference samples, not direct templates | Historical report formatting quality is insufficient; standardization improvements are needed; direct reuse would perpetuate existing issues |
| Report templates independent of Skills | Templates can be iterated independently, share components across Skills, and template changes don't require Skill code modifications |
| Summary mode as a first-class citizen | The need to quickly view conclusions is no less frequent than full reports; it cannot be treated as an auxiliary feature |
| Phase 3 split into 3a/3b/3c | The three paths have entirely different complexities and dependencies; bundled delivery carries high risk; splitting enables independent acceptance |
| All remote collection strictly read-only | Security baseline: inspection and analysis phases must never modify the target system's state |
