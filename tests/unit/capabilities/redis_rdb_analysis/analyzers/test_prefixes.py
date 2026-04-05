from dba_assistant.capabilities.redis_rdb_analysis.analyzers.prefixes import analyze_prefixes
from dba_assistant.capabilities.redis_rdb_analysis.types import (
    InputSourceKind,
    KeyRecord,
    NormalizedRdbDataset,
    SampleInput,
)


def test_analyze_prefixes_sorts_top_prefixes_and_focus_breakdown() -> None:
    dataset = NormalizedRdbDataset(
        samples=[SampleInput(source="/tmp/a.rdb", kind=InputSourceKind.LOCAL_RDB)],
        records=[
            KeyRecord("sample-1", "loan:1", "hash", 100, True, 60, ("loan",)),
            KeyRecord("sample-1", "loan:2", "list", 200, False, None, ("loan",)),
            KeyRecord("sample-1", "queue:1", "list", 300, False, None, ("queue",)),
        ],
    )

    result = analyze_prefixes(dataset, focus_prefixes=("loan:*",))

    assert result["prefix_top_summary"]["rows"][0] == ["loan:*", "2", "300"]
    assert result["prefix_expiration_breakdown"]["rows"] == [["loan:*", "1", "1", "2"]]
