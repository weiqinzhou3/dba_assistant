from __future__ import annotations

from typing import Any

from dba_assistant.capabilities.redis_rdb_analysis.reports.localization import (
    build_localized_focused_prefix_section,
    build_localized_section,
    focused_prefix_section_title,
    normalize_report_language,
    report_title,
    section_title,
)
from dba_assistant.capabilities.redis_rdb_analysis.types import EffectiveProfile
from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TableBlock, TextBlock


SUMMARY_SOURCE_IDS = ("overall_summary", "executive_summary", "analysis_results")
BIG_KEY_SECTION_IDS = (
    "top_big_keys",
    "top_string_keys",
    "top_hash_keys",
    "top_list_keys",
    "top_set_keys",
    "top_zset_keys",
    "top_stream_keys",
    "top_other_keys",
)
SECTION_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("overview", ("background", "sample_overview", "overall_summary")),
    (
        "distribution_analysis",
        (
            "key_type_summary",
            "key_type_memory_breakdown",
            "expiration_summary",
            "non_expiration_summary",
            "prefix_top_summary",
            "prefix_expiration_breakdown",
        ),
    ),
    ("big_key_analysis", BIG_KEY_SECTION_IDS + ("loan_prefix_detail",)),
)


def assemble_report(
    analysis_result: dict[str, dict[str, object]],
    *,
    profile: EffectiveProfile,
    title: str | None = None,
    language: str = "zh-CN",
) -> AnalysisReport:
    language = normalize_report_language(language)
    sections: list[ReportSectionModel] = []
    allowed_ids = set(profile.sections)

    for group_id, child_ids in SECTION_GROUPS:
        group_children = [
            section
            for child_id in child_ids
            if child_id in allowed_ids and (section := _assemble_section(child_id, analysis_result.get(child_id, {}), language=language, level=2)) is not None
        ]
        if group_children:
            sections.append(ReportSectionModel(id=group_id, title=section_title(group_id, language), level=1))
            sections.extend(group_children)

    if "focused_prefix_analysis" in allowed_ids:
        focused_prefix_sections = _assemble_focused_prefix_sections(
            analysis_result.get("focused_prefix_analysis", {}),
            language=language,
        )
        if focused_prefix_sections:
            sections.append(
                ReportSectionModel(
                    id="focused_prefix_analysis",
                    title=section_title("focused_prefix_analysis", language),
                    level=1,
                )
            )
            sections.extend(focused_prefix_sections)

    if "conclusions" in allowed_ids and (conclusions := _assemble_section("conclusions", analysis_result.get("conclusions", {}), language=language, level=1)) is not None:
        sections.append(conclusions)

    return AnalysisReport(
        title=report_title(language),
        summary=_build_deterministic_summary(analysis_result, language=language),
        sections=sections,
        metadata={"profile": profile.name},
        language=language,
    )


def _build_deterministic_summary(
    analysis_result: dict[str, dict[str, object]],
    *,
    language: str,
) -> str | None:
    overall = _pick_summary_payload(analysis_result)
    if not overall:
        return None

    total_samples = int(overall.get("total_samples", 0))
    total_keys = int(overall.get("total_keys", 0))
    total_bytes = int(overall.get("total_bytes", 0))

    key_type_payload = analysis_result.get("key_type_summary", {})
    dominant_type = _dominant_key_type(key_type_payload)
    expiration_payload = analysis_result.get("expiration_summary", {})
    expired_count = int(expiration_payload.get("expired_count", 0))
    has_big_keys = any(bool(analysis_result.get(section_id, {}).get("rows")) for section_id in BIG_KEY_SECTION_IDS)
    big_key_limit = _section_limit(analysis_result.get("top_big_keys", {})) or 100
    prefix_payload = analysis_result.get("prefix_top_summary", {})
    top_prefix, prefix_ratio = _top_prefix_concentration(prefix_payload, total_keys=total_keys)

    if language == "en-US":
        sentences = [_english_scale_sentence(total_samples, total_keys, total_bytes)]
        if dominant_type:
            sentences.append(f"The {dominant_type} type contributes the highest memory share.")
        if expired_count > 0:
            sentences.append("Expiration is configured for part of the dataset.")
        elif total_keys > 0:
            sentences.append("No keys with expiration were found in the sampled dataset.")
        if has_big_keys:
            if big_key_limit == 100:
                sentences.append("Large keys were detected in the Top 100 ranking.")
            else:
                sentences.append(f"Large keys were detected in the Top {big_key_limit} ranking.")
        if top_prefix and prefix_ratio >= 0.5:
            sentences.append(f"Key counts are relatively concentrated under prefix {top_prefix}.")
        sentences.append("No additional deterministic high-risk findings were identified.")
        return " ".join(sentences)

    sentences = [f"本次分析共覆盖 {total_samples} 个样本、{total_keys} 个键，累计内存占用 {total_bytes} 字节。"]
    if dominant_type:
        sentences.append(f"当前内存占用最高的键类型为 {dominant_type}。")
    if expired_count > 0:
        sentences.append("样本中存在已设置过期时间的键，建议结合业务策略核对过期配置是否合理。")
    elif total_keys > 0:
        sentences.append("样本中未发现已设置过期时间的键。")
    if has_big_keys:
        if big_key_limit == 100:
            sentences.append("已识别出需要重点关注的大 Key。")
        else:
            sentences.append(f"已识别出需要重点关注的大 Key，当前报告按 Top {big_key_limit} 口径展示。")
    if top_prefix and prefix_ratio >= 0.5:
        sentences.append(f"键数量在前缀 {top_prefix} 下呈现较高集中度，建议结合业务场景进一步核查。")
    sentences.append("当前未发现额外确定性高风险，建议结合业务侧访问特征持续评估高占用键。")
    return "".join(sentences)


def _assemble_section(
    section_id: str,
    payload: dict[str, object],
    *,
    language: str,
    level: int,
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
            blocks.append(
                TableBlock(
                    title=str(localized.get("table_title", section_title(section_id, language, limit=_section_limit(payload)))),
                    columns=_as_string_list(localized.get("columns")),
                    rows=table_rows,
                )
            )

    if not blocks:
        return None
    return ReportSectionModel(
        id=section_id,
        title=str(localized.get("section_title", section_title(section_id, language, limit=_section_limit(payload)))),
        level=level,
        blocks=blocks,
    )


def _assemble_focused_prefix_sections(
    payload: dict[str, object],
    *,
    language: str,
) -> list[ReportSectionModel]:
    raw_sections = payload.get("sections")
    if not isinstance(raw_sections, list):
        return []

    sections: list[ReportSectionModel] = []
    for raw_section in raw_sections:
        if not isinstance(raw_section, dict):
            continue
        localized = build_localized_focused_prefix_section(raw_section, language)
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
        if isinstance(rows, list) and rows:
            blocks.append(
                TableBlock(
                    title=str(localized.get("table_title")),
                    columns=_as_string_list(localized.get("columns")),
                    rows=[[ _stringify(cell) for cell in row] for row in rows if isinstance(row, list)],
                )
            )

        if not blocks:
            continue

        section_id = f"focused_prefix_detail:{raw_section.get('prefix', '')}"
        sections.append(
            ReportSectionModel(
                id=section_id,
                title=str(localized.get("section_title", focused_prefix_section_title(str(raw_section.get("prefix", "")), language))),
                level=2,
                blocks=blocks,
            )
        )
    return sections


def _pick_summary_payload(analysis_result: dict[str, dict[str, object]]) -> dict[str, object]:
    for key in SUMMARY_SOURCE_IDS:
        payload = analysis_result.get(key)
        if payload:
            return payload
    return {}


def _dominant_key_type(payload: dict[str, object]) -> str | None:
    memory_bytes = payload.get("memory_bytes")
    if isinstance(memory_bytes, dict) and memory_bytes:
        return max(memory_bytes, key=lambda key: (int(memory_bytes[key]), str(key)))
    rows = payload.get("rows")
    if isinstance(rows, list) and rows:
        first_row = rows[0]
        if isinstance(first_row, list) and first_row:
            return str(first_row[0])
    return None


def _top_prefix_concentration(payload: dict[str, object], *, total_keys: int) -> tuple[str | None, float]:
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows or total_keys <= 0:
        return None, 0.0
    first_row = rows[0]
    if not isinstance(first_row, list) or len(first_row) < 2:
        return None, 0.0
    prefix = str(first_row[0])
    try:
        prefix_count = int(first_row[1])
    except (TypeError, ValueError):
        return prefix, 0.0
    return prefix, prefix_count / total_keys


def _english_scale_sentence(total_samples: int, total_keys: int, total_bytes: int) -> str:
    sample_label = "sample" if total_samples == 1 else "samples"
    key_label = "key" if total_keys == 1 else "keys"
    return f"The analysis covers {total_samples} {sample_label}, {total_keys} {key_label}, and {total_bytes} bytes."


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _stringify(value: Any) -> str:
    return "" if value is None else str(value)


def _section_limit(payload: dict[str, object]) -> int | None:
    raw_limit = payload.get("limit")
    if raw_limit is None:
        return None
    try:
        return int(raw_limit)
    except (TypeError, ValueError):
        return None
