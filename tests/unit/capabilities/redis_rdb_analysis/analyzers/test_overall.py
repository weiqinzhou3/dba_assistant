from dba_assistant.capabilities.redis_rdb_analysis.analyzers.overall import analyze_overall
from dba_assistant.capabilities.redis_rdb_analysis.types import (
    EffectiveProfile,
    InputSourceKind,
    KeyRecord,
    NormalizedRdbDataset,
    SampleInput,
)


def test_analyze_overall_combines_core_sections_and_rcs_custom_section() -> None:
    dataset = NormalizedRdbDataset(
        samples=[
            SampleInput(source="/tmp/a.rdb", kind=InputSourceKind.LOCAL_RDB, label="host-a"),
            SampleInput(source="/tmp/b.rdb", kind=InputSourceKind.LOCAL_RDB, label="host-b"),
        ],
        records=[
            KeyRecord("sample-1", "loan:1", "hash", 100, True, 60, ("loan",)),
            KeyRecord("sample-1", "loan:2", "list", 200, False, None, ("loan",)),
            KeyRecord("sample-2", "queue:1", "set", 300, False, None, ("queue",)),
        ],
    )
    profile = EffectiveProfile(
        name="rcs",
        sections=("overall_summary", "key_type_summary", "expiration_summary", "top_big_keys", "top_string_keys", "loan_prefix_detail"),
        focus_prefixes=("loan:*",),
        top_n={"top_big_keys": 2, "string_big_keys": 1, "hash_big_keys": 1, "list_big_keys": 1, "set_big_keys": 1, "prefix_top": 5},
    )

    result = analyze_overall(dataset, profile=profile)

    assert result["overall_summary"] == {
        "total_samples": 2,
        "total_keys": 3,
        "total_bytes": 600,
    }
    assert result["key_type_summary"]["counts"]["list"] == 1
    assert result["expiration_summary"]["expired_count"] == 1
    assert "top_string_keys" in result
    assert "top_keys_by_type" not in result
    assert "loan_prefix_detail" in result


def test_analyze_overall_adds_requested_prefix_detail_sections_with_requested_top_n() -> None:
    dataset = NormalizedRdbDataset(
        samples=[SampleInput(source="/tmp/a.rdb", kind=InputSourceKind.LOCAL_RDB, label="host-a")],
        records=[
            KeyRecord("sample-1", "order:1", "string", 500, True, 30, ("order",)),
            KeyRecord("sample-1", "order:2", "hash", 400, False, None, ("order",)),
            KeyRecord("sample-1", "order:3", "string", 300, False, None, ("order",)),
            KeyRecord("sample-1", "mq:1", "stream", 450, False, None, ("mq",)),
        ],
    )
    profile = EffectiveProfile(
        name="rcs",
        sections=("overall_summary", "prefix_top_summary", "focused_prefix_analysis"),
        focus_prefixes=("order:*", "mq:*"),
        top_n={
            "prefix_top": 10,
            "top_big_keys": 10,
            "string_big_keys": 10,
            "hash_big_keys": 10,
            "list_big_keys": 10,
            "set_big_keys": 10,
            "zset_big_keys": 10,
            "stream_big_keys": 10,
            "other_big_keys": 10,
            "focused_prefix_top_keys": 2,
        },
    )

    result = analyze_overall(dataset, profile=profile)

    assert "focused_prefix_analysis" in result
    sections = result["focused_prefix_analysis"]["sections"]
    assert [section["prefix"] for section in sections] == ["order:*", "mq:*"]
    assert len(sections[0]["top_keys"]) == 2
