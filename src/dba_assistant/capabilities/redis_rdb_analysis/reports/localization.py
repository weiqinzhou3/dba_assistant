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


def section_title(section_id: str, language: str) -> str:
    titles = {
        "en-US": {
            "executive_summary": "Executive Summary",
            "background": "Background",
            "analysis_results": "Analysis Results",
            "sample_overview": "Sample Overview",
            "overall_summary": "Overall Summary",
            "key_type_summary": "Key Type Summary",
            "key_type_memory_breakdown": "Key Type Memory Breakdown",
            "expiration_summary": "Expiration Summary",
            "non_expiration_summary": "Non-Expiration Summary",
            "prefix_top_summary": "Top Prefixes",
            "prefix_expiration_breakdown": "Prefix Expiration Breakdown",
            "top_big_keys": "Top Big Keys",
            "top_string_keys": "Top String Keys",
            "top_hash_keys": "Top Hash Keys",
            "top_list_keys": "Top List Keys",
            "top_set_keys": "Top Set Keys",
            "top_zset_keys": "Top Zset Keys",
            "top_stream_keys": "Top Stream Keys",
            "top_other_keys": "Top Other Keys",
            "loan_prefix_detail": "Loan Prefix Detail",
            "conclusions": "Conclusions",
        },
        "zh-CN": {
            "executive_summary": "执行摘要",
            "background": "背景信息",
            "analysis_results": "分析结果",
            "sample_overview": "样本概览",
            "overall_summary": "总体概览",
            "key_type_summary": "Key 类型概览",
            "key_type_memory_breakdown": "Key 类型内存分布",
            "expiration_summary": "过期分布",
            "non_expiration_summary": "永久 Key 分布",
            "prefix_top_summary": "前缀 Top 统计",
            "prefix_expiration_breakdown": "关注前缀过期分布",
            "top_big_keys": "总体大 Key Top",
            "top_string_keys": "String 大 Key",
            "top_hash_keys": "Hash 大 Key",
            "top_list_keys": "List 大 Key",
            "top_set_keys": "Set 大 Key",
            "top_zset_keys": "Zset 大 Key",
            "top_stream_keys": "Stream 大 Key",
            "top_other_keys": "其他类型大 Key",
            "loan_prefix_detail": "Loan 前缀详情",
            "conclusions": "结论",
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
            "summary": f"{total_samples} samples, {total_keys} keys, {total_bytes} bytes.",
            "columns": ["Metric", "Value"],
            "rows": [["Samples", str(total_samples)], ["Keys", str(total_keys)], ["Bytes", str(total_bytes)]],
        }
    return {
        "summary": f"共 {total_samples} 个样本，{total_keys} 个 key，{total_bytes} 字节。",
        "columns": ["指标", "值"],
        "rows": [["样本数", str(total_samples)], ["Key 数", str(total_keys)], ["字节数", str(total_bytes)]],
    }


def _build_background_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    profile_name = str(payload.get("profile_name", "generic"))
    focus_prefix_count = int(payload.get("focus_prefix_count", 0))
    if language == "en-US":
        return {
            "summary": "Deterministic Phase 3 RDB analysis over normalized datasets.",
            "columns": ["Metric", "Value"],
            "rows": [["Profile", profile_name], ["Focused Prefixes", str(focus_prefix_count)]],
        }
    return {
        "summary": "基于标准化数据集的确定性 Phase 3 RDB 分析。",
        "columns": ["指标", "值"],
        "rows": [["Profile", profile_name], ["关注前缀数", str(focus_prefix_count)]],
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
            "summary": "Input samples included in the analysis.",
            "columns": ["Sample", "Kind", "Source"],
            "rows": rows,
        }
    return {
        "summary": "本次分析包含的输入样本如下。",
        "columns": ["样本", "类型", "来源"],
        "rows": rows,
    }


def _build_key_type_summary_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    counts = payload.get("counts")
    memory_bytes = payload.get("memory_bytes")
    rows = payload.get("rows")
    total_keys = sum(counts.values()) if isinstance(counts, dict) else 0
    total_types = len(counts) if isinstance(counts, dict) else 0
    if not isinstance(rows, list):
        rows = []
    if language == "en-US":
        return {
            "summary": f"{total_keys} keys across {total_types} key types.",
            "columns": ["Key Type", "Count", "Bytes"],
            "rows": rows,
        }
    return {
        "summary": f"共 {total_keys} 个 key，分布在 {total_types} 种 key type 中。",
        "columns": ["Key 类型", "数量", "字节数"],
        "rows": rows,
    }


def _build_key_type_memory_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = []
    if language == "en-US":
        return {
            "summary": "Memory grouped by key type.",
            "columns": ["Key Type", "Bytes"],
            "rows": rows,
        }
    return {
        "summary": "按 key type 聚合的内存分布。",
        "columns": ["Key 类型", "字节数"],
        "rows": rows,
    }


def _build_expiration_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    expired_count = int(payload.get("expired_count", 0))
    persistent_count = int(payload.get("persistent_count", 0))
    if language == "en-US":
        return {
            "summary": f"{expired_count} keys expire and {persistent_count} keys persist.",
            "columns": ["Bucket", "Count"],
            "rows": [["With Expiration", str(expired_count)], ["Without Expiration", str(persistent_count)]],
        }
    return {
        "summary": f"有 {expired_count} 个 key 设置了过期，{persistent_count} 个 key 为永久保存。",
        "columns": ["分桶", "数量"],
        "rows": [["有过期", str(expired_count)], ["无过期", str(persistent_count)]],
    }


def _build_non_expiration_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    persistent_count = int(payload.get("persistent_count", 0))
    if language == "en-US":
        return {
            "summary": f"{persistent_count} keys do not expire.",
            "columns": ["Bucket", "Count"],
            "rows": [["Without Expiration", str(persistent_count)]],
        }
    return {
        "summary": f"共有 {persistent_count} 个 key 不会过期。",
        "columns": ["分桶", "数量"],
        "rows": [["无过期", str(persistent_count)]],
    }


def _build_prefix_top_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = []
    if not rows:
        return {}
    if language == "en-US":
        return {
            "summary": "Top prefixes by key count.",
            "columns": ["Prefix", "Count", "Bytes"],
            "rows": rows,
        }
    return {
        "summary": "按 key 数量排序的前缀 Top 列表。",
        "columns": ["前缀", "数量", "字节数"],
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
            "summary": "Expiration breakdown for focused prefixes.",
            "columns": ["Prefix", "Expired", "Persistent", "Total"],
            "rows": rows,
        }
    return {
        "summary": "关注前缀的过期分布情况。",
        "columns": ["前缀", "有过期", "无过期", "总数"],
        "rows": rows,
    }


def _build_top_big_keys_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = []
    if not rows:
        return {}
    if language == "en-US":
        return {
            "summary": "Largest keys in the dataset.",
            "columns": ["Key", "Type", "Bytes"],
            "rows": rows,
        }
    return {
        "summary": "当前数据集中体积最大的 key。",
        "columns": ["Key", "类型", "字节数"],
        "rows": rows,
    }


def _build_typed_big_keys_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = []
    if not rows:
        return {}
    type_name = section_title(section_id, language)
    if language == "en-US":
        return {
            "summary": f"Largest keys for {type_name.lower()}.",
            "columns": ["Key", "Bytes"],
            "rows": rows,
        }
    return {
        "summary": f"{type_name} 列表。",
        "columns": ["Key", "字节数"],
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
            "summary": "Loan-prefixed keys in descending size order.",
            "columns": ["Key", "Type", "Bytes"],
            "rows": rows,
        }
    return {
        "summary": "按大小倒序排列的 loan 前缀 key。",
        "columns": ["Key", "类型", "字节数"],
        "rows": rows,
    }


def _build_conclusions_section(section_id: str, payload: dict[str, object], language: str) -> dict[str, Any]:
    summary = "No additional deterministic concerns were found by the generic analyzers." if language == "en-US" else "通用分析器未发现额外的确定性风险。"
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
        "columns": [str(column) for column in columns],
        "rows": [[str(cell) for cell in row] for row in rows if isinstance(row, list)],
    }


def _sample_kind_label(kind: str, language: str) -> str:
    labels = {
        "en-US": {
            "local_rdb": "Local RDB",
            "remote_redis": "Remote Redis",
            "precomputed": "Precomputed",
            "preparsed_mysql": "MySQL Dataset",
        },
        "zh-CN": {
            "local_rdb": "本地 RDB",
            "remote_redis": "远端 Redis",
            "precomputed": "预处理文件",
            "preparsed_mysql": "MySQL 数据集",
        },
    }
    return labels[language].get(kind, kind)
