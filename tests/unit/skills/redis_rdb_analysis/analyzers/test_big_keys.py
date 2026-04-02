from dba_assistant.skills.redis_rdb_analysis.analyzers.big_keys import analyze_big_keys
from dba_assistant.skills.redis_rdb_analysis.types import (
    InputSourceKind,
    KeyRecord,
    NormalizedRdbDataset,
    SampleInput,
)


def test_analyze_big_keys_limits_and_groups_by_type() -> None:
    dataset = NormalizedRdbDataset(
        samples=[SampleInput(source="/tmp/a.rdb", kind=InputSourceKind.LOCAL_RDB)],
        records=[
            KeyRecord("sample-1", "loan:1", "hash", 100, True, 60, ("loan",)),
            KeyRecord("sample-1", "queue:1", "list", 300, False, None, ("queue",)),
            KeyRecord("sample-1", "loan:2", "hash", 250, False, None, ("loan",)),
        ],
    )

    result = analyze_big_keys(dataset, top_n={"top_big_keys": 2, "hash_big_keys": 1, "list_big_keys": 1})

    assert result["top_big_keys"]["rows"] == [["queue:1", "list", "300"], ["loan:2", "hash", "250"]]
    assert result["top_hash_keys"]["rows"] == [["loan:2", "250"]]
    assert result["top_list_keys"]["rows"] == [["queue:1", "300"]]
