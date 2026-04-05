from __future__ import annotations

from typing import Any

from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TableBlock, TextBlock
from dba_assistant.capabilities.redis_rdb_analysis.types import EffectiveProfile


def assemble_report(
    analysis_result: dict[str, dict[str, object]],
    *,
    profile: EffectiveProfile,
    title: str,
) -> AnalysisReport:
    sections: list[ReportSectionModel] = []
    summary = _pick_summary(analysis_result)

    for section_id in profile.sections:
        payload = analysis_result.get(section_id, {})
        sections.append(_assemble_section(section_id, payload))

    return AnalysisReport(
        title=title,
        summary=summary,
        sections=sections,
        metadata={"profile": profile.name},
    )


def _pick_summary(analysis_result: dict[str, dict[str, object]]) -> str | None:
    for key in ("overall_summary", "executive_summary", "analysis_results"):
        payload = analysis_result.get(key)
        if payload and isinstance(payload.get("summary"), str):
            return str(payload["summary"])
    return None


def _assemble_section(section_id: str, payload: dict[str, object]) -> ReportSectionModel:
    blocks: list[TextBlock | TableBlock] = []

    summary = payload.get("summary")
    if isinstance(summary, str) and summary:
        blocks.append(TextBlock(text=summary))

    paragraphs = payload.get("paragraphs")
    if isinstance(paragraphs, list):
        for paragraph in paragraphs:
            if isinstance(paragraph, str) and paragraph:
                blocks.append(TextBlock(text=paragraph))

    rows = payload.get("rows")
    if isinstance(rows, list):
        columns = _as_string_list(payload.get("columns"))
        blocks.append(
            TableBlock(
                title=str(payload.get("table_title", _titleize(section_id))),
                columns=columns,
                rows=[[_stringify(cell) for cell in row] for row in rows if isinstance(row, list)],
            )
        )

    return ReportSectionModel(id=section_id, title=_titleize(section_id), blocks=blocks)


def _titleize(section_id: str) -> str:
    return section_id.replace("_", " ").title()


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _stringify(value: Any) -> str:
    return "" if value is None else str(value)
