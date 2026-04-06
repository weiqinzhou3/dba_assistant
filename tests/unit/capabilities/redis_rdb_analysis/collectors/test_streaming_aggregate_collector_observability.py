import json
from pathlib import Path
from types import SimpleNamespace

from dba_assistant.application.request_models import RdbOverrides
from dba_assistant.capabilities.redis_rdb_analysis.collectors.streaming_aggregate_collector import (
    StreamingAggregateCollector,
)
from dba_assistant.capabilities.redis_rdb_analysis.profile_resolver import resolve_profile
from dba_assistant.core.observability import bootstrap_observability, reset_observability_state
from dba_assistant.deep_agent_integration.config import ObservabilityConfig


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_streaming_aggregate_collector_emits_structured_performance_logs(tmp_path: Path) -> None:
    reset_observability_state()
    config = ObservabilityConfig(
        enabled=True,
        level="INFO",
        console_enabled=False,
        log_dir=tmp_path / "logs",
        app_log_file="app.log.jsonl",
        audit_log_file="audit.jsonl",
    )
    bootstrap_observability(config)

    rdb_path = tmp_path / "sample.rdb"
    rdb_path.write_bytes(b"test")

    collector = StreamingAggregateCollector(
        stream_parser=lambda path: SimpleNamespace(
            strategy_name="python_stream",
            strategy_detail="memory-safe",
            rows=[
                {
                    "key_name": "loan:1",
                    "key_type": "string",
                    "size_bytes": 128,
                    "has_expiration": False,
                },
                {
                    "key_name": "session:1",
                    "key_type": "hash",
                    "size_bytes": 64,
                    "has_expiration": True,
                },
            ],
        ),
        profile=resolve_profile("rcs", RdbOverrides()),
        progress_log_interval=1,
    )

    result = collector.collect([rdb_path])

    assert result.metadata["rows_processed"] == "2"

    records = _read_jsonl(config.app_log_path)
    performance_records = [
        record
        for record in records
        if record.get("logger") == "dba_assistant.capabilities.redis_rdb_analysis.collectors.streaming_aggregate_collector"
    ]

    assert performance_records
    assert any(record.get("event_name") == "redis_rdb_stream_progress" for record in performance_records)
    assert any(record.get("event_name") == "redis_rdb_stream_phase" for record in performance_records)

    reset_observability_state()
