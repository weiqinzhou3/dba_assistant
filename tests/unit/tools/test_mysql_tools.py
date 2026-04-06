"""Tests for MySQL tools (WI-4) and adaptor write path."""
import json

import pytest

from dba_assistant.adaptors.mysql_adaptor import MySQLAdaptor, MySQLConnectionConfig
from dba_assistant.tools.mysql_tools import (
    load_preparsed_dataset_from_mysql,
    mysql_read_query,
    stage_rdb_rows_to_mysql,
)


def _make_config() -> MySQLConnectionConfig:
    return MySQLConnectionConfig(
        host="localhost", port=3306, user="test", password="test", database="testdb",
    )


class FakeConnection:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.params: list[object] = []
        self.committed = False
        self.closed = False
        self._result: list[dict] = []
        self._rowcount = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
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
        if params:
            self._conn.params.append(params)

    def executemany(self, sql, params):
        self._conn.queries.append(sql)
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
