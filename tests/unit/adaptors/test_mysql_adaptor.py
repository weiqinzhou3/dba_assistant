import time

import pytest

from dba_assistant.adaptors.mysql_adaptor import (
    MySQLAdaptor,
    MySQLAuthenticationError,
    MySQLConnectTimeoutError,
    MySQLConnectionConfig,
    MySQLConnectionFailedError,
    MySQLReadTimeoutError,
    MySQLWriteTimeoutError,
)


def _make_config() -> MySQLConnectionConfig:
    return MySQLConnectionConfig(
        host="192.168.23.176",
        port=3306,
        user="root",
        password="Root@1234!",
        database="rcs",
        connect_timeout_seconds=5.0,
        read_timeout_seconds=15.0,
        write_timeout_seconds=30.0,
    )


class _Cursor:
    def __init__(
        self,
        *,
        execute_error: Exception | None = None,
        executemany_error: Exception | None = None,
    ) -> None:
        self.execute_error = execute_error
        self.executemany_error = executemany_error
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, _sql: str, _params=None) -> None:
        if self.execute_error is not None:
            raise self.execute_error

    def executemany(self, _sql: str, _params) -> None:
        if self.executemany_error is not None:
            raise self.executemany_error

    def fetchall(self):
        return []


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def test_mysql_adaptor_open_passes_configured_timeouts_and_fails_fast_on_connect_timeout() -> None:
    captured: dict[str, object] = {}

    def fake_connect(**kwargs):
        captured.update(kwargs)
        raise TimeoutError("timed out")

    adaptor = MySQLAdaptor(connect=fake_connect)
    started = time.perf_counter()

    with pytest.raises(MySQLConnectTimeoutError, match="host=192.168.23.176"):
        adaptor.execute_query(_make_config(), "SELECT 1")

    elapsed = time.perf_counter() - started
    assert elapsed < 0.5
    assert captured["connect_timeout"] == 5.0
    assert captured["read_timeout"] == 15.0
    assert captured["write_timeout"] == 30.0


def test_mysql_adaptor_wraps_connection_failures_with_clear_context() -> None:
    adaptor = MySQLAdaptor(
        connect=lambda **_kwargs: (_ for _ in ()).throw(OSError("Network is unreachable"))
    )

    with pytest.raises(MySQLConnectionFailedError) as exc_info:
        adaptor.execute_query(_make_config(), "SELECT 1")

    message = str(exc_info.value)
    assert "stage=connect" in message
    assert "host=192.168.23.176" in message
    assert "port=3306" in message
    assert "database=rcs" in message
    assert "network is unreachable" in message.lower()


def test_mysql_adaptor_wraps_authentication_failures_with_clear_context() -> None:
    adaptor = MySQLAdaptor(
        connect=lambda **_kwargs: (_ for _ in ()).throw(
            Exception("(1045, \"Access denied for user 'root'\")")
        )
    )

    with pytest.raises(MySQLAuthenticationError) as exc_info:
        adaptor.execute_query(_make_config(), "SELECT 1")

    assert "authentication failed" in str(exc_info.value).lower()
    assert "stage=connect" in str(exc_info.value)


def test_mysql_adaptor_wraps_read_timeout_failures() -> None:
    adaptor = MySQLAdaptor(
        connect=lambda **_kwargs: _Connection(_Cursor(execute_error=TimeoutError("read timed out")))
    )

    with pytest.raises(MySQLReadTimeoutError) as exc_info:
        adaptor.execute_query(_make_config(), "SELECT 1")

    assert "stage=read" in str(exc_info.value)
    assert "read timeout" in str(exc_info.value).lower()


def test_mysql_adaptor_wraps_write_timeout_failures() -> None:
    adaptor = MySQLAdaptor(
        connect=lambda **_kwargs: _Connection(_Cursor(executemany_error=TimeoutError("write timed out")))
    )

    with pytest.raises(MySQLWriteTimeoutError) as exc_info:
        adaptor.execute_write(_make_config(), "INSERT INTO t VALUES (%s)", params=[("x",)])

    assert "stage=write" in str(exc_info.value)
    assert "write timeout" in str(exc_info.value).lower()
