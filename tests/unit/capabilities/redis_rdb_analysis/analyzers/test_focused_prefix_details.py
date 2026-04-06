from dba_assistant.capabilities.redis_rdb_analysis.analyzers.focused_prefix_details import (
    analyze_focused_prefix_details,
)
from dba_assistant.capabilities.redis_rdb_analysis.types import (
    InputSourceKind,
    KeyRecord,
    NormalizedRdbDataset,
    SampleInput,
)


def _dataset() -> NormalizedRdbDataset:
    return NormalizedRdbDataset(
        samples=[SampleInput(source="/tmp/a.rdb", kind=InputSourceKind.LOCAL_RDB)],
        records=[
            KeyRecord("sample-1", "order:1", "string", 900, True, 60, ("order",)),
            KeyRecord("sample-1", "order:2", "hash", 700, False, None, ("order",)),
            KeyRecord("sample-1", "order:3", "string", 500, False, None, ("order",)),
            KeyRecord("sample-1", "mq:1", "stream", 800, False, None, ("mq",)),
            KeyRecord("sample-1", "mq:2", "stream", 600, True, 30, ("mq",)),
            KeyRecord("sample-1", "loan:1", "hash", 400, False, None, ("loan",)),
        ],
    )


def test_analyze_focused_prefix_details_supports_arbitrary_prefixes_and_top_n() -> None:
    result = analyze_focused_prefix_details(
        _dataset(),
        focus_prefixes=("order:*", "mq:*"),
        top_n=2,
    )

    assert [section["prefix"] for section in result["sections"]] == ["order:*", "mq:*"]
    order_section = result["sections"][0]
    assert order_section["matched_key_count"] == 3
    assert order_section["total_size_bytes"] == 2100
    assert order_section["key_type_breakdown"] == {"string": 2, "hash": 1}
    assert len(order_section["top_keys"]) == 2
    assert order_section["top_keys"][0] == ["order:1", "string", "900"]
    assert order_section["expiration_stats"] == {
        "with_expiration": 1,
        "without_expiration": 2,
    }


def test_analyze_focused_prefix_details_keeps_zero_match_sections() -> None:
    result = analyze_focused_prefix_details(
        _dataset(),
        focus_prefixes=("device:*",),
        top_n=10,
    )

    device_section = result["sections"][0]
    assert device_section["prefix"] == "device:*"
    assert device_section["matched_key_count"] == 0
    assert device_section["total_size_bytes"] == 0
    assert device_section["top_keys"] == []
    assert "未匹配到符合条件的键" in device_section["summary_text"]
