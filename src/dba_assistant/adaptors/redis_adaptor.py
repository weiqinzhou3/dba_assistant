"""Redis adaptor for read-only inspection access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from redis import Redis
from redis.exceptions import AuthenticationError, ConnectionError, RedisError, TimeoutError


DEFAULT_CONFIG_PATTERN = "maxmemory*"
ALLOWED_CONFIG_PATTERNS = frozenset({DEFAULT_CONFIG_PATTERN, "dir", "dbfilename"})
DEFAULT_SLOWLOG_LENGTH = 5
MAX_SLOWLOG_LENGTH = 5


@dataclass(frozen=True)
class RedisConnectionConfig:
    host: str
    port: int = 6379
    db: int = 0
    username: str | None = None
    password: str | None = None
    socket_timeout: float = 5.0


class RedisAdaptor:
    def __init__(self, client_factory: Callable[..., Any] = Redis) -> None:
        self._client_factory = client_factory

    def ping(self, connection: RedisConnectionConfig) -> dict[str, Any]:
        return self._run_read_only_probe(
            connection,
            callback=lambda client: client.ping(),
            formatter=lambda payload: {"ok": bool(payload)},
        )

    def info(
        self,
        connection: RedisConnectionConfig,
        *,
        section: str | None = None,
    ) -> dict[str, Any]:
        return self._run_read_only_probe(
            connection,
            callback=lambda client: client.info(section=section),
            formatter=lambda payload: dict(payload),
        )

    def config_get(
        self,
        connection: RedisConnectionConfig,
        *,
        pattern: str = DEFAULT_CONFIG_PATTERN,
    ) -> dict[str, Any]:
        self._validate_config_pattern(pattern)
        return self._run_structured_probe(
            connection,
            metadata={"pattern": pattern},
            callback=lambda client: client.config_get(pattern),
            formatter=lambda data: {"data": dict(data)},
        )

    def slowlog_get(
        self,
        connection: RedisConnectionConfig,
        *,
        length: int = DEFAULT_SLOWLOG_LENGTH,
    ) -> dict[str, Any]:
        self._validate_slowlog_length(length)
        return self._run_structured_probe(
            connection,
            metadata={"requested_length": length},
            callback=lambda client: client.slowlog_get(length),
            formatter=lambda data: {
                "count": len(data),
                "entries": [self._summarize_slowlog_entry(entry) for entry in data],
            },
        )

    def client_list(self, connection: RedisConnectionConfig) -> dict[str, Any]:
        return self._run_structured_probe(
            connection,
            metadata={},
            callback=lambda client: client.client_list(),
            formatter=lambda data: {"count": len(data)},
        )

    def _connect(self, connection: RedisConnectionConfig) -> Any:
        return self._client_factory(
            host=connection.host,
            port=connection.port,
            db=connection.db,
            username=connection.username,
            password=connection.password,
            socket_timeout=connection.socket_timeout,
            decode_responses=True,
        )

    def _run(self, connection: RedisConnectionConfig, callback: Callable[[Any], Any]) -> Any:
        client = self._connect(connection)
        try:
            return callback(client)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    def _run_structured_probe(
        self,
        connection: RedisConnectionConfig,
        *,
        metadata: dict[str, Any],
        callback: Callable[[Any], Any],
        formatter: Callable[[Any], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            payload = self._run(connection, callback)
        except AuthenticationError as error:
            return self._probe_unavailable(metadata, "authentication_failed", error)
        except ConnectionError as error:
            return self._probe_unavailable(metadata, "connection_failed", error)
        except TimeoutError as error:
            return self._probe_unavailable(metadata, "timeout_failed", error)
        except PermissionError as error:
            return self._probe_unavailable(metadata, "permission_denied", error)
        except RedisError as error:
            kind = self._classify_admin_error(error)
            if kind is None:
                raise
            return self._probe_unavailable(metadata, kind, error)

        return {"available": True, **metadata, **formatter(payload)}

    def _run_read_only_probe(
        self,
        connection: RedisConnectionConfig,
        *,
        callback: Callable[[Any], Any],
        formatter: Callable[[Any], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            payload = self._run(connection, callback)
        except AuthenticationError as error:
            return self._probe_unavailable({}, "authentication_failed", error)
        except ConnectionError as error:
            return self._probe_unavailable({}, "connection_failed", error)
        except TimeoutError as error:
            return self._probe_unavailable({}, "timeout_failed", error)

        return formatter(payload)

    def _probe_unavailable(
        self,
        metadata: dict[str, Any],
        kind: str,
        error: BaseException,
    ) -> dict[str, Any]:
        return {
            "available": False,
            **metadata,
            "error": {"kind": kind, "message": str(error)},
        }

    def _classify_admin_error(self, error: RedisError) -> str | None:
        message = str(error).lower()
        if "noperm" in message or "permission" in message:
            return "permission_denied"
        if "unknown command" in message or "disabled" in message:
            return "command_unavailable"
        return None

    def _summarize_slowlog_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        if "id" in entry:
            summary["id"] = entry["id"]
        if "duration" in entry:
            summary["duration"] = entry["duration"]

        command = entry.get("command")
        if isinstance(command, str) and command:
            summary["command"] = command.split()[0].upper()

        return summary

    def _validate_config_pattern(self, pattern: str) -> None:
        if pattern not in ALLOWED_CONFIG_PATTERNS:
            raise ValueError(
                f"Phase 2 config pattern must be one of {sorted(ALLOWED_CONFIG_PATTERNS)}."
            )

    def _validate_slowlog_length(self, length: int) -> None:
        if not 1 <= length <= MAX_SLOWLOG_LENGTH:
            raise ValueError(
                f"Phase 2 slowlog length must be between 1 and {MAX_SLOWLOG_LENGTH}."
            )
