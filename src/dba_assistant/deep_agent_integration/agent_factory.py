from __future__ import annotations

from agents import Agent, ModelSettings

from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig
from dba_assistant.deep_agent_integration.config import AppConfig
from dba_assistant.deep_agent_integration.model_provider import build_model
from dba_assistant.deep_agent_integration.tool_registry import build_redis_tools


def build_phase2_agent(
    config: AppConfig,
    redis_connection: RedisConnectionConfig,
    redis_adaptor: RedisAdaptor | None = None,
) -> Agent:
    model = build_model(config.model)
    tools = build_redis_tools(redis_connection, adaptor=redis_adaptor)

    return Agent(
        name="dba-assistant-phase2",
        instructions=(
            "You are the Phase 2 integration-validation agent for DBA Assistant. "
            "Use only the provided read-only Redis tools. "
            "Do not attempt writes, destructive actions, SSH, MySQL, or custom runtime behavior. "
            "Summarize the structured tool outputs plainly."
        ),
        model=model,
        tools=tools,
        model_settings=ModelSettings(temperature=config.model.temperature),
    )
