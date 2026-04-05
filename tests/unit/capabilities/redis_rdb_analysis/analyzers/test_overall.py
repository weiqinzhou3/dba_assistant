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
        sections=("overall_summary", "key_type_summary", "expiration_summary", "top_big_keys", "loan_prefix_detail"),
        focus_prefixes=("loan:*",),
        top_n={"top_big_keys": 2, "hash_big_keys": 1, "list_big_keys": 1, "set_big_keys": 1, "prefix_top": 5},
    )

    result = analyze_overall(dataset, profile=profile)

    assert result["overall_summary"]["summary"] == "2 samples, 3 keys, 600 bytes."
    assert result["key_type_summary"]["counts"]["list"] == 1
    assert result["expiration_summary"]["expired_count"] == 1
    assert "loan_prefix_detail" in result
