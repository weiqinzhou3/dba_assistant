"""Tests for MySQL tools (WI-4) and adaptor write path."""
import json
from pathlib import Path

import pytest

from dba_assistant.adaptors.mysql_adaptor import (
    MySQLAdaptor,
    MySQLConnectionConfig,
    MySQLOperationError,
    MySQLReadTimeoutError,
    MySQLWriteTimeoutError,
)
from dba_assistant.core.observability import bootstrap_observability, reset_observability_state
from dba_assistant.deep_agent_integration.config import ObservabilityConfig
from dba_assistant.capabilities.redis_rdb_analysis.types import EffectiveProfile
from dba_assistant.tools.mysql_tools import (
    MySQLStagingSession,
    analyze_staged_rdb_rows,
    create_staging_table,
    format_mysql_error,
    insert_staging_batch,
    load_preparsed_dataset_from_mysql,
    mysql_read_query,
    stage_rdb_rows_to_mysql,
)


def _make_config() -> MySQLConnectionConfig:
    return MySQLConnectionConfig(
        host="localhost", port=3306, user="test", password="test", database="testdb",
    )


class FakeConnection:
    def __init__(
        self,
        *,
        execute_error: Exception | None = None,
        executemany_error: Exception | None = None,
        commit_error: Exception | None = None,
    ) -> None:
        self.queries: list[str] = []
        self.params: list[object] = []
        self.committed = False
        self.closed = False
        self._result: list[dict] = []
        self._rowcount = 0
        self._execute_error = execute_error
        self._executemany_error = executemany_error
        self._commit_error = commit_error

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        if self._commit_error is not None:
            raise self._commit_error
        self.committed = True

    def close(self):
        self.closed = True


class FakeCursor:
    def __init__(self, conn: FakeConnection) -> None:
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql, params=None):
        self._conn.queries.append(sql)
        if self._conn._execute_error is not None:
            raise self._conn._execute_error
        if params:
            self._conn.params.append(params)

    def executemany(self, sql, params):
        self._conn.queries.append(sql)
        if self._conn._executemany_error is not None:
            raise self._conn._executemany_error
        self._conn.params.extend(params)
        self.rowcount = len(params)
        self._conn._rowcount = len(params)

    def fetchall(self):
        return self._conn._result

    @property
    def rowcount(self):
        return self._conn._rowcount

    @rowcount.setter
    def rowcount(self, value):
        self._conn._rowcount = value


def test_mysql_read_query_returns_json() -> None:
    conn = FakeConnection()
    conn._result = [{"id": 1, "name": "test"}]
    adaptor = MySQLAdaptor(connect=lambda **_kw: conn)
    config = _make_config()

    result = mysql_read_query(adaptor, config, "SELECT * FROM t")
    parsed = json.loads(result)

    assert parsed == [{"id": 1, "name": "test"}]
    assert conn.closed


def test_load_preparsed_dataset_from_mysql_returns_dataset_json() -> None:
    conn = FakeConnection()
    conn._result = [{"key_name": "cache:1", "size_bytes": 100}]
    adaptor = MySQLAdaptor(connect=lambda **_kw: conn)
    config = _make_config()

    result = load_preparsed_dataset_from_mysql(adaptor, config, "rdb_staging")
    parsed = json.loads(result)

    assert parsed["source"] == "mysql:rdb_staging"
    assert len(parsed["rows"]) == 1
    assert "rdb_staging" in conn.queries[0]


def test_stage_rdb_rows_to_mysql_creates_table_and_inserts() -> None:
    conn = FakeConnection()
    adaptor = MySQLAdaptor(connect=lambda **_kw: conn)
    config = _make_config()
    rows = [
        {"key_name": "cache:1", "key_type": "string", "size_bytes": "100"},
        {"key_name": "cache:2", "key_type": "hash", "size_bytes": "200"},
    ]

    result = stage_rdb_rows_to_mysql(adaptor, config, "staging_t", rows)
    parsed = json.loads(result)

    assert parsed["table"] == "staging_t"
    # Should have CREATE TABLE + INSERT (2 queries across 2 connections)
    assert any("CREATE TABLE" in q for q in conn.queries)
    assert any("INSERT INTO" in q for q in conn.queries)


def test_stage_rdb_rows_to_mysql_preserves_null_bool_and_int_params() -> None:
    conn = FakeConnection()
    adaptor = MySQLAdaptor(connect=lambda **_kw: conn)
    config = _make_config()
    rows = [
        {
            "key_name": "cache:1",
            "key_type": "string",
            "size_bytes": 123,
            "has_expiration": False,
            "ttl_seconds": None,
        }
    ]

    stage_rdb_rows_to_mysql(adaptor, config, "staging_t", rows)

    assert conn.params == [("manual", "manual", "cache:1", "string", 123, 0, None)]


def test_stage_rdb_rows_empty_returns_zero() -> None:
    adaptor = MySQLAdaptor(connect=lambda **_kw: FakeConnection())
    config = _make_config()

    result = stage_rdb_rows_to_mysql(adaptor, config, "staging_t", [])
    parsed = json.loads(result)

    assert parsed["staged"] == 0


def test_mysql_adaptor_execute_write_commits() -> None:
    conn = FakeConnection()
    adaptor = MySQLAdaptor(connect=lambda **_kw: conn)
    config = _make_config()

    adaptor.execute_write(config, "CREATE TABLE t (id INT)")

    assert conn.committed
    assert conn.closed


def test_create_staging_table_wraps_failures_with_operation_context() -> None:
    conn = FakeConnection(execute_error=Exception("ddl blocked by metadata lock"))
    adaptor = MySQLAdaptor(connect=lambda **_kw: conn)
    config = _make_config()

    with pytest.raises(MySQLOperationError) as exc_info:
        create_staging_table(adaptor, config, "staging_t")

    message = str(exc_info.value)
    assert "create table failed" in message.lower()
    assert "operation=create_table" in message
    assert "stage=write" in message
    assert "table=staging_t" in message
    assert "host=localhost" in message
    assert "ddl blocked by metadata lock" in message.lower()
    assert "create table failed" in format_mysql_error(exc_info.value).lower()


def test_insert_staging_batch_timeout_includes_insert_batch_context() -> None:
    conn = FakeConnection(executemany_error=TimeoutError("write timed out"))
    adaptor = MySQLAdaptor(connect=lambda **_kw: conn)
    session = MySQLStagingSession(
        connection=_make_config(),
        database_name="testdb",
        table_name="staging_t",
        run_id="run-1",
        batch_size=2000,
    )

    with pytest.raises(MySQLWriteTimeoutError) as exc_info:
        insert_staging_batch(
            adaptor,
            session,
            source_file="/tmp/sample.rdb",
            rows=[{"key_name": "cache:1", "key_type": "string", "size_bytes": 1}],
        )

    message = str(exc_info.value)
    assert "write timeout" in message.lower()
    assert "operation=insert_batch" in message
    assert "stage=write" in message
    assert "table=staging_t" in message


def test_insert_staging_batch_commit_timeout_includes_commit_stage() -> None:
    conn = FakeConnection(commit_error=TimeoutError("write timed out"))
    adaptor = MySQLAdaptor(connect=lambda **_kw: conn)
    session = MySQLStagingSession(
        connection=_make_config(),
        database_name="testdb",
        table_name="staging_t",
        run_id="run-1",
        batch_size=2000,
    )

    with pytest.raises(MySQLWriteTimeoutError) as exc_info:
        insert_staging_batch(
            adaptor,
            session,
            source_file="/tmp/sample.rdb",
            rows=[{"key_name": "cache:1", "key_type": "string", "size_bytes": 1}],
        )

    message = str(exc_info.value)
    assert "write timeout" in message.lower()
    assert "operation=insert_batch" in message
    assert "stage=commit" in message
    assert "table=staging_t" in message


@pytest.mark.parametrize("limit", [None, "", "None", "null", "NULL"])
def test_load_preparsed_dataset_from_mysql_uses_default_limit_for_nullish_limit_values(limit: object) -> None:
    conn = FakeConnection()
    conn._result = [{"key_name": "cache:1", "size_bytes": 100}]
    adaptor = MySQLAdaptor(connect=lambda **_kw: conn)
    config = _make_config()

    load_preparsed_dataset_from_mysql(adaptor, config, "rdb_staging", limit=limit)

    assert conn.queries[0].endswith("LIMIT 100000")


def test_load_preparsed_dataset_from_mysql_rejects_non_numeric_limit() -> None:
    adaptor = MySQLAdaptor(connect=lambda **_kw: FakeConnection())
    config = _make_config()

    with pytest.raises(ValueError, match="Invalid MySQL dataset row limit"):
        load_preparsed_dataset_from_mysql(adaptor, config, "rdb_staging", limit="oops")


def test_analyze_staged_rdb_rows_normalizes_missing_mysql_top_n_keys() -> None:
    session = MySQLStagingSession(
        connection=_make_config(),
        database_name="testdb",
        table_name="rdb_staging",
        run_id="run-1",
        batch_size=100,
    )
    profile = EffectiveProfile(
        name="rcs",
        sections=("overall_summary", "prefix_top_summary", "focused_prefix_analysis", "top_big_keys"),
        focus_prefixes=("loan:*",),
        top_n={"top_big_keys": 2},
    )

    class FakeReadAdaptor:
        def read_query(self, _config, sql: str):
            if "COUNT(*) AS total_keys" in sql:
                return [{"total_keys": 2, "total_bytes": 300}]
            if "GROUP BY key_type" in sql and "memory_bytes" in sql:
                return [{"key_type": "string", "key_count": 2, "memory_bytes": 300}]
            if "expired_count" in sql:
                return [{"expired_count": 1, "persistent_count": 1}]
            if "GROUP BY prefix_label" in sql:
                return [{"prefix_label": "loan:*", "key_count": 2, "memory_bytes": 300}]
            if "matched_key_count" in sql:
                return [
                    {
                        "matched_key_count": 2,
                        "total_size_bytes": 300,
                        "with_expiration": 1,
                        "without_expiration": 1,
                    }
                ]
            if "GROUP BY key_type ORDER BY key_count DESC" in sql:
                return [{"key_type": "string", "key_count": 2}]
            if "SELECT key_name, key_type, size_bytes" in sql:
                return [{"key_name": "loan:1", "key_type": "string", "size_bytes": 200}]
            if "SELECT key_name, size_bytes" in sql:
                return [{"key_name": "loan:1", "size_bytes": 200}]
            return []

    result = analyze_staged_rdb_rows(
        FakeReadAdaptor(),
        session,
        profile=profile,
        sample_rows=[["sample-1", "local_rdb", "/tmp/dump.rdb"]],
    )

    assert result["prefix_top_summary"]["rows"] == [["loan:*", "2", "300"]]
    assert result["focused_prefix_analysis"]["sections"][0]["limit"] == 100
    assert result["top_big_keys"]["limit"] == 2


def test_analyze_staged_rdb_rows_emits_analysis_phase_logs(tmp_path: Path) -> None:
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

    session = MySQLStagingSession(
        connection=_make_config(),
        database_name="testdb",
        table_name="rdb_staging",
        run_id="run-1",
        batch_size=100,
    )
    profile = EffectiveProfile(
        name="rcs",
        sections=("overall_summary", "prefix_top_summary", "focused_prefix_analysis", "top_big_keys"),
        focus_prefixes=("loan:*",),
        top_n={"top_big_keys": 2, "prefix_top": 2, "focused_prefix_top_keys": 2},
    )

    class FakeReadAdaptor:
        def read_query(self, _config, sql: str):
            if "COUNT(*) AS total_keys" in sql:
                return [{"total_keys": 2, "total_bytes": 300}]
            if "GROUP BY key_type" in sql and "memory_bytes" in sql:
                return [{"key_type": "string", "key_count": 2, "memory_bytes": 300}]
            if "expired_count" in sql:
                return [{"expired_count": 1, "persistent_count": 1}]
            if "GROUP BY prefix_label" in sql:
                return [{"prefix_label": "loan:*", "key_count": 2, "memory_bytes": 300}]
            if "matched_key_count" in sql:
                return [{"matched_key_count": 2, "total_size_bytes": 300, "with_expiration": 1, "without_expiration": 1}]
            if "GROUP BY key_type ORDER BY key_count DESC" in sql:
                return [{"key_type": "string", "key_count": 2}]
            if "SELECT key_name, key_type, size_bytes" in sql:
                return [{"key_name": "loan:1", "key_type": "string", "size_bytes": 200}]
            if "SELECT key_name, size_bytes" in sql:
                return [{"key_name": "loan:1", "size_bytes": 200}]
            return []

    analyze_staged_rdb_rows(
        FakeReadAdaptor(),
        session,
        profile=profile,
        sample_rows=[["sample-1", "local_rdb", "/tmp/dump.rdb"]],
    )

    records = [
        json.loads(line)
        for line in observability.app_log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    phase_records = [record for record in records if record.get("event_name") == "mysql_analysis_phase"]

    assert any(record.get("query_name") == "overall_summary" and record.get("stage") == "start" for record in phase_records)
    assert any(record.get("query_name") == "prefix_top_summary" and record.get("stage") == "end" for record in phase_records)
    assert any(record.get("query_name") == "focused_prefix_top_keys" and record.get("stage") == "end" for record in phase_records)
    assert any(record.get("query_name") == "top_big_keys" and record.get("stage") == "end" for record in phase_records)
    assert all(record.get("mysql_table") == "rdb_staging" for record in phase_records)

    reset_observability_state()


def test_analyze_staged_rdb_rows_skips_loan_prefix_detail_when_profile_does_not_request_it() -> None:
    session = MySQLStagingSession(
        connection=_make_config(),
        database_name="testdb",
        table_name="rdb_staging",
        run_id="run-1",
        batch_size=100,
    )
    profile = EffectiveProfile(
        name="rcs",
        sections=("overall_summary", "prefix_top_summary"),
        top_n={"top_big_keys": 2, "prefix_top": 2},
    )

    class FakeReadAdaptor:
        def read_query(self, _config, sql: str):
            if "AND key_name LIKE 'loan:%'" in sql:
                raise AssertionError("loan_prefix_detail must not run when the section is not requested")
            if "COUNT(*) AS total_keys" in sql:
                return [{"total_keys": 2, "total_bytes": 300}]
            if "GROUP BY key_type" in sql and "memory_bytes" in sql:
                return [{"key_type": "string", "key_count": 2, "memory_bytes": 300}]
            if "expired_count" in sql:
                return [{"expired_count": 1, "persistent_count": 1}]
            if "GROUP BY prefix_label" in sql:
                return [{"prefix_label": "loan:*", "key_count": 2, "memory_bytes": 300}]
            return []

    result = analyze_staged_rdb_rows(
        FakeReadAdaptor(),
        session,
        profile=profile,
        sample_rows=[["sample-1", "local_rdb", "/tmp/dump.rdb"]],
    )

    assert result["loan_prefix_detail"]["rows"] == []


def test_analyze_staged_rdb_rows_applies_limit_to_loan_prefix_detail_query() -> None:
    session = MySQLStagingSession(
        connection=_make_config(),
        database_name="testdb",
        table_name="rdb_staging",
        run_id="run-1",
        batch_size=100,
    )
    profile = EffectiveProfile(
        name="rcs",
        sections=("overall_summary", "loan_prefix_detail"),
        top_n={"top_big_keys": 7, "focused_prefix_top_keys": 7},
    )
    captured_sql: list[str] = []

    class FakeReadAdaptor:
        def read_query(self, _config, sql: str):
            captured_sql.append(sql)
            if "COUNT(*) AS total_keys" in sql:
                return [{"total_keys": 2, "total_bytes": 300}]
            if "GROUP BY key_type" in sql and "memory_bytes" in sql:
                return [{"key_type": "string", "key_count": 2, "memory_bytes": 300}]
            if "expired_count" in sql:
                return [{"expired_count": 1, "persistent_count": 1}]
            if "AND key_name LIKE 'loan:%'" in sql:
                return [{"key_name": "loan:1", "key_type": "string", "size_bytes": 200}]
            return []

    result = analyze_staged_rdb_rows(
        FakeReadAdaptor(),
        session,
        profile=profile,
        sample_rows=[["sample-1", "local_rdb", "/tmp/dump.rdb"]],
    )

    loan_queries = [sql for sql in captured_sql if "AND key_name LIKE 'loan:%'" in sql]
    assert loan_queries
    assert "LIMIT 7" in loan_queries[0]
    assert result["loan_prefix_detail"]["limit"] == 7


def test_analyze_staged_rdb_rows_wraps_analysis_timeout_with_query_name() -> None:
    session = MySQLStagingSession(
        connection=_make_config(),
        database_name="testdb",
        table_name="rdb_staging",
        run_id="run-1",
        batch_size=100,
    )
    profile = EffectiveProfile(
        name="rcs",
        sections=("overall_summary", "prefix_top_summary"),
        top_n={"prefix_top": 2},
    )

    class FakeReadAdaptor:
        def read_query(self, config, sql: str):
            if "COUNT(*) AS total_keys" in sql:
                return [{"total_keys": 2, "total_bytes": 300}]
            if "GROUP BY key_type" in sql and "memory_bytes" in sql:
                return [{"key_type": "string", "key_count": 2, "memory_bytes": 300}]
            if "expired_count" in sql:
                return [{"expired_count": 1, "persistent_count": 1}]
            if "GROUP BY prefix_label" in sql:
                raise MySQLReadTimeoutError(
                    summary="MySQL read timeout",
                    stage="read",
                    config=config,
                    root_cause="timed out after 15.0s",
                )
            return []

    with pytest.raises(MySQLOperationError) as exc_info:
        analyze_staged_rdb_rows(
            FakeReadAdaptor(),
            session,
            profile=profile,
            sample_rows=[["sample-1", "local_rdb", "/tmp/dump.rdb"]],
        )

    message = str(exc_info.value)
    assert "query_name=prefix_top_summary" in message
    assert "operation=analysis_query" in message
