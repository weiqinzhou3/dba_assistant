# DBA Assistant Master Plan v2

## Rules

- Deep Agent SDK is the runtime foundation.
- The repository-wide execution shape is `CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`.
- AGENTS.md is the global policy and security boundary layer.
- Skill is the basic unit for a single DBA scenario.
- Tool is a business action exposed to the Agent.
- Adaptor is the integration boundary for external systems.
- Interface surfaces stay thin and prompt-first; request normalization happens before Deep Agent execution.
- Abstractions are introduced on demand, but when multiple Skills exhibit the same pattern, it must be extracted into a shared layer.
- Phase 1 remains offline, read-only, report-generation only.
- No custom runtime framework is introduced until proven necessary by real complexity.
- Dangerous write operations must integrate unified-agent human approval through HITL / `interrupt_on` in later phases.

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

### Unified Execution Shape

All user-facing surfaces must converge into the same execution path:

`CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

**Design principles:**

- CLI, API, and WebUI are interaction surfaces, not orchestration systems.
- A shared interface-adapter layer is responsible for request normalization, secret extraction, explicit override handling, and artifact-oriented boundary behavior.
- One unified Deep Agent is responsible for selecting Skills and Tools from prompt intent plus normalized runtime inputs.
- Business routing must not be hardcoded in CLI handlers.
- Future capabilities must extend this path rather than introduce parallel runtimes or surface-specific routers.

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

### Interface Adapter Layer

The Interface Adapter Layer is the shared boundary between surfaces and the unified Deep Agent.

**Responsibilities:**

- Load repository configuration.
- Normalize prompt-first requests into a shared structured request object.
- Extract secrets and structured runtime inputs without forcing users into parameter-only workflows.
- Apply explicit surface overrides when present.
- Preserve one contract that future CLI, API, and WebUI surfaces can all reuse.

### Unified Orchestrator Layer

The unified orchestrator constructs one Deep Agent with:

- repository memory from `AGENTS.md`
- repository skills
- repository tools
- shared runtime configuration
- approval rules for sensitive tool calls

The orchestrator is responsible for agent execution and approval-aware resumption, not for domain-specific business logic.

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
├── CLAUDE.md                          # Symlink / compatibility entry
├── README.md
├── docs/
│   ├── dba_assistant_master_plan_en.md
│   ├── phases/
│   │   ├── phase-1.md
│   │   ├── ...
│   │   └── phase-8.md
│   └── superpowers/
├── config/
│   ├── config.yaml
│   └── profiles/
├── src/
│   ├── dba_assistant/
│   │   ├── application/               # Shared request models, explicit surface fields, and secret scrubbing
│   │   ├── interface/                 # CLI / API / WebUI shared boundary
│   │   ├── orchestrator/              # Unified Deep Agent assembly and tool exposure
│   │   ├── deep_agent_integration/    # Deep Agents runtime support
│   │   ├── prompts/                   # Externalized system prompts and agent instructions
│   │   ├── core/                      # Shared collector / reporter / analyzer / audit layers
│   │   ├── adaptors/                  # External system integrations
│   │   └── tools/                     # Agent-visible business tools
│   ├── claude-code-source-code/       # Reference-only source layer
│   └── docs/                          # Reference-only docs layer
├── skills/                            # Repository skill docs
│   ├── redis-rdb-analysis/
│   ├── redis-inspection-report/
│   └── redis-cve-report/
├── templates/                         # Report templates
│   └── reports/
│       ├── shared/                    # Shared template components
│       ├── rdb-analysis/              # RDB analysis report template
│       ├── inspection/                # Inspection report template
│       └── cve/                       # CVE report template
├── references/
│   └── report-samples/                # Historical report samples (reference only)
│       └── ...
├── tests/
│   ├── fixtures/
│   ├── unit/
│   └── e2e/
└── pyproject.toml
```

---

## Phased Plan

### Phase 1: Architecture Foundation & Shared Layers

- Status: Planning
- **Goal:** Establish the repository structure and deliver the interface definitions and offline implementations for the Collector / Reporter / Template shared layers.

**Tasks:**

1. Establish repository directory structure and create AGENTS.md.
2. Define Collector interfaces and types under `src/dba_assistant/core/collector/`.
   - Declare `ICollector<TInput, TOutput>` interface.
   - Implement `OfflineCollector` base class: read data from local files/directories, validate format, output structured data.
   - Remote Collector: interface definition only, no implementation.
3. Define Reporter interfaces and types under `src/dba_assistant/core/reporter/`.
   - Declare `IReporter<TAnalysis>` interface: receive analysis result data structure, output target format.
   - Implement `DocxReporter` base class: render analysis results into Word documents based on templates.
   - Implement `SummaryReporter`: format analysis results into terminal-readable structured text output.
   - PDF and HTML Reporters: interface definition only, no implementation.
4. Establish the report template system.
   - Create `templates/reports/shared/` and implement shared components: cover page, risk level styles, disclaimer, etc.
   - Analyze historical report samples (placed in `references/report-samples/`), extract content structure, and identify areas for improvement.
   - Build initial standard template skeletons for the RDB analysis and inspection reports.
5. Establish the reference file isolation rules for `src/claude-code-source-code/` and `src/docs/`, and create a README explaining usage constraints.
6. Set up the base testing framework and write unit tests for the Collector and Reporter interfaces.

**Acceptance criteria:**
- The Collector interface can be called by Skills; the offline path can read local files and output structured data.
- The Reporter interface can be called by Skills; at minimum DocxReporter and SummaryReporter are functional.
- Template skeletons are ready and can render a minimal Word document with a cover page, headings, and tables.
- Tests pass.

---

### Phase 2: Runtime Assembly & Remote Collection Foundation

- Status: Planning
- **Goal:** Establish the shared interface-adapter boundary, unified Deep Agent orchestration, provider-capable runtime assembly, and the first real read-only remote collection path.

**Tasks:**

1. Implement the repository-owned Deep Agents runtime assembly.
   - configure model loading
   - configure backend / memory / skill sources
   - avoid introducing a custom runtime framework
2. Implement the shared interface-adapter boundary.
   - normalize prompt-first requests into one structured application request
   - preserve compatibility with future CLI, API, and WebUI surfaces
3. Implement the unified orchestrator.
   - construct one Deep Agent with repository skills and tools
   - let the Deep Agent select capabilities instead of relying on CLI-side routing
4. Implement Remote Collector infrastructure:
   - `RedisAdaptor`: manage Redis connections for read-only Redis inspection and discovery
   - `SSHAdaptor`: host-access abstraction for later phases
   - `MySQLAdaptor`: staging / query abstraction for later phases
5. Keep all remote collection paths **read-only** in this phase.
6. Establish the approval model for future sensitive tool calls through unified-agent HITL / `interrupt_on`.
7. Implement PDF Reporter and HTML Reporter if complexity is manageable; otherwise defer them.

**Acceptance criteria:**
- Prompt-first requests can enter the shared boundary and reach the unified Deep Agent.
- The Agent can invoke registered skills and tools through the SDK.
- At least one remote Adaptor (Redis direct connection) is functional.
- The runtime remains lightweight with no custom framework.

---

### Phase 3: Skill One — Redis RDB Memory Analysis Report

- Status: Planning
- **Goal:** Implement the `redis_rdb_analysis` skill under the unified Deep Agent architecture, supporting multiple input paths, profile-driven reporting, and shared output modes.

**Input paths (by priority):**

| Path | Description | Data Flow | Phase |
|------|-------------|-----------|-------|
| A: `legacy_sql_pipeline` | Reproduce the current manual workflow | Multiple RDB files → rdb-tools parsing → Write to MySQL → Execute existing SQL analysis → Generate report | 3a |
| B: `precomputed_dataset` | Analysis data already exists in MySQL or exported form | MySQL query results / Pre-exported CSV or JSON → Generate report | 3b |
| C: `direct_memory_analysis` | No external tool or database dependency | Multiple RDB files → direct parsing → In-memory statistical analysis → Generate report | 3c |

**Architectural constraints:**

- The skill is selected by the unified Deep Agent from prompt intent and normalized inputs.
- Prompt can select a profile such as `generic` or `rcs`, and can provide bounded analysis overrides.
- Prompt can influence analysis focus, but Phase 3 does not rely on unconstrained SQL generation.
- Unless explicitly requested or required by the legacy workflow, the default analysis path should not depend on MySQL staging.
- If the input source is a remote Redis target and an RDB acquisition step is required, the acquisition must be approval-gated inside the unified-agent flow.

**Implementation breakdown:**

#### Phase 3a: `legacy_sql_pipeline` (Deliver First)

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

#### Phase 3b: `precomputed_dataset`

1. Implement MySQL Query Collector: query existing analysis data from MySQL directly, or read from pre-exported CSV/JSON.
2. Reuse the Analyzer and Reporter from Phase 3a.
3. Testing: given MySQL fixture data, generate a report.

#### Phase 3c: `direct_memory_analysis`

1. Implement RDB Direct Parser Collector: parse RDB files directly using Python/Node libraries, without rdb-tools or MySQL.
2. Implement a lightweight Analyzer: perform statistics in memory, outputting the same `RdbAnalysisResult`.
3. Reuse the Reporter.
4. Testing: given fixture RDB files, generate a report with no external dependencies.

**Output modes (shared across all paths and routed through the shared report renderer):**

| Mode | Description |
|------|-------------|
| `report` + `docx` | Full Word report |
| `report` + `pdf` | Full PDF report |
| `report` + `html` | Full HTML report |
| `summary` | Structured summary output for prompt-first interaction and chaining |

**Acceptance criteria:**
- After Phase 3a completion, the current manual workflow is fully reproducible, generating documents of higher quality than historical reports.
- After Phase 3b/3c completion, all three paths work independently with consistent output structures.

---

### Phase 4: Skill Two — Redis Inspection Report

- Status: Planning
- **Goal:** Implement the `redis_inspection_report` skill as a Redis inspection capability under the unified Deep Agent architecture.

**Input paths:**

| Path | Description | Data Flow | Phase |
|------|-------------|-----------|-------|
| A: Offline source data | Multiple source data files already collected locally | Local evidence bundle → Parse & normalize → Analyze → Generate report | 4a |
| B: Remote real-time collection | Connect to Redis / host access for live collection | Redis INFO + CONFIG + SLOWLOG + CLIENT LIST + host evidence → Analyze → Generate report | 4b |

**Architectural constraints:**

- The unified Deep Agent chooses this skill from prompt intent; no dedicated CLI-only route is assumed.
- Collection remains read-only in this phase.
- Inspection output reuses the shared report model and rendering path.
- Any future risky host or database action must be approval-gated inside the unified-agent execution path.

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

**Output modes (same report contract as Phase 3):**
- `report` in `docx` / `pdf` / `html`
- `summary` for prompt-first interaction

**Acceptance criteria:**
- After Phase 4a completion, offline source data can produce a standardized, clearly structured document of higher quality than historical reports.
- After Phase 4b completion, the remote collection pipeline is functional with output structures consistent with the offline path.
- Summary mode provides conclusions directly in the terminal without opening a file.

---

### Phase 5: Audit & Security Baseline

- Status: Planning
- **Goal:** Add execution audit and safety-baseline capabilities around the unified Deep Agent architecture.

**Tasks:**

1. Implement lightweight JSONL execution logging under `src/dba_assistant/core/audit/logger.py`.
2. Recorded content:
   - caller surface and normalized input summary (sanitized)
   - selected Skill / capability path
   - Tool invocation sequence and duration
   - approval and interruption events
   - output path and output mode
   - execution result (success / failure / partial failure / denied)
   - error messages and stack traces (if any)
3. Retroactively add audit instrumentation to Phase 3 and Phase 4 Skills.
4. Ensure future dangerous operations must pass through unified-agent approval and audit recording.

**Acceptance criteria:**
- Each unified-agent execution generates a complete JSONL audit record in the `logs/` directory.
- Approval-gated operations can be audited as first-class execution events.
- Audit logging does not materially impact execution performance.

---

### Phase 6: Skill Three — Redis CVE Security Report

- Status: Planning
- **Goal:** Implement the `redis_cve_report` skill under the unified Deep Agent architecture, supporting multi-source aggregation and version impact assessment.

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

**Architectural constraints:**

- The unified Deep Agent selects this skill from prompt intent.
- CVE-source collectors remain internal implementation components beneath the skill boundary.
- Reports reuse the shared report model and rendering path.

**Output modes (same shared report contract as above):**
- `report` (`docx` / `pdf` / `html`)
- `summary`

**Acceptance criteria:**
- Multi-source aggregation is functional with graceful degradation and logging for source failures.
- LLM impact assessment works when a version range is provided.
- Reports include complete data source provenance information.

---

### Phase 7: Report Template Continuous Optimization

- Status: Ongoing alongside each Phase
- **Goal:** Continuously improve shared report quality based on actual generated reports while preserving the unified architecture.

**Ongoing tasks:**
- After each Skill's first report is generated, review output quality, compare against historical reports, and identify areas for improvement.
- Optimization focus: layout professionalism, information density, readability, risk visualization, remediation recommendation actionability.
- Collect usage feedback and solidify high-frequency adjustments into template defaults.
- Ensure improvements land in the shared report model / renderer where possible, not in surface-specific rendering forks.

---

### Phase 8: Future Expansion

- Status: Deferred
- Integrate dangerous write operations requiring approval (e.g., CONFIG SET, SLAVEOF) through unified-agent HITL / `interrupt_on`.
- Only introduce a general-purpose framework when complexity has been proven.
- Expand to additional DBA skills (MySQL, MongoDB, etc.) after the Redis scope is stabilized, while preserving `CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`.

---

## Cross-Phase Dependencies

```
Phase 1 (Shared layer interfaces + Offline Collector + DocxReporter + SummaryReporter + Template skeletons)
  │
  ├─→ Phase 2 (Interface adapter + Unified Deep Agent + Remote Adaptors + Additional Reporter formats)
  │     │
  │     ├─→ Phase 3a (`legacy_sql_pipeline`)
  │     │     ├─→ Phase 3b (`precomputed_dataset`)
  │     │     └─→ Phase 3c (`direct_memory_analysis`)
  │     │
  │     └─→ Phase 4a (Inspection offline source data → Report)
  │           └─→ Phase 4b (Inspection remote collection → Report)
  │
  ├─→ Phase 5 (Audit logging, approval auditing, retroactively instrument Phase 3/4)
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
| One Deep Agent for all surfaces | CLI, API, and WebUI should reuse one orchestration path so business routing is not duplicated by surface |
| Prompt-first outside, structured boundary inside | User interaction remains natural-language-first while the application boundary preserves deterministic contracts for tools, approvals, and future surfaces |
| Dangerous operations go through HITL / `interrupt_on` | Sensitive tool calls must be gated inside the unified-agent flow, not by ad hoc surface-specific logic |
