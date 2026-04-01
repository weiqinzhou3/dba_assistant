# DBA Assistant Repository Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Python-first, phase-oriented repository scaffold for DBA Assistant as a Deep Agent SDK-based project, without implementing runtime behavior or business logic.

**Architecture:** Preserve `src/claude-code-source-code/` and `src/docs/` as reference-only material. Introduce a single production package root at `src/dba_assistant/`, document Deep Agent SDK as the repository's runtime foundation, add phase documents under `docs/phases/`, and create contract-oriented placeholders for core layers, skills, tools, templates, and tests. Every created file is documentation or boundary scaffolding only. Runtime assembly is deferred, not removed from the architecture.

**Tech Stack:** Python 3.11+, `pyproject.toml`, Markdown, filesystem symlink, pytest-oriented test layout

**Git Note:** The current workspace is not a git repository. This plan uses verification checkpoints instead of commit checkpoints.

---

## File Structure Map

**Create or modify these root files:**

- Create: `AGENTS.md`
- Create: `CLAUDE.md` (symlink to `AGENTS.md`)
- Create: `README.md`
- Create: `.gitignore`
- Create: `pyproject.toml`

**Create these planning and phase files:**

- Create: `docs/phases/README.md`
- Create: `docs/phases/phase-1.md`
- Create: `docs/phases/phase-2.md`
- Create: `docs/phases/phase-3.md`
- Create: `docs/phases/phase-4.md`
- Create: `docs/phases/phase-5.md`
- Create: `docs/phases/phase-6.md`
- Create: `docs/phases/phase-7.md`
- Create: `docs/phases/phase-8.md`

**Create these source-boundary files:**

- Create: `src/README.md`
- Create: `src/dba_assistant/README.md`
- Create: `src/dba_assistant/__init__.py`
- Create: `src/dba_assistant/core/__init__.py`
- Create: `src/dba_assistant/adaptors/__init__.py`
- Create: `src/dba_assistant/skills/__init__.py`
- Create: `src/dba_assistant/tools/__init__.py`

**Create these shared core placeholders:**

- Create: `src/dba_assistant/core/collector/README.md`
- Create: `src/dba_assistant/core/collector/__init__.py`
- Create: `src/dba_assistant/core/collector/types.py`
- Create: `src/dba_assistant/core/reporter/README.md`
- Create: `src/dba_assistant/core/reporter/__init__.py`
- Create: `src/dba_assistant/core/reporter/types.py`
- Create: `src/dba_assistant/core/analyzer/README.md`
- Create: `src/dba_assistant/core/analyzer/__init__.py`
- Create: `src/dba_assistant/core/analyzer/types.py`
- Create: `src/dba_assistant/core/audit/README.md`
- Create: `src/dba_assistant/core/audit/__init__.py`
- Create: `src/dba_assistant/core/audit/logger.py`

**Create these adaptor and tool placeholders:**

- Create: `src/dba_assistant/adaptors/README.md`
- Create: `src/dba_assistant/adaptors/filesystem_adaptor.py`
- Create: `src/dba_assistant/adaptors/redis_adaptor.py`
- Create: `src/dba_assistant/adaptors/ssh_adaptor.py`
- Create: `src/dba_assistant/adaptors/mysql_adaptor.py`
- Create: `src/dba_assistant/tools/README.md`

**Create these skill placeholders:**

- Create: `src/dba_assistant/skills/README.md`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/README.md`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/SKILL.md`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/__init__.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzer.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/collectors/README.md`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/collectors/__init__.py`
- Create: `src/dba_assistant/skills/redis_inspection_report/README.md`
- Create: `src/dba_assistant/skills/redis_inspection_report/SKILL.md`
- Create: `src/dba_assistant/skills/redis_inspection_report/__init__.py`
- Create: `src/dba_assistant/skills/redis_inspection_report/analyzer.py`
- Create: `src/dba_assistant/skills/redis_inspection_report/collectors/README.md`
- Create: `src/dba_assistant/skills/redis_inspection_report/collectors/__init__.py`
- Create: `src/dba_assistant/skills/redis_cve_report/README.md`
- Create: `src/dba_assistant/skills/redis_cve_report/SKILL.md`
- Create: `src/dba_assistant/skills/redis_cve_report/__init__.py`
- Create: `src/dba_assistant/skills/redis_cve_report/analyzer.py`
- Create: `src/dba_assistant/skills/redis_cve_report/collectors/README.md`
- Create: `src/dba_assistant/skills/redis_cve_report/collectors/__init__.py`

**Create these template, reference, and test placeholders:**

- Create: `templates/README.md`
- Create: `templates/reports/README.md`
- Create: `templates/reports/shared/README.md`
- Create: `templates/reports/rdb-analysis/README.md`
- Create: `templates/reports/inspection/README.md`
- Create: `templates/reports/cve/README.md`
- Create: `references/README.md`
- Create: `references/report-samples/README.md`
- Create: `tests/README.md`
- Create: `tests/unit/README.md`
- Create: `tests/e2e/README.md`
- Create: `tests/fixtures/README.md`

### Task 1: Create Root Policy and Project Configuration

**Files:**
- Create: `AGENTS.md`
- Create: `README.md`
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `CLAUDE.md` (symlink)

- [ ] **Step 1: Create the required root and phase directories**

Run:

```bash
mkdir -p docs/phases src/dba_assistant/core/collector src/dba_assistant/core/reporter src/dba_assistant/core/analyzer src/dba_assistant/core/audit src/dba_assistant/adaptors src/dba_assistant/skills src/dba_assistant/tools templates/reports/shared templates/reports/rdb-analysis templates/reports/inspection templates/reports/cve references/report-samples tests/unit tests/e2e tests/fixtures
```

Expected: command exits with code `0` and creates the scaffold directory tree without touching `src/claude-code-source-code` or `src/docs`.

- [ ] **Step 2: Write `AGENTS.md`**

```markdown
# DBA Assistant Repository Policy

## Purpose

This repository is developed phase by phase from the DBA Assistant master plan. Initialization creates repository scaffolding only. Functional delivery happens later, one phase at a time.

## Non-Negotiable Rules

- `AGENTS.md` is the repository policy source of truth.
- DBA Assistant is a Deep Agent SDK-based project.
- Production code must live under `src/dba_assistant/`.
- `src/claude-code-source-code/` and `src/docs/` are reference-only inputs for design and coding guidance.
- Do not copy runtime implementation code from the reference layer into production modules.
- Do not import production modules from the reference layer, and do not import the reference layer into production modules.
- Follow the master plan when reference material and local preference diverge.
- Phase work must stay scoped. Do not mix unfinished later-phase behavior into an earlier-phase delivery.

## Repository Layout Rules

- `docs/phases/` stores execution-oriented phase notes.
- `templates/reports/` stores repository-owned report template work.
- `references/report-samples/` stores historical report samples for comparison only.
- `tests/` stores repository-native fixtures and verification assets.

## Initialization Rules

- `/init` creates structure, contracts, and documentation only.
- `/init` must not claim runtime completeness.
- Placeholder modules must clearly state `scaffold-only` status.

## Language Direction

- The repository is Python-first.
- TypeScript files under the reference layer do not define the production language choice.
```

- [ ] **Step 3: Write `README.md`**

```markdown
# DBA Assistant

DBA Assistant is a phase-oriented repository for building Redis-focused DBA analysis and reporting workflows on top of a Python implementation path.

## Current Status

This repository is currently initialized as a scaffold. It contains:

- explicit documentation that the project is built on Deep Agent SDK
- the master plan
- reference materials under `src/`
- phase documents under `docs/phases/`
- production package placeholders under `src/dba_assistant/`
- template and test scaffolding

It does not yet contain working collector, analyzer, reporter, adaptor, or runtime implementations.

## Repository Boundaries

- Production code: `src/dba_assistant/`
- Reference-only content: `src/claude-code-source-code/`, `src/docs/`
- Report templates: `templates/reports/`
- Historical report samples: `references/report-samples/`

## Runtime Foundation

DBA Assistant is intended to run on Deep Agent SDK.

Initialization does not implement the SDK bootstrap yet, but the repository is not framework-neutral. Later phase work must wire skills, tools, and adaptors into a Deep Agent SDK application rather than inventing a separate runtime model.

## Development Model

Work is expected to proceed phase by phase:

1. establish shared foundations
2. add runtime and collection infrastructure
3. implement skills incrementally
4. expand audit, templates, and future safety controls
```

- [ ] **Step 4: Write `.gitignore` and `pyproject.toml`**

`.gitignore`

```gitignore
.DS_Store
__pycache__/
.pytest_cache/
.venv/
*.pyc
*.pyo
*.pyd
build/
dist/
*.egg-info/
```

`pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "dba-assistant"
version = "0.1.0"
description = "Phase-oriented scaffold for the DBA Assistant project."
readme = "README.md"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8,<9"]

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 5: Create the Claude compatibility symlink**

Run:

```bash
ln -s AGENTS.md CLAUDE.md
```

Expected: `CLAUDE.md` exists as a symlink targeting `AGENTS.md`.

- [ ] **Step 6: Verify root policy and configuration**

Run:

```bash
test -f AGENTS.md && test -f README.md && test -f .gitignore && test -f pyproject.toml && test -L CLAUDE.md && [ "$(readlink CLAUDE.md)" = "AGENTS.md" ] && python3 -c "import pathlib, tomllib; tomllib.loads(pathlib.Path('pyproject.toml').read_text())"
```

Expected: command exits with code `0`.

### Task 2: Write Phase Index and Foundation Phase Documents

**Files:**
- Create: `docs/phases/README.md`
- Create: `docs/phases/phase-1.md`
- Create: `docs/phases/phase-2.md`

- [ ] **Step 1: Write `docs/phases/README.md`**

```markdown
# Phase Documents

This directory breaks the DBA Assistant master plan into phase-specific working notes.

Each phase document should be used for:

- scope control
- delivery inspection
- dependency tracking
- acceptance review

These documents describe intended work. They do not imply that the phase is already implemented.
```

- [ ] **Step 2: Write `docs/phases/phase-1.md`**

```markdown
# Phase 1

## Objective

Establish shared repository foundations for collectors, reporters, analyzers, audit, templates, and tests.

## Scope

- define production package boundaries
- reserve shared core paths
- document offline-first phase intent
- prepare template and test areas for later implementation

## Inputs

- `docs/dba_assistant_master_plan_en.md`
- `AGENTS.md`
- existing reference material under `src/`

## Outputs

- documented scaffold under `src/dba_assistant/core/`
- scaffold template directories under `templates/reports/`
- scaffold test directories under `tests/`

## Directories Involved

- `src/dba_assistant/core/`
- `templates/reports/`
- `tests/`

## Dependencies

- none

## Acceptance Criteria

- shared core directories exist
- template directories exist
- test directories exist
- no functional collector or reporter logic is introduced during scaffold setup

## Non-Goals

- collector implementation
- reporter implementation
- runtime execution
```

- [ ] **Step 3: Write `docs/phases/phase-2.md`**

```markdown
# Phase 2

## Objective

Prepare for Deep Agent SDK assembly and remote collection work without implementing it during initialization.

## Scope

- reserve adaptor and tool ownership boundaries
- explicitly document Deep Agent SDK as the future runtime assembly target
- document the read-only remote collection direction
- keep production code separate from the reference layer

## Inputs

- `docs/dba_assistant_master_plan_en.md`
- `AGENTS.md`
- `docs/phases/phase-1.md`

## Outputs

- scaffold adaptor package
- scaffold tool package
- documented phase boundary for later Deep Agent SDK runtime work

## Directories Involved

- `src/dba_assistant/adaptors/`
- `src/dba_assistant/tools/`

## Dependencies

- `docs/phases/phase-1.md`

## Acceptance Criteria

- adaptor module paths exist
- tool package path exists
- phase notes explicitly identify Deep Agent SDK as the runtime foundation
- no runtime registration logic is added during scaffold setup

## Non-Goals

- Deep Agent SDK integration
- live remote connections
- command execution behavior
```

- [ ] **Step 4: Verify the foundation phase documents**

Run:

```bash
test -f docs/phases/README.md && test -f docs/phases/phase-1.md && test -f docs/phases/phase-2.md
```

Expected: command exits with code `0`.

### Task 3: Write Skill Delivery Phase Documents

**Files:**
- Create: `docs/phases/phase-3.md`
- Create: `docs/phases/phase-4.md`

- [ ] **Step 1: Write `docs/phases/phase-3.md`**

```markdown
# Phase 3

## Objective

Implement the Redis RDB analysis skill in later work, while keeping initialization limited to contracts and paths.

## Scope

- reserve the `redis_rdb_analysis` production package
- document the three planned delivery paths
- define where later collector, analyzer, and reporting work belongs

## Inputs

- `docs/dba_assistant_master_plan_en.md`
- `docs/phases/phase-1.md`
- `docs/phases/phase-2.md`

## Outputs

- skill scaffold under `src/dba_assistant/skills/redis_rdb_analysis/`
- contract-oriented `SKILL.md`

## Directories Involved

- `src/dba_assistant/skills/redis_rdb_analysis/`

## Dependencies

- `docs/phases/phase-1.md`
- `docs/phases/phase-2.md`

## Acceptance Criteria

- skill directory exists
- `SKILL.md` exists
- analyzer and collectors placeholders exist
- no parsing, SQL, or report-generation logic is implemented during initialization

## Non-Goals

- RDB parsing
- MySQL import
- report generation
```

- [ ] **Step 2: Write `docs/phases/phase-4.md`**

```markdown
# Phase 4

## Objective

Implement the Redis inspection report skill in later work, while keeping initialization limited to contracts and paths.

## Scope

- reserve the `redis_inspection_report` production package
- document offline and remote collection paths
- define where inspection analysis and report work will live

## Inputs

- `docs/dba_assistant_master_plan_en.md`
- `docs/phases/phase-1.md`
- `docs/phases/phase-2.md`

## Outputs

- skill scaffold under `src/dba_assistant/skills/redis_inspection_report/`
- contract-oriented `SKILL.md`

## Directories Involved

- `src/dba_assistant/skills/redis_inspection_report/`

## Dependencies

- `docs/phases/phase-1.md`
- `docs/phases/phase-2.md`

## Acceptance Criteria

- skill directory exists
- `SKILL.md` exists
- analyzer and collectors placeholders exist
- no inspection command, parsing, or reporting logic is implemented during initialization

## Non-Goals

- Redis collection
- SSH collection
- inspection report rendering
```

- [ ] **Step 3: Verify the skill delivery phase documents**

Run:

```bash
test -f docs/phases/phase-3.md && test -f docs/phases/phase-4.md
```

Expected: command exits with code `0`.

### Task 4: Write Audit, Security, and Future Phase Documents

**Files:**
- Create: `docs/phases/phase-5.md`
- Create: `docs/phases/phase-6.md`
- Create: `docs/phases/phase-7.md`
- Create: `docs/phases/phase-8.md`

- [ ] **Step 1: Write `docs/phases/phase-5.md`**

```markdown
# Phase 5

## Objective

Introduce audit and security baseline work in later implementation phases.

## Scope

- reserve the audit logger path
- document JSONL-oriented audit expectations
- define the retroactive instrumentation intent for skills

## Inputs

- `docs/dba_assistant_master_plan_en.md`
- `docs/phases/phase-3.md`
- `docs/phases/phase-4.md`

## Outputs

- scaffold audit package
- documented audit phase boundary

## Directories Involved

- `src/dba_assistant/core/audit/`

## Dependencies

- `docs/phases/phase-3.md`
- `docs/phases/phase-4.md`

## Acceptance Criteria

- audit package exists
- logger placeholder exists
- no executable audit pipeline is implemented during initialization

## Non-Goals

- JSONL logging behavior
- execution tracing
- human confirmation implementation
```

- [ ] **Step 2: Write `docs/phases/phase-6.md`**

```markdown
# Phase 6

## Objective

Prepare the Redis CVE report skill for later implementation while keeping initialization contract-only.

## Scope

- reserve the `redis_cve_report` production package
- document online and offline CVE source expectations
- define where future analyzer and reporting logic will live

## Inputs

- `docs/dba_assistant_master_plan_en.md`
- `docs/phases/phase-1.md`
- `docs/phases/phase-2.md`

## Outputs

- skill scaffold under `src/dba_assistant/skills/redis_cve_report/`
- contract-oriented `SKILL.md`

## Directories Involved

- `src/dba_assistant/skills/redis_cve_report/`

## Dependencies

- `docs/phases/phase-1.md`
- `docs/phases/phase-2.md`

## Acceptance Criteria

- skill directory exists
- `SKILL.md` exists
- analyzer and collectors placeholders exist
- no external fetch logic is implemented during initialization

## Non-Goals

- CVE API calls
- deduplication logic
- LLM impact assessment
```

- [ ] **Step 3: Write `docs/phases/phase-7.md`**

```markdown
# Phase 7

## Objective

Document template optimization as an ongoing quality track rather than a one-time initialization deliverable.

## Scope

- define how generated reports will be reviewed later
- preserve template ownership under repository-controlled paths

## Inputs

- `docs/dba_assistant_master_plan_en.md`
- `templates/reports/`

## Outputs

- documented optimization policy

## Directories Involved

- `templates/reports/`
- `references/report-samples/`

## Dependencies

- `docs/phases/phase-1.md`
- `docs/phases/phase-3.md`
- `docs/phases/phase-4.md`
- `docs/phases/phase-6.md`

## Acceptance Criteria

- template optimization intent is documented
- no template rendering behavior is added during initialization

## Non-Goals

- final template design
- visual polish work
- report comparison automation
```

- [ ] **Step 4: Write `docs/phases/phase-8.md`**

```markdown
# Phase 8

## Objective

Document future expansion boundaries so initialization does not accidentally introduce out-of-scope behavior.

## Scope

- record deferred dangerous-write operations
- record future multi-database expansion direction
- keep initialization neutral on later framework choices

## Inputs

- `docs/dba_assistant_master_plan_en.md`
- `AGENTS.md`

## Outputs

- documented future-expansion boundary

## Directories Involved

- `docs/phases/`

## Dependencies

- `docs/phases/phase-5.md`

## Acceptance Criteria

- future work is clearly documented as deferred
- initialization does not pre-implement safety workflows

## Non-Goals

- write operations
- approval interrupts
- MySQL or MongoDB skill implementation
```

- [ ] **Step 5: Verify the later phase documents**

Run:

```bash
test -f docs/phases/phase-5.md && test -f docs/phases/phase-6.md && test -f docs/phases/phase-7.md && test -f docs/phases/phase-8.md
```

Expected: command exits with code `0`.

### Task 5: Establish Source Boundaries and the Production Package Root

**Files:**
- Create: `src/README.md`
- Create: `src/dba_assistant/README.md`
- Create: `src/dba_assistant/__init__.py`
- Create: `src/dba_assistant/core/__init__.py`
- Create: `src/dba_assistant/adaptors/__init__.py`
- Create: `src/dba_assistant/skills/__init__.py`
- Create: `src/dba_assistant/tools/__init__.py`

- [ ] **Step 1: Create the production package directories**

Run:

```bash
mkdir -p src/dba_assistant/core src/dba_assistant/adaptors src/dba_assistant/skills src/dba_assistant/tools
```

Expected: command exits with code `0` and leaves `src/claude-code-source-code/` and `src/docs/` untouched.

- [ ] **Step 2: Write `src/README.md`**

```markdown
# Source Tree Notes

This `src/` directory contains both reference material and the repository's future production package.

## Reference-Only Content

- `src/claude-code-source-code/`
- `src/docs/`

These paths exist to support design and coding reference. They are not runtime dependencies for DBA Assistant.

## Production Content

- `src/dba_assistant/`

This path is the only production package root introduced by repository initialization.

It is reserved for the repository's future Deep Agent SDK application code.
```

- [ ] **Step 3: Write `src/dba_assistant/README.md` and `src/dba_assistant/__init__.py`**

`src/dba_assistant/README.md`

```markdown
# dba_assistant Package

This package is the production code root for DBA Assistant.

Initialization creates package boundaries only. Functional implementation is deferred to later phases.
```

`src/dba_assistant/__init__.py`

```python
"""DBA Assistant production package scaffold."""
```

- [ ] **Step 4: Write package-level `__init__.py` files**

`src/dba_assistant/core/__init__.py`

```python
"""Shared core package scaffold for DBA Assistant."""
```

`src/dba_assistant/adaptors/__init__.py`

```python
"""External adaptor package scaffold for DBA Assistant."""
```

`src/dba_assistant/skills/__init__.py`

```python
"""Skill package scaffold for DBA Assistant."""
```

`src/dba_assistant/tools/__init__.py`

```python
"""Tool package scaffold for DBA Assistant."""
```

- [ ] **Step 5: Verify the production package root**

Run:

```bash
test -f src/README.md && test -f src/dba_assistant/README.md && test -f src/dba_assistant/__init__.py && test -f src/dba_assistant/core/__init__.py && test -f src/dba_assistant/adaptors/__init__.py && test -f src/dba_assistant/skills/__init__.py && test -f src/dba_assistant/tools/__init__.py
```

Expected: command exits with code `0`.

### Task 6: Create Shared Core, Adaptor, and Tool Placeholder Modules

**Files:**
- Create: `src/dba_assistant/core/collector/README.md`
- Create: `src/dba_assistant/core/collector/__init__.py`
- Create: `src/dba_assistant/core/collector/types.py`
- Create: `src/dba_assistant/core/reporter/README.md`
- Create: `src/dba_assistant/core/reporter/__init__.py`
- Create: `src/dba_assistant/core/reporter/types.py`
- Create: `src/dba_assistant/core/analyzer/README.md`
- Create: `src/dba_assistant/core/analyzer/__init__.py`
- Create: `src/dba_assistant/core/analyzer/types.py`
- Create: `src/dba_assistant/core/audit/README.md`
- Create: `src/dba_assistant/core/audit/__init__.py`
- Create: `src/dba_assistant/core/audit/logger.py`
- Create: `src/dba_assistant/adaptors/README.md`
- Create: `src/dba_assistant/adaptors/filesystem_adaptor.py`
- Create: `src/dba_assistant/adaptors/redis_adaptor.py`
- Create: `src/dba_assistant/adaptors/ssh_adaptor.py`
- Create: `src/dba_assistant/adaptors/mysql_adaptor.py`
- Create: `src/dba_assistant/tools/README.md`

- [ ] **Step 1: Write collector placeholders**

`src/dba_assistant/core/collector/README.md`

```markdown
# Collector Layer

This directory reserves the shared collector boundary for DBA Assistant.

Status: scaffold-only.

Implementation of collector interfaces and offline or remote collection behavior is deferred to later phase work.
```

`src/dba_assistant/core/collector/__init__.py`

```python
"""Collector layer scaffold."""
```

`src/dba_assistant/core/collector/types.py`

```python
"""Collector contract scaffold.

Real collector interfaces are intentionally deferred.
"""
```

- [ ] **Step 2: Write reporter placeholders**

`src/dba_assistant/core/reporter/README.md`

```markdown
# Reporter Layer

This directory reserves the shared reporting boundary for DBA Assistant.

Status: scaffold-only.

Docx, PDF, HTML, and summary rendering logic will be implemented in later phases.
```

`src/dba_assistant/core/reporter/__init__.py`

```python
"""Reporter layer scaffold."""
```

`src/dba_assistant/core/reporter/types.py`

```python
"""Reporter contract scaffold.

Real reporter interfaces are intentionally deferred.
"""
```

- [ ] **Step 3: Write analyzer and audit placeholders**

`src/dba_assistant/core/analyzer/README.md`

```markdown
# Analyzer Layer

This directory reserves shared analysis result boundaries for DBA Assistant.

Status: scaffold-only.
```

`src/dba_assistant/core/analyzer/__init__.py`

```python
"""Analyzer layer scaffold."""
```

`src/dba_assistant/core/analyzer/types.py`

```python
"""Analyzer result contract scaffold.

Real analysis schemas are intentionally deferred.
"""
```

`src/dba_assistant/core/audit/README.md`

```markdown
# Audit Layer

This directory reserves the audit boundary for later JSONL-oriented execution logging work.

Status: scaffold-only.
```

`src/dba_assistant/core/audit/__init__.py`

```python
"""Audit layer scaffold."""
```

`src/dba_assistant/core/audit/logger.py`

```python
"""Audit logger scaffold.

Functional audit logging is intentionally deferred to a later phase.
"""
```

- [ ] **Step 4: Write adaptor placeholders**

`src/dba_assistant/adaptors/README.md`

```markdown
# Adaptors

This directory reserves integration boundaries for filesystems, Redis, SSH, and MySQL.

Status: scaffold-only.

No live connections or command execution behavior should be added during initialization.
```

`src/dba_assistant/adaptors/filesystem_adaptor.py`

```python
"""Filesystem adaptor scaffold."""
```

`src/dba_assistant/adaptors/redis_adaptor.py`

```python
"""Redis adaptor scaffold."""
```

`src/dba_assistant/adaptors/ssh_adaptor.py`

```python
"""SSH adaptor scaffold."""
```

`src/dba_assistant/adaptors/mysql_adaptor.py`

```python
"""MySQL adaptor scaffold."""
```

- [ ] **Step 5: Write tool placeholders**

`src/dba_assistant/tools/README.md`

```markdown
# Tools

This directory reserves business tool registration and orchestration paths for later phases.

Status: scaffold-only.
```

- [ ] **Step 6: Verify Python placeholder syntax**

Run:

```bash
python3 -m py_compile src/dba_assistant/__init__.py src/dba_assistant/core/__init__.py src/dba_assistant/core/collector/__init__.py src/dba_assistant/core/collector/types.py src/dba_assistant/core/reporter/__init__.py src/dba_assistant/core/reporter/types.py src/dba_assistant/core/analyzer/__init__.py src/dba_assistant/core/analyzer/types.py src/dba_assistant/core/audit/__init__.py src/dba_assistant/core/audit/logger.py src/dba_assistant/adaptors/__init__.py src/dba_assistant/adaptors/filesystem_adaptor.py src/dba_assistant/adaptors/redis_adaptor.py src/dba_assistant/adaptors/ssh_adaptor.py src/dba_assistant/adaptors/mysql_adaptor.py src/dba_assistant/skills/__init__.py src/dba_assistant/tools/__init__.py
```

Expected: command exits with code `0`.

### Task 7: Create the Redis Skill Scaffolds

**Files:**
- Create: `src/dba_assistant/skills/README.md`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/README.md`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/SKILL.md`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/__init__.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzer.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/collectors/README.md`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/collectors/__init__.py`
- Create: `src/dba_assistant/skills/redis_inspection_report/README.md`
- Create: `src/dba_assistant/skills/redis_inspection_report/SKILL.md`
- Create: `src/dba_assistant/skills/redis_inspection_report/__init__.py`
- Create: `src/dba_assistant/skills/redis_inspection_report/analyzer.py`
- Create: `src/dba_assistant/skills/redis_inspection_report/collectors/README.md`
- Create: `src/dba_assistant/skills/redis_inspection_report/collectors/__init__.py`
- Create: `src/dba_assistant/skills/redis_cve_report/README.md`
- Create: `src/dba_assistant/skills/redis_cve_report/SKILL.md`
- Create: `src/dba_assistant/skills/redis_cve_report/__init__.py`
- Create: `src/dba_assistant/skills/redis_cve_report/analyzer.py`
- Create: `src/dba_assistant/skills/redis_cve_report/collectors/README.md`
- Create: `src/dba_assistant/skills/redis_cve_report/collectors/__init__.py`

- [ ] **Step 1: Write the skill package index**

`src/dba_assistant/skills/README.md`

```markdown
# Skills

This directory stores repository-native skill implementations.

Status: scaffold-only.

These skills are future Deep Agent SDK skill units, even though initialization does not register them yet.

Each skill directory must contain:

- `SKILL.md` for the contract
- placeholder Python modules for future implementation
- collector subdirectories for source-specific logic
```

- [ ] **Step 2: Write the Redis RDB analysis skill scaffold**

`src/dba_assistant/skills/redis_rdb_analysis/README.md`

```markdown
# redis-rdb-analysis

Phase owner: Phase 3

Status: scaffold-only.

This directory reserves the production package path for the Redis RDB analysis skill.
```

`src/dba_assistant/skills/redis_rdb_analysis/SKILL.md`

````markdown
```yaml
skill:
  name: redis-rdb-analysis
  description: Generate Redis RDB analysis outputs from repository-supported collection paths.

status:
  phase_owner: phase-3
  implementation_status: scaffold-only
  execution_status: not-runnable

input_contract:
  required_data:
    - name: source_path
      type: string
      description: Path to one RDB file, an exported analysis data file, or a directory selected by the collector path.
  supported_collectors:
    - offline
    - remote-mysql
  parameters:
    - name: output_mode
      type: string
      default: report
      description: Output mode, either report or summary.
    - name: output_format
      type: string
      default: docx
      description: Report format when output_mode is report.

output_contract:
  analysis_schema: RdbAnalysisResult
  supported_modes:
    - report
    - summary
  supported_formats:
    - docx
    - pdf
    - html
  default_mode: report
  default_format: docx
```

Notes:

- This file defines contract intent only.
- Parsing, SQL workflows, and rendering belong to later phase implementation.
- The skill is intended for later integration into the repository's Deep Agent SDK runtime.
````

`src/dba_assistant/skills/redis_rdb_analysis/__init__.py`

```python
"""redis_rdb_analysis skill scaffold."""
```

`src/dba_assistant/skills/redis_rdb_analysis/analyzer.py`

```python
"""Analyzer scaffold for redis-rdb-analysis."""
```

`src/dba_assistant/skills/redis_rdb_analysis/collectors/README.md`

```markdown
# redis-rdb-analysis Collectors

This directory reserves collector implementations for offline and MySQL-backed RDB analysis paths.

Status: scaffold-only.
```

`src/dba_assistant/skills/redis_rdb_analysis/collectors/__init__.py`

```python
"""Collector package scaffold for redis_rdb_analysis."""
```

- [ ] **Step 3: Write the Redis inspection report skill scaffold**

`src/dba_assistant/skills/redis_inspection_report/README.md`

```markdown
# redis-inspection-report

Phase owner: Phase 4

Status: scaffold-only.

This directory reserves the production package path for the Redis inspection report skill.
```

`src/dba_assistant/skills/redis_inspection_report/SKILL.md`

````markdown
```yaml
skill:
  name: redis-inspection-report
  description: Generate Redis inspection report outputs from offline or remote collection paths.

status:
  phase_owner: phase-4
  implementation_status: scaffold-only
  execution_status: not-runnable

input_contract:
  required_data:
    - name: source_path
      type: string
      description: Path to an inspection bundle directory or remote target selected by the collector path.
  supported_collectors:
    - offline
    - remote-redis
    - remote-ssh
  parameters:
    - name: output_mode
      type: string
      default: report
      description: Output mode, either report or summary.
    - name: output_format
      type: string
      default: docx
      description: Report format when output_mode is report.

output_contract:
  analysis_schema: InspectionAnalysisResult
  supported_modes:
    - report
    - summary
  supported_formats:
    - docx
    - pdf
    - html
  default_mode: report
  default_format: docx
```

Notes:

- This file defines contract intent only.
- Collection, normalization, analysis, and rendering belong to later phase implementation.
- The skill is intended for later integration into the repository's Deep Agent SDK runtime.
````

`src/dba_assistant/skills/redis_inspection_report/__init__.py`

```python
"""redis_inspection_report skill scaffold."""
```

`src/dba_assistant/skills/redis_inspection_report/analyzer.py`

```python
"""Analyzer scaffold for redis-inspection-report."""
```

`src/dba_assistant/skills/redis_inspection_report/collectors/README.md`

```markdown
# redis-inspection-report Collectors

This directory reserves collector implementations for offline and remote inspection data paths.

Status: scaffold-only.
```

`src/dba_assistant/skills/redis_inspection_report/collectors/__init__.py`

```python
"""Collector package scaffold for redis_inspection_report."""
```

- [ ] **Step 4: Write the Redis CVE report skill scaffold**

`src/dba_assistant/skills/redis_cve_report/README.md`

```markdown
# redis-cve-report

Phase owner: Phase 6

Status: scaffold-only.

This directory reserves the production package path for the Redis CVE report skill.
```

`src/dba_assistant/skills/redis_cve_report/SKILL.md`

````markdown
```yaml
skill:
  name: redis-cve-report
  description: Generate Redis CVE intelligence outputs from online or offline data sources.

status:
  phase_owner: phase-6
  implementation_status: scaffold-only
  execution_status: not-runnable

input_contract:
  required_data:
    - name: time_range
      type: string
      description: Natural language or explicit time range for the CVE search window.
  supported_collectors:
    - offline
    - online-fetch
  parameters:
    - name: redis_version_range
      type: string
      default: ""
      description: Optional Redis version range for later impact assessment.
    - name: output_mode
      type: string
      default: report
      description: Output mode, either report or summary.
    - name: output_format
      type: string
      default: docx
      description: Report format when output_mode is report.

output_contract:
  analysis_schema: RedisCveAnalysisResult
  supported_modes:
    - report
    - summary
  supported_formats:
    - docx
    - pdf
    - html
  default_mode: report
  default_format: docx
```

Notes:

- This file defines contract intent only.
- Fetching, deduplication, and impact assessment belong to later phase implementation.
- The skill is intended for later integration into the repository's Deep Agent SDK runtime.
````

`src/dba_assistant/skills/redis_cve_report/__init__.py`

```python
"""redis_cve_report skill scaffold."""
```

`src/dba_assistant/skills/redis_cve_report/analyzer.py`

```python
"""Analyzer scaffold for redis-cve-report."""
```

`src/dba_assistant/skills/redis_cve_report/collectors/README.md`

```markdown
# redis-cve-report Collectors

This directory reserves collector implementations for online and offline CVE source paths.

Status: scaffold-only.
```

`src/dba_assistant/skills/redis_cve_report/collectors/__init__.py`

```python
"""Collector package scaffold for redis_cve_report."""
```

- [ ] **Step 5: Verify skill scaffold paths and Python syntax**

Run:

```bash
test -f src/dba_assistant/skills/README.md && test -f src/dba_assistant/skills/redis_rdb_analysis/SKILL.md && test -f src/dba_assistant/skills/redis_inspection_report/SKILL.md && test -f src/dba_assistant/skills/redis_cve_report/SKILL.md && python3 -m py_compile src/dba_assistant/skills/redis_rdb_analysis/__init__.py src/dba_assistant/skills/redis_rdb_analysis/analyzer.py src/dba_assistant/skills/redis_rdb_analysis/collectors/__init__.py src/dba_assistant/skills/redis_inspection_report/__init__.py src/dba_assistant/skills/redis_inspection_report/analyzer.py src/dba_assistant/skills/redis_inspection_report/collectors/__init__.py src/dba_assistant/skills/redis_cve_report/__init__.py src/dba_assistant/skills/redis_cve_report/analyzer.py src/dba_assistant/skills/redis_cve_report/collectors/__init__.py
```

Expected: command exits with code `0`.

### Task 8: Create Template, Reference, and Test Scaffolds

**Files:**
- Create: `templates/README.md`
- Create: `templates/reports/README.md`
- Create: `templates/reports/shared/README.md`
- Create: `templates/reports/rdb-analysis/README.md`
- Create: `templates/reports/inspection/README.md`
- Create: `templates/reports/cve/README.md`
- Create: `references/README.md`
- Create: `references/report-samples/README.md`
- Create: `tests/README.md`
- Create: `tests/unit/README.md`
- Create: `tests/e2e/README.md`
- Create: `tests/fixtures/README.md`

- [ ] **Step 1: Write template ownership files**

`templates/README.md`

```markdown
# Templates

This directory stores repository-owned template work.

Status: scaffold-only.
```

`templates/reports/README.md`

```markdown
# Report Templates

This directory stores standard report template work for DBA Assistant.

Historical reports must be treated as reference samples, not direct templates.
```

`templates/reports/shared/README.md`

```markdown
# Shared Report Template Components

This directory reserves shared report template assets such as cover layout, disclaimer blocks, and risk presentation styles.

Status: scaffold-only.
```

`templates/reports/rdb-analysis/README.md`

```markdown
# RDB Analysis Templates

This directory reserves standard templates for Redis RDB analysis reports.

Status: scaffold-only.
```

`templates/reports/inspection/README.md`

```markdown
# Inspection Report Templates

This directory reserves standard templates for Redis inspection reports.

Status: scaffold-only.
```

`templates/reports/cve/README.md`

```markdown
# CVE Report Templates

This directory reserves standard templates for Redis CVE reports.

Status: scaffold-only.
```

- [ ] **Step 2: Write reference ownership files**

`references/README.md`

```markdown
# References

This directory stores non-production reference assets owned by this repository.
```

`references/report-samples/README.md`

```markdown
# Historical Report Samples

This directory stores historical report examples for structure and style comparison.

These samples are references only. They must not be treated as the repository's canonical templates.
```

- [ ] **Step 3: Write test scaffold notes**

`tests/README.md`

```markdown
# Tests

This directory stores repository-native tests, fixtures, and end-to-end verification assets.

Status: scaffold-only.
```

`tests/unit/README.md`

```markdown
# Unit Tests

Unit tests for repository-owned modules will be added here in later phases.
```

`tests/e2e/README.md`

```markdown
# End-to-End Tests

End-to-end workflow checks will be added here in later phases.
```

`tests/fixtures/README.md`

```markdown
# Test Fixtures

Repository-native fixture data for skills and reporters will be added here in later phases.
```

- [ ] **Step 4: Verify template, reference, and test scaffold paths**

Run:

```bash
test -f templates/README.md && test -f templates/reports/README.md && test -f templates/reports/shared/README.md && test -f templates/reports/rdb-analysis/README.md && test -f templates/reports/inspection/README.md && test -f templates/reports/cve/README.md && test -f references/README.md && test -f references/report-samples/README.md && test -f tests/README.md && test -f tests/unit/README.md && test -f tests/e2e/README.md && test -f tests/fixtures/README.md
```

Expected: command exits with code `0`.

### Task 9: Run Final Scaffold Validation

**Files:**
- Verify: `AGENTS.md`
- Verify: `CLAUDE.md`
- Verify: `docs/phases/*.md`
- Verify: `src/dba_assistant/**`
- Verify: `templates/**`
- Verify: `references/**`
- Verify: `tests/**`

- [ ] **Step 1: List the final scaffold tree**

Run:

```bash
find docs/phases src/dba_assistant templates references tests -maxdepth 3 -type f | sort
```

Expected: output lists the newly created scaffold files under each planned area.

- [ ] **Step 2: Re-check the symlink and reference isolation paths**

Run:

```bash
test -L CLAUDE.md && [ "$(readlink CLAUDE.md)" = "AGENTS.md" ] && test -d src/claude-code-source-code && test -d src/docs && test -d src/dba_assistant
```

Expected: command exits with code `0`.

- [ ] **Step 3: Re-check Python syntax across the production package**

Run:

```bash
python3 -m py_compile src/dba_assistant/__init__.py src/dba_assistant/core/__init__.py src/dba_assistant/core/collector/__init__.py src/dba_assistant/core/collector/types.py src/dba_assistant/core/reporter/__init__.py src/dba_assistant/core/reporter/types.py src/dba_assistant/core/analyzer/__init__.py src/dba_assistant/core/analyzer/types.py src/dba_assistant/core/audit/__init__.py src/dba_assistant/core/audit/logger.py src/dba_assistant/adaptors/__init__.py src/dba_assistant/adaptors/filesystem_adaptor.py src/dba_assistant/adaptors/redis_adaptor.py src/dba_assistant/adaptors/ssh_adaptor.py src/dba_assistant/adaptors/mysql_adaptor.py src/dba_assistant/skills/__init__.py src/dba_assistant/skills/redis_rdb_analysis/__init__.py src/dba_assistant/skills/redis_rdb_analysis/analyzer.py src/dba_assistant/skills/redis_rdb_analysis/collectors/__init__.py src/dba_assistant/skills/redis_inspection_report/__init__.py src/dba_assistant/skills/redis_inspection_report/analyzer.py src/dba_assistant/skills/redis_inspection_report/collectors/__init__.py src/dba_assistant/skills/redis_cve_report/__init__.py src/dba_assistant/skills/redis_cve_report/analyzer.py src/dba_assistant/skills/redis_cve_report/collectors/__init__.py src/dba_assistant/tools/__init__.py
```

Expected: command exits with code `0`.

- [ ] **Step 4: Confirm initialization remains scaffold-only**

Run:

```bash
rg -n "scaffold-only|not-runnable|reference-only" AGENTS.md README.md docs/phases src/dba_assistant templates references tests
```

Expected: output shows explicit boundary markers across the scaffold and no file claims that runtime behavior already exists.

- [ ] **Step 5: Confirm Deep Agent SDK is explicitly documented**

Run:

```bash
rg -n "Deep Agent SDK" AGENTS.md README.md docs/phases/phase-2.md docs/superpowers/specs/2026-04-01-init-repository-scaffold-design.md docs/superpowers/plans/2026-04-01-init-repository-scaffold.md
```

Expected: output shows repository-level documentation that DBA Assistant is built on Deep Agent SDK, even though initialization remains scaffold-only.

## Self-Review

**Spec coverage:** This plan covers root policy files, Deep Agent SDK foundation documentation, phase documents, Python package scaffolding, shared layers, adaptors, skill contracts, templates, references, tests, symlink setup, and validation.

**Placeholder scan:** The plan avoids `TBD`, `TODO`, and similar empty markers. Every code-writing step includes concrete file content.

**Type consistency:** All production-code paths consistently use the Python package root `src/dba_assistant/`. Reference-only paths remain `src/claude-code-source-code/` and `src/docs/`.
