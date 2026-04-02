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
    summary: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
