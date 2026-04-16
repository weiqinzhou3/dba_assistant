from __future__ import annotations

from dataclasses import dataclass, field
from dba_assistant.core.analyzer.types import AnalysisResult, ReportSection, TableModel


@dataclass(frozen=True)
class TextBlock:
    text: str


@dataclass(frozen=True)
class TextRun:
    text: str
    bold: bool = False


@dataclass(frozen=True)
class RichTextBlock:
    lines: list[list[TextRun]]


@dataclass(frozen=True)
class InfoTableRow:
    label: str
    text: str
    bullet: bool = False


@dataclass(frozen=True)
class InfoTableBlock:
    rows: list[InfoTableRow]
    table_kind: str | None = None


@dataclass(frozen=True)
class TableBlock:
    title: str
    columns: list[str]
    rows: list[list[str]]
    show_title: bool = True
    table_kind: str | None = None


@dataclass(frozen=True)
class ReportSectionModel:
    id: str
    title: str
    level: int = 1
    blocks: list[TextBlock | RichTextBlock | InfoTableBlock | TableBlock] = field(default_factory=list)


@dataclass(frozen=True)
class AnalysisReport:
    title: str
    sections: list[ReportSectionModel]
    summary: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    language: str = "zh-CN"


def coerce_analysis_report(analysis: AnalysisReport | AnalysisResult) -> AnalysisReport:
    if isinstance(analysis, AnalysisReport):
        return analysis

    sections: list[ReportSectionModel] = []

    if analysis.risk_summary:
        sections.append(
            ReportSectionModel(
                id="risk_summary",
                title="Risk Summary",
                blocks=[
                    TextBlock(text=f"- {key}: {value}")
                    for key, value in sorted(analysis.risk_summary.items())
                ],
            )
        )

    for section in analysis.sections:
        sections.append(_coerce_section(section))

    return AnalysisReport(
        title=analysis.title,
        summary=analysis.summary,
        sections=sections,
        metadata={key: str(value) for key, value in analysis.metadata.items()},
        language="zh-CN",
    )


def render_summary_text(report: AnalysisReport, *, language: str | None = None) -> str:
    labels = _summary_labels(language or report.language)
    lines = [report.title]

    if report.summary:
        lines.extend(["", report.summary])

    if report.metadata:
        lines.extend(["", labels["metadata"]])
        for key, value in sorted(report.metadata.items()):
            lines.append(f"- {key}: {value}")

    for section in report.sections:
        lines.extend(["", section.title])
        for block in section.blocks:
            if isinstance(block, TextBlock):
                lines.append(block.text)
                continue
            if isinstance(block, RichTextBlock):
                lines.extend("".join(run.text for run in line) for line in block.lines)
                continue
            if isinstance(block, InfoTableBlock):
                for row in block.rows:
                    lines.append(f"{row.label}: {row.text}")
                continue
            if block.show_title and block.title:
                lines.append(block.title)
            if block.columns:
                lines.append(", ".join(block.columns))
            for row in block.rows:
                lines.append(", ".join(row))

    return "\n".join(lines)


def _summary_labels(language: str) -> dict[str, str]:
    if language == "en-US":
        return {
            "metadata": "Metadata",
        }
    return {
        "metadata": "元数据",
    }


def _coerce_section(section: ReportSection) -> ReportSectionModel:
    blocks: list[TextBlock | RichTextBlock | InfoTableBlock | TableBlock] = []

    if section.summary:
        blocks.append(TextBlock(text=section.summary))

    for paragraph in section.paragraphs:
        blocks.append(TextBlock(text=paragraph))

    for table in section.tables:
        blocks.append(_coerce_table(table))

    return ReportSectionModel(
        id=_section_id(section.title),
        title=section.title,
        level=1,
        blocks=blocks,
    )


def _coerce_table(table: TableModel) -> TableBlock:
    return TableBlock(
        title=table.title,
        columns=[str(column) for column in table.columns],
        rows=[[str(cell) for cell in row] for row in table.rows],
    )


def _section_id(title: str) -> str:
    return title.lower().replace(" ", "_")
