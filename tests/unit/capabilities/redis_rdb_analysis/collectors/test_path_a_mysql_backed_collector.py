from pathlib import Path
import json
from types import SimpleNamespace

from dba_assistant.core.observability import bootstrap_observability, reset_observability_state
from dba_assistant.deep_agent_integration.config import ObservabilityConfig
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
    assert "batch_size=2" in result.progress[0]
    assert "batch_size=2" in result.progress[1]


def test_path_a_mysql_backed_collector_emits_batch_phase_logs_with_effective_batch_size(
    tmp_path,
    capsys,
) -> None:
    reset_observability_state()
    observability = ObservabilityConfig(
        enabled=True,
        console_enabled=True,
        console_level="WARNING",
        file_level="INFO",
        log_dir=tmp_path / "logs",
        app_log_file="app.log.jsonl",
        audit_log_file="audit.jsonl",
    )
    bootstrap_observability(observability)

    rdb_path = tmp_path / "sample.rdb"
    rdb_path.write_bytes(b"rdb")

    collector = PathAMySQLBackedCollector(
        stream_parser=lambda _path: iter(
            [
                {"key_name": "a", "key_type": "string", "size_bytes": 1, "has_expiration": False},
                {"key_name": "b", "key_type": "string", "size_bytes": 2, "has_expiration": False},
                {"key_name": "c", "key_type": "string", "size_bytes": 3, "has_expiration": False},
            ]
        ),
        batch_size=2,
        table_name="rdb_stage_runtime",
        stage_rows_to_mysql=lambda table_name, rows, *, source_file, run_id: {
            "table": table_name,
            "database": "analysis_db",
            "mysql_host": "db.example",
            "mysql_port": 3306,
        },
        mysql_target_host="db.example",
        mysql_target_port=3306,
        mysql_target_database="analysis_db",
    )

    result = collector.collect([rdb_path])
    console_output = capsys.readouterr().err

    assert result.batch_size == 2
    records = [
        json.loads(line)
        for line in observability.app_log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    phase_records = [
        record
        for record in records
        if record.get("event_name") == "mysql_staging_phase"
    ]

    assert phase_records
    assert any(record.get("stage") == "batch_start" for record in phase_records)
    assert any(record.get("stage") == "batch_end" for record in phase_records)
    assert any(record.get("stage") == "staging_complete" for record in phase_records)
    assert any(record.get("mysql_stage_batch_size") == 2 for record in phase_records)
    assert any(record.get("batch_number") == 1 for record in phase_records)
    assert any(record.get("batch_rows") == 2 for record in phase_records)
    assert any(record.get("cumulative_rows") == 2 for record in phase_records)
    assert any(record.get("mysql_host") == "db.example" for record in phase_records)
    assert any(record.get("mysql_port") == 3306 for record in phase_records)
    assert any(record.get("mysql_database") == "analysis_db" for record in phase_records)
    assert any(record.get("mysql_table") == "rdb_stage_runtime" for record in phase_records)
    assert all("elapsed_seconds" in record for record in phase_records)
    assert "mysql staging batch" not in console_output.lower()

    reset_observability_state()
