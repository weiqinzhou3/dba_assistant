# Phase 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the shared Collector, Reporter, and Template foundations for Phase 1, including a functional offline collection path, a functional summary reporter, a minimal functional docx reporter, and passing unit tests.

**Architecture:** Keep the repository Python-first and aligned with the Deep Agent SDK direction, but scope Phase 1 strictly to offline, read-only shared foundations. Build a generic `AnalysisResult` schema, a reusable `OfflineCollector` base class, and a minimal template-driven docx reporting path using repository-owned template modules under `templates/reports/`. Reference-layer content under `src/claude-code-source-code/` and `src/docs/` remains isolated and is not imported by production code.

**Tech Stack:** Python 3.11, pytest, python-docx, dataclasses, pathlib, importlib

---

## File Structure Map

**Modify existing files:**

- Modify: `pyproject.toml`
- Modify: `src/dba_assistant/core/analyzer/types.py`
- Modify: `src/dba_assistant/core/collector/__init__.py`
- Modify: `src/dba_assistant/core/collector/types.py`
- Modify: `src/dba_assistant/core/reporter/__init__.py`
- Modify: `src/dba_assistant/core/reporter/types.py`

**Create collector foundation files:**

- Create: `src/dba_assistant/core/collector/offline_collector.py`
- Create: `src/dba_assistant/core/collector/remote_collector.py`

**Create reporter foundation files:**

- Create: `src/dba_assistant/core/reporter/summary_reporter.py`
- Create: `src/dba_assistant/core/reporter/docx_reporter.py`
- Create: `src/dba_assistant/core/reporter/pdf_reporter.py`
- Create: `src/dba_assistant/core/reporter/html_reporter.py`

**Create reference-isolation and template files:**

- Create: `src/references/README.md`
- Create: `templates/reports/shared/cover.py`
- Create: `templates/reports/shared/risk_level_styles.py`
- Create: `templates/reports/shared/disclaimer.py`
- Create: `templates/reports/shared/table_styles.py`
- Create: `templates/reports/rdb-analysis/template_spec.py`
- Create: `templates/reports/inspection/template_spec.py`

**Create unit tests:**

- Create: `tests/unit/core/reporter/test_report_types.py`
- Create: `tests/unit/core/collector/test_offline_collector.py`
- Create: `tests/unit/core/reporter/test_template_specs.py`
- Create: `tests/unit/core/reporter/test_summary_reporter.py`
- Create: `tests/unit/core/reporter/test_docx_reporter.py`

### Task 1: Build Shared Analysis and Reporter Type Foundations

**Files:**
- Modify: `src/dba_assistant/core/analyzer/types.py`
- Modify: `src/dba_assistant/core/reporter/types.py`
- Create: `tests/unit/core/reporter/test_report_types.py`

- [ ] **Step 1: Write the failing tests for shared analysis and reporter types**

```python
# tests/unit/core/reporter/test_report_types.py
from pathlib import Path

from dba_assistant.core.analyzer.types import AnalysisResult, ReportSection, TableModel
from dba_assistant.core.reporter.types import OutputMode, ReportFormat, ReportOutputConfig


def test_report_output_config_defaults_to_docx_report_mode(tmp_path: Path) -> None:
    config = ReportOutputConfig(output_path=tmp_path / "report.docx")

    assert config.mode is OutputMode.REPORT
    assert config.format is ReportFormat.DOCX
    assert config.output_path == tmp_path / "report.docx"


def test_analysis_result_preserves_nested_sections_and_tables() -> None:
    table = TableModel(
        title="Top Keys",
        columns=["Key", "Bytes"],
        rows=[["user:1", "128"]],
    )
    section = ReportSection(
        title="Largest Keys",
        summary="Largest keys in the dataset",
        paragraphs=["The dataset is dominated by user session keys."],
        tables=[table],
    )
    analysis = AnalysisResult(
        title="Redis RDB Analysis",
        summary="No urgent risk found.",
        sections=[section],
        metadata={"environment": "prod"},
        risk_summary={"warning": 1},
    )

    assert analysis.sections[0].tables[0].rows[0][1] == "128"
    assert analysis.metadata["environment"] == "prod"
    assert analysis.risk_summary["warning"] == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/unit/core/reporter/test_report_types.py`

Expected: FAIL with import errors or missing attributes because the shared analysis and reporter types are not implemented yet.

- [ ] **Step 3: Implement the shared analysis result and reporter config types**

```python
# src/dba_assistant/core/analyzer/types.py
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TableModel:
    title: str
    columns: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class ReportSection:
    title: str
    summary: str
    paragraphs: list[str] = field(default_factory=list)
    tables: list[TableModel] = field(default_factory=list)


@dataclass(frozen=True)
class AnalysisResult:
    title: str
    summary: str
    sections: list[ReportSection]
    metadata: dict[str, str] = field(default_factory=dict)
    risk_summary: dict[str, int] = field(default_factory=dict)
```

```python
# src/dba_assistant/core/reporter/types.py
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Generic, TypeVar


class OutputMode(str, Enum):
    REPORT = "report"
    SUMMARY = "summary"


class ReportFormat(str, Enum):
    DOCX = "docx"
    PDF = "pdf"
    HTML = "html"
    SUMMARY = "summary"


@dataclass(frozen=True)
class ReportOutputConfig:
    output_path: Path | None = None
    mode: OutputMode = OutputMode.REPORT
    format: ReportFormat = ReportFormat.DOCX
    template_name: str | None = None


@dataclass(frozen=True)
class ReportArtifact:
    format: ReportFormat
    output_path: Path | None
    content: str | None = None


TAnalysis = TypeVar("TAnalysis")


class IReporter(ABC, Generic[TAnalysis]):
    @abstractmethod
    def render(self, analysis: TAnalysis, config: ReportOutputConfig) -> ReportArtifact:
        raise NotImplementedError
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/unit/core/reporter/test_report_types.py`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit the shared type foundations**

```bash
git add tests/unit/core/reporter/test_report_types.py src/dba_assistant/core/analyzer/types.py src/dba_assistant/core/reporter/types.py
git commit -m "feat: add shared analysis and reporter types"
```

### Task 2: Implement Collector Contracts and the Offline Collector Base Class

**Files:**
- Modify: `src/dba_assistant/core/collector/types.py`
- Modify: `src/dba_assistant/core/collector/__init__.py`
- Create: `src/dba_assistant/core/collector/offline_collector.py`
- Create: `src/dba_assistant/core/collector/remote_collector.py`
- Create: `tests/unit/core/collector/test_offline_collector.py`

- [ ] **Step 1: Write the failing tests for the offline collector path**

```python
# tests/unit/core/collector/test_offline_collector.py
from pathlib import Path

import pytest

from dba_assistant.core.collector.offline_collector import OfflineCollector
from dba_assistant.core.collector.types import CollectedFile, OfflineCollectorInput


class EchoCollector(OfflineCollector[dict[str, str]]):
    def transform(
        self,
        collector_input: OfflineCollectorInput,
        files: list[CollectedFile],
    ) -> dict[str, str]:
        return {str(item.relative_path): item.text for item in files}


def test_offline_collector_reads_a_single_file(tmp_path: Path) -> None:
    source = tmp_path / "info.txt"
    source.write_text("role:master\n", encoding="utf-8")

    result = EchoCollector().collect(OfflineCollectorInput(source=source))

    assert result == {"info.txt": "role:master\n"}


def test_offline_collector_reads_directory_with_suffix_filter(tmp_path: Path) -> None:
    root = tmp_path / "inspection"
    root.mkdir()
    (root / "info.txt").write_text("used_memory:42\n", encoding="utf-8")
    (root / "notes.log").write_text("skip me\n", encoding="utf-8")

    result = EchoCollector().collect(
        OfflineCollectorInput(
            source=root,
            recursive=False,
            allowed_suffixes=(".txt",),
        )
    )

    assert result == {"info.txt": "used_memory:42\n"}


def test_offline_collector_rejects_missing_source(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    with pytest.raises(FileNotFoundError):
        EchoCollector().collect(OfflineCollectorInput(source=missing))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/unit/core/collector/test_offline_collector.py`

Expected: FAIL because `OfflineCollector`, `CollectedFile`, and `OfflineCollectorInput` are not implemented yet.

- [ ] **Step 3: Implement collector contracts and the offline collector base class**

```python
# src/dba_assistant/core/collector/types.py
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar


TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class ICollector(ABC, Generic[TInput, TOutput]):
    @abstractmethod
    def collect(self, collector_input: TInput) -> TOutput:
        raise NotImplementedError


@dataclass(frozen=True)
class OfflineCollectorInput:
    source: Path
    recursive: bool = False
    allowed_suffixes: tuple[str, ...] = ()
    encoding: str = "utf-8"


@dataclass(frozen=True)
class CollectedFile:
    path: Path
    relative_path: Path
    text: str
```

```python
# src/dba_assistant/core/collector/offline_collector.py
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generic, TypeVar

from dba_assistant.core.collector.types import CollectedFile, ICollector, OfflineCollectorInput


TOutput = TypeVar("TOutput")


class OfflineCollector(ICollector[OfflineCollectorInput, TOutput], Generic[TOutput], ABC):
    def collect(self, collector_input: OfflineCollectorInput) -> TOutput:
        source = collector_input.source
        if not source.exists():
            raise FileNotFoundError(f"Offline collection source does not exist: {source}")

        files = self._read_files(collector_input)
        return self.transform(collector_input, files)

    def _read_files(self, collector_input: OfflineCollectorInput) -> list[CollectedFile]:
        source = collector_input.source
        if source.is_file():
            return [self._read_file(source, source.parent, collector_input)]

        pattern = "**/*" if collector_input.recursive else "*"
        collected: list[CollectedFile] = []
        for path in sorted(item for item in source.glob(pattern) if item.is_file()):
            if collector_input.allowed_suffixes and path.suffix not in collector_input.allowed_suffixes:
                continue
            collected.append(self._read_file(path, source, collector_input))
        return collected

    def _read_file(
        self,
        path: Path,
        root: Path,
        collector_input: OfflineCollectorInput,
    ) -> CollectedFile:
        text = path.read_text(encoding=collector_input.encoding)
        relative_path = path.relative_to(root) if path.parent != root else Path(path.name)
        return CollectedFile(path=path, relative_path=relative_path, text=text)

    @abstractmethod
    def transform(
        self,
        collector_input: OfflineCollectorInput,
        files: list[CollectedFile],
    ) -> TOutput:
        raise NotImplementedError
```

```python
# src/dba_assistant/core/collector/remote_collector.py
from __future__ import annotations

from abc import ABC
from typing import Generic, TypeVar

from dba_assistant.core.collector.types import ICollector


TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class RemoteCollector(ICollector[TInput, TOutput], Generic[TInput, TOutput], ABC):
    """Phase 1 interface-only base class for future remote collectors."""
```

```python
# src/dba_assistant/core/collector/__init__.py
"""Collector layer scaffold."""

from dba_assistant.core.collector.offline_collector import OfflineCollector
from dba_assistant.core.collector.remote_collector import RemoteCollector
from dba_assistant.core.collector.types import CollectedFile, ICollector, OfflineCollectorInput

__all__ = [
    "CollectedFile",
    "ICollector",
    "OfflineCollector",
    "OfflineCollectorInput",
    "RemoteCollector",
]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/unit/core/collector/test_offline_collector.py`

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit the collector foundation**

```bash
git add tests/unit/core/collector/test_offline_collector.py src/dba_assistant/core/collector/types.py src/dba_assistant/core/collector/offline_collector.py src/dba_assistant/core/collector/remote_collector.py src/dba_assistant/core/collector/__init__.py
git commit -m "feat: add offline collector foundation"
```

### Task 3: Implement Shared Template Components and Reference Isolation Notes

**Files:**
- Create: `src/references/README.md`
- Create: `templates/reports/shared/cover.py`
- Create: `templates/reports/shared/risk_level_styles.py`
- Create: `templates/reports/shared/disclaimer.py`
- Create: `templates/reports/shared/table_styles.py`
- Create: `templates/reports/rdb-analysis/template_spec.py`
- Create: `templates/reports/inspection/template_spec.py`
- Create: `tests/unit/core/reporter/test_template_specs.py`

- [ ] **Step 1: Write the failing tests for shared template modules**

```python
# tests/unit/core/reporter/test_template_specs.py
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def load_module(relative_path: str, module_name: str):
    path = Path(relative_path)
    spec = spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_risk_level_styles_expose_critical_style() -> None:
    module = load_module(
        "templates/reports/shared/risk_level_styles.py",
        "risk_level_styles",
    )

    assert module.RISK_LEVEL_STYLES["critical"]["label"] == "Critical"


def test_rdb_template_spec_exposes_cover_and_disclaimer_flags() -> None:
    module = load_module(
        "templates/reports/rdb-analysis/template_spec.py",
        "rdb_template_spec",
    )

    assert module.TEMPLATE["template_name"] == "rdb-analysis"
    assert module.TEMPLATE["include_disclaimer"] is True


def test_inspection_template_spec_exposes_summary_heading() -> None:
    module = load_module(
        "templates/reports/inspection/template_spec.py",
        "inspection_template_spec",
    )

    assert module.TEMPLATE["template_name"] == "inspection"
    assert module.TEMPLATE["summary_heading"] == "Executive Summary"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/unit/core/reporter/test_template_specs.py`

Expected: FAIL because the shared template component files and template spec files do not exist yet.

- [ ] **Step 3: Implement the shared template modules and reference-isolation note**

```python
# templates/reports/shared/cover.py
from dataclasses import dataclass


@dataclass(frozen=True)
class CoverSpec:
    title: str
    subtitle: str
    metadata_order: tuple[str, ...]


def build_cover_spec(
    title: str,
    subtitle: str,
    metadata_order: tuple[str, ...] = ("client", "environment", "generated_at"),
) -> CoverSpec:
    return CoverSpec(title=title, subtitle=subtitle, metadata_order=metadata_order)
```

```python
# templates/reports/shared/risk_level_styles.py
RISK_LEVEL_STYLES = {
    "normal": {"label": "Normal", "color": "2E7D32"},
    "warning": {"label": "Warning", "color": "ED6C02"},
    "critical": {"label": "Critical", "color": "D32F2F"},
    "urgent": {"label": "Urgent", "color": "6A1B9A"},
}


def get_risk_style(level: str) -> dict[str, str]:
    key = level.strip().lower()
    return RISK_LEVEL_STYLES[key]
```

```python
# templates/reports/shared/disclaimer.py
DISCLAIMER_TITLE = "Disclaimer"
DISCLAIMER_PARAGRAPHS = [
    "This report is generated from collected evidence and configured analysis logic.",
    "Recommendations should be reviewed by an engineer before operational changes are made.",
]
```

```python
# templates/reports/shared/table_styles.py
DEFAULT_DOCX_TABLE_STYLE = "Table Grid"
```

```python
# templates/reports/rdb-analysis/template_spec.py
TEMPLATE = {
    "template_name": "rdb-analysis",
    "cover_title": "Redis RDB Analysis Report",
    "cover_subtitle": "Phase 1 standard report skeleton",
    "summary_heading": "Executive Summary",
    "include_disclaimer": True,
}
```

```python
# templates/reports/inspection/template_spec.py
TEMPLATE = {
    "template_name": "inspection",
    "cover_title": "Redis Inspection Report",
    "cover_subtitle": "Phase 1 standard report skeleton",
    "summary_heading": "Executive Summary",
    "include_disclaimer": True,
}
```

```markdown
# src/references/README.md

This directory reserves the reference-layer isolation area described by the master plan.

Current repository state:

- `src/claude-code-source-code/` and `src/docs/` remain reference-only inputs
- production code must remain under `src/dba_assistant/`
- future reference assets that belong under the repository's own organized reference layer should be documented here rather than imported into production modules
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/unit/core/reporter/test_template_specs.py`

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit the shared template foundations**

```bash
git add tests/unit/core/reporter/test_template_specs.py src/references/README.md templates/reports/shared/cover.py templates/reports/shared/risk_level_styles.py templates/reports/shared/disclaimer.py templates/reports/shared/table_styles.py templates/reports/rdb-analysis/template_spec.py templates/reports/inspection/template_spec.py
git commit -m "feat: add phase 1 template foundations"
```

### Task 4: Implement the Summary Reporter

**Files:**
- Modify: `src/dba_assistant/core/reporter/__init__.py`
- Create: `src/dba_assistant/core/reporter/summary_reporter.py`
- Create: `tests/unit/core/reporter/test_summary_reporter.py`

- [ ] **Step 1: Write the failing tests for the summary reporter**

```python
# tests/unit/core/reporter/test_summary_reporter.py
from pathlib import Path

from dba_assistant.core.analyzer.types import AnalysisResult, ReportSection, TableModel
from dba_assistant.core.reporter.summary_reporter import SummaryReporter
from dba_assistant.core.reporter.types import OutputMode, ReportFormat, ReportOutputConfig


def build_analysis() -> AnalysisResult:
    return AnalysisResult(
        title="Redis RDB Analysis",
        summary="No urgent risk found.",
        sections=[
            ReportSection(
                title="Largest Keys",
                summary="Largest keys in the dataset",
                paragraphs=["Two session keys dominate memory usage."],
                tables=[
                    TableModel(
                        title="Top Keys",
                        columns=["Key", "Bytes"],
                        rows=[["session:1", "2048"]],
                    )
                ],
            )
        ],
        metadata={"environment": "prod"},
        risk_summary={"warning": 1},
    )


def test_summary_reporter_returns_rendered_text() -> None:
    artifact = SummaryReporter().render(
        build_analysis(),
        ReportOutputConfig(
            mode=OutputMode.SUMMARY,
            format=ReportFormat.SUMMARY,
            output_path=None,
        ),
    )

    assert artifact.output_path is None
    assert artifact.content is not None
    assert "Redis RDB Analysis" in artifact.content
    assert "Largest Keys" in artifact.content
    assert "session:1" in artifact.content


def test_summary_reporter_can_write_summary_to_a_text_file(tmp_path: Path) -> None:
    output_path = tmp_path / "summary.txt"

    artifact = SummaryReporter().render(
        build_analysis(),
        ReportOutputConfig(
            mode=OutputMode.SUMMARY,
            format=ReportFormat.SUMMARY,
            output_path=output_path,
        ),
    )

    assert artifact.output_path == output_path
    assert output_path.read_text(encoding="utf-8").startswith("Redis RDB Analysis")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/unit/core/reporter/test_summary_reporter.py`

Expected: FAIL because `SummaryReporter` does not exist yet.

- [ ] **Step 3: Implement the summary reporter**

```python
# src/dba_assistant/core/reporter/summary_reporter.py
from __future__ import annotations

from pathlib import Path

from dba_assistant.core.analyzer.types import AnalysisResult
from dba_assistant.core.reporter.types import IReporter, ReportArtifact, ReportOutputConfig, ReportFormat


class SummaryReporter(IReporter[AnalysisResult]):
    def render(self, analysis: AnalysisResult, config: ReportOutputConfig) -> ReportArtifact:
        content = self._render_text(analysis)
        if config.output_path is not None:
            config.output_path.parent.mkdir(parents=True, exist_ok=True)
            config.output_path.write_text(content, encoding="utf-8")
        return ReportArtifact(
            format=ReportFormat.SUMMARY,
            output_path=config.output_path,
            content=content,
        )

    def _render_text(self, analysis: AnalysisResult) -> str:
        lines = [analysis.title, "=" * len(analysis.title), "", analysis.summary, ""]

        if analysis.metadata:
            lines.append("Metadata")
            lines.append("--------")
            for key, value in sorted(analysis.metadata.items()):
                lines.append(f"- {key}: {value}")
            lines.append("")

        if analysis.risk_summary:
            lines.append("Risk Summary")
            lines.append("------------")
            for key, value in sorted(analysis.risk_summary.items()):
                lines.append(f"- {key}: {value}")
            lines.append("")

        for section in analysis.sections:
            lines.append(section.title)
            lines.append("-" * len(section.title))
            lines.append(section.summary)
            lines.append("")
            lines.extend(section.paragraphs)
            if section.paragraphs:
                lines.append("")
            for table in section.tables:
                lines.append(table.title)
                lines.append(", ".join(table.columns))
                for row in table.rows:
                    lines.append(", ".join(row))
                lines.append("")

        return "\n".join(lines).strip() + "\n"
```

```python
# src/dba_assistant/core/reporter/__init__.py
"""Reporter layer scaffold."""

from dba_assistant.core.reporter.summary_reporter import SummaryReporter
from dba_assistant.core.reporter.types import IReporter, OutputMode, ReportArtifact, ReportFormat, ReportOutputConfig

__all__ = [
    "IReporter",
    "OutputMode",
    "ReportArtifact",
    "ReportFormat",
    "ReportOutputConfig",
    "SummaryReporter",
]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/unit/core/reporter/test_summary_reporter.py`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit the summary reporter**

```bash
git add tests/unit/core/reporter/test_summary_reporter.py src/dba_assistant/core/reporter/summary_reporter.py src/dba_assistant/core/reporter/__init__.py
git commit -m "feat: add summary reporter"
```

### Task 5: Implement the Minimal Functional Docx Reporter and Interface-Only Future Reporters

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/dba_assistant/core/reporter/__init__.py`
- Create: `src/dba_assistant/core/reporter/docx_reporter.py`
- Create: `src/dba_assistant/core/reporter/pdf_reporter.py`
- Create: `src/dba_assistant/core/reporter/html_reporter.py`
- Create: `tests/unit/core/reporter/test_docx_reporter.py`

- [ ] **Step 1: Write the failing test for the docx reporter**

```python
# tests/unit/core/reporter/test_docx_reporter.py
from pathlib import Path

from docx import Document

from dba_assistant.core.analyzer.types import AnalysisResult, ReportSection, TableModel
from dba_assistant.core.reporter.docx_reporter import DocxReporter
from dba_assistant.core.reporter.types import OutputMode, ReportFormat, ReportOutputConfig


def build_analysis() -> AnalysisResult:
    return AnalysisResult(
        title="Redis RDB Analysis",
        summary="No urgent risk found.",
        sections=[
            ReportSection(
                title="Largest Keys",
                summary="Largest keys in the dataset",
                paragraphs=["Two session keys dominate memory usage."],
                tables=[
                    TableModel(
                        title="Top Keys",
                        columns=["Key", "Bytes"],
                        rows=[["session:1", "2048"]],
                    )
                ],
            )
        ],
        metadata={"environment": "prod", "generated_at": "2026-04-01"},
        risk_summary={"warning": 1},
    )


def test_docx_reporter_creates_a_minimal_report_document(tmp_path: Path) -> None:
    output_path = tmp_path / "rdb-analysis.docx"

    artifact = DocxReporter().render(
        build_analysis(),
        ReportOutputConfig(
            output_path=output_path,
            mode=OutputMode.REPORT,
            format=ReportFormat.DOCX,
            template_name="rdb-analysis",
        ),
    )

    document = Document(output_path)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)

    assert artifact.output_path == output_path
    assert output_path.exists()
    assert "Redis RDB Analysis Report" in text
    assert "Largest Keys" in text
    assert len(document.tables) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest -q tests/unit/core/reporter/test_docx_reporter.py`

Expected: FAIL because `DocxReporter` does not exist and `python-docx` is not declared in project dependencies yet.

- [ ] **Step 3: Add the docx dependency and install project dependencies**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "dba-assistant"
version = "0.1.0"
description = "Phase-oriented scaffold for the DBA Assistant project."
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "python-docx>=1.1,<2",
]

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

Run: `.venv/bin/python -m pip install -e ".[dev]"`

Expected: installation completes successfully and makes `python-docx` available in the local environment.

- [ ] **Step 4: Implement the docx reporter and interface-only PDF/HTML reporters**

```python
# src/dba_assistant/core/reporter/docx_reporter.py
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any

from docx import Document

from dba_assistant.core.analyzer.types import AnalysisResult, ReportSection, TableModel
from dba_assistant.core.reporter.types import IReporter, ReportArtifact, ReportOutputConfig, ReportFormat


class DocxReporter(IReporter[AnalysisResult]):
    def __init__(self, repository_root: Path | None = None) -> None:
        self.repository_root = repository_root or Path(__file__).resolve().parents[4]

    def render(self, analysis: AnalysisResult, config: ReportOutputConfig) -> ReportArtifact:
        if config.output_path is None:
            raise ValueError("DocxReporter requires an output_path.")

        template_name = config.template_name or "rdb-analysis"
        template = self._load_module(
            self.repository_root / "templates" / "reports" / template_name / "template_spec.py",
            f"{template_name.replace('-', '_')}_template",
        ).TEMPLATE
        cover_module = self._load_module(
            self.repository_root / "templates" / "reports" / "shared" / "cover.py",
            "shared_cover",
        )
        disclaimer_module = self._load_module(
            self.repository_root / "templates" / "reports" / "shared" / "disclaimer.py",
            "shared_disclaimer",
        )
        table_style_module = self._load_module(
            self.repository_root / "templates" / "reports" / "shared" / "table_styles.py",
            "shared_table_styles",
        )

        cover = cover_module.build_cover_spec(
            title=template["cover_title"],
            subtitle=template["cover_subtitle"],
        )

        document = Document()
        document.add_heading(cover.title, level=0)
        if cover.subtitle:
            document.add_paragraph(cover.subtitle)
        for key in cover.metadata_order:
            if key in analysis.metadata:
                document.add_paragraph(f"{key}: {analysis.metadata[key]}")

        document.add_heading(template["summary_heading"], level=1)
        document.add_paragraph(analysis.summary)

        for section in analysis.sections:
            self._render_section(document, section, table_style_module.DEFAULT_DOCX_TABLE_STYLE)

        if template["include_disclaimer"]:
            document.add_heading(disclaimer_module.DISCLAIMER_TITLE, level=1)
            for paragraph in disclaimer_module.DISCLAIMER_PARAGRAPHS:
                document.add_paragraph(paragraph)

        config.output_path.parent.mkdir(parents=True, exist_ok=True)
        document.save(config.output_path)
        return ReportArtifact(format=ReportFormat.DOCX, output_path=config.output_path, content=None)

    def _render_section(self, document: Document, section: ReportSection, table_style: str) -> None:
        document.add_heading(section.title, level=1)
        document.add_paragraph(section.summary)
        for paragraph in section.paragraphs:
            document.add_paragraph(paragraph)
        for table in section.tables:
            self._render_table(document, table, table_style)

    def _render_table(self, document: Document, table: TableModel, table_style: str) -> None:
        document.add_paragraph(table.title)
        docx_table = document.add_table(rows=1, cols=len(table.columns))
        docx_table.style = table_style
        for index, column in enumerate(table.columns):
            docx_table.rows[0].cells[index].text = column
        for row in table.rows:
            cells = docx_table.add_row().cells
            for index, value in enumerate(row):
                cells[index].text = value

    def _load_module(self, path: Path, module_name: str) -> ModuleType:
        spec = spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load module at {path}")
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
```

```python
# src/dba_assistant/core/reporter/pdf_reporter.py
from dba_assistant.core.analyzer.types import AnalysisResult
from dba_assistant.core.reporter.types import IReporter, ReportArtifact, ReportOutputConfig


class PdfReporter(IReporter[AnalysisResult]):
    def render(self, analysis: AnalysisResult, config: ReportOutputConfig) -> ReportArtifact:
        raise NotImplementedError("PDF reporting is defined at interface level only in Phase 1.")
```

```python
# src/dba_assistant/core/reporter/html_reporter.py
from dba_assistant.core.analyzer.types import AnalysisResult
from dba_assistant.core.reporter.types import IReporter, ReportArtifact, ReportOutputConfig


class HtmlReporter(IReporter[AnalysisResult]):
    def render(self, analysis: AnalysisResult, config: ReportOutputConfig) -> ReportArtifact:
        raise NotImplementedError("HTML reporting is defined at interface level only in Phase 1.")
```

```python
# src/dba_assistant/core/reporter/__init__.py
"""Reporter layer scaffold."""

from dba_assistant.core.reporter.docx_reporter import DocxReporter
from dba_assistant.core.reporter.html_reporter import HtmlReporter
from dba_assistant.core.reporter.pdf_reporter import PdfReporter
from dba_assistant.core.reporter.summary_reporter import SummaryReporter
from dba_assistant.core.reporter.types import IReporter, OutputMode, ReportArtifact, ReportFormat, ReportOutputConfig

__all__ = [
    "DocxReporter",
    "HtmlReporter",
    "IReporter",
    "OutputMode",
    "PdfReporter",
    "ReportArtifact",
    "ReportFormat",
    "ReportOutputConfig",
    "SummaryReporter",
]
```

- [ ] **Step 5: Run the docx test and the full Phase 1 unit suite**

Run: `.venv/bin/python -m pytest -q tests/unit/core/reporter/test_docx_reporter.py tests/unit/core/reporter/test_report_types.py tests/unit/core/reporter/test_template_specs.py tests/unit/core/reporter/test_summary_reporter.py tests/unit/core/collector/test_offline_collector.py`

Expected: PASS with all unit tests green.

- [ ] **Step 6: Commit the docx reporter and Phase 1 unit-test baseline**

```bash
git add pyproject.toml src/dba_assistant/core/reporter/docx_reporter.py src/dba_assistant/core/reporter/pdf_reporter.py src/dba_assistant/core/reporter/html_reporter.py src/dba_assistant/core/reporter/__init__.py tests/unit/core/reporter/test_docx_reporter.py
git commit -m "feat: add phase 1 docx reporter foundation"
```

## Self-Review

**Spec coverage:** The plan covers the Phase 1 requirements for Collector interfaces, a functional offline collection path, Reporter interfaces, a functional summary reporter, a minimal functional docx reporter, shared template components, reference isolation notes, and unit tests.

**Placeholder scan:** No `TBD`, `TODO`, or abstract “implement later” steps remain inside the plan tasks. Interface-only items for remote collector, PDF reporter, and HTML reporter are explicitly scoped because the master plan defines them as interface-only in Phase 1.

**Type consistency:** The plan uses one shared `AnalysisResult` model across collectors and reporters, one `OfflineCollectorInput` type for the offline collector path, and one `ReportOutputConfig` / `ReportArtifact` pair across reporter implementations.
