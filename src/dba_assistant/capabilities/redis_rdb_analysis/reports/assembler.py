from __future__ import annotations

from typing import Any

from dba_assistant.capabilities.redis_rdb_analysis.reports.localization import (
    build_localized_section,
    normalize_report_language,
    report_title,
    section_title,
)
from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TableBlock, TextBlock
from dba_assistant.capabilities.redis_rdb_analysis.types import EffectiveProfile


def assemble_report(
    analysis_result: dict[str, dict[str, object]],
    *,
    profile: EffectiveProfile,
    title: str | None = None,
    language: str = "zh-CN",
) -> AnalysisReport:
    language = normalize_report_language(language)
    sections: list[ReportSectionModel] = []
    summary = _pick_summary(analysis_result, language=language)

    for section_id in profile.sections:
        payload = analysis_result.get(section_id, {})
        section = _assemble_section(section_id, payload, language=language)
        if section is not None:
            sections.append(section)

    return AnalysisReport(
        title=report_title(language),
        summary=summary,
        sections=sections,
        metadata={"profile": profile.name},
        language=language,
    )


def _pick_summary(analysis_result: dict[str, dict[str, object]], *, language: str) -> str | None:
    for key in ("overall_summary", "executive_summary", "analysis_results"):
        payload = analysis_result.get(key)
        if payload:
            localized = build_localized_section(key, payload, language)
            if isinstance(localized.get("summary"), str) and localized["summary"]:
                return str(localized["summary"])
    return None


def _assemble_section(
    section_id: str,
    payload: dict[str, object],
    *,
    language: str,
) -> ReportSectionModel | None:
    localized = build_localized_section(section_id, payload, language)
    blocks: list[TextBlock | TableBlock] = []

    summary = localized.get("summary")
    if isinstance(summary, str) and summary:
        blocks.append(TextBlock(text=summary))

    paragraphs = localized.get("paragraphs")
    if isinstance(paragraphs, list):
        for paragraph in paragraphs:
            if isinstance(paragraph, str) and paragraph:
                blocks.append(TextBlock(text=paragraph))

    rows = localized.get("rows")
    if isinstance(rows, list):
        table_rows = [[_stringify(cell) for cell in row] for row in rows if isinstance(row, list)]
        if table_rows:
            columns = _as_string_list(localized.get("columns"))
            blocks.append(
                TableBlock(
                    title=str(localized.get("table_title", section_title(section_id, language))),
                    columns=columns,
                    rows=table_rows,
                )
            )

    if not blocks:
        return None
    return ReportSectionModel(id=section_id, title=section_title(section_id, language), blocks=blocks)


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _stringify(value: Any) -> str:
    return "" if value is None else str(value)
