from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from time import perf_counter
from typing import Any, Callable


@dataclass(frozen=True)
class MySQLConnectionConfig:
    host: str
    port: int
    user: str
    password: str
    database: str | None = None
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 15.0
    write_timeout_seconds: float = 30.0


class MySQLOperationError(ValueError):
    def __init__(
        self,
        *,
        summary: str,
        stage: str,
        config: MySQLConnectionConfig,
        root_cause: str,
        operation: str | None = None,
        table: str | None = None,
        query_name: str | None = None,
    ) -> None:
        self.summary = summary
        self.stage = stage
        self.host = config.host
        self.port = config.port
        self.database = config.database or ""
        self.root_cause = root_cause
        self.operation = operation
        self.table = table or ""
        self.query_name = query_name or ""
        parts = [
            f"{summary}: host={self.host} port={self.port} "
            f"database={self.database or '<none>'} stage={stage}"
        ]
        if self.operation:
            parts.append(f"operation={self.operation}")
        if self.table:
            parts.append(f"table={self.table}")
        if self.query_name:
            parts.append(f"query_name={self.query_name}")
        parts.append(f"cause={root_cause}")
        super().__init__(" ".join(parts))


class MySQLConnectTimeoutError(MySQLOperationError):
    pass


class MySQLConnectionFailedError(MySQLOperationError):
    pass


class MySQLAuthenticationError(MySQLOperationError):
    pass


class MySQLReadTimeoutError(MySQLOperationError):
    pass


class MySQLWriteTimeoutError(MySQLOperationError):
    pass


class MySQLAdaptor:
    def __init__(self, connect: Callable[..., Any] | None = None) -> None:
        self._connect = connect or _default_connect

    @staticmethod
    def dict_cursor_class() -> object:
        pymysql = _load_pymysql()
        if pymysql is None:
            return dict
        return pymysql.cursors.DictCursor

    def _open(self, config: MySQLConnectionConfig) -> Any:
        kwargs: dict[str, Any] = {
            "host": config.host,
            "port": config.port,
            "user": config.user,
            "password": config.password,
            "cursorclass": self.dict_cursor_class(),
            "connect_timeout": config.connect_timeout_seconds,
            "read_timeout": config.read_timeout_seconds,
            "write_timeout": config.write_timeout_seconds,
        }
        if config.database:
            kwargs["database"] = config.database
        try:
            return self._connect(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise _wrap_mysql_error(exc, stage="connect", config=config) from exc

    # --- Read path ---

    def execute_query(self, config: MySQLConnectionConfig, sql: str) -> list[dict[str, Any]]:
        connection = self._open(config)
        try:
            with connection.cursor() as cursor:
                try:
                    cursor.execute(sql)
                    return list(cursor.fetchall())
                except Exception as exc:  # noqa: BLE001
                    raise _wrap_mysql_error(exc, stage="read", config=config) from exc
        finally:
            _close_quietly(connection)

    def read_query(self, config: MySQLConnectionConfig, sql: str) -> list[dict[str, Any]]:
        """Execute a bounded read-only SQL query and return the result set."""
        return self.execute_query(config, sql)

    # --- Write path ---

    def execute_write(
        self,
        config: MySQLConnectionConfig,
        sql: str,
        params: list[tuple[Any, ...]] | None = None,
        log_hook: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> int:
        """Execute a write statement (INSERT/CREATE/etc.) and return affected row count."""
        connection = self._open(config)
        try:
            with connection.cursor() as cursor:
                rowcount = 0
                try:
                    if params:
                        _emit_log_hook(log_hook, "executemany_start", {"param_count": len(params)})
                        write_started = perf_counter()
                        cursor.executemany(sql, params)
                        rowcount = int(cursor.rowcount or 0)
                        _emit_log_hook(
                            log_hook,
                            "executemany_end",
                            {
                                "param_count": len(params),
                                "rowcount": rowcount,
                                "elapsed_seconds": round(perf_counter() - write_started, 6),
                            },
                        )
                    else:
                        _emit_log_hook(log_hook, "execute_start", {})
                        write_started = perf_counter()
                        cursor.execute(sql)
                        rowcount = int(cursor.rowcount or 0)
                        _emit_log_hook(
                            log_hook,
                            "execute_end",
                            {
                                "rowcount": rowcount,
                                "elapsed_seconds": round(perf_counter() - write_started, 6),
                            },
                        )
                except Exception as exc:  # noqa: BLE001
                    raise _wrap_mysql_error(exc, stage="write", config=config) from exc
                try:
                    _emit_log_hook(log_hook, "commit_start", {"rowcount": rowcount})
                    commit_started = perf_counter()
                    connection.commit()
                    _emit_log_hook(
                        log_hook,
                        "commit_end",
                        {
                            "rowcount": rowcount,
                            "elapsed_seconds": round(perf_counter() - commit_started, 6),
                        },
                    )
                    return rowcount
                except Exception as exc:  # noqa: BLE001
                    raise _wrap_mysql_error(exc, stage="commit", config=config) from exc
        finally:
            _close_quietly(connection)


def _default_connect(**kwargs: Any) -> Any:
    pymysql = _load_pymysql(required=True)
    return pymysql.connect(**kwargs)


def _load_pymysql(*, required: bool = False) -> Any | None:
    try:
        return import_module("pymysql")
    except ModuleNotFoundError:
        if required:
            raise RuntimeError("PyMySQL is required for MySQLAdaptor default connections.") from None
        return None


def _close_quietly(connection: Any) -> None:
    try:
        connection.close()
    except Exception:  # noqa: BLE001
        return None


def _emit_log_hook(
    log_hook: Callable[[str, dict[str, Any]], None] | None,
    event: str,
    payload: dict[str, Any],
) -> None:
    if log_hook is None:
        return None
    log_hook(event, payload)
    return None


def _wrap_mysql_error(
    exc: Exception,
    *,
    stage: str,
    config: MySQLConnectionConfig,
) -> MySQLOperationError:
    if isinstance(exc, MySQLOperationError):
        return exc

    message = _exception_message(exc)
    lowered = message.lower()
    code = _extract_mysql_error_code(exc)

    if code == 1045 or "access denied" in lowered or "authentication failed" in lowered:
        return MySQLAuthenticationError(
            summary="MySQL authentication failed",
            stage=stage,
            config=config,
            root_cause=_summarize_root_cause(lowered, message),
        )

    if _is_timeout_error(exc, lowered):
        timeout = _stage_timeout_seconds(stage, config)
        root_cause = f"timed out after {timeout:.1f}s"
        if stage == "connect":
            return MySQLConnectTimeoutError(
                summary="MySQL connect timeout",
                stage=stage,
                config=config,
                root_cause=root_cause,
            )
        if stage == "read":
            return MySQLReadTimeoutError(
                summary="MySQL read timeout",
                stage=stage,
                config=config,
                root_cause=root_cause,
            )
        return MySQLWriteTimeoutError(
            summary="MySQL write timeout",
            stage=stage,
            config=config,
            root_cause=root_cause,
        )

    if stage == "connect" and _is_connection_failure(code, lowered):
        return MySQLConnectionFailedError(
            summary="MySQL connection failed",
            stage=stage,
            config=config,
            root_cause=_summarize_root_cause(lowered, message),
        )

    return MySQLOperationError(
        summary="MySQL operation failed",
        stage=stage,
        config=config,
        root_cause=_summarize_root_cause(lowered, message),
    )


def _exception_message(exc: Exception) -> str:
    if exc.args:
        return " ".join(str(part) for part in exc.args if part is not None).strip() or str(exc)
    return str(exc)


def _extract_mysql_error_code(exc: Exception) -> int | None:
    if not exc.args:
        return None
    first = exc.args[0]
    if isinstance(first, int):
        return first
    text = str(first).strip()
    if text.isdigit():
        return int(text)
    return None


def _is_timeout_error(exc: Exception, lowered: str) -> bool:
    return isinstance(exc, TimeoutError) or "timed out" in lowered or "timeout" in lowered


def _is_connection_failure(code: int | None, lowered: str) -> bool:
    if code in {2002, 2003, 2005}:
        return True
    return any(
        marker in lowered
        for marker in (
            "connection refused",
            "network is unreachable",
            "can't connect",
            "cannot connect",
            "no route to host",
            "name or service not known",
            "temporary failure in name resolution",
            "unknown mysql server host",
        )
    )


def _summarize_root_cause(lowered: str, original: str) -> str:
    for marker in (
        "connection refused",
        "network is unreachable",
        "no route to host",
        "access denied",
        "unknown mysql server host",
        "temporary failure in name resolution",
        "name or service not known",
    ):
        if marker in lowered:
            return marker
    return original.strip() or "unknown MySQL error"


def _stage_timeout_seconds(stage: str, config: MySQLConnectionConfig) -> float:
    if stage == "connect":
        return config.connect_timeout_seconds
    if stage == "read":
        return config.read_timeout_seconds
    return config.write_timeout_seconds
