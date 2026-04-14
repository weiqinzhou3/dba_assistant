from __future__ import annotations

from typing import Any, Callable

from dba_assistant.adaptors.redis_adaptor import (
    DEFAULT_CONFIG_PATTERN,
    DEFAULT_SLOWLOG_LENGTH,
    RedisAdaptor,
)
from dba_assistant.orchestrator.tool_helpers import named_tool


def make_redis_inspection_tools(
    context: Any,
    adaptor: RedisAdaptor,
    *,
    resolve_connection: Callable[..., tuple[Any, Any]],
) -> list:
    """Build the read-only Redis inspection tools."""

    def redis_ping(
        redis_host: str = "",
        redis_port: int | None = None,
        redis_db: int | None = None,
    ) -> dict[str, object]:
        _, connection = resolve_connection(
            context,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
        )
        return adaptor.ping(connection)

    def redis_info(
        section: str | None = None,
        redis_host: str = "",
        redis_port: int | None = None,
        redis_db: int | None = None,
    ) -> dict[str, object]:
        _, connection = resolve_connection(
            context,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
        )
        return adaptor.info(connection, section=section)

    def redis_config_get(
        redis_host: str = "",
        redis_port: int | None = None,
        redis_db: int | None = None,
    ) -> dict[str, object]:
        _, connection = resolve_connection(
            context,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
        )
        return adaptor.config_get(connection, pattern=DEFAULT_CONFIG_PATTERN)

    def redis_slowlog_get(
        redis_host: str = "",
        redis_port: int | None = None,
        redis_db: int | None = None,
    ) -> dict[str, object]:
        _, connection = resolve_connection(
            context,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
        )
        return adaptor.slowlog_get(connection, length=DEFAULT_SLOWLOG_LENGTH)

    def redis_client_list(
        redis_host: str = "",
        redis_port: int | None = None,
        redis_db: int | None = None,
    ) -> dict[str, object]:
        _, connection = resolve_connection(
            context,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
        )
        return adaptor.client_list(connection)

    return [
        named_tool(
            redis_ping,
            "redis_ping",
            "Ping Redis and return availability status. Parameters: redis_host, redis_port, redis_db.",
        ),
        named_tool(
            redis_info,
            "redis_info",
            "Return read-only Redis INFO data. Parameters: section, redis_host, redis_port, redis_db.",
        ),
        named_tool(
            redis_config_get,
            "redis_config_get",
            "Return bounded Redis CONFIG GET probe (maxmemory, dir, dbfilename). Parameters: redis_host, redis_port, redis_db.",
        ),
        named_tool(
            redis_slowlog_get,
            "redis_slowlog_get",
            "Return bounded Redis SLOWLOG GET entries. Parameters: redis_host, redis_port, redis_db.",
        ),
        named_tool(
            redis_client_list,
            "redis_client_list",
            "Return Redis client-list count. Parameters: redis_host, redis_port, redis_db.",
        ),
    ]
