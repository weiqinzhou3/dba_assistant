import asyncio

from agents.tool import ToolContext

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.deep_agent_integration.tool_registry import build_redis_tools


class FakeRedisAdaptor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, RedisConnectionConfig, dict[str, object]]] = []

    def ping(self, connection: RedisConnectionConfig) -> dict[str, bool]:
        self.calls.append(("ping", connection, {}))
        return {"ok": True}

    def info(self, connection: RedisConnectionConfig, *, section: str | None = None) -> dict[str, object]:
        self.calls.append(("info", connection, {"section": section}))
        return {"role": "master", "section": section}

    def config_get(self, connection: RedisConnectionConfig, *, pattern: str = "maxmemory*") -> dict[str, object]:
        self.calls.append(("config_get", connection, {"pattern": pattern}))
        return {"available": True, "pattern": pattern, "data": {"maxmemory": "0"}}

    def slowlog_get(self, connection: RedisConnectionConfig, *, length: int = 5) -> dict[str, object]:
        self.calls.append(("slowlog_get", connection, {"length": length}))
        return {"available": True, "requested_length": length, "count": 1, "entries": [{"id": 1}]}

    def client_list(self, connection: RedisConnectionConfig) -> dict[str, object]:
        self.calls.append(("client_list", connection, {}))
        return {"available": True, "count": 1}


async def _invoke(tool, payload: str) -> object:
    ctx = ToolContext(context=None, tool_name=tool.name, tool_call_id="call-1", tool_arguments=payload)
    return await tool.on_invoke_tool(ctx, payload)


def test_build_redis_tools_exposes_phase2_safe_tools_and_structured_outputs() -> None:
    connection = RedisConnectionConfig(host="redis.example", port=6380, db=7)
    adaptor = FakeRedisAdaptor()

    tools = build_redis_tools(connection, adaptor=adaptor)

    assert [tool.name for tool in tools] == [
        "redis_ping",
        "redis_info",
        "redis_config_get",
        "redis_slowlog_get",
        "redis_client_list",
    ]

    assert asyncio.run(_invoke(tools[0], "{}")) == {"ok": True}
    assert asyncio.run(_invoke(tools[1], '{"section": "memory"}')) == {"role": "master", "section": "memory"}
    assert asyncio.run(_invoke(tools[2], "{}")) == {
        "available": True,
        "pattern": "maxmemory*",
        "data": {"maxmemory": "0"},
    }
    assert asyncio.run(_invoke(tools[3], "{}")) == {
        "available": True,
        "requested_length": 5,
        "count": 1,
        "entries": [{"id": 1}],
    }
    assert asyncio.run(_invoke(tools[4], "{}")) == {"available": True, "count": 1}

    assert adaptor.calls == [
        ("ping", connection, {}),
        ("info", connection, {"section": "memory"}),
        ("config_get", connection, {"pattern": "maxmemory*"}),
        ("slowlog_get", connection, {"length": 5}),
        ("client_list", connection, {}),
    ]
