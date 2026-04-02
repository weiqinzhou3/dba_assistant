from dba_assistant.skills.redis_rdb_analysis.analyzers.expiration import analyze_expiration
from dba_assistant.skills.redis_rdb_analysis.types import (
    InputSourceKind,
    KeyRecord,
    NormalizedRdbDataset,
    SampleInput,
)


def test_analyze_expiration_counts_expiring_and_persistent_keys() -> None:
    dataset = NormalizedRdbDataset(
        samples=[SampleInput(source="/tmp/a.rdb", kind=InputSourceKind.LOCAL_RDB)],
        records=[
            KeyRecord("sample-1", "loan:1", "hash", 100, True, 60, ("loan",)),
            KeyRecord("sample-1", "loan:2", "hash", 100, False, None, ("loan",)),
        ],
    )

    result = analyze_expiration(dataset)

    assert result["expired_count"] == 1
    assert result["persistent_count"] == 1
    assert result["rows"] == [["with expiration", "1"], ["without expiration", "1"]]
