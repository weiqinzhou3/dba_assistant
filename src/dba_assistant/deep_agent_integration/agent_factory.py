from __future__ import annotations

from deepagents import create_deep_agent

from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig
from dba_assistant.deep_agent_integration.config import AppConfig
from dba_assistant.deep_agent_integration.model_provider import build_model
from dba_assistant.deep_agent_integration.runtime_support import (
    build_runtime_backend,
    build_runtime_checkpointer,
    get_memory_sources,
    get_skill_sources,
)
from dba_assistant.deep_agent_integration.tool_registry import build_redis_tools


def build_phase2_agent(
    config: AppConfig,
    redis_connection: RedisConnectionConfig,
    redis_adaptor: RedisAdaptor | None = None,
) -> object:
    model = build_model(config.model)
    tools = build_redis_tools(redis_connection, adaptor=redis_adaptor)
    backend = build_runtime_backend()
    checkpointer = build_runtime_checkpointer()

    return create_deep_agent(
        name="dba-assistant-phase2",
        model=model,
        tools=tools,
        backend=backend,
        checkpointer=checkpointer,
        skills=get_skill_sources(),
        memory=get_memory_sources(),
        system_prompt=(
            "You are the Phase 2 integration-validation agent for DBA Assistant. "
            "Use only the provided read-only Redis tools. "
            "Do not attempt writes, destructive actions, SSH, MySQL, or custom runtime behavior. "
            "Summarize the structured tool outputs plainly."
        ),
    )
