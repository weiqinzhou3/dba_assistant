from __future__ import annotations

from collections.abc import Callable

from agents import function_tool

from dba_assistant.adaptors.redis_adaptor import DEFAULT_CONFIG_PATTERN, DEFAULT_SLOWLOG_LENGTH, RedisAdaptor, RedisConnectionConfig


def build_redis_tools(
    connection: RedisConnectionConfig,
    adaptor: RedisAdaptor | None = None,
) -> list:
    redis_adaptor = adaptor or RedisAdaptor()

    return [
        function_tool(
            _make_ping_tool(redis_adaptor, connection),
            name_override="redis_ping",
            description_override="Ping Redis and return a structured availability payload.",
        ),
        function_tool(
            _make_info_tool(redis_adaptor, connection),
            name_override="redis_info",
            description_override="Return read-only Redis INFO data in structured form.",
        ),
        function_tool(
            _make_config_get_tool(redis_adaptor, connection),
            name_override="redis_config_get",
            description_override="Return the bounded Phase 2 Redis CONFIG GET probe.",
        ),
        function_tool(
            _make_slowlog_get_tool(redis_adaptor, connection),
            name_override="redis_slowlog_get",
            description_override="Return the bounded Phase 2 Redis SLOWLOG GET probe.",
        ),
        function_tool(
            _make_client_list_tool(redis_adaptor, connection),
            name_override="redis_client_list",
            description_override="Return structured Redis client-list metadata.",
        ),
    ]


def _make_ping_tool(
    adaptor: RedisAdaptor,
    connection: RedisConnectionConfig,
) -> Callable[[], dict[str, object]]:
    def redis_ping() -> dict[str, object]:
        return adaptor.ping(connection)

    return redis_ping


def _make_info_tool(
    adaptor: RedisAdaptor,
    connection: RedisConnectionConfig,
) -> Callable[..., dict[str, object]]:
    def redis_info(section: str | None = None) -> dict[str, object]:
        return adaptor.info(connection, section=section)

    return redis_info


def _make_config_get_tool(
    adaptor: RedisAdaptor,
    connection: RedisConnectionConfig,
) -> Callable[[], dict[str, object]]:
    def redis_config_get() -> dict[str, object]:
        return adaptor.config_get(connection, pattern=DEFAULT_CONFIG_PATTERN)

    return redis_config_get


def _make_slowlog_get_tool(
    adaptor: RedisAdaptor,
    connection: RedisConnectionConfig,
) -> Callable[[], dict[str, object]]:
    def redis_slowlog_get() -> dict[str, object]:
        return adaptor.slowlog_get(connection, length=DEFAULT_SLOWLOG_LENGTH)

    return redis_slowlog_get


def _make_client_list_tool(
    adaptor: RedisAdaptor,
    connection: RedisConnectionConfig,
) -> Callable[[], dict[str, object]]:
    def redis_client_list() -> dict[str, object]:
        return adaptor.client_list(connection)

    return redis_client_list
