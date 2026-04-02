# Phase 3 Redis RDB Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `redis_rdb_analysis` skill end-to-end across `3a`, `3b`, and `3c`, with a generic profile, an RCS profile, unified analysis contracts, prompt-driven bounded overrides, and generic report generation.

**Architecture:** Keep one skill, `redis_rdb_analysis`, and route all RDB analysis through a single application/service boundary. Normalize all collector paths into one dataset model, resolve `generic` or `rcs` profiles plus prompt overrides into an effective profile, run deterministic analyzers, and render results through a generic report-generation layer. Remote Redis support stays inside `analyze_rdb`, but actual RDB acquisition pauses for explicit confirmation.

**Tech Stack:** Python 3.11, pytest, PyYAML, python-docx, redis-py, PyMySQL, Paramiko, rdbtools CLI/library, dataclasses, subprocess

---

## File Structure Map

**Modify existing files:**

- Modify: `pyproject.toml`
- Modify: `src/dba_assistant/application/request_models.py`
- Modify: `src/dba_assistant/application/prompt_parser.py`
- Modify: `src/dba_assistant/application/service.py`
- Modify: `src/dba_assistant/cli.py`
- Modify: `src/dba_assistant/adaptors/__init__.py`
- Modify: `src/dba_assistant/adaptors/redis_adaptor.py`
- Modify: `src/dba_assistant/adaptors/mysql_adaptor.py`
- Modify: `src/dba_assistant/adaptors/ssh_adaptor.py`
- Modify: `src/dba_assistant/core/reporter/__init__.py`
- Modify: `src/dba_assistant/core/reporter/docx_reporter.py`
- Modify: `src/dba_assistant/core/reporter/summary_reporter.py`
- Modify: `src/dba_assistant/deep_agent_integration/tool_registry.py`
- Modify: `src/dba_assistant/skills/redis_rdb_analysis/SKILL.md`
- Modify: `src/dba_assistant/skills/redis_rdb_analysis/README.md`
- Modify: `src/dba_assistant/skills/redis_rdb_analysis/__init__.py`
- Modify: `src/dba_assistant/skills/redis_rdb_analysis/analyzer.py`
- Modify: `src/dba_assistant/skills/redis_rdb_analysis/collectors/__init__.py`
- Modify: `templates/reports/rdb-analysis/template_spec.py`
- Modify: `docs/phases/phase-3.md`

**Create shared report-model files:**

- Create: `src/dba_assistant/core/reporter/report_model.py`
- Create: `src/dba_assistant/core/reporter/generate_analysis_report.py`

**Create Phase 3 skill files:**

- Create: `src/dba_assistant/skills/redis_rdb_analysis/types.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/profile_resolver.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/path_router.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/service.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/remote_input.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/profiles/generic.yaml`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/profiles/rcs.yaml`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/reports/__init__.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/reports/assembler.py`

**Create Phase 3 analyzer files:**

- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzers/__init__.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzers/overall.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzers/key_types.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzers/expiration.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzers/prefixes.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzers/big_keys.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzers/rcs_custom.py`

**Create Phase 3 collector files:**

- Create: `src/dba_assistant/skills/redis_rdb_analysis/collectors/path_a_rdb_toolchain_collector.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/collectors/path_b_precomputed_collector.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/collectors/path_c_direct_parser_collector.py`

**Create tool files:**

- Create: `src/dba_assistant/tools/analyze_rdb.py`
- Create: `src/dba_assistant/tools/generate_analysis_report.py`

**Create test fixtures and tests:**

- Create: `tests/fixtures/rdb/direct/sample_key_records.json`
- Create: `tests/fixtures/rdb/precomputed/sample_precomputed_rows.json`
- Create: `tests/fixtures/rdb/sql/sample_top_keys.csv`
- Create: `tests/unit/skills/redis_rdb_analysis/test_types.py`
- Create: `tests/unit/skills/redis_rdb_analysis/test_profile_resolver.py`
- Create: `tests/unit/skills/redis_rdb_analysis/test_path_router.py`
- Create: `tests/unit/skills/redis_rdb_analysis/test_service.py`
- Create: `tests/unit/skills/redis_rdb_analysis/test_remote_input.py`
- Create: `tests/unit/skills/redis_rdb_analysis/analyzers/test_overall.py`
- Create: `tests/unit/skills/redis_rdb_analysis/analyzers/test_key_types.py`
- Create: `tests/unit/skills/redis_rdb_analysis/analyzers/test_expiration.py`
- Create: `tests/unit/skills/redis_rdb_analysis/analyzers/test_prefixes.py`
- Create: `tests/unit/skills/redis_rdb_analysis/analyzers/test_big_keys.py`
- Create: `tests/unit/skills/redis_rdb_analysis/reports/test_assembler.py`
- Create: `tests/unit/skills/redis_rdb_analysis/collectors/test_path_a_rdb_toolchain_collector.py`
- Create: `tests/unit/skills/redis_rdb_analysis/collectors/test_path_b_precomputed_collector.py`
- Create: `tests/unit/skills/redis_rdb_analysis/collectors/test_path_c_direct_parser_collector.py`
- Create: `tests/unit/tools/test_analyze_rdb.py`
- Create: `tests/unit/core/reporter/test_generate_analysis_report.py`
- Create: `tests/e2e/test_phase_3_rdb_analysis.py`

### Task 1: Add Phase 3 Dependencies and Shared Skill Contracts

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/dba_assistant/skills/redis_rdb_analysis/SKILL.md`
- Modify: `src/dba_assistant/skills/redis_rdb_analysis/README.md`
- Modify: `src/dba_assistant/skills/redis_rdb_analysis/__init__.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/types.py`
- Create: `tests/unit/skills/redis_rdb_analysis/test_types.py`

- [ ] **Step 1: Write the failing tests for Phase 3 request, dataset, and confirmation contracts**

```python
# tests/unit/skills/redis_rdb_analysis/test_types.py
from pathlib import Path

from dba_assistant.skills.redis_rdb_analysis.types import (
    AnalysisStatus,
    ConfirmationRequest,
    EffectiveProfile,
    InputSourceKind,
    KeyRecord,
    NormalizedRdbDataset,
    RdbAnalysisRequest,
    SampleInput,
)


def test_rdb_analysis_request_defaults_to_generic_and_merged_output() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
    )

    assert request.profile_name == "generic"
    assert request.merge_multiple_inputs is True
    assert request.path_mode == "auto"


def test_normalized_dataset_keeps_sample_and_record_boundaries() -> None:
    dataset = NormalizedRdbDataset(
        samples=[SampleInput(source=Path("/tmp/a.rdb"), kind=InputSourceKind.LOCAL_RDB, label="host-a")],
        records=[
            KeyRecord(
                sample_id="sample-1",
                key_name="loan:10001",
                key_type="hash",
                size_bytes=2048,
                has_expiration=False,
                ttl_seconds=None,
                prefix_segments=("loan",),
            )
        ],
    )

    assert dataset.samples[0].label == "host-a"
    assert dataset.records[0].prefix_segments == ("loan",)


def test_confirmation_request_marks_remote_fetch_as_confirmation_required() -> None:
    response = ConfirmationRequest(
        status=AnalysisStatus.CONFIRMATION_REQUIRED,
        message="Existing RDB found on remote host.",
        required_action="fetch_existing",
    )

    assert response.status is AnalysisStatus.CONFIRMATION_REQUIRED
    assert response.required_action == "fetch_existing"
```

- [ ] **Step 2: Run the new type tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis/test_types.py`

Expected: FAIL because `dba_assistant.skills.redis_rdb_analysis.types` does not exist yet.

- [ ] **Step 3: Add the dependencies and implement the shared Phase 3 type layer**

```toml
# pyproject.toml
[project]
dependencies = [
    "openai-agents",
    "PyYAML>=6,<7",
    "python-docx>=1.1,<2",
    "redis>=5",
    "PyMySQL>=1,<2",
    "paramiko>=3,<4",
    "rdbtools>=0.1,<1",
]
```

```python
# src/dba_assistant/skills/redis_rdb_analysis/types.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class InputSourceKind(str, Enum):
    LOCAL_RDB = "local_rdb"
    REMOTE_REDIS = "remote_redis"
    PRECOMPUTED = "precomputed"


class AnalysisStatus(str, Enum):
    READY = "ready"
    CONFIRMATION_REQUIRED = "confirmation_required"


@dataclass(frozen=True)
class SampleInput:
    source: Path | str
    kind: InputSourceKind
    label: str | None = None


@dataclass(frozen=True)
class KeyRecord:
    sample_id: str
    key_name: str
    key_type: str
    size_bytes: int
    has_expiration: bool
    ttl_seconds: int | None
    prefix_segments: tuple[str, ...]


@dataclass(frozen=True)
class NormalizedRdbDataset:
    samples: list[SampleInput]
    records: list[KeyRecord]


@dataclass(frozen=True)
class EffectiveProfile:
    name: str
    sections: tuple[str, ...]
    focus_prefixes: tuple[str, ...] = ()
    top_n: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RdbAnalysisRequest:
    prompt: str
    inputs: list[SampleInput]
    profile_name: str = "generic"
    path_mode: str = "auto"
    merge_multiple_inputs: bool = True
    profile_overrides: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfirmationRequest:
    status: AnalysisStatus
    message: str
    required_action: str
```

```markdown
# src/dba_assistant/skills/redis_rdb_analysis/README.md

Phase 3 owns the `redis_rdb_analysis` skill.

This package will provide:

- profile-driven Redis RDB analysis
- path routing across `3a`, `3b`, and `3c`
- remote Redis discovery plus confirmation-gated RDB acquisition
- report assembly for generic and RCS output profiles
```

```python
# src/dba_assistant/skills/redis_rdb_analysis/__init__.py
from dba_assistant.skills.redis_rdb_analysis.types import (
    AnalysisStatus,
    ConfirmationRequest,
    EffectiveProfile,
    InputSourceKind,
    KeyRecord,
    NormalizedRdbDataset,
    RdbAnalysisRequest,
    SampleInput,
)

__all__ = [
    "AnalysisStatus",
    "ConfirmationRequest",
    "EffectiveProfile",
    "InputSourceKind",
    "KeyRecord",
    "NormalizedRdbDataset",
    "RdbAnalysisRequest",
    "SampleInput",
]
```

- [ ] **Step 4: Run the type tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis/test_types.py`

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit the shared contracts**

```bash
git add pyproject.toml \
  src/dba_assistant/skills/redis_rdb_analysis/SKILL.md \
  src/dba_assistant/skills/redis_rdb_analysis/README.md \
  src/dba_assistant/skills/redis_rdb_analysis/__init__.py \
  src/dba_assistant/skills/redis_rdb_analysis/types.py \
  tests/unit/skills/redis_rdb_analysis/test_types.py
git commit -m "feat: add phase 3 rdb analysis contracts"
```

### Task 2: Add Profile Files and Prompt-Driven Bounded Overrides

**Files:**
- Modify: `src/dba_assistant/application/request_models.py`
- Modify: `src/dba_assistant/application/prompt_parser.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/profile_resolver.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/profiles/generic.yaml`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/profiles/rcs.yaml`
- Create: `tests/unit/skills/redis_rdb_analysis/test_profile_resolver.py`

- [ ] **Step 1: Write the failing tests for profile loading and prompt overrides**

```python
# tests/unit/skills/redis_rdb_analysis/test_profile_resolver.py
from dba_assistant.application.prompt_parser import normalize_raw_request
from dba_assistant.skills.redis_rdb_analysis.profile_resolver import resolve_profile


def test_resolve_generic_profile_includes_expiration_and_prefix_sections() -> None:
    request = normalize_raw_request(
        "analyze this rdb with the generic profile",
        default_output_mode="summary",
    )

    profile = resolve_profile("generic", request.rdb_overrides)

    assert "expiration_summary" in profile.sections
    assert "prefix_top_summary" in profile.sections


def test_prompt_can_add_focus_prefix_and_override_top_n() -> None:
    request = normalize_raw_request(
        "按通用profile分析这个rdb，重点看order:*前缀，prefix top 30，hash top 20",
        default_output_mode="summary",
    )

    profile = resolve_profile("generic", request.rdb_overrides)

    assert "order:*" in profile.focus_prefixes
    assert profile.top_n["prefix_top"] == 30
    assert profile.top_n["hash_big_keys"] == 20


def test_rcs_profile_keeps_loan_detail_section() -> None:
    request = normalize_raw_request(
        "按rcs profile分析这批rdb",
        default_output_mode="summary",
    )

    profile = resolve_profile("rcs", request.rdb_overrides)

    assert "loan_prefix_detail" in profile.sections
```

- [ ] **Step 2: Run the profile resolver tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis/test_profile_resolver.py`

Expected: FAIL because `resolve_profile()` and `request.rdb_overrides` do not exist yet.

- [ ] **Step 3: Add profile YAML files, request override fields, and the resolver**

```python
# src/dba_assistant/application/request_models.py
from pathlib import Path
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuntimeInputs:
    redis_host: str | None = None
    redis_port: int = 6379
    redis_db: int = 0
    output_mode: str = "summary"
    input_paths: tuple[Path, ...] = ()
    report_format: str = "summary"


@dataclass(frozen=True)
class RdbOverrides:
    profile_name: str | None = None
    focus_prefixes: tuple[str, ...] = ()
    include_sections: tuple[str, ...] = ()
    top_n: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedRequest:
    raw_prompt: str
    prompt: str
    runtime_inputs: RuntimeInputs
    secrets: Secrets
    rdb_overrides: RdbOverrides = field(default_factory=RdbOverrides)
```

```python
# src/dba_assistant/application/prompt_parser.py
_PROFILE_PATTERN = re.compile(r"(?i)\b(?P<profile>generic|rcs)\s+profile\b|(?P<profile_cn>通用|rcs)\s*profile")
_PREFIX_PATTERN = re.compile(r"(?i)(?P<prefix>[a-z0-9_-]+:\*)")
_TOP_N_PATTERN = re.compile(r"(?i)(?P<section>prefix|hash|list|set|top)\s+top\s+(?P<count>\d+)")


def normalize_raw_request(
    raw_prompt: str,
    *,
    default_output_mode: str,
    input_paths: tuple[Path, ...] = (),
) -> NormalizedRequest:
    password_match, password_pattern = _extract_password(raw_prompt)
    prompt = raw_prompt
    if password_match is not None and password_pattern is not None:
        prompt = password_pattern.sub(" ", prompt, count=1)
    prompt = _WHITESPACE_PATTERN.sub(" ", prompt).strip()
    host_match = _HOST_PORT_PATTERN.search(prompt)
    db_match = _DB_PATTERN.search(prompt)
    output_mode = _extract_output_mode(prompt, default_output_mode)
    return NormalizedRequest(
        raw_prompt=raw_prompt,
        prompt=prompt,
        runtime_inputs=RuntimeInputs(
            redis_host=host_match.group("host") if host_match else None,
            redis_port=int(host_match.group("port")) if host_match else 6379,
            redis_db=int(db_match.group("db")) if db_match else 0,
            output_mode=output_mode,
            input_paths=input_paths,
            report_format="summary" if output_mode == "summary" else "docx",
        ),
        secrets=Secrets(redis_password=_clean_secret(password_match.group("password")) if password_match else None),
        rdb_overrides=_extract_rdb_overrides(prompt),
    )


def _extract_rdb_overrides(prompt: str) -> RdbOverrides:
    focus_prefixes = tuple(match.group("prefix") for match in _PREFIX_PATTERN.finditer(prompt))
    top_n: dict[str, int] = {}
    for match in _TOP_N_PATTERN.finditer(prompt):
        section = match.group("section").lower()
        count = int(match.group("count"))
        mapping = {
            "prefix": "prefix_top",
            "hash": "hash_big_keys",
            "list": "list_big_keys",
            "set": "set_big_keys",
            "top": "top_big_keys",
        }
        top_n[mapping[section]] = count
    profile_match = _PROFILE_PATTERN.search(prompt)
    profile_name = None
    if profile_match:
        profile_name = (profile_match.group("profile") or profile_match.group("profile_cn") or "").lower()
        if profile_name == "通用":
            profile_name = "generic"
    return RdbOverrides(profile_name=profile_name, focus_prefixes=focus_prefixes, top_n=top_n)
```

```python
# src/dba_assistant/skills/redis_rdb_analysis/profile_resolver.py
from __future__ import annotations

from pathlib import Path

import yaml

from dba_assistant.application.request_models import RdbOverrides
from dba_assistant.skills.redis_rdb_analysis.types import EffectiveProfile


PROFILE_DIR = Path(__file__).resolve().parent / "profiles"


def resolve_profile(profile_name: str, overrides: RdbOverrides) -> EffectiveProfile:
    path = PROFILE_DIR / f"{profile_name}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    sections = tuple(data["report"]["sections"])
    top_n = dict(data["analysis"]["top_n"])
    top_n.update(overrides.top_n)
    focus_prefixes = tuple(data["analysis"].get("focus_prefixes", ())) + overrides.focus_prefixes
    return EffectiveProfile(
        name=data["name"],
        sections=sections,
        focus_prefixes=focus_prefixes,
        top_n=top_n,
    )
```

```yaml
# src/dba_assistant/skills/redis_rdb_analysis/profiles/generic.yaml
name: generic
report:
  sections:
    - executive_summary
    - sample_overview
    - overall_summary
    - key_type_summary
    - key_type_memory_breakdown
    - expiration_summary
    - prefix_top_summary
    - prefix_expiration_breakdown
    - top_big_keys
    - top_keys_by_type
    - conclusions
analysis:
  top_n:
    prefix_top: 20
    top_big_keys: 20
    list_big_keys: 10
    hash_big_keys: 10
    set_big_keys: 10
  focus_prefixes: []
```

```yaml
# src/dba_assistant/skills/redis_rdb_analysis/profiles/rcs.yaml
name: rcs
report:
  sections:
    - background
    - analysis_results
    - overall_summary
    - expiration_summary
    - non_expiration_summary
    - prefix_top_summary
    - loan_prefix_detail
    - top_big_keys
    - top_list_keys
    - top_set_keys
    - top_hash_keys
    - conclusions
analysis:
  top_n:
    prefix_top: 20
    top_big_keys: 20
    list_big_keys: 10
    hash_big_keys: 10
    set_big_keys: 10
  focus_prefixes:
    - "loan:*"
    - "cis:*"
    - "tag:*"
```

- [ ] **Step 4: Run the profile tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis/test_profile_resolver.py`

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit the profile system**

```bash
git add src/dba_assistant/application/request_models.py \
  src/dba_assistant/application/prompt_parser.py \
  src/dba_assistant/skills/redis_rdb_analysis/profile_resolver.py \
  src/dba_assistant/skills/redis_rdb_analysis/profiles/generic.yaml \
  src/dba_assistant/skills/redis_rdb_analysis/profiles/rcs.yaml \
  tests/unit/skills/redis_rdb_analysis/test_profile_resolver.py
git commit -m "feat: add phase 3 profile resolution"
```

### Task 3: Build Generic Analyzers and the Report Assembler

**Files:**
- Create: `src/dba_assistant/core/reporter/report_model.py`
- Create: `src/dba_assistant/core/reporter/generate_analysis_report.py`
- Modify: `src/dba_assistant/core/reporter/__init__.py`
- Modify: `src/dba_assistant/core/reporter/docx_reporter.py`
- Modify: `src/dba_assistant/core/reporter/summary_reporter.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzers/__init__.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzers/overall.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzers/key_types.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzers/expiration.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzers/prefixes.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzers/big_keys.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/analyzers/rcs_custom.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/reports/assembler.py`
- Create: `tests/unit/skills/redis_rdb_analysis/analyzers/test_overall.py`
- Create: `tests/unit/skills/redis_rdb_analysis/analyzers/test_key_types.py`
- Create: `tests/unit/skills/redis_rdb_analysis/analyzers/test_expiration.py`
- Create: `tests/unit/skills/redis_rdb_analysis/analyzers/test_prefixes.py`
- Create: `tests/unit/skills/redis_rdb_analysis/analyzers/test_big_keys.py`
- Create: `tests/unit/skills/redis_rdb_analysis/reports/test_assembler.py`
- Create: `tests/unit/core/reporter/test_generate_analysis_report.py`

- [ ] **Step 1: Write the failing analyzer and assembler tests**

```python
# tests/unit/skills/redis_rdb_analysis/analyzers/test_key_types.py
from dba_assistant.skills.redis_rdb_analysis.analyzers.key_types import analyze_key_types
from dba_assistant.skills.redis_rdb_analysis.types import KeyRecord, NormalizedRdbDataset, SampleInput, InputSourceKind


def test_analyze_key_types_counts_types_and_memory() -> None:
    dataset = NormalizedRdbDataset(
        samples=[SampleInput(source="/tmp/a.rdb", kind=InputSourceKind.LOCAL_RDB, label="host-a")],
        records=[
            KeyRecord("sample-1", "loan:1", "hash", 100, False, None, ("loan",)),
            KeyRecord("sample-1", "queue:1", "list", 300, True, 120, ("queue",)),
        ],
    )

    result = analyze_key_types(dataset)

    assert result["counts"]["hash"] == 1
    assert result["memory_bytes"]["list"] == 300
```

```python
# tests/unit/skills/redis_rdb_analysis/reports/test_assembler.py
from dba_assistant.skills.redis_rdb_analysis.reports.assembler import assemble_report
from dba_assistant.skills.redis_rdb_analysis.types import EffectiveProfile


def test_assembler_orders_sections_from_profile() -> None:
    profile = EffectiveProfile(
        name="generic",
        sections=("executive_summary", "expiration_summary", "top_big_keys"),
    )
    analysis_result = {
        "executive_summary": {"summary": "ok"},
        "expiration_summary": {"summary": "ttl"},
        "top_big_keys": {"rows": [["loan:1", "2048"]]},
    }

    report = assemble_report(analysis_result, profile=profile, title="Redis RDB Analysis")

    assert [section.id for section in report.sections] == [
        "executive_summary",
        "expiration_summary",
        "top_big_keys",
    ]
```

```python
# tests/unit/core/reporter/test_generate_analysis_report.py
from dba_assistant.core.reporter.generate_analysis_report import generate_analysis_report
from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock
from dba_assistant.core.reporter.types import ReportFormat, ReportOutputConfig


def test_generate_analysis_report_returns_summary_artifact() -> None:
    report = AnalysisReport(
        title="Redis RDB Analysis",
        sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
    )

    artifact = generate_analysis_report(report, ReportOutputConfig(format=ReportFormat.SUMMARY))

    assert artifact.content == "Redis RDB Analysis\n\nSummary\nok"
```

- [ ] **Step 2: Run the analyzer and assembler tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis/analyzers/test_key_types.py tests/unit/skills/redis_rdb_analysis/reports/test_assembler.py tests/unit/core/reporter/test_generate_analysis_report.py`

Expected: FAIL because the analyzer modules, report model, and generator do not exist yet.

- [ ] **Step 3: Implement analyzers, report model, and generic report rendering**

```python
# src/dba_assistant/core/reporter/report_model.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TextBlock:
    text: str


@dataclass(frozen=True)
class TableBlock:
    title: str
    columns: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class ReportSectionModel:
    id: str
    title: str
    blocks: list[TextBlock | TableBlock] = field(default_factory=list)


@dataclass(frozen=True)
class AnalysisReport:
    title: str
    sections: list[ReportSectionModel]
    metadata: dict[str, str] = field(default_factory=dict)
```

```python
# src/dba_assistant/skills/redis_rdb_analysis/analyzers/key_types.py
from __future__ import annotations

from collections import Counter, defaultdict

from dba_assistant.skills.redis_rdb_analysis.types import NormalizedRdbDataset


def analyze_key_types(dataset: NormalizedRdbDataset) -> dict[str, dict[str, int]]:
    counts = Counter(record.key_type for record in dataset.records)
    memory_bytes: dict[str, int] = defaultdict(int)
    for record in dataset.records:
        memory_bytes[record.key_type] += record.size_bytes
    return {"counts": dict(counts), "memory_bytes": dict(memory_bytes)}
```

```python
# src/dba_assistant/skills/redis_rdb_analysis/reports/assembler.py
from __future__ import annotations

from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TableBlock, TextBlock
from dba_assistant.skills.redis_rdb_analysis.types import EffectiveProfile


def assemble_report(
    analysis_result: dict[str, dict[str, object]],
    *,
    profile: EffectiveProfile,
    title: str,
) -> AnalysisReport:
    sections: list[ReportSectionModel] = []
    for section_id in profile.sections:
        payload = analysis_result.get(section_id, {})
        blocks = []
        if "summary" in payload:
            blocks.append(TextBlock(text=str(payload["summary"])))
        if "rows" in payload:
            blocks.append(
                TableBlock(
                    title=section_id,
                    columns=[str(value) for value in payload.get("columns", [])],
                    rows=[[str(cell) for cell in row] for row in payload["rows"]],
                )
            )
        sections.append(ReportSectionModel(id=section_id, title=section_id, blocks=blocks))
    return AnalysisReport(title=title, sections=sections)
```

```python
# src/dba_assistant/core/reporter/generate_analysis_report.py
from __future__ import annotations

from dba_assistant.core.reporter.docx_reporter import DocxReporter
from dba_assistant.core.reporter.report_model import AnalysisReport, TableBlock, TextBlock
from dba_assistant.core.reporter.summary_reporter import SummaryReporter
from dba_assistant.core.reporter.types import ReportArtifact, ReportFormat, ReportOutputConfig


def generate_analysis_report(report: AnalysisReport, config: ReportOutputConfig) -> ReportArtifact:
    if config.format is ReportFormat.SUMMARY:
        lines = [report.title]
        for section in report.sections:
            lines.append("")
            lines.append(section.title)
            for block in section.blocks:
                if isinstance(block, TextBlock):
                    lines.append(block.text)
                elif isinstance(block, TableBlock):
                    lines.extend([" | ".join(block.columns)] + [" | ".join(row) for row in block.rows])
        return ReportArtifact(format=ReportFormat.SUMMARY, output_path=None, content="\n".join(lines))
    if config.format is ReportFormat.DOCX:
        return DocxReporter().render(report, config)
    return SummaryReporter().render(report, config)
```

- [ ] **Step 4: Run the analyzer and report tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis/analyzers/test_key_types.py tests/unit/skills/redis_rdb_analysis/reports/test_assembler.py tests/unit/core/reporter/test_generate_analysis_report.py`

Expected: PASS with all tests green.

- [ ] **Step 5: Commit the analyzer and report layer**

```bash
git add src/dba_assistant/core/reporter \
  src/dba_assistant/skills/redis_rdb_analysis/analyzers \
  src/dba_assistant/skills/redis_rdb_analysis/reports \
  tests/unit/skills/redis_rdb_analysis/analyzers \
  tests/unit/skills/redis_rdb_analysis/reports \
  tests/unit/core/reporter/test_generate_analysis_report.py
git commit -m "feat: add phase 3 analyzers and report assembly"
```

### Task 4: Implement Path 3c and Make It the Default Non-MySQL Route

**Files:**
- Create: `src/dba_assistant/skills/redis_rdb_analysis/path_router.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/collectors/path_c_direct_parser_collector.py`
- Create: `tests/fixtures/rdb/direct/sample_key_records.json`
- Create: `tests/unit/skills/redis_rdb_analysis/test_path_router.py`
- Create: `tests/unit/skills/redis_rdb_analysis/collectors/test_path_c_direct_parser_collector.py`

- [ ] **Step 1: Write the failing tests for path routing and direct parsing**

```python
# tests/unit/skills/redis_rdb_analysis/test_path_router.py
from pathlib import Path

from dba_assistant.skills.redis_rdb_analysis.path_router import choose_path
from dba_assistant.skills.redis_rdb_analysis.types import InputSourceKind, RdbAnalysisRequest, SampleInput


def test_choose_path_defaults_to_3c_for_local_rdb() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
    )

    assert choose_path(request) == "3c"


def test_choose_path_uses_3a_when_mysql_staging_is_requested() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb via mysql staging",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
        path_mode="3a",
    )

    assert choose_path(request) == "3a"
```

```python
# tests/unit/skills/redis_rdb_analysis/collectors/test_path_c_direct_parser_collector.py
from pathlib import Path

from dba_assistant.skills.redis_rdb_analysis.collectors.path_c_direct_parser_collector import PathCDirectParserCollector


def test_path_c_collector_returns_normalized_dataset_from_parser_output(tmp_path: Path) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")

    collector = PathCDirectParserCollector(
        parser=lambda _: [
            {"key_name": "loan:1", "key_type": "hash", "size_bytes": 128, "has_expiration": False, "ttl_seconds": None}
        ]
    )

    dataset = collector.collect([source])

    assert dataset.records[0].key_name == "loan:1"
    assert dataset.records[0].prefix_segments == ("loan",)
```

- [ ] **Step 2: Run the path router and path 3c tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis/test_path_router.py tests/unit/skills/redis_rdb_analysis/collectors/test_path_c_direct_parser_collector.py`

Expected: FAIL because the router and direct collector do not exist yet.

- [ ] **Step 3: Implement the path router and direct collector**

```python
# src/dba_assistant/skills/redis_rdb_analysis/path_router.py
from __future__ import annotations

from dba_assistant.skills.redis_rdb_analysis.types import InputSourceKind, RdbAnalysisRequest


def choose_path(request: RdbAnalysisRequest) -> str:
    if request.path_mode in {"3a", "3b", "3c"}:
        return request.path_mode
    if any(sample.kind is InputSourceKind.PRECOMPUTED for sample in request.inputs):
        return "3b"
    if "mysql" in request.prompt.lower() or "sql-style" in request.prompt.lower():
        return "3a"
    return "3c"
```

```python
# src/dba_assistant/skills/redis_rdb_analysis/collectors/path_c_direct_parser_collector.py
from __future__ import annotations

from pathlib import Path
from typing import Callable

from dba_assistant.skills.redis_rdb_analysis.types import InputSourceKind, KeyRecord, NormalizedRdbDataset, SampleInput


class PathCDirectParserCollector:
    def __init__(self, parser: Callable[[Path], list[dict[str, object]]]) -> None:
        self._parser = parser

    def collect(self, paths: list[Path]) -> NormalizedRdbDataset:
        samples: list[SampleInput] = []
        records: list[KeyRecord] = []
        for index, path in enumerate(paths, start=1):
            sample_id = f"sample-{index}"
            samples.append(SampleInput(source=path, kind=InputSourceKind.LOCAL_RDB, label=path.stem))
            for item in self._parser(path):
                key_name = str(item["key_name"])
                records.append(
                    KeyRecord(
                        sample_id=sample_id,
                        key_name=key_name,
                        key_type=str(item["key_type"]),
                        size_bytes=int(item["size_bytes"]),
                        has_expiration=bool(item["has_expiration"]),
                        ttl_seconds=int(item["ttl_seconds"]) if item["ttl_seconds"] is not None else None,
                        prefix_segments=tuple(key_name.split(":")[:1]),
                    )
                )
        return NormalizedRdbDataset(samples=samples, records=records)
```

- [ ] **Step 4: Run the path 3c tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis/test_path_router.py tests/unit/skills/redis_rdb_analysis/collectors/test_path_c_direct_parser_collector.py`

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit the default path routing and direct parser**

```bash
git add src/dba_assistant/skills/redis_rdb_analysis/path_router.py \
  src/dba_assistant/skills/redis_rdb_analysis/collectors/path_c_direct_parser_collector.py \
  tests/unit/skills/redis_rdb_analysis/test_path_router.py \
  tests/unit/skills/redis_rdb_analysis/collectors/test_path_c_direct_parser_collector.py
git commit -m "feat: add phase 3 direct rdb analysis path"
```

### Task 5: Implement Path 3a with `rdb-tools`, MySQL Staging, and SQL Aggregation

**Files:**
- Modify: `src/dba_assistant/adaptors/mysql_adaptor.py`
- Modify: `src/dba_assistant/adaptors/__init__.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/collectors/path_a_rdb_toolchain_collector.py`
- Create: `tests/fixtures/rdb/sql/sample_top_keys.csv`
- Create: `tests/unit/skills/redis_rdb_analysis/collectors/test_path_a_rdb_toolchain_collector.py`

- [ ] **Step 1: Write the failing tests for MySQL staging and SQL aggregation collection**

```python
# tests/unit/skills/redis_rdb_analysis/collectors/test_path_a_rdb_toolchain_collector.py
from pathlib import Path

from dba_assistant.skills.redis_rdb_analysis.collectors.path_a_rdb_toolchain_collector import PathARdbToolchainCollector


def test_path_a_collector_runs_parser_import_and_query(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    calls: list[str] = []

    collector = PathARdbToolchainCollector(
        run_rdb_tools=lambda path: calls.append(f"parse:{path.name}") or tmp_path / "dump.csv",
        mysql_import=lambda csv_path: calls.append(f"import:{csv_path.name}"),
        fetch_rows=lambda: [{"key_name": "loan:1", "key_type": "hash", "size_bytes": 128, "has_expiration": False, "ttl_seconds": None}],
    )

    dataset = collector.collect([source])

    assert calls == ["parse:dump.rdb", "import:dump.csv"]
    assert dataset.records[0].key_name == "loan:1"
```

- [ ] **Step 2: Run the path 3a collector test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis/collectors/test_path_a_rdb_toolchain_collector.py`

Expected: FAIL because the collector and MySQL adaptor behavior do not exist yet.

- [ ] **Step 3: Implement the MySQL adaptor and path 3a collector**

```python
# src/dba_assistant/adaptors/mysql_adaptor.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pymysql


@dataclass(frozen=True)
class MySQLConnectionConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


class MySQLAdaptor:
    def __init__(self, connect: Callable[..., Any] = pymysql.connect) -> None:
        self._connect = connect

    def execute_query(self, config: MySQLConnectionConfig, sql: str) -> list[dict[str, Any]]:
        connection = self._connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=config.database,
            cursorclass=pymysql.cursors.DictCursor,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                return list(cursor.fetchall())
        finally:
            connection.close()
```

```python
# src/dba_assistant/skills/redis_rdb_analysis/collectors/path_a_rdb_toolchain_collector.py
from __future__ import annotations

from pathlib import Path
from typing import Callable

from dba_assistant.skills.redis_rdb_analysis.collectors.path_c_direct_parser_collector import PathCDirectParserCollector
from dba_assistant.skills.redis_rdb_analysis.types import NormalizedRdbDataset


class PathARdbToolchainCollector:
    def __init__(
        self,
        *,
        run_rdb_tools: Callable[[Path], Path],
        mysql_import: Callable[[Path], None],
        fetch_rows: Callable[[], list[dict[str, object]]],
    ) -> None:
        self._run_rdb_tools = run_rdb_tools
        self._mysql_import = mysql_import
        self._fetch_rows = fetch_rows

    def collect(self, paths: list[Path]) -> NormalizedRdbDataset:
        parser_rows: list[dict[str, object]] = []
        for path in paths:
            csv_path = self._run_rdb_tools(path)
            self._mysql_import(csv_path)
            parser_rows.extend(self._fetch_rows())
        bridge = PathCDirectParserCollector(parser=lambda _: parser_rows)
        return bridge.collect(paths)
```

- [ ] **Step 4: Run the path 3a collector test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis/collectors/test_path_a_rdb_toolchain_collector.py`

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit the toolchain and MySQL path**

```bash
git add src/dba_assistant/adaptors/mysql_adaptor.py \
  src/dba_assistant/adaptors/__init__.py \
  src/dba_assistant/skills/redis_rdb_analysis/collectors/path_a_rdb_toolchain_collector.py \
  tests/unit/skills/redis_rdb_analysis/collectors/test_path_a_rdb_toolchain_collector.py
git commit -m "feat: add phase 3 mysql staging path"
```

### Task 6: Implement Path 3b for Existing MySQL or Exported Analysis Data

**Files:**
- Create: `src/dba_assistant/skills/redis_rdb_analysis/collectors/path_b_precomputed_collector.py`
- Create: `tests/fixtures/rdb/precomputed/sample_precomputed_rows.json`
- Create: `tests/unit/skills/redis_rdb_analysis/collectors/test_path_b_precomputed_collector.py`

- [ ] **Step 1: Write the failing test for loading precomputed analysis inputs**

```python
# tests/unit/skills/redis_rdb_analysis/collectors/test_path_b_precomputed_collector.py
from pathlib import Path

from dba_assistant.skills.redis_rdb_analysis.collectors.path_b_precomputed_collector import PathBPrecomputedCollector


def test_path_b_collector_reads_json_rows_and_normalizes_records(tmp_path: Path) -> None:
    source = tmp_path / "rows.json"
    source.write_text(
        '[{"key_name": "loan:1", "key_type": "hash", "size_bytes": 128, "has_expiration": false, "ttl_seconds": null}]',
        encoding="utf-8",
    )

    dataset = PathBPrecomputedCollector().collect([source])

    assert dataset.records[0].key_type == "hash"
    assert dataset.records[0].size_bytes == 128
```

- [ ] **Step 2: Run the path 3b test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis/collectors/test_path_b_precomputed_collector.py`

Expected: FAIL because the precomputed collector does not exist yet.

- [ ] **Step 3: Implement the precomputed collector**

```python
# src/dba_assistant/skills/redis_rdb_analysis/collectors/path_b_precomputed_collector.py
from __future__ import annotations

import json
from pathlib import Path

from dba_assistant.skills.redis_rdb_analysis.collectors.path_c_direct_parser_collector import PathCDirectParserCollector


class PathBPrecomputedCollector:
    def collect(self, paths: list[Path]):
        rows: list[dict[str, object]] = []
        for path in paths:
            rows.extend(json.loads(path.read_text(encoding="utf-8")))
        bridge = PathCDirectParserCollector(parser=lambda _: rows)
        return bridge.collect(paths)
```

- [ ] **Step 4: Run the path 3b test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis/collectors/test_path_b_precomputed_collector.py`

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit the precomputed path**

```bash
git add src/dba_assistant/skills/redis_rdb_analysis/collectors/path_b_precomputed_collector.py \
  tests/unit/skills/redis_rdb_analysis/collectors/test_path_b_precomputed_collector.py
git commit -m "feat: add phase 3 precomputed analysis path"
```

### Task 7: Add Remote Redis Discovery, SSH Acquisition, and Confirmation-Gated Analysis

**Files:**
- Modify: `src/dba_assistant/adaptors/redis_adaptor.py`
- Modify: `src/dba_assistant/adaptors/ssh_adaptor.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/remote_input.py`
- Create: `src/dba_assistant/skills/redis_rdb_analysis/service.py`
- Create: `tests/unit/skills/redis_rdb_analysis/test_remote_input.py`
- Create: `tests/unit/skills/redis_rdb_analysis/test_service.py`

- [ ] **Step 1: Write the failing tests for discovery and confirmation-required analysis**

```python
# tests/unit/skills/redis_rdb_analysis/test_remote_input.py
from dba_assistant.skills.redis_rdb_analysis.remote_input import discover_remote_rdb


def test_discover_remote_rdb_reports_existing_snapshot(monkeypatch) -> None:
    adaptor = type(
        "RedisAdaptorStub",
        (),
        {
            "info": lambda self, *_args, **_kwargs: {"rdb_last_save_time": 1712031000, "rdb_bgsave_in_progress": 0},
            "config_get": lambda self, *_args, **_kwargs: {"available": True, "data": {"dir": "/data/redis", "dbfilename": "dump.rdb"}},
        },
    )()

    discovery = discover_remote_rdb(adaptor, object())

    assert discovery["rdb_path"] == "/data/redis/dump.rdb"
    assert discovery["requires_confirmation"] is True
```

```python
# tests/unit/skills/redis_rdb_analysis/test_service.py
from pathlib import Path

from dba_assistant.skills.redis_rdb_analysis.service import analyze_rdb
from dba_assistant.skills.redis_rdb_analysis.types import AnalysisStatus, InputSourceKind, RdbAnalysisRequest, SampleInput


def test_analyze_rdb_returns_confirmation_request_for_remote_redis_without_confirmation() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze latest rdb",
        inputs=[SampleInput(source="10.0.0.8:6379", kind=InputSourceKind.REMOTE_REDIS)],
    )

    result = analyze_rdb(request, profile=None, remote_discovery=lambda *_args, **_kwargs: {"rdb_path": "/data/redis/dump.rdb"})

    assert result.status is AnalysisStatus.CONFIRMATION_REQUIRED
```

- [ ] **Step 2: Run the remote-input and service tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis/test_remote_input.py tests/unit/skills/redis_rdb_analysis/test_service.py`

Expected: FAIL because the remote discovery and unified service do not exist yet.

- [ ] **Step 3: Implement the narrow SSH adaptor, remote discovery, and unified analysis service**

```python
# src/dba_assistant/adaptors/ssh_adaptor.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import paramiko


@dataclass(frozen=True)
class SSHConnectionConfig:
    host: str
    port: int = 22
    username: str | None = None
    password: str | None = None


class SSHAdaptor:
    def __init__(self, client_factory: Callable[[], paramiko.SSHClient] = paramiko.SSHClient) -> None:
        self._client_factory = client_factory

    def fetch_file(self, config: SSHConnectionConfig, remote_path: str, local_path: Path) -> Path:
        client = self._client_factory()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(config.host, port=config.port, username=config.username, password=config.password)
        try:
            sftp = client.open_sftp()
            try:
                sftp.get(remote_path, str(local_path))
            finally:
                sftp.close()
        finally:
            client.close()
        return local_path
```

```python
# src/dba_assistant/skills/redis_rdb_analysis/remote_input.py
from __future__ import annotations

from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig


def discover_remote_rdb(adaptor: RedisAdaptor, connection: RedisConnectionConfig) -> dict[str, object]:
    persistence = adaptor.info(connection, section="persistence")
    config = adaptor.config_get(connection, pattern="dir")
    filename = adaptor.config_get(connection, pattern="dbfilename")
    data = {}
    data.update(config.get("data", {}))
    data.update(filename.get("data", {}))
    return {
        "lastsave": persistence.get("rdb_last_save_time"),
        "bgsave_in_progress": persistence.get("rdb_bgsave_in_progress"),
        "rdb_path": f"{data.get('dir')}/{data.get('dbfilename')}",
        "requires_confirmation": True,
    }
```

```python
# src/dba_assistant/skills/redis_rdb_analysis/service.py
from __future__ import annotations

from dba_assistant.skills.redis_rdb_analysis.path_router import choose_path
from dba_assistant.skills.redis_rdb_analysis.profile_resolver import resolve_profile
from dba_assistant.skills.redis_rdb_analysis.types import AnalysisStatus, ConfirmationRequest, InputSourceKind, RdbAnalysisRequest


def analyze_rdb(request: RdbAnalysisRequest, *, profile, remote_discovery):
    if any(sample.kind is InputSourceKind.REMOTE_REDIS for sample in request.inputs):
        discovery = remote_discovery(request)
        return ConfirmationRequest(
            status=AnalysisStatus.CONFIRMATION_REQUIRED,
            message=f"Remote RDB available at {discovery['rdb_path']}.",
            required_action="fetch_existing",
        )
    selected_path = choose_path(request)
    effective_profile = profile or resolve_profile(request.profile_name, request.profile_overrides)
    return {"path": selected_path, "profile": effective_profile.name}
```

- [ ] **Step 4: Run the remote-input and unified service tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis/test_remote_input.py tests/unit/skills/redis_rdb_analysis/test_service.py`

Expected: PASS with both tests green.

- [ ] **Step 5: Commit remote discovery and confirmation gating**

```bash
git add src/dba_assistant/adaptors/redis_adaptor.py \
  src/dba_assistant/adaptors/ssh_adaptor.py \
  src/dba_assistant/skills/redis_rdb_analysis/remote_input.py \
  src/dba_assistant/skills/redis_rdb_analysis/service.py \
  tests/unit/skills/redis_rdb_analysis/test_remote_input.py \
  tests/unit/skills/redis_rdb_analysis/test_service.py
git commit -m "feat: add remote rdb discovery and confirmation gating"
```

### Task 8: Wire Tools, CLI, and End-to-End Phase 3 Report Generation

**Files:**
- Modify: `src/dba_assistant/application/service.py`
- Modify: `src/dba_assistant/cli.py`
- Modify: `src/dba_assistant/deep_agent_integration/tool_registry.py`
- Create: `src/dba_assistant/tools/analyze_rdb.py`
- Create: `src/dba_assistant/tools/generate_analysis_report.py`
- Modify: `docs/phases/phase-3.md`
- Create: `tests/unit/tools/test_analyze_rdb.py`
- Create: `tests/e2e/test_phase_3_rdb_analysis.py`

- [ ] **Step 1: Write the failing tests for the public tool surface and CLI wiring**

```python
# tests/unit/tools/test_analyze_rdb.py
from pathlib import Path

from dba_assistant.tools.analyze_rdb import analyze_rdb_tool


def test_analyze_rdb_tool_uses_generic_profile_by_default(tmp_path: Path) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")

    result = analyze_rdb_tool(
        prompt="analyze this rdb",
        input_paths=[source],
        service=lambda request: {"path": request.path_mode, "profile": request.profile_name},
    )

    assert result["profile"] == "generic"
```

```python
# tests/e2e/test_phase_3_rdb_analysis.py
from pathlib import Path

from dba_assistant.cli import main


def test_cli_rdb_command_emits_summary(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")

    monkeypatch.setattr(
        "dba_assistant.application.service.execute_request",
        lambda request, *, config: "Redis RDB Analysis\n\nSummary\nok",
    )

    exit_code = main(["ask", "analyze this rdb with summary", "--input", str(source)])

    assert exit_code == 0
    assert "Redis RDB Analysis" in capsys.readouterr().out
```

- [ ] **Step 2: Run the tool and CLI tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/unit/tools/test_analyze_rdb.py tests/e2e/test_phase_3_rdb_analysis.py`

Expected: FAIL because the public tool module and `--input` CLI support do not exist yet.

- [ ] **Step 3: Implement the tool surface and CLI wiring**

```python
# src/dba_assistant/tools/analyze_rdb.py
from __future__ import annotations

from pathlib import Path

from dba_assistant.skills.redis_rdb_analysis.service import analyze_rdb
from dba_assistant.skills.redis_rdb_analysis.types import InputSourceKind, RdbAnalysisRequest, SampleInput


def analyze_rdb_tool(prompt: str, input_paths: list[Path], *, service=analyze_rdb):
    request = RdbAnalysisRequest(
        prompt=prompt,
        inputs=[SampleInput(source=path, kind=InputSourceKind.LOCAL_RDB) for path in input_paths],
    )
    return service(request)
```

```python
# src/dba_assistant/tools/generate_analysis_report.py
from __future__ import annotations

from dba_assistant.core.reporter.generate_analysis_report import generate_analysis_report

__all__ = ["generate_analysis_report"]
```

```python
# src/dba_assistant/cli.py
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dba-assistant")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("prompt")
    ask_parser.add_argument("--config", default=None)
    ask_parser.add_argument("--input", action="append", default=[])
    return parser
```

```python
# src/dba_assistant/application/service.py
from dba_assistant.core.reporter.types import ReportFormat, ReportOutputConfig
from dba_assistant.deep_agent_integration.run import run_phase2_request


def execute_request(request: NormalizedRequest, *, config: AppConfig) -> str:
    if request.runtime_inputs.input_paths:
        from dba_assistant.tools.analyze_rdb import analyze_rdb_tool
        from dba_assistant.tools.generate_analysis_report import generate_analysis_report

        analysis_result = analyze_rdb_tool(request.prompt, request.runtime_inputs.input_paths)
        artifact = generate_analysis_report(
            analysis_result,
            ReportOutputConfig(
                format=ReportFormat.SUMMARY
                if request.runtime_inputs.output_mode == "summary"
                else ReportFormat.DOCX
            ),
        )
        return artifact.content or ""
    redis_connection = RedisConnectionConfig(
        host=request.runtime_inputs.redis_host,
        port=request.runtime_inputs.redis_port,
        db=request.runtime_inputs.redis_db,
        password=request.secrets.redis_password,
        socket_timeout=config.runtime.redis_socket_timeout,
    )
    return run_phase2_request(request.prompt, config=config, redis_connection=redis_connection)
```

- [ ] **Step 4: Run the focused tool, CLI, and full Phase 3 test suite**

Run: `.venv/bin/python -m pytest -q tests/unit/skills/redis_rdb_analysis tests/unit/tools/test_analyze_rdb.py tests/e2e/test_phase_3_rdb_analysis.py`

Expected: PASS with all Phase 3 tests green.

- [ ] **Step 5: Commit the public tool surface, CLI, and docs**

```bash
git add src/dba_assistant/application/service.py \
  src/dba_assistant/cli.py \
  src/dba_assistant/deep_agent_integration/tool_registry.py \
  src/dba_assistant/tools/analyze_rdb.py \
  src/dba_assistant/tools/generate_analysis_report.py \
  docs/phases/phase-3.md \
  tests/unit/tools/test_analyze_rdb.py \
  tests/e2e/test_phase_3_rdb_analysis.py
git commit -m "feat: wire phase 3 rdb analysis entry points"
```

## Self-Review

### Spec Coverage

- Generic `redis_rdb_analysis` skill with `generic` and `rcs` profiles: covered by Tasks 1-3.
- Prompt-driven bounded overrides: covered by Task 2.
- `3a`, `3b`, and `3c` path preservation: covered by Tasks 4-6.
- Default non-MySQL execution: covered by Task 4 path router and Task 6 service flow.
- Remote Redis discovery and confirmation-gated acquisition: covered by Task 7.
- Generic report output layer: covered by Task 3 and Task 8.
- Prompt-first CLI/debug surface: covered by Task 8.

### Placeholder Scan

- No `TODO`, `TBD`, or “implement later” language remains in the tasks.
- Each task has explicit files, test commands, implementation snippets, and commit steps.

### Type Consistency

- The plan consistently uses `RdbAnalysisRequest`, `NormalizedRdbDataset`, `EffectiveProfile`, `ConfirmationRequest`, `analyze_rdb`, and `generate_analysis_report`.
- The public reporting entry is consistently named `generate_analysis_report`, not `generate_rdb_report`.
- The input-routing contract consistently uses `3a`, `3b`, and `3c`.
