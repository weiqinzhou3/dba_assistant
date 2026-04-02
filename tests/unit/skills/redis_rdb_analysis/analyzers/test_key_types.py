from dba_assistant.skills.redis_rdb_analysis.analyzers.key_types import analyze_key_types
from dba_assistant.skills.redis_rdb_analysis.types import (
    InputSourceKind,
    KeyRecord,
    NormalizedRdbDataset,
    SampleInput,
)


def test_analyze_key_types_counts_types_and_memory() -> None:
    dataset = NormalizedRdbDataset(
        samples=[SampleInput(source="/tmp/a.rdb", kind=InputSourceKind.LOCAL_RDB, label="host-a")],
        records=[
            KeyRecord("sample-1", "loan:1", "hash", 100, False, None, ("loan",)),
            KeyRecord("sample-1", "queue:1", "list", 300, True, 120, ("queue",)),
        ],
    )

    result = analyze_key_types(dataset)

    assert result["counts"]["hash"] == 1
    assert result["memory_bytes"]["list"] == 300
    assert result["rows"][0] == ["list", "1", "300"]
