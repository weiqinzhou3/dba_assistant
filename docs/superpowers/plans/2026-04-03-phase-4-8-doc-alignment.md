# Phase 4-8 Documentation Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `Phase 4` through `Phase 8` documentation so the target phase definitions strictly follow the current repository architecture: prompt-first surfaces feeding one Deep Agent that orchestrates repository skills and tools.

**Architecture:** The phase documents should define target delivery outcomes, not current CLI behavior. Each phase must assume the stable top-level shape `CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`, with domain collectors, analyzers, reporters, HITL gates, and shared report rendering beneath that boundary.

**Tech Stack:** Markdown docs, repository phase docs under `docs/phases/`, current runtime docs under `README.md` and `docs/phases/current-scaffold-status.md`

---

### Task 1: Rewrite Phase 4-8 Target Definitions

**Files:**
- Modify: `docs/phases/phase-4.md`
- Modify: `docs/phases/phase-5.md`
- Modify: `docs/phases/phase-6.md`
- Modify: `docs/phases/phase-7.md`
- Modify: `docs/phases/phase-8.md`

- [ ] Remove CLI-driven route wording from each phase file.
- [ ] Add the unified Deep Agent architecture constraint to each phase.
- [ ] Express each phase as target delivery scope only, not current implementation status.
- [ ] Make Phase 4 and Phase 6 explicitly skill-oriented (`redis_inspection_report`, `redis_cve_report`) under one Deep Agent.
- [ ] Make Phase 5 explicitly cover normalized requests, tool traces, approvals, and artifacts rather than CLI-command logging only.
- [ ] Make Phase 7 and Phase 8 explicitly extend the shared report/runtime architecture instead of introducing parallel entry systems.

### Task 2: Fix Directly Conflicting Status Docs

**Files:**
- Modify: `docs/phases/current-scaffold-status.md`
- Modify: `docs/phases/README.md` if needed

- [ ] Update current status text so it no longer contradicts delivered Phase 3 work.
- [ ] Keep the separation between “target phase definitions” and “current repo state” explicit.
- [ ] Keep architecture wording consistent with the unified Deep Agent model.

### Task 3: Verify Documentation Consistency

**Files:**
- Check: `README.md`
- Check: `docs/phases/phase-2.md`
- Check: `docs/phases/phase-3.md`
- Check: `docs/phases/phase-4.md`
- Check: `docs/phases/phase-5.md`
- Check: `docs/phases/phase-6.md`
- Check: `docs/phases/phase-7.md`
- Check: `docs/phases/phase-8.md`
- Check: `docs/phases/current-scaffold-status.md`

- [ ] Run a targeted text search for stale CLI-routing and application-routing wording.
- [ ] Read the edited phase docs once end-to-end for contradictions.
- [ ] Run `git diff --check` to ensure clean doc edits.

