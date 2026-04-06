from dba_assistant.capabilities.redis_rdb_analysis.reports.assembler import assemble_report
from dba_assistant.capabilities.redis_rdb_analysis.types import EffectiveProfile


def test_assembler_orders_sections_from_profile_and_converts_tables() -> None:
    profile = EffectiveProfile(
        name="generic",
        sections=(
            "executive_summary",
            "sample_overview",
            "overall_summary",
            "key_type_summary",
            "key_type_memory_breakdown",
            "expiration_summary",
            "prefix_top_summary",
            "top_big_keys",
        ),
    )
    analysis_result = {
        "executive_summary": {"total_samples": 1, "total_keys": 2, "total_bytes": 3},
        "sample_overview": {"sample_rows": [["sample-1", "local_rdb", "/tmp/dump.rdb"]]},
        "overall_summary": {"total_samples": 1, "total_keys": 2, "total_bytes": 3},
        "key_type_summary": {
            "counts": {"string": 2},
            "memory_bytes": {"string": 3},
            "rows": [["string", "2", "3"]],
        },
        "key_type_memory_breakdown": {"rows": [["string", "3"]]},
        "expiration_summary": {"expired_count": 1, "persistent_count": 1},
        "prefix_top_summary": {"rows": [["loan", "2", "3"]]},
        "top_big_keys": {"rows": [["loan:1", "string", "2048"]], "columns": ["key", "type", "bytes"]},
    }

    report = assemble_report(analysis_result, profile=profile, title="Redis RDB Analysis", language="en-US")

    assert report.summary == (
        "The analysis covers 1 sample, 2 keys, and 3 bytes. "
        "The string type contributes the highest memory share. "
        "Expiration is configured for part of the dataset. "
        "Large keys were detected in the Top 100 ranking. "
        "Key counts are relatively concentrated under prefix loan. "
        "No additional deterministic high-risk findings were identified."
    )
    assert [(section.id, section.level) for section in report.sections] == [
        ("overview", 1),
        ("sample_overview", 2),
        ("overall_summary", 2),
        ("distribution_analysis", 1),
        ("key_type_summary", 2),
        ("key_type_memory_breakdown", 2),
        ("expiration_summary", 2),
        ("prefix_top_summary", 2),
        ("big_key_analysis", 1),
        ("top_big_keys", 2),
    ]
    assert all(section.id != "executive_summary" for section in report.sections)
    assert report.sections[4].blocks[1].title == "Key Type Distribution Overview"
    assert report.sections[6].blocks[1].rows == [["With Expiration", "1"], ["Without Expiration", "1"]]


def test_assembler_defaults_to_chinese_localized_titles() -> None:
    profile = EffectiveProfile(
        name="generic",
        sections=("executive_summary", "overall_summary", "top_string_keys"),
    )
    analysis_result = {
        "overall_summary": {"total_samples": 1, "total_keys": 1, "total_bytes": 128},
        "key_type_summary": {
            "counts": {"string": 1},
            "memory_bytes": {"string": 128},
            "rows": [["string", "1", "128"]],
        },
        "expiration_summary": {"expired_count": 0, "persistent_count": 1},
        "top_string_keys": {"rows": [["session:1", "128"]]},
    }

    report = assemble_report(analysis_result, profile=profile, title="ignored", language="zh-CN")

    assert report.title == "Redis RDB 分析报告"
    assert report.summary == (
        "本次分析共覆盖 1 个样本、1 个键，累计内存占用 128 字节。"
        "当前内存占用最高的键类型为 string。"
        "样本中未发现已设置过期时间的键。"
        "已识别出需要重点关注的大 Key。"
        "当前未发现额外确定性高风险，建议结合业务侧访问特征持续评估高占用键。"
    )
    assert [section.title for section in report.sections] == [
        "样本与总体概况",
        "总体概览",
        "大 Key 分析",
        "String 类型大 Key（Top 100）",
    ]
    table_block = report.sections[3].blocks[1]
    assert table_block.title == "String 类型大 Key（Top 100）"
    assert table_block.columns == ["键名", "内存占用（字节）"]


def test_assembler_omits_empty_sections_consistently() -> None:
    profile = EffectiveProfile(
        name="generic",
        sections=("top_stream_keys", "top_hash_keys"),
    )
    analysis_result = {
        "top_stream_keys": {"rows": []},
        "top_hash_keys": {"rows": [["loan:1", "100"]]},
    }

    report = assemble_report(analysis_result, profile=profile, title="ignored", language="zh-CN")

    assert [section.id for section in report.sections] == ["big_key_analysis", "top_hash_keys"]


def test_assembler_preserves_english_localization_for_formal_titles_and_columns() -> None:
    profile = EffectiveProfile(
        name="generic",
        sections=("key_type_summary", "top_string_keys"),
    )
    analysis_result = {
        "key_type_summary": {
            "counts": {"string": 1},
            "memory_bytes": {"string": 128},
            "rows": [["string", "1", "128"]],
        },
        "top_string_keys": {"rows": [["session:1", "128"]]},
    }

    report = assemble_report(analysis_result, profile=profile, title="ignored", language="en-US")

    assert report.title == "Redis RDB Analysis Report"
    assert [section.title for section in report.sections] == [
        "Data Distribution Analysis",
        "Key Type Distribution Overview",
        "Big Key Analysis",
        "String Big Keys (Top 100)",
    ]
    key_type_table = report.sections[1].blocks[1]
    assert key_type_table.title == "Key Type Distribution Overview"
    assert key_type_table.columns == ["Key Type", "Key Count", "Memory Usage (Bytes)"]


def test_assembler_adds_focused_prefix_chapter_and_subsections() -> None:
    profile = EffectiveProfile(
        name="rcs",
        sections=("overall_summary", "top_big_keys", "focused_prefix_analysis", "conclusions"),
    )
    analysis_result = {
        "overall_summary": {"total_samples": 1, "total_keys": 4, "total_bytes": 1024},
        "key_type_summary": {
            "counts": {"string": 2, "hash": 1, "stream": 1},
            "memory_bytes": {"string": 600, "hash": 200, "stream": 224},
        },
        "expiration_summary": {"expired_count": 1, "persistent_count": 3},
        "top_big_keys": {"rows": [["order:1", "string", "500"]], "limit": 10},
        "focused_prefix_analysis": {
            "sections": [
                {
                    "prefix": "order:*",
                    "matched_key_count": 2,
                    "total_size_bytes": 700,
                    "key_type_breakdown": {"string": 1, "hash": 1},
                    "expiration_stats": {"with_expiration": 1, "without_expiration": 1},
                    "top_keys": [["order:1", "string", "500"], ["order:2", "hash", "200"]],
                    "summary_text": "已匹配到 2 个以 order:* 为范围的键。",
                    "limit": 10,
                },
                {
                    "prefix": "mq:*",
                    "matched_key_count": 0,
                    "total_size_bytes": 0,
                    "key_type_breakdown": {},
                    "expiration_stats": {"with_expiration": 0, "without_expiration": 0},
                    "top_keys": [],
                    "summary_text": "未匹配到符合条件的键。",
                    "limit": 10,
                },
            ]
        },
    }

    report = assemble_report(analysis_result, profile=profile, title="ignored", language="zh-CN")

    assert [section.title for section in report.sections] == [
        "样本与总体概况",
        "总体概览",
        "大 Key 分析",
        "总体大 Key 排名（Top 10）",
        "重点前缀详情分析",
        "前缀 order:* 详情",
        "前缀 mq:* 详情",
        "结论与建议",
    ]
    assert report.sections[5].blocks[1].title == "前缀 order:* Top Keys（Top 10）"
    assert report.sections[5].blocks[1].rows == [["order:1", "string", "500"], ["order:2", "hash", "200"]]
    assert report.sections[6].blocks[0].text == "未匹配到符合条件的键。"


def test_assembler_switches_to_focus_only_report_scope() -> None:
    profile = EffectiveProfile(
        name="rcs",
        sections=("overall_summary", "top_big_keys", "focused_prefix_analysis", "conclusions"),
        focus_only=True,
    )
    analysis_result = {
        "overall_summary": {"total_samples": 1, "total_keys": 4, "total_bytes": 1024},
        "focused_prefix_analysis": {
            "sections": [
                {
                    "prefix": "tag:*",
                    "matched_key_count": 2,
                    "total_size_bytes": 700,
                    "key_type_breakdown": {"string": 1, "hash": 1},
                    "expiration_stats": {"with_expiration": 1, "without_expiration": 1},
                    "top_keys": [["tag:1", "string", "500"], ["tag:2", "hash", "200"]],
                    "summary_text": "已匹配到 2 个以 tag:* 为范围的键。",
                    "limit": 10,
                }
            ]
        },
    }

    report = assemble_report(analysis_result, profile=profile, title="ignored", language="zh-CN")

    assert report.metadata["scope"] == "focused_prefix_only"
    assert report.summary is not None
    assert "仅输出用户指定的重点前缀详情" in report.summary
    assert [section.title for section in report.sections] == [
        "重点前缀详情分析",
        "前缀 tag:* 详情",
    ]
