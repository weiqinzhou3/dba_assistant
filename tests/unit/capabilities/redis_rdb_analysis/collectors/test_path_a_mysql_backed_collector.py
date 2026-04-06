from pathlib import Path

from dba_assistant.capabilities.redis_rdb_analysis.collectors.path_a_mysql_backed_collector import (
    PathAMySQLBackedCollector,
)


def test_path_a_mysql_backed_collector_uses_one_shared_table_and_batches_rows() -> None:
    staged_batches: list[tuple[str, list[dict[str, object]], str, str]] = []
    rows_by_path = {
        Path("/tmp/a.rdb"): [
            {
                "key_name": "cache:1",
                "key_type": "string",
                "size_bytes": 123,
                "has_expiration": False,
                "ttl_seconds": None,
            },
            {
                "key_name": "cache:2",
                "key_type": "hash",
                "size_bytes": 122,
                "has_expiration": True,
                "ttl_seconds": 60,
            },
            {
                "key_name": "cache:3",
                "key_type": "string",
                "size_bytes": 121,
                "has_expiration": False,
                "ttl_seconds": None,
            },
        ],
        Path("/tmp/b.rdb"): [
            {
                "key_name": "session:1",
                "key_type": "string",
                "size_bytes": 120,
                "has_expiration": False,
                "ttl_seconds": None,
            }
        ],
    }

    collector = PathAMySQLBackedCollector(
        stream_parser=lambda path: iter(rows_by_path[path]),
        batch_size=2,
        stage_rows_to_mysql=lambda table_name, rows, *, source_file, run_id: staged_batches.append(
            (table_name, list(rows), source_file, run_id)
        )
        or {"table": table_name, "database": "analysis_db"},
    )

    result = collector.collect([Path("/tmp/a.rdb"), Path("/tmp/b.rdb")])

    assert result.table_name.startswith("rdb_stage_auto_")
    assert result.row_count == 4
    assert result.batch_size == 2
    assert len(staged_batches) == 3
    assert len({table_name for table_name, *_rest in staged_batches}) == 1
    assert len({run_id for *_rest, run_id in staged_batches}) == 1
    assert result.source_files == ("/tmp/a.rdb", "/tmp/b.rdb")
    assert "file 1/2" in result.progress[0]
    assert "file 2/2" in result.progress[1]
