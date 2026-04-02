"""Redis adaptor for read-only inspection access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from redis import Redis


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

    def ping(self, connection: RedisConnectionConfig) -> dict[str, bool]:
        return {"ok": bool(self._run(connection, lambda client: client.ping()))}

    def info(
        self,
        connection: RedisConnectionConfig,
        *,
        section: str | None = None,
    ) -> dict[str, Any]:
        return dict(self._run(connection, lambda client: client.info(section=section)))

    def config_get(
        self,
        connection: RedisConnectionConfig,
        *,
        pattern: str = "*",
    ) -> dict[str, str]:
        return dict(self._run(connection, lambda client: client.config_get(pattern)))

    def slowlog_get(
        self,
        connection: RedisConnectionConfig,
        *,
        length: int = 10,
    ) -> list[dict[str, Any]]:
        return list(self._run(connection, lambda client: client.slowlog_get(length)))

    def client_list(self, connection: RedisConnectionConfig) -> list[dict[str, Any]]:
        return list(self._run(connection, lambda client: client.client_list()))

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
