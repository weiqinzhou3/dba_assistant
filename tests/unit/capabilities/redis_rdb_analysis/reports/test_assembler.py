from dba_assistant.capabilities.redis_rdb_analysis.reports.assembler import assemble_report
from dba_assistant.capabilities.redis_rdb_analysis.types import EffectiveProfile


def test_assembler_orders_sections_from_profile_and_converts_tables() -> None:
    profile = EffectiveProfile(
        name="generic",
        sections=("executive_summary", "expiration_summary", "top_big_keys"),
    )
    analysis_result = {
        "executive_summary": {"summary": "ok"},
        "expiration_summary": {"summary": "ttl", "rows": [["with expiration", "1"]], "columns": ["bucket", "count"]},
        "top_big_keys": {"rows": [["loan:1", "2048"]], "columns": ["key", "bytes"]},
    }

    report = assemble_report(analysis_result, profile=profile, title="Redis RDB Analysis")

    assert [section.id for section in report.sections] == [
        "executive_summary",
        "expiration_summary",
        "top_big_keys",
    ]
    assert report.sections[1].blocks[1].rows == [["with expiration", "1"]]
