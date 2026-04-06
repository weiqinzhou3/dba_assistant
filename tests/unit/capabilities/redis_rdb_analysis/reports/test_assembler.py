from dba_assistant.capabilities.redis_rdb_analysis.reports.assembler import assemble_report
from dba_assistant.capabilities.redis_rdb_analysis.types import EffectiveProfile


def test_assembler_orders_sections_from_profile_and_converts_tables() -> None:
    profile = EffectiveProfile(
        name="generic",
        sections=("executive_summary", "expiration_summary", "top_big_keys"),
    )
    analysis_result = {
        "executive_summary": {"total_samples": 1, "total_keys": 2, "total_bytes": 3},
        "expiration_summary": {"expired_count": 1, "persistent_count": 1},
        "top_big_keys": {"rows": [["loan:1", "2048"]], "columns": ["key", "bytes"]},
    }

    report = assemble_report(analysis_result, profile=profile, title="Redis RDB Analysis", language="en-US")

    assert [section.id for section in report.sections] == [
        "executive_summary",
        "expiration_summary",
        "top_big_keys",
    ]
    assert report.sections[1].blocks[1].rows == [["With Expiration", "1"], ["Without Expiration", "1"]]


def test_assembler_defaults_to_chinese_localized_titles() -> None:
    profile = EffectiveProfile(
        name="generic",
        sections=("overall_summary", "top_string_keys"),
    )
    analysis_result = {
        "overall_summary": {"total_samples": 1, "total_keys": 1, "total_bytes": 128},
        "top_string_keys": {"rows": [["session:1", "128"]]},
    }

    report = assemble_report(analysis_result, profile=profile, title="ignored", language="zh-CN")

    assert report.title == "Redis RDB 分析报告"
    assert report.summary == "共 1 个样本，1 个 key，128 字节。"
    assert report.sections[0].title == "总体概览"
    assert report.sections[1].title == "String 大 Key"


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

    assert [section.id for section in report.sections] == ["top_hash_keys"]
