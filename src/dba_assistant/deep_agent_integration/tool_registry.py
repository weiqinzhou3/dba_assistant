from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from dba_assistant.adaptors.redis_adaptor import DEFAULT_CONFIG_PATTERN, DEFAULT_SLOWLOG_LENGTH, RedisAdaptor, RedisConnectionConfig


def build_redis_tools(
    connection: RedisConnectionConfig,
    adaptor: RedisAdaptor | None = None,
) -> list:
    redis_adaptor = adaptor or RedisAdaptor()
    return [
        _named_tool(
            _make_ping_tool(redis_adaptor, connection),
            "redis_ping",
            "Ping Redis and return a structured availability payload.",
        ),
        _named_tool(
            _make_info_tool(redis_adaptor, connection),
            "redis_info",
            "Return read-only Redis INFO data in structured form.",
        ),
        _named_tool(
            _make_config_get_tool(redis_adaptor, connection),
            "redis_config_get",
            "Return the bounded Phase 2 Redis CONFIG GET probe.",
        ),
        _named_tool(
            _make_slowlog_get_tool(redis_adaptor, connection),
            "redis_slowlog_get",
            "Return the bounded Phase 2 Redis SLOWLOG GET probe.",
        ),
        _named_tool(
            _make_client_list_tool(redis_adaptor, connection),
            "redis_client_list",
            "Return structured Redis client-list metadata.",
        ),
    ]


def build_phase3_tools() -> list:
    return [
        _named_tool(
            _make_analyze_rdb_tool(),
            "analyze_rdb",
            "Analyze local Redis RDB files and return structured Phase 3 results.",
        )
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


def _make_analyze_rdb_tool() -> Callable[..., object]:
    def analyze_rdb(prompt: str, input_paths: list[str]) -> object:
        from dba_assistant.tools.analyze_rdb import analyze_rdb_tool

        return analyze_rdb_tool(prompt=prompt, input_paths=[Path(path) for path in input_paths])

    return analyze_rdb


def _named_tool(func: Callable[..., object], name: str, description: str) -> Callable[..., object]:
    func.__name__ = name
    func.__doc__ = description
    return func
