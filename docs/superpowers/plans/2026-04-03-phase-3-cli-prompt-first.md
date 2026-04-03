# Phase 3 CLI Prompt-First Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Phase 3 CLI prompt-first while preserving a small parameter layer for override and future GUI/API reuse, and document the resulting parameter contract and request data flow.

**Architecture:** Extend the existing prompt parser and normalized request model so prompt text can carry Phase 3 reporting intent such as profile, report format, output path, and routing hints. Keep the CLI thin, let explicit CLI parameters override prompt-derived values, rename the internal route vocabulary to stable formal names, and add user-facing docs that explain both usage and the end-to-end execution flow.

**Tech Stack:** Python 3.11, argparse, PyYAML, pytest, existing DBA Assistant application/service layer

---

### Task 1: Extend the normalized request contract for prompt-first Phase 3 output intent

**Files:**
- Modify: `src/dba_assistant/application/request_models.py`
- Test: `tests/unit/application/test_prompt_parser.py`

- [ ] **Step 1: Write the failing tests for report format and output-path parsing**

```python
from pathlib import Path

from dba_assistant.application.prompt_parser import normalize_raw_request


def test_normalize_raw_request_extracts_docx_report_request() -> None:
    request = normalize_raw_request(
        "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.profile_name == "rcs"
    assert request.runtime_inputs.output_mode == "report"
    assert request.runtime_inputs.report_format == "docx"
    assert request.runtime_inputs.output_path == Path("/tmp/rcs.docx")


def test_normalize_raw_request_extracts_mysql_routing_hint() -> None:
    request = normalize_raw_request(
        "按 generic profile 分析这个 rdb，使用 mysql 路径并输出 summary",
        default_output_mode="summary",
    )

    assert request.rdb_overrides.route_name == "legacy_sql_pipeline"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/application/test_prompt_parser.py -q`
Expected: FAIL because `RuntimeInputs` and `RdbOverrides` do not yet expose `report_format`, `output_path`, or `route_name`.

- [ ] **Step 3: Add the new normalized request fields**

```python
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RuntimeInputs:
    redis_host: str | None = None
    redis_port: int = 6379
    redis_db: int = 0
    output_mode: str = "summary"
    report_format: str | None = None
    output_path: Path | None = None
    input_paths: tuple[Path, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RdbOverrides:
    profile_name: str | None = None
    route_name: str | None = None
    focus_prefixes: tuple[str, ...] = ()
    top_n: dict[str, int] = field(default_factory=dict)
```

- [ ] **Step 4: Update prompt parsing to populate the new fields**

```python
def normalize_raw_request(
    raw_prompt: str,
    *,
    default_output_mode: str,
    input_paths: list[Path] | tuple[Path, ...] | None = None,
) -> NormalizedRequest:
    ...
    report_format, output_path = _extract_report_output_intent(prompt)
    route_name = _extract_route_name(prompt)

    return NormalizedRequest(
        raw_prompt=raw_prompt,
        prompt=prompt,
        runtime_inputs=RuntimeInputs(
            redis_host=host_match.group("host") if host_match else None,
            redis_port=int(host_match.group("port")) if host_match else 6379,
            redis_db=int(db_match.group("db")) if db_match else 0,
            output_mode="report" if report_format else default_output_mode,
            report_format=report_format,
            output_path=output_path,
            input_paths=tuple(input_paths or ()),
        ),
        secrets=Secrets(...),
        rdb_overrides=_extract_rdb_overrides(prompt, route_name=route_name),
    )
```

- [ ] **Step 5: Run the parser test suite**

Run: `pytest tests/unit/application/test_prompt_parser.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/dba_assistant/application/request_models.py src/dba_assistant/application/prompt_parser.py tests/unit/application/test_prompt_parser.py
git commit -m "feat: parse phase 3 prompt-first report intent"
```

### Task 2: Introduce formal route names and preserve the 3a/3b/3c mapping

**Files:**
- Modify: `src/dba_assistant/skills/redis_rdb_analysis/path_router.py`
- Modify: `src/dba_assistant/skills/redis_rdb_analysis/service.py`
- Modify: `src/dba_assistant/skills/redis_rdb_analysis/types.py`
- Test: `tests/unit/skills/redis_rdb_analysis/test_path_router.py`
- Test: `tests/unit/skills/redis_rdb_analysis/test_rdb_analysis_service.py`
- Test: `tests/unit/tools/test_analyze_rdb.py`

- [ ] **Step 1: Write the failing route-name tests**

```python
from pathlib import Path

from dba_assistant.skills.redis_rdb_analysis.path_router import choose_path
from dba_assistant.skills.redis_rdb_analysis.types import InputSourceKind, RdbAnalysisRequest, SampleInput


def test_choose_path_prefers_formal_direct_memory_analysis_name() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
    )

    assert choose_path(request) == "direct_memory_analysis"


def test_choose_path_returns_precomputed_dataset_for_precomputed_input() -> None:
    request = RdbAnalysisRequest(
        prompt="summarize this exported analysis",
        inputs=[SampleInput(source=Path("/tmp/export.json"), kind=InputSourceKind.PRECOMPUTED)],
    )

    assert choose_path(request) == "precomputed_dataset"
```

- [ ] **Step 2: Run the route tests to verify they fail**

Run: `pytest tests/unit/skills/redis_rdb_analysis/test_path_router.py -q`
Expected: FAIL because the current router still returns `3a`, `3b`, and `3c`.

- [ ] **Step 3: Replace internal route naming with formal names**

```python
_EXPLICIT_PATHS = frozenset(
    {
        "legacy_sql_pipeline",
        "precomputed_dataset",
        "direct_memory_analysis",
    }
)
_ROUTE_NAME_BY_PHASE_LABEL = {
    "3a": "legacy_sql_pipeline",
    "3b": "precomputed_dataset",
    "3c": "direct_memory_analysis",
}


def choose_path(request: RdbAnalysisRequest) -> str:
    if request.path_mode in _ROUTE_NAME_BY_PHASE_LABEL:
        return _ROUTE_NAME_BY_PHASE_LABEL[request.path_mode]
    if request.path_mode in _EXPLICIT_PATHS:
        return request.path_mode
    ...
    if any(hint in prompt for hint in _MYSQL_PATH_HINTS):
        return "legacy_sql_pipeline"
    return "direct_memory_analysis"
```

- [ ] **Step 4: Update service metadata and collector dispatch**

```python
if selected_path == "precomputed_dataset":
    ...

if selected_path == "direct_memory_analysis":
    ...

if selected_path == "legacy_sql_pipeline":
    ...

metadata = {
    **report.metadata,
    "input_count": str(len(dataset.samples)),
    "route": selected_path,
}
```

- [ ] **Step 5: Update service and tool tests to expect the formal names**

```python
assert result.metadata["route"] == "legacy_sql_pipeline"
```

- [ ] **Step 6: Run the affected route and service tests**

Run: `pytest tests/unit/skills/redis_rdb_analysis/test_path_router.py tests/unit/skills/redis_rdb_analysis/test_rdb_analysis_service.py tests/unit/tools/test_analyze_rdb.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/dba_assistant/skills/redis_rdb_analysis/path_router.py src/dba_assistant/skills/redis_rdb_analysis/service.py src/dba_assistant/skills/redis_rdb_analysis/types.py tests/unit/skills/redis_rdb_analysis/test_path_router.py tests/unit/skills/redis_rdb_analysis/test_rdb_analysis_service.py tests/unit/tools/test_analyze_rdb.py
git commit -m "refactor: rename phase 3 routes with formal names"
```

### Task 3: Make the CLI prompt-first while preserving explicit overrides

**Files:**
- Modify: `src/dba_assistant/cli.py`
- Modify: `src/dba_assistant/application/service.py`
- Test: `tests/e2e/test_phase_3_rdb_analysis.py`
- Test: `tests/unit/application/test_service.py`

- [ ] **Step 1: Write the failing CLI precedence tests**

```python
from pathlib import Path
from types import SimpleNamespace

from dba_assistant.cli import main


def test_cli_prompt_first_renders_docx_request_from_prompt(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"))
    captured: dict[str, object] = {}

    monkeypatch.setattr("dba_assistant.cli.load_app_config", lambda config_path=None: config)

    def fake_execute_request(request, *, config):
        captured["request"] = request
        return "/tmp/rcs.docx"

    monkeypatch.setattr("dba_assistant.cli.execute_request", fake_execute_request)

    exit_code = main([
        "ask",
        "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx",
        "--input",
        str(source),
    ])

    assert exit_code == 0
    assert captured["request"].rdb_overrides.profile_name == "rcs"
    assert captured["request"].runtime_inputs.report_format == "docx"
    assert captured["request"].runtime_inputs.output_path == Path("/tmp/rcs.docx")
```

- [ ] **Step 2: Run the CLI and service tests to verify they fail**

Run: `pytest tests/e2e/test_phase_3_rdb_analysis.py tests/unit/application/test_service.py -q`
Expected: FAIL because the current CLI and service do not carry prompt-derived report intent through execution.

- [ ] **Step 3: Add a small explicit override layer without changing the prompt-first UX**

```python
ask_parser.add_argument("--config", default=None)
ask_parser.add_argument("--input", action="append", default=[], type=Path)
ask_parser.add_argument("--profile", default=None)
ask_parser.add_argument("--report-format", default=None)
ask_parser.add_argument("--output", default=None, type=Path)
```

```python
request = normalize_raw_request(...)
request = _apply_cli_overrides(
    request,
    profile_name=args.profile,
    report_format=args.report_format,
    output_path=args.output,
)
```

- [ ] **Step 4: Update the application service so summary vs docx output follows the normalized request**

```python
output_format = request.runtime_inputs.report_format or "summary"

artifact = generate_analysis_report(
    analysis_result,
    ReportOutputConfig(
        format=ReportFormat(output_format),
        output_path=request.runtime_inputs.output_path,
        template_name="rdb-analysis",
    ),
)
return artifact.content or str(artifact.output_path or "")
```

- [ ] **Step 5: Run the CLI and application tests**

Run: `pytest tests/e2e/test_phase_3_rdb_analysis.py tests/unit/application/test_service.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/dba_assistant/cli.py src/dba_assistant/application/service.py tests/e2e/test_phase_3_rdb_analysis.py tests/unit/application/test_service.py
git commit -m "feat: make phase 3 cli prompt-first with overrides"
```

### Task 4: Add user-facing Phase 3 CLI and flow documentation

**Files:**
- Create: `docs/phase-3-cli-usage.md`
- Create: `docs/phase-3-rdb-flow.md`
- Modify: `docs/phases/phase-3.md`

- [ ] **Step 1: Write the CLI usage document**

```markdown
# Phase 3 CLI Usage

## Prompt-First Usage

Primary command:

```sh
dba-assistant ask "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx" --input /path/to/dump.rdb
```

## Retained Parameters

- `--config`: load an explicit config file
- `--input`: provide one or more local input files
- `--profile`: explicit override for prompt-derived profile selection
- `--report-format`: explicit override for prompt-derived output format
- `--output`: explicit override for prompt-derived output path

## Precedence

1. prompt is parsed first
2. explicit parameters override prompt-derived values
3. execution uses the final normalized request
```

- [ ] **Step 2: Write the flow document**

```markdown
# Phase 3 RDB Flow

## Example Request

`按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx`

## Data Flow

1. CLI receives prompt plus optional parameters.
2. `prompt_parser` extracts `profile_name=rcs`, `report_format=docx`, and `output_path=/tmp/rcs.docx`.
3. Explicit parameters, if present, override those values.
4. The application layer builds a normalized request.
5. `analyze_rdb` resolves the input source and chooses one of:
   - `legacy_sql_pipeline` (`3a`)
   - `precomputed_dataset` (`3b`)
   - `direct_memory_analysis` (`3c`)
6. `profile_resolver` loads the profile and applies prompt overrides.
7. `generate_analysis_report` writes the final report artifact.
```

- [ ] **Step 3: Update the Phase 3 phase document with the route-name mapping**

```markdown
| Path | Formal Route Name | Description |
|------|-------------------|-------------|
| A: Full custom pipeline | `legacy_sql_pipeline` | Reproduce the current manual workflow |
| B: Skip parsing and import | `precomputed_dataset` | Analysis data already exists in MySQL |
| C: Pure offline direct analysis | `direct_memory_analysis` | No external tool or database dependency |
```

- [ ] **Step 4: Review the docs for consistency**

Run: `sed -n '1,260p' docs/phase-3-cli-usage.md && printf '\n---\n' && sed -n '1,260p' docs/phase-3-rdb-flow.md && printf '\n---\n' && sed -n '1,220p' docs/phases/phase-3.md`
Expected: The prompt-first guidance, retained parameter definitions, and route-name mapping are internally consistent.

- [ ] **Step 5: Commit**

```bash
git add docs/phase-3-cli-usage.md docs/phase-3-rdb-flow.md docs/phases/phase-3.md
git commit -m "docs: add phase 3 cli and flow guides"
```

### Task 5: Run final verification and publish

**Files:**
- Modify: none
- Test: `tests/unit/application/test_prompt_parser.py`
- Test: `tests/unit/application/test_service.py`
- Test: `tests/unit/skills/redis_rdb_analysis/test_path_router.py`
- Test: `tests/unit/skills/redis_rdb_analysis/test_rdb_analysis_service.py`
- Test: `tests/unit/tools/test_analyze_rdb.py`
- Test: `tests/e2e/test_phase_3_rdb_analysis.py`

- [ ] **Step 1: Run the focused verification suite**

Run:

```bash
. .venv/bin/activate && python -m pytest -q \
  tests/unit/application/test_prompt_parser.py \
  tests/unit/application/test_service.py \
  tests/unit/skills/redis_rdb_analysis/test_path_router.py \
  tests/unit/skills/redis_rdb_analysis/test_rdb_analysis_service.py \
  tests/unit/tools/test_analyze_rdb.py \
  tests/e2e/test_phase_3_rdb_analysis.py
```

Expected: PASS

- [ ] **Step 2: Run a real prompt-first CLI smoke test**

Run:

```bash
. .venv/bin/activate && dba-assistant ask \
  "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx" \
  --config config/config.example.yaml \
  --input tests/fixtures/rdb/precomputed/sample_precomputed_rows.json
```

Expected: command exits successfully and prints a resulting output path or summary-compatible success value.

- [ ] **Step 3: Run `git diff --check`**

Run: `git diff --check`
Expected: no output

- [ ] **Step 4: Commit the final verification pass**

```bash
git add -A
git commit -m "chore: finish phase 3 prompt-first cli correction"
```

