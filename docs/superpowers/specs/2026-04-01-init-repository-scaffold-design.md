# Repository Scaffold Initialization Design

## Summary

This design defines the `/init` scope for the DBA Assistant repository.

The repository itself is a DBA Assistant project whose runtime foundation is Deep Agent SDK, as defined by `docs/dba_assistant_master_plan_en.md`.

The initialization goal is to create a phase-oriented project scaffold for that Deep Agent SDK-based project, without implementing runtime behavior, business logic, external integrations, or report rendering.

The scaffold must make the repository ready for incremental phase execution and inspection. Each later phase should be able to add implementation into a stable directory structure and documented boundary, rather than reshaping the repository during delivery.

The scaffold should be Python-first. It should not let the TypeScript-heavy reference materials under `src/` dictate the production language choice for this repository.

## Scope

### In Scope

- Create the top-level repository structure described by the master plan.
- Create `AGENTS.md` as the global policy file.
- Create a Claude-readable symlink that points to `AGENTS.md`.
- Create phase documentation files for `Phase 1` through `Phase 8`.
- Create placeholder source directories and boundary files for:
  - shared core layers
  - adaptors
  - skills
  - tools
  - templates
  - references
  - tests
- Create placeholder `SKILL.md` files for the initial Redis skills.
- Create minimal project-level engineering files such as `README.md`, `pyproject.toml`, and Python test/config placeholders.
- Add concise README or placeholder files where needed so empty directories remain visible and their purpose is explicit.

### Out of Scope

- Deep Agent SDK runtime implementation
- Skill registration and execution logic
- Collector, analyzer, reporter, adaptor, or audit implementations
- Redis, MySQL, SSH, or CVE live integrations
- Real report templates or report rendering
- Test implementation beyond scaffold-level placeholders
- Any claim that a phase is already functional

## Design Principles

### 1. Scaffold, not implementation

Every file created by `/init` must either:

- define a boundary,
- document intent,
- reserve a stable path for future implementation, or
- keep the repository structurally complete.

It must not silently introduce partial business behavior.

### 2. Phase-driven repository evolution

The repository should be inspectable by phase. A reviewer must be able to open phase documentation and see:

- what that phase is meant to deliver,
- which directories and files belong to it,
- what dependencies it has,
- what is explicitly deferred.

The phase structure must also make one architectural fact explicit from day one: this repository is meant to become a Deep Agent SDK application, not a generic scripting project or a framework-agnostic utility repository.

### 3. Reference isolation

The existing content under `src/` that serves as design reference must remain isolated from future production code. The scaffold must preserve that architectural boundary and avoid turning reference material into runtime dependency.

Specifically:

- `src/claude-code-source-code` is a local reference repository, not a production dependency.
- `src/docs` is a local reference document area, not a production dependency.
- initialization must not copy implementation code from those paths into the production package as a shortcut
- initialization must not create imports from production modules into those reference paths
- future implementation may study patterns from the reference layer, but must write repository-native code

### 4. Stable paths for later work

Future implementation should not need to rename major directories. The initialization step should create the final intended layout early so later work adds code into stable paths.

### 5. Python-first production layout

The scaffold should reserve Python package paths for real implementation work.

Reference material may remain under `src/`, but production code should live in a dedicated Python package subtree so later phases do not mix reference content with importable business modules.

### 6. Deep Agent SDK as runtime foundation

The scaffold must explicitly document that:

- DBA Assistant is built on Deep Agent SDK as its runtime foundation
- skills under `src/dba_assistant/skills/` are future Deep Agent SDK skill units
- tools under `src/dba_assistant/tools/` are future Deep Agent SDK-exposed business actions
- adaptors under `src/dba_assistant/adaptors/` are support integrations beneath those skills and tools
- `/init` defers runtime assembly work, but does not make the project runtime-agnostic

## Repository Structure

The scaffold should create or normalize the following structure:

```text
dba_assistant/
├── AGENTS.md
├── CLAUDE.md -> AGENTS.md
├── README.md
├── pyproject.toml
├── docs/
│   ├── dba_assistant_master_plan_en.md
│   ├── phases/
│   │   ├── phase-1.md
│   │   ├── phase-2.md
│   │   ├── phase-3.md
│   │   ├── phase-4.md
│   │   ├── phase-5.md
│   │   ├── phase-6.md
│   │   ├── phase-7.md
│   │   └── phase-8.md
│   └── superpowers/
│       └── specs/
├── src/
│   ├── claude-code-source-code/
│   ├── docs/
│   ├── README.md
│   └── dba_assistant/
│       ├── __init__.py
│       ├── core/
│       │   ├── collector/
│       │   ├── reporter/
│       │   ├── analyzer/
│       │   └── audit/
│       ├── adaptors/
│       ├── skills/
│       │   ├── redis_rdb_analysis/
│       │   ├── redis_inspection_report/
│       │   └── redis_cve_report/
│       └── tools/
├── templates/
│   └── reports/
│       ├── shared/
│       ├── rdb-analysis/
│       ├── inspection/
│       └── cve/
├── references/
│   └── report-samples/
└── tests/
    ├── unit/
    ├── e2e/
    └── fixtures/
```

## Planned File Types

### Policy and repository guidance

- `AGENTS.md`
  - global engineering, safety, and architectural rules for this repository, including the Deep Agent SDK foundation
- `CLAUDE.md`
  - symlink to `AGENTS.md`
- `README.md`
  - repository purpose, Deep Agent SDK foundation, current state, and phase-oriented development model

### Project configuration

- `pyproject.toml`
  - minimal Python project metadata, dependency groups, and tool configuration placeholders
- optional Python support files
  - for example `.gitignore`, `pytest.ini`, or tool-specific config if needed by the scaffold

### Phase documents

Each `docs/phases/phase-N.md` file should contain:

- objective
- scope
- inputs and outputs
- directories involved
- dependencies on earlier phases
- acceptance criteria
- explicit non-goals

`phase-2.md` must explicitly identify Deep Agent SDK assembly as the future runtime integration phase, even though initialization does not implement it.

### Core placeholders

`src/dba_assistant/core/**` should include placeholder files that establish future module ownership, for example:

- `types.py`
- `README.md`
- optional `.gitkeep` where a directory exists only as a future container

These files should describe the intended purpose and the implementation status as `scaffold only`.

This Python package must be the only production code root introduced by `/init`. The existing `src/claude-code-source-code` and `src/docs` trees remain reference-only and must not be treated as importable implementation sources for DBA Assistant.

The package layout should make it clear that this production root exists to host the repository's future Deep Agent SDK application code.

### Skill placeholders

Each initial skill directory should contain:

- `SKILL.md`
- `README.md`
- `collectors/` placeholder
- `analyzer.py` placeholder
- `__init__.py` placeholder

`SKILL.md` should include:

- skill name and description
- input contract
- output contract
- supported collectors
- supported modes and formats
- current status
- notes on which phase will implement real behavior

The wording in each `SKILL.md` should make it clear that the skill is intended to be integrated into the repository's Deep Agent SDK runtime in later phase work.

Directory naming should follow Python package conventions such as `redis_rdb_analysis`, while the skill metadata inside `SKILL.md` may keep business-facing names such as `redis-rdb-analysis`.

### Template placeholders

Template directories should contain placeholder files or README files clarifying:

- this is the standard template area owned by the repository
- historical reports under `references/report-samples/` are references only
- template implementation is deferred to later phases

### Test placeholders

The test tree should exist from day one, but only with scaffold markers and purpose notes.

## Phase Documentation Strategy

The phase documents are part of the scaffold deliverable, not optional extras.

They should be written so later work can use them as execution checkpoints:

- `phase-1.md`: shared layers and offline-first scaffold expectations
- `phase-2.md`: runtime assembly and remote collection foundation
- `phase-3.md`: Redis RDB analysis skill roadmap
- `phase-4.md`: Redis inspection report roadmap
- `phase-5.md`: audit and security baseline roadmap
- `phase-6.md`: Redis CVE report roadmap
- `phase-7.md`: template optimization policy
- `phase-8.md`: future expansion boundaries

## Error Handling

The initialization must handle pre-existing repository content conservatively:

- keep existing master plan documents
- keep existing reference materials
- keep the existing `src/claude-code-source-code` and `src/docs` trees as reference-only content
- do not move reference-layer files into the production package
- do not copy reference-layer implementation into scaffold source files
- avoid deleting or renaming user-provided files unless explicitly required
- add scaffold files around existing content rather than rewriting reference material

If a planned path already contains user content, initialization should prefer additive placeholders or README files instead of destructive normalization.

## Testing Strategy

`/init` should not implement business tests. It should only make the repository verifiable at the scaffold level.

Expected validation after initialization:

- expected directories exist
- required policy and README files exist
- phase documents exist
- skill directories exist with `SKILL.md`
- Claude-readable symlink exists and points to `AGENTS.md`
- scaffold Python project config files are syntactically valid

## Acceptance Criteria

The initialization is complete when:

1. The repository structure matches the master plan at the scaffold level.
2. `AGENTS.md` exists and a Claude-readable symlink points to it.
3. Each phase has a dedicated document under `docs/phases/`.
4. The 3 initial skill directories exist with contract-oriented placeholders.
5. Core, adaptor, tools, template, reference, and test areas all exist with explicit purpose markers.
6. No business logic or runtime implementation is incorrectly presented as complete.
7. Repository-level documents explicitly state that DBA Assistant is a Deep Agent SDK-based project.

## Implementation Notes for the Later Plan

When moving from this design into the implementation plan, the work should be organized as scaffold tasks only:

- task for repository policy and root config files
- task for phase document creation
- task for Python package scaffold under `src/dba_assistant/`
- task for skill scaffold generation
- task for template/reference/test scaffold
- task for symlink creation and verification

The implementation plan should explicitly avoid blending scaffold creation with actual phase delivery.

## Self-Review

- No placeholders such as `TBD` or `TODO` remain in this design.
- The scope is intentionally limited to repository scaffolding.
- The design aligns with the user correction that implementation will happen phase by phase later.
- The design preserves the master plan structure without claiming runtime completeness.
