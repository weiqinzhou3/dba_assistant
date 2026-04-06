import builtins

from dba_assistant.capabilities.redis_rdb_analysis.analyzers.big_keys import analyze_big_keys
from dba_assistant.capabilities.redis_rdb_analysis.types import (
    InputSourceKind,
    KeyRecord,
    NormalizedRdbDataset,
    SampleInput,
)


def test_analyze_big_keys_limits_and_groups_by_type() -> None:
    dataset = NormalizedRdbDataset(
        samples=[SampleInput(source="/tmp/a.rdb", kind=InputSourceKind.LOCAL_RDB)],
        records=[
            KeyRecord("sample-1", "session:1", "string", 400, False, None, ("session",)),
            KeyRecord("sample-1", "loan:1", "hash", 100, True, 60, ("loan",)),
            KeyRecord("sample-1", "queue:1", "list", 300, False, None, ("queue",)),
            KeyRecord("sample-1", "member:1", "set", 200, False, None, ("member",)),
            KeyRecord("sample-1", "rank:1", "zset", 250, False, None, ("rank",)),
            KeyRecord("sample-1", "stream:1", "stream", 150, False, None, ("stream",)),
            KeyRecord("sample-1", "module:1", "module", 50, False, None, ("module",)),
            KeyRecord("sample-1", "loan:2", "hash", 250, False, None, ("loan",)),
        ],
    )

    result = analyze_big_keys(
        dataset,
        top_n={
            "top_big_keys": 2,
            "string_big_keys": 1,
            "hash_big_keys": 1,
            "list_big_keys": 1,
            "set_big_keys": 1,
            "zset_big_keys": 1,
            "stream_big_keys": 1,
            "other_big_keys": 1,
        },
    )

    assert result["top_big_keys"]["rows"] == [["session:1", "string", "400"], ["queue:1", "list", "300"]]
    assert result["top_string_keys"]["rows"] == [["session:1", "400"]]
    assert result["top_hash_keys"]["rows"] == [["loan:2", "250"]]
    assert result["top_list_keys"]["rows"] == [["queue:1", "300"]]
    assert result["top_set_keys"]["rows"] == [["member:1", "200"]]
    assert result["top_zset_keys"]["rows"] == [["rank:1", "250"]]
    assert result["top_stream_keys"]["rows"] == [["stream:1", "150"]]
    assert result["top_other_keys"]["rows"] == [["module:1", "50"]]
    assert "top_keys_by_type" not in result


def test_analyze_big_keys_defaults_all_type_limits_to_one_hundred() -> None:
    dataset = NormalizedRdbDataset(
        samples=[SampleInput(source="/tmp/a.rdb", kind=InputSourceKind.LOCAL_RDB)],
        records=[
            KeyRecord("sample-1", f"string:{index}", "string", 500 - index, False, None, ("string",))
            for index in range(120)
        ],
    )

    result = analyze_big_keys(dataset)

    assert len(result["top_big_keys"]["rows"]) == 100
    assert len(result["top_string_keys"]["rows"]) == 100


def test_analyze_big_keys_keeps_empty_type_sections_consistent() -> None:
    dataset = NormalizedRdbDataset(
        samples=[SampleInput(source="/tmp/a.rdb", kind=InputSourceKind.LOCAL_RDB)],
        records=[KeyRecord("sample-1", "loan:1", "hash", 100, False, None, ("loan",))],
    )

    result = analyze_big_keys(dataset)

    assert result["top_stream_keys"]["rows"] == []


def test_analyze_big_keys_does_not_depend_on_global_sorted(monkeypatch) -> None:
    dataset = NormalizedRdbDataset(
        samples=[SampleInput(source="/tmp/a.rdb", kind=InputSourceKind.LOCAL_RDB)],
        records=[
            KeyRecord("sample-1", "cache:9", "string", 9, False, None, ("cache",)),
            KeyRecord("sample-1", "cache:1", "string", 1, False, None, ("cache",)),
            KeyRecord("sample-1", "loan:5", "hash", 5, False, None, ("loan",)),
        ],
    )

    def fail_sorted(*_args, **_kwargs):
        raise AssertionError("analyze_big_keys should not require builtins.sorted over the full dataset")

    monkeypatch.setattr(builtins, "sorted", fail_sorted)

    result = analyze_big_keys(
        dataset,
        top_n={
            "top_big_keys": 2,
            "string_big_keys": 2,
            "hash_big_keys": 1,
            "list_big_keys": 1,
            "set_big_keys": 1,
            "zset_big_keys": 1,
            "stream_big_keys": 1,
            "other_big_keys": 1,
        },
    )

    assert result["top_big_keys"]["rows"] == [["cache:9", "string", "9"], ["loan:5", "hash", "5"]]
