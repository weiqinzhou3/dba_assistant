"""Tests for MySQL tool wiring in orchestrator (WI-5)."""
from pathlib import Path

from dba_assistant.adaptors.mysql_adaptor import MySQLConnectionConfig
from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
from dba_assistant.orchestrator.tools import build_all_tools


def _make_request(**overrides) -> NormalizedRequest:
    defaults = dict(
        raw_prompt="test",
        prompt="test",
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            input_paths=(Path("/tmp/dump.rdb"),),
        ),
        secrets=Secrets(),
        rdb_overrides=RdbOverrides(profile_name="generic"),
    )
    defaults.update(overrides)
    return NormalizedRequest(**defaults)


def test_build_all_tools_includes_mysql_tools_with_mysql_connection() -> None:
    request = _make_request()
    mysql_conn = MySQLConnectionConfig(
        host="db.example", port=3306, user="test", password="test", database="testdb",
    )
    tools = build_all_tools(request, mysql_connection=mysql_conn)
    names = [t.__name__ for t in tools]

    assert "mysql_read_query" in names
    assert "load_preparsed_dataset_from_mysql" in names
    assert "stage_rdb_rows_to_mysql" in names


def test_build_all_tools_excludes_mysql_tools_without_connection() -> None:
    request = _make_request()
    tools = build_all_tools(request)
    names = [t.__name__ for t in tools]

    assert "mysql_read_query" not in names
    assert "stage_rdb_rows_to_mysql" not in names


def test_build_all_tools_includes_both_redis_and_mysql_tools() -> None:
    request = _make_request()
    redis_conn = RedisConnectionConfig(host="redis.example", port=6379)
    mysql_conn = MySQLConnectionConfig(
        host="db.example", port=3306, user="test", password="test", database="testdb",
    )
    tools = build_all_tools(request, connection=redis_conn, mysql_connection=mysql_conn)
    names = [t.__name__ for t in tools]

    assert "analyze_local_rdb" in names
    assert "redis_ping" in names
    assert "mysql_read_query" in names
    assert "stage_rdb_rows_to_mysql" in names
