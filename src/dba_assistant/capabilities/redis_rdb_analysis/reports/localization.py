from __future__ import annotations

from typing import Any


def normalize_report_language(language: str | None) -> str:
    if not language:
        return "zh-CN"
    lowered = language.lower()
    if lowered.startswith("en"):
        return "en-US"
    return "zh-CN"


def report_title(language: str) -> str:
    return "Redis RDB Analysis Report" if language == "en-US" else "Redis RDB 分析报告"


def section_title(
    section_id: str,
    language: str,
    *,
    limit: int | None = None,
) -> str:
    display_limit = limit or 100
    titles = {
        "en-US": {
            "overview": "Sample and Overall Overview",
            "distribution_analysis": "Data Distribution Analysis",
            "big_key_analysis": "Big Key Analysis",
            "focused_prefix_analysis": "Focused Prefix Detail Analysis",
            "executive_summary": "Executive Summary",
            "background": "Analysis Background",
            "analysis_results": "Analysis Results",
            "sample_overview": "Sample Overview",
            "overall_summary": "Overall Overview",
            "key_type_summary": "Key Type Distribution Overview",
            "key_type_memory_breakdown": "Key Type Memory Usage Distribution",
            "expiration_summary": "Expiration Distribution",
            "non_expiration_summary": "Persistent Key Distribution",
            "prefix_top_summary": "Prefix Statistics",
            "prefix_expiration_breakdown": "Prefix Expiration Distribution",
            "top_big_keys": f"Overall Big Keys Ranking (Top {display_limit})",
            "top_string_keys": f"String Big Keys (Top {display_limit})",
            "top_hash_keys": f"Hash Big Keys (Top {display_limit})",
            "top_list_keys": f"List Big Keys (Top {display_limit})",
            "top_set_keys": f"Set Big Keys (Top {display_limit})",
            "top_zset_keys": f"ZSet Big Keys (Top {display_limit})",
            "top_stream_keys": f"Stream Big Keys (Top {display_limit})",
            "top_other_keys": f"Other Big Keys (Top {display_limit})",
            "loan_prefix_detail": "Loan Prefix Key Details",
            "conclusions": "Conclusions and Recommendations",
        },
        "zh-CN": {
            "overview": "样本与总体概况",
            "distribution_analysis": "数据分布分析",
            "big_key_analysis": "大 Key 分析",
            "focused_prefix_analysis": "重点前缀详情分析",
            "executive_summary": "执行摘要",
            "background": "分析背景",
            "analysis_results": "分析结果",
            "sample_overview": "样本概览",
            "overall_summary": "总体概览",
            "key_type_summary": "键类型分布概览",
            "key_type_memory_breakdown": "各键类型内存占用分布",
            "expiration_summary": "过期分布",
            "non_expiration_summary": "未设置过期键分布",
            "prefix_top_summary": "前缀统计",
            "prefix_expiration_breakdown": "重点前缀过期分布",
            "top_big_keys": f"总体大 Key 排名（Top {display_limit}）",
            "top_string_keys": f"String 类型大 Key（Top {display_limit}）",
            "top_hash_keys": f"Hash 类型大 Key（Top {display_limit}）",
            "top_list_keys": f"List 类型大 Key（Top {display_limit}）",
            "top_set_keys": f"Set 类型大 Key（Top {display_limit}）",
            "top_zset_keys": f"ZSet 类型大 Key（Top {display_limit}）",
            "top_stream_keys": f"Stream 类型大 Key（Top {display_limit}）",
            "top_other_keys": f"其他类型大 Key（Top {display_limit}）",
            "loan_prefix_detail": "Loan 前缀键明细",
            "conclusions": "结论与建议",
        },
    }
    return titles[language].get(section_id, section_id)


def build_localized_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    builders = {
        "executive_summary": _build_overall_section,
        "analysis_results": _build_overall_section,
        "overall_summary": _build_overall_section,
        "background": _build_background_section,
        "sample_overview": _build_sample_overview_section,
        "key_type_summary": _build_key_type_summary_section,
        "key_type_memory_breakdown": _build_key_type_memory_section,
        "expiration_summary": _build_expiration_section,
        "non_expiration_summary": _build_non_expiration_section,
        "prefix_top_summary": _build_prefix_top_section,
        "prefix_expiration_breakdown": _build_prefix_expiration_section,
        "top_big_keys": _build_top_big_keys_section,
        "top_string_keys": _build_typed_big_keys_section,
        "top_hash_keys": _build_typed_big_keys_section,
        "top_list_keys": _build_typed_big_keys_section,
        "top_set_keys": _build_typed_big_keys_section,
        "top_zset_keys": _build_typed_big_keys_section,
        "top_stream_keys": _build_typed_big_keys_section,
        "top_other_keys": _build_typed_big_keys_section,
        "loan_prefix_detail": _build_loan_prefix_section,
        "conclusions": _build_conclusions_section,
    }
    builder = builders.get(section_id, _build_fallback_section)
    return builder(section_id, payload, language)


def _build_overall_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    total_samples = int(payload.get("total_samples", 0))
    total_keys = int(payload.get("total_keys", 0))
    total_bytes = int(payload.get("total_bytes", 0))
    if language == "en-US":
        return {
            "summary": (
                f"This section summarizes {total_samples} sample, {total_keys} key, and {total_bytes} bytes."
                if total_samples == 1 and total_keys == 1
                else f"This section summarizes {total_samples} samples, {total_keys} keys, and {total_bytes} bytes."
            ),
            "table_title": section_title(section_id, language),
            "columns": ["Metric", "Value"],
            "rows": [["Sample Count", str(total_samples)], ["Key Count", str(total_keys)], ["Memory Usage (Bytes)", str(total_bytes)]],
        }
    return {
        "summary": f"本节汇总展示本次分析的样本规模、键数量及总体内存占用情况，共涉及 {total_samples} 个样本、{total_keys} 个键、{total_bytes} 字节。",
        "table_title": section_title(section_id, language),
        "columns": ["指标项", "指标值"],
        "rows": [["样本数", str(total_samples)], ["键数量", str(total_keys)], ["内存占用（字节）", str(total_bytes)]],
    }


def _build_background_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    profile_name = str(payload.get("profile_name", "generic"))
    focus_prefix_count = int(payload.get("focus_prefix_count", 0))
    if language == "en-US":
        return {
            "summary": "The report is generated deterministically from normalized datasets and the active analysis profile.",
            "table_title": section_title(section_id, language),
            "columns": ["Metric", "Value"],
            "rows": [["Profile", profile_name], ["Focused Prefix Count", str(focus_prefix_count)]],
        }
    return {
        "summary": "本报告依据标准化数据集及当前启用的分析配置生成，用于反映当前样本的结构性特征。",
        "table_title": section_title(section_id, language),
        "columns": ["指标项", "指标值"],
        "rows": [["分析配置", profile_name], ["重点关注前缀数", str(focus_prefix_count)]],
    }


def _build_sample_overview_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    sample_rows = payload.get("sample_rows")
    rows = []
    if isinstance(sample_rows, list):
        for row in sample_rows:
            if isinstance(row, list) and len(row) == 3:
                rows.append([str(row[0]), _sample_kind_label(str(row[1]), language), str(row[2])])
    if not rows:
        return {}
    if language == "en-US":
        return {
            "summary": "The following input samples were included in this analysis.",
            "table_title": "Sample Inventory",
            "columns": ["Sample Name", "Sample Type", "Source"],
            "rows": rows,
        }
    return {
        "summary": "本节列示纳入本次分析的输入样本及其来源信息。",
        "table_title": "样本清单",
        "columns": ["样本名称", "样本类型", "数据来源"],
        "rows": rows,
    }


def _build_key_type_summary_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    counts = payload.get("counts")
    rows = payload.get("rows")
    total_keys = sum(counts.values()) if isinstance(counts, dict) else 0
    total_types = len(counts) if isinstance(counts, dict) else 0
    if not isinstance(rows, list):
        rows = []
    if language == "en-US":
        return {
            "summary": f"{total_keys} keys are distributed across {total_types} key types.",
            "table_title": section_title(section_id, language),
            "columns": ["Key Type", "Key Count", "Memory Usage (Bytes)"],
            "rows": rows,
        }
    return {
        "summary": f"本节从数量与内存占用两个维度展示各键类型分布情况，共涉及 {total_keys} 个键、{total_types} 类键类型。",
        "table_title": section_title(section_id, language),
        "columns": ["键类型", "键数量", "内存占用（字节）"],
        "rows": rows,
    }


def _build_key_type_memory_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = []
    if language == "en-US":
        return {
            "summary": "This section shows memory usage aggregated by key type.",
            "table_title": section_title(section_id, language),
            "columns": ["Key Type", "Memory Usage (Bytes)"],
            "rows": rows,
        }
    return {
        "summary": "本节展示各键类型对应的内存占用情况，以识别主要内存消耗来源。",
        "table_title": section_title(section_id, language),
        "columns": ["键类型", "内存占用（字节）"],
        "rows": rows,
    }


def _build_expiration_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    expired_count = int(payload.get("expired_count", 0))
    persistent_count = int(payload.get("persistent_count", 0))
    if language == "en-US":
        return {
            "summary": f"Expiration is configured for {expired_count} keys, while {persistent_count} keys have no expiration.",
            "table_title": section_title(section_id, language),
            "columns": ["Expiration Status", "Key Count"],
            "rows": [["With Expiration", str(expired_count)], ["Without Expiration", str(persistent_count)]],
        }
    return {
        "summary": f"样本中共有 {expired_count} 个键设置了过期时间，另有 {persistent_count} 个键未设置过期时间。",
        "table_title": section_title(section_id, language),
        "columns": ["过期状态", "键数量"],
        "rows": [["设置过期", str(expired_count)], ["未设置过期", str(persistent_count)]],
    }


def _build_non_expiration_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    persistent_count = int(payload.get("persistent_count", 0))
    if language == "en-US":
        return {
            "summary": f"{persistent_count} keys do not have an expiration configured.",
            "table_title": section_title(section_id, language),
            "columns": ["Expiration Status", "Key Count"],
            "rows": [["Without Expiration", str(persistent_count)]],
        }
    return {
        "summary": f"本节展示未设置过期时间的键数量，共计 {persistent_count} 个。",
        "table_title": section_title(section_id, language),
        "columns": ["过期状态", "键数量"],
        "rows": [["未设置过期", str(persistent_count)]],
    }


def _build_prefix_top_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = []
    if not rows:
        return {}
    if language == "en-US":
        return {
            "summary": "The following prefixes rank highest by key count and memory usage.",
            "table_title": section_title(section_id, language),
            "columns": ["Prefix", "Key Count", "Memory Usage (Bytes)"],
            "rows": rows,
        }
    return {
        "summary": "本节展示按键数量排序的主要前缀分布情况，用于识别高集中度业务域。",
        "table_title": section_title(section_id, language),
        "columns": ["前缀", "键数量", "内存占用（字节）"],
        "rows": rows,
    }


def _build_prefix_expiration_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = []
    if not rows:
        return {}
    if language == "en-US":
        return {
            "summary": "This section breaks down expiration coverage for focused prefixes.",
            "table_title": section_title(section_id, language),
            "columns": ["Prefix", "With Expiration", "Without Expiration", "Total"],
            "rows": rows,
        }
    return {
        "summary": "本节展示重点前缀下键的过期配置分布情况。",
        "table_title": section_title(section_id, language),
        "columns": ["前缀", "设置过期", "未设置过期", "总数"],
        "rows": rows,
    }


def _build_top_big_keys_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    rows = payload.get("rows")
    limit = int(payload.get("limit", 100))
    if not isinstance(rows, list):
        rows = []
    if not rows:
        return {}
    if language == "en-US":
        return {
            "summary": "The table below lists the overall largest keys ranked by memory usage.",
            "table_title": section_title(section_id, language, limit=limit),
            "section_title": section_title(section_id, language, limit=limit),
            "columns": ["Key Name", "Key Type", "Memory Usage (Bytes)"],
            "rows": rows,
        }
    return {
        "summary": "本节列示样本中按内存占用排序的总体大 Key，用于快速识别主要风险对象。",
        "table_title": section_title(section_id, language, limit=limit),
        "section_title": section_title(section_id, language, limit=limit),
        "columns": ["键名", "键类型", "内存占用（字节）"],
        "rows": rows,
    }


def _build_typed_big_keys_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    rows = payload.get("rows")
    limit = int(payload.get("limit", 100))
    if not isinstance(rows, list):
        rows = []
    if not rows:
        return {}
    title = section_title(section_id, language, limit=limit)
    if language == "en-US":
        return {
            "summary": f"The table below lists the largest keys within the {title.rsplit(' (Top', 1)[0].lower()} category.",
            "section_title": title,
            "table_title": title,
            "columns": ["Key Name", "Memory Usage (Bytes)"],
            "rows": rows,
        }
    return {
        "summary": f"本节展示 {title}，用于识别同类型数据结构中的主要高占用对象。",
        "section_title": title,
        "table_title": title,
        "columns": ["键名", "内存占用（字节）"],
        "rows": rows,
    }


def _build_loan_prefix_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = []
    if not rows:
        return {}
    if language == "en-US":
        return {
            "summary": "This section lists loan-prefixed keys in descending memory usage order.",
            "table_title": section_title(section_id, language),
            "columns": ["Key Name", "Key Type", "Memory Usage (Bytes)"],
            "rows": rows,
        }
    return {
        "summary": "本节按内存占用从高到低展示 loan 前缀相关键明细。",
        "table_title": section_title(section_id, language),
        "columns": ["键名", "键类型", "内存占用（字节）"],
        "rows": rows,
    }


def _build_conclusions_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    summary = (
        "No additional deterministic high-risk findings were identified. Prioritize review of high-memory key types, large keys, and concentrated prefixes together with business access patterns."
        if language == "en-US"
        else "基于当前样本及既定分析逻辑，未发现额外确定性高风险。建议结合业务访问特征，优先复核高占用键类型、大 Key 及高集中度前缀。"
    )
    return {
        "summary": summary,
        "rows": [],
        "columns": [],
    }


def _build_fallback_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    columns = payload.get("columns") if isinstance(payload.get("columns"), list) else []
    return {
        "summary": str(payload.get("summary", "")) if payload.get("summary") else "",
        "table_title": section_title(section_id, language, limit=int(payload.get("limit", 100))),
        "section_title": section_title(section_id, language, limit=int(payload.get("limit", 100))),
        "columns": [str(column) for column in columns],
        "rows": [[str(cell) for cell in row] for row in rows if isinstance(row, list)],
    }


def _sample_kind_label(kind: str, language: str) -> str:
    labels = {
        "en-US": {
            "local_rdb": "Local RDB",
            "remote_redis": "Remote Redis",
            "precomputed": "Precomputed Dataset",
            "preparsed_mysql": "MySQL-backed Dataset",
        },
        "zh-CN": {
            "local_rdb": "本地 RDB",
            "remote_redis": "远端 Redis",
            "precomputed": "预处理数据集",
            "preparsed_mysql": "MySQL 数据集",
        },
    }
    return labels[language].get(kind, kind)


def focused_prefix_section_title(prefix: str, language: str) -> str:
    if language == "en-US":
        return f"Prefix {prefix} Details"
    return f"前缀 {prefix} 详情"


def focused_prefix_table_title(prefix: str, language: str, *, limit: int) -> str:
    if language == "en-US":
        return f"Prefix {prefix} Top Keys (Top {limit})"
    return f"前缀 {prefix} Top Keys（Top {limit}）"


def build_localized_focused_prefix_section(payload: dict[str, object], language: str) -> dict[str, Any]:
    prefix = str(payload.get("prefix", ""))
    limit = int(payload.get("limit", 100))
    key_type_breakdown = payload.get("key_type_breakdown")
    expiration_stats = payload.get("expiration_stats")
    top_keys = payload.get("top_keys")
    matched_key_count = int(payload.get("matched_key_count", 0))
    total_size_bytes = int(payload.get("total_size_bytes", 0))

    if not isinstance(key_type_breakdown, dict):
        key_type_breakdown = {}
    if not isinstance(expiration_stats, dict):
        expiration_stats = {}
    if not isinstance(top_keys, list):
        top_keys = []

    if matched_key_count <= 0:
        summary = "No keys matched the requested prefix." if language == "en-US" else "未匹配到符合条件的键。"
        return {
            "summary": summary,
            "paragraphs": [],
            "rows": [],
            "columns": [],
            "section_title": focused_prefix_section_title(prefix, language),
        }

    type_summary = ", ".join(f"{key_type}={count}" for key_type, count in sorted(key_type_breakdown.items()))
    with_expiration = int(expiration_stats.get("with_expiration", 0))
    without_expiration = int(expiration_stats.get("without_expiration", 0))

    if language == "en-US":
        summary = (
            f"Prefix {prefix} matches {matched_key_count} keys with a total of {total_size_bytes} bytes. "
            f"Expiration covers {with_expiration} keys and {without_expiration} keys are persistent. "
            f"Key type breakdown: {type_summary if type_summary else 'none'}."
        )
        paragraphs = []
        columns = ["Key Name", "Key Type", "Memory Usage (Bytes)"]
    else:
        summary = (
            f"此前缀范围共匹配 {matched_key_count} 个键，累计内存占用 {total_size_bytes} 字节；"
            f"其中设置过期 {with_expiration} 个，未设置过期 {without_expiration} 个。"
            f"键类型分布：{type_summary if type_summary else '未匹配到数据。'}"
        )
        paragraphs = []
        columns = ["键名", "键类型", "内存占用（字节）"]

    return {
        "summary": summary,
        "paragraphs": paragraphs,
        "table_title": focused_prefix_table_title(prefix, language, limit=limit),
        "section_title": focused_prefix_section_title(prefix, language),
        "columns": columns,
        "rows": top_keys,
    }
