# DBA Assistant Architecture Constraints Addendum v1

## Positioning

This document is an **architecture-constraint addendum** to `docs/dba_assistant_master_plan_en.md`.

It does not replace the master plan. Instead, it freezes the architectural constraints that must remain stable during subsequent implementation, so that Codex / Claude Code do not gradually drift the repository into a mixed, confusing, or surface-specific structure.

When this addendum conflicts with temporary implementation convenience, this addendum takes precedence.
When this addendum conflicts with the master plan, the master plan takes precedence unless this addendum is intentionally merged back into the master plan.

---

## Rules

* `skills/` must remain the standard Deep Agents skill directory.
* `skills/` must contain **skill documents only**, not repository business implementation code.
* Python business implementation code must not continue to live under `skills/`.
* The repository-wide execution shape remains:
  `CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`.
* Interface surfaces stay thin and prompt-first.
* Prompt-first does **not** mean removing structured contracts; it means structured contracts should be filled primarily by request normalization rather than by surface-specific business routing.
* Tools are the business actions exposed to the Agent.
* Capabilities / Services are the primary home of domain logic.
* Adaptors, shared parsers, and shared reporting infrastructure are repository-wide shared layers and must not be reimplemented independently inside each capability.
* Collector logic may be capability-specific, but collectors must compose shared infrastructure instead of re-creating it.
* Profile definitions belong to capability/domain implementation layers, not to skill-document layers.
* Dangerous write operations must integrate unified-agent human approval through HITL / `interrupt_on`.
* New code must not introduce routing or orchestration logic back into CLI handlers.

---

## Relationship to the Master Plan

This addendum extends the master plan in four important ways:

1. It makes the distinction between **skill documents** and **business implementation code** explicit.
2. It freezes the rule that shared infrastructure must not be repeatedly rebuilt inside each capability.
3. It defines where profiles, report templates, collectors, parsers, and capability services belong.
4. It provides a concrete anti-drift checklist for future implementation work.

The master plan already defines the high-level architecture and phased direction.
This addendum narrows the repository implementation rules so that future work remains consistent with the original design intent.

---

## Core Architecture Constraints

### Unified Execution Shape

All user-facing surfaces must still converge into one execution path:

`CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

**Constraint refinement:**

* CLI, API, and WebUI must not become alternative orchestration systems.
* Shared request normalization must happen before Deep Agent execution.
* Capability selection belongs to the unified Deep Agent.
* Surface-specific code must not hardcode domain routing that should belong to the Agent or downstream domain services.

### Skill Boundary

The repository must distinguish clearly between:

1. **Agent-facing skill documents**
2. **Python business implementation code**

A skill is a usage-oriented unit for the Agent, not the home of core implementation code.

Therefore:

* `skills/` is a skill-document layer.
* `skills/<skill-name>/SKILL.md` defines the skill contract for the Agent.
* `skills/` must not become a mixed directory containing business services, collectors, parsers, and domain implementation code.

### Tool Boundary

A tool is the business action exposed to the Agent.

A tool should:

* receive agent-callable parameters
* translate them into normalized domain inputs where needed
* invoke capability/domain services
* return a stable tool result to the Agent

A tool should **not** become the main home of large business logic.

### Capability / Service Boundary

The real domain implementation should live in capability-oriented code packages, for example:

* `src/dba_assistant/capabilities/redis_rdb_analysis/`
* `src/dba_assistant/capabilities/redis_inspection_report/`
* `src/dba_assistant/capabilities/redis_cve_report/`

Capability/service layers may contain:

* service orchestration
* domain types
* path routing
* profile resolution
* collectors
* assemblers
* report-domain logic
* capability-specific normalization

They must not be confused with Agent skill documents.

### Shared Infrastructure Boundary

The repository must maintain shared infrastructure for cross-capability reuse.

These shared layers include, at minimum:

* `adaptors/`

  * Redis adaptor
  * MySQL adaptor
  * SSH adaptor
* `parsers/`

  * shared parser strategies
  * format loaders
  * reusable parser abstractions
* `reporting/` or equivalent shared report infrastructure

  * docx/html/pdf rendering base
  * artifact writing helpers
  * shared table/chart helpers

These layers are cross-capability infrastructure and must not be rebuilt inside each capability package.

### Collector Rule

Collectors may remain capability-specific, because they are often tied to one capability's required data contract.

However:

* collectors must compose shared adaptors/parsers where possible
* collectors must not secretly reintroduce capability-local Redis/MySQL/SSH clients
* collectors should focus on data gathering and normalization for the capability, not reimplementing shared system integrations

### Profile Rule

Profiles must be preserved when they represent:

* report templates
* default views
* section structures
* grading rules
* capability-specific presentation defaults

But profiles do **not** belong in the skill-document layer.

Profiles belong in the capability/domain implementation layer, for example:

* `src/dba_assistant/capabilities/redis_cve_report/profiles/`
* `src/dba_assistant/capabilities/redis_rdb_analysis/profiles/`
* `src/dba_assistant/capabilities/redis_inspection_report/profiles/`

`SKILL.md` may describe:

* which profiles are supported
* which profile is default
* when a profile should be used

But profile implementation definitions must remain outside `skills/`.

---

## Required Directory Pattern

The repository should converge toward the following pattern:

```text
skills/
  redis-cve-report/
    SKILL.md
  redis-inspection-report/
    SKILL.md
  redis-rdb-analysis/
    SKILL.md

src/
  dba_assistant/
    interface/
    application/
    orchestrator/
    tools/
    capabilities/
      redis_cve_report/
      redis_inspection_report/
      redis_rdb_analysis/
    adaptors/
    parsers/
    reporting/
    core/
```

### Naming Rules

#### Skill-document directories

Skill-document directories under `skills/` must follow Deep Agents naming rules:

* lowercase
* alphanumeric plus single hyphens
* no underscores

Examples:

* `redis-cve-report`
* `redis-inspection-report`
* `redis-rdb-analysis`

#### Python package directories

Python code packages must remain valid Python package names:

* use `snake_case`
* do not use hyphens

Examples:

* `redis_cve_report`
* `redis_inspection_report`
* `redis_rdb_analysis`

This means the repository must intentionally maintain **different naming conventions** for:

* skill-document directories
* Python implementation directories

This is correct and expected.

---

## Skill Content Constraints

Each skill under `skills/` should contain:

* valid YAML frontmatter
* one-line summary
* trigger conditions
* when-to-use guidance
* risk / approval notes
* recommended tool usage
* profile usage notes
* examples

It should **not** contain:

* Python business logic
* collector implementations
* parser implementations
* MySQL/SSH/Redis adaptor code
* report generation implementation code

---

## Tool-to-Capability Dependency Rule

Tools must not depend on Python packages whose path semantically represents Agent skills.

That means:

* `tools/*.py` should not import `skills.*` business code packages
* `orchestrator/*.py` should not directly depend on `skills.*` implementation packages
* instead, both should depend on capability/domain packages

**Preferred direction:**

`tools -> capabilities/services -> shared adaptors/parsers/reporting`

**Disallowed drift direction:**

`tools -> skills business package -> mixed domain code`

---

## Prompt-First Constraint Clarification

The repository remains prompt-first.

This means:

* user intent should primarily be expressed in prompt form
* structured request fields still exist inside the application boundary
* prompt parsing and request normalization should fill those fields when possible
* CLI flags remain available as overrides / reproducibility / debugging aids

This does **not** mean:

* removing structured contracts
* moving business routing back into CLI
* letting surface code bypass the normalized request boundary

---

## Shared vs Capability-Specific Decision Rule

When deciding where code belongs, use the following rule:

### Put code in shared infrastructure if:

* multiple capabilities are likely to reuse it
* it describes an external system boundary
* it is a generic parser/loader/renderer abstraction
* it is a generic report-output facility

Examples:

* Redis connection adaptor
* MySQL connection/query adaptor
* SSH adaptor
* generic RDB parser strategy abstraction
* generic docx/html/pdf renderers

### Put code in capability/domain packages if:

* it exists primarily for one capability's analysis semantics
* it encodes one capability's collectors, profiles, report sections, or route rules
* it transforms shared raw inputs into one capability's domain-specific analysis result

Examples:

* Redis RDB route choice logic
* Redis CVE report profile definitions
* Redis inspection report-specific normalization rules

---

## Explicit Anti-Patterns

The following patterns are forbidden going forward:

### Anti-pattern 1: Skill directory as mixed implementation directory

Example of forbidden drift:

* `skills/redis_rdb_analysis/service.py`
* `skills/redis_rdb_analysis/types.py`
* `skills/redis_rdb_analysis/collectors/...`

### Anti-pattern 2: Tool importing skill implementation package

Example of forbidden drift:

* `tools/analyze_rdb.py` importing `skills.redis_rdb_analysis.service`

### Anti-pattern 3: Rebuilding SSH / MySQL / Redis clients inside each capability

Example of forbidden drift:

* one SSH client under RDB analysis
* another SSH client under inspection
* another MySQL query helper under CVE report

### Anti-pattern 4: Profile implementation stored next to skill docs

Skill docs may describe profiles, but profile implementation must live in capability/domain code.

### Anti-pattern 5: Surface-specific business routing

CLI/API/WebUI handlers must not become parallel domain routers.

---

## Redis RDB as the Canonical Migration Example

The Redis RDB capability should be used as the canonical reference for this restructuring.

### Desired end state

* `skills/redis-rdb-analysis/SKILL.md` contains only skill-facing guidance.
* `src/dba_assistant/capabilities/redis_rdb_analysis/` contains the domain implementation.
* `tools/analyze_rdb.py` calls the capability/service layer.
* shared Redis/MySQL/SSH access remains in `adaptors/`.
* shared parser infrastructure remains in `parsers/` where appropriate.

If this pattern is stable for Redis RDB, the same repository rule can later be applied to inspection and CVE capabilities.

---

## Review Checklist for Codex / Claude Code

Before introducing a new file or module, the coding agent must answer:

1. Is this file a skill document or business implementation code?
2. If it is business code, why is it not under a capability/domain package?
3. Is this external-system access logic already present in shared adaptors?
4. Is this parser/renderer generic enough to belong in shared infrastructure?
5. If this is collector logic, is it reusing shared adaptors instead of reimplementing them?
6. If this is profile logic, is it in the capability layer rather than in `skills/`?
7. Will this change make CLI/API/WebUI thicker than they should be?
8. Does this change reinforce or violate:
   `skills -> tools -> capabilities/services -> shared infrastructure`

If the answer indicates mixing boundaries, the change should be redesigned before implementation.

---

## Implementation Guidance for Future Changes

When a future feature is added:

1. Add or update the corresponding skill document under `skills/`.
2. Expose or extend the necessary tool surface under `tools/`.
3. Implement or extend the domain behavior in `capabilities/`.
4. Reuse shared adaptors/parsers/reporting if applicable.
5. Only introduce new shared infrastructure if multiple capabilities exhibit the same pattern.

This keeps the project aligned with the master plan while preventing structural drift.

---

## Final Constraint Summary

The project must converge on the following stable architecture:

```text
skills (Deep Agents skill docs only)
  -> tools (agent-callable actions)
  -> capabilities/services (domain implementation)
  -> shared adaptors/parsers/reporting (cross-capability infrastructure)
  -> external systems / files / CLIs
```

This is the architectural constraint that should be used to review all subsequent changes.

