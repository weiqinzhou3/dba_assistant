import json
from pathlib import Path

from dba_assistant.capabilities.redis_rdb_analysis.collectors.path_c_direct_parser_collector import PathCDirectParserCollector
from dba_assistant.capabilities.redis_rdb_analysis.types import InputSourceKind


def test_path_c_collector_returns_normalized_dataset_from_parser_output() -> None:
    fixture_path = Path("tests/fixtures/rdb/direct/sample_key_records.json")
    rows = json.loads(fixture_path.read_text(encoding="utf-8"))

    collector = PathCDirectParserCollector(parser=lambda _: rows)

    dataset = collector.collect([Path("/tmp/cache-prod.rdb")])

    assert dataset.samples == [
        dataset.samples[0].__class__(
            source=Path("/tmp/cache-prod.rdb"),
            kind=InputSourceKind.LOCAL_RDB,
            label="cache-prod",
        )
    ]
    assert dataset.records[0].sample_id == "sample-1"
    assert dataset.records[0].key_name == "loan:1"
    assert dataset.records[0].prefix_segments == ("loan",)
    assert dataset.records[1].prefix_segments == ("loan", "active")
    assert dataset.records[2].prefix_segments == ()


def test_path_c_collector_keeps_parser_calls_and_sample_boundaries() -> None:
    seen_paths: list[Path] = []

    def parser(path: Path) -> list[dict[str, object]]:
        seen_paths.append(path)
        return [
            {
                "key_name": f"{path.stem}:1",
                "key_type": "hash",
                "size_bytes": 10,
                "has_expiration": False,
                "ttl_seconds": None,
            }
        ]

    collector = PathCDirectParserCollector(parser=parser)
    paths = [Path("/tmp/a.rdb"), Path("/tmp/b.rdb")]

    dataset = collector.collect(paths)

    assert seen_paths == paths
    assert [sample.label for sample in dataset.samples] == ["a", "b"]
    assert [record.sample_id for record in dataset.records] == ["sample-1", "sample-2"]
