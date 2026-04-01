"""Shared analysis result models used across Phase 1 reporters."""

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
