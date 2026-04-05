import json
from pathlib import Path

import pytest

from dba_assistant.core.reporter.report_model import AnalysisReport
from dba_assistant.parsers import rdb_parser_strategy as parser_strategy_module
from dba_assistant.capabilities.redis_rdb_analysis import service as service_module
from dba_assistant.capabilities.redis_rdb_analysis.service import analyze_rdb
from dba_assistant.capabilities.redis_rdb_analysis.types import (
    AnalysisStatus,
    ConfirmationRequest,
    InputSourceKind,
    RdbAnalysisRequest,
    SampleInput,
)

HDT_BINARY = Path(".tools/bin/rdb")


def test_analyze_rdb_returns_confirmation_request_for_remote_redis_without_confirmation() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze latest rdb",
        inputs=[SampleInput(source="10.0.0.8:6379", kind=InputSourceKind.REMOTE_REDIS)],
    )

    result = analyze_rdb(
        request,
        profile=None,
        remote_discovery=lambda *_args, **_kwargs: {"rdb_path": "/data/redis/dump.rdb"},
    )

    assert isinstance(result, ConfirmationRequest)
    assert result.status is AnalysisStatus.CONFIRMATION_REQUIRED
    assert result.required_action == "fetch_existing"
    assert "/data/redis/dump.rdb" in result.message


def test_analyze_rdb_returns_analysis_report_for_local_inputs(monkeypatch) -> None:
    rows = json.loads(Path("tests/fixtures/rdb/direct/sample_key_records.json").read_text(encoding="utf-8"))
    request = RdbAnalysisRequest(
        prompt="analyze this rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
    )
    monkeypatch.setattr("dba_assistant.capabilities.redis_rdb_analysis.service._parse_rdb_rows", lambda _path: rows)

    result = analyze_rdb(
        request,
        profile=None,
        remote_discovery=lambda *_args, **_kwargs: {"rdb_path": "/data/redis/dump.rdb"},
    )

    assert isinstance(result, AnalysisReport)
    assert result.title == "Redis RDB Analysis"
    assert result.metadata["profile"] == "generic"
    assert result.metadata["route"] == "direct_rdb_analysis"
    assert result.metadata["path"] == "3c"
    assert any(section.id == "top_big_keys" for section in result.sections)


def test_analyze_rdb_local_inputs_do_not_call_remote_discovery(monkeypatch) -> None:
    rows = json.loads(Path("tests/fixtures/rdb/direct/sample_key_records.json").read_text(encoding="utf-8"))
    request = RdbAnalysisRequest(
        prompt="analyze this local rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
    )
    monkeypatch.setattr("dba_assistant.capabilities.redis_rdb_analysis.service._parse_rdb_rows", lambda _path: rows)

    def fail_remote_discovery(*_args, **_kwargs):
        raise AssertionError("remote_discovery should not be called for local inputs")

    result = analyze_rdb(
        request,
        profile=None,
        remote_discovery=fail_remote_discovery,
    )

    assert isinstance(result, AnalysisReport)


def test_analyze_rdb_returns_analysis_report_for_precomputed_inputs() -> None:
    request = RdbAnalysisRequest(
        prompt="summarize this exported analysis",
        inputs=[
            SampleInput(
                source=Path("tests/fixtures/rdb/precomputed/sample_precomputed_rows.json"),
                kind=InputSourceKind.PRECOMPUTED,
            )
        ],
    )

    result = analyze_rdb(
        request,
        profile=None,
        remote_discovery=lambda *_args, **_kwargs: {"rdb_path": "/data/redis/dump.rdb"},
    )

    assert isinstance(result, AnalysisReport)
    assert result.title == "Redis RDB Analysis"
    assert result.metadata["profile"] == "generic"
    assert result.metadata["route"] == "preparsed_dataset_analysis"
    assert result.metadata["path"] == "3b"
    assert any(section.id == "sample_overview" for section in result.sections)


def test_analyze_rdb_returns_analysis_report_for_preparsed_mysql_inputs() -> None:
    rows = json.loads(Path("tests/fixtures/rdb/direct/sample_key_records.json").read_text(encoding="utf-8"))
    request = RdbAnalysisRequest(
        prompt="summarize this mysql dataset",
        inputs=[SampleInput(source="mysql:preparsed_keys", kind=InputSourceKind.PREPARSED_MYSQL)],
        mysql_table="preparsed_keys",
    )
    calls: dict[str, object] = {}

    def fake_load_preparsed_dataset_from_mysql(table_name: str) -> dict[str, object]:
        calls["table_name"] = table_name
        return {"source": f"mysql:{table_name}", "rows": rows}

    result = analyze_rdb(
        request,
        profile=None,
        remote_discovery=lambda *_args, **_kwargs: {"rdb_path": "/data/redis/dump.rdb"},
        load_preparsed_dataset_from_mysql=fake_load_preparsed_dataset_from_mysql,
    )

    assert isinstance(result, AnalysisReport)
    assert calls["table_name"] == "preparsed_keys"
    assert result.metadata["route"] == "preparsed_dataset_analysis"
    assert result.metadata["path"] == "3b"
    assert any(section.id == "sample_overview" for section in result.sections)


def test_analyze_rdb_database_backed_route_stages_rows_and_reloads_mysql_dataset(
    monkeypatch,
) -> None:
    rows = json.loads(Path("tests/fixtures/rdb/direct/sample_key_records.json").read_text(encoding="utf-8"))
    request = RdbAnalysisRequest(
        prompt="analyze this rdb via mysql",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
        path_mode="database_backed_analysis",
    )
    calls: dict[str, object] = {}

    monkeypatch.setattr(service_module, "_parse_rdb_rows", lambda _path: rows)

    def fake_stage_rdb_rows_to_mysql(table_name: str, parsed_rows: list[dict[str, object]]) -> dict[str, object]:
        calls["stage"] = (table_name, parsed_rows)
        return {"table": table_name, "staged": len(parsed_rows)}

    def fake_load_preparsed_dataset_from_mysql(table_name: str) -> dict[str, object]:
        calls["load"] = table_name
        return {"source": f"mysql:{table_name}", "rows": rows}

    result = analyze_rdb(
        request,
        profile=None,
        remote_discovery=lambda *_args, **_kwargs: {"rdb_path": "/data/redis/dump.rdb"},
        stage_rdb_rows_to_mysql=fake_stage_rdb_rows_to_mysql,
        load_preparsed_dataset_from_mysql=fake_load_preparsed_dataset_from_mysql,
    )

    assert isinstance(result, AnalysisReport)
    staged_table, staged_rows = calls["stage"]
    assert staged_table.startswith("rdb_stage_")
    assert staged_rows == rows
    assert calls["load"] == staged_table
    assert result.metadata["route"] == "database_backed_analysis"
    assert result.metadata["path"] == "3a"
    assert any(section.id == "top_big_keys" for section in result.sections)


def test_analyze_rdb_remote_discovery_requires_rdb_path() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze remote redis",
        inputs=[SampleInput(source="10.0.0.8:6379", kind=InputSourceKind.REMOTE_REDIS)],
    )

    with pytest.raises(ValueError, match="remote_discovery did not return rdb_path"):
        analyze_rdb(
            request,
            profile=None,
            remote_discovery=lambda *_args, **_kwargs: {},
        )


@pytest.mark.skipif(not HDT_BINARY.exists(), reason="HDT3213/rdb binary is not available in this workspace")
def test_analyze_rdb_uses_hdt_parser_strategy_for_v11_fixture() -> None:
    parser_strategy_module.build_default_rdb_parser_strategy.cache_clear()

    request = RdbAnalysisRequest(
        prompt="analyze a Redis 7 function dump",
        inputs=[
            SampleInput(
                source=Path("tests/fixtures/rdb/high_version/redis_v11_function.rdb"),
                kind=InputSourceKind.LOCAL_RDB,
            )
        ],
    )

    result = analyze_rdb(
        request,
        profile=None,
        remote_discovery=lambda *_args, **_kwargs: {"rdb_path": "/data/redis/dump.rdb"},
    )

    assert isinstance(result, AnalysisReport)
    assert result.metadata["route"] == "direct_rdb_analysis"
    assert result.metadata["path"] == "3c"
    assert result.metadata["parser_strategy"] == "HdtRdbCliStrategy"
    assert result.metadata["parser_binary"] == str(HDT_BINARY.resolve())
    assert result.summary == "1 samples, 0 keys, 0 bytes."

    parser_strategy_module.build_default_rdb_parser_strategy.cache_clear()
