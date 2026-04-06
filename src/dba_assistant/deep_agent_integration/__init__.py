"""Repository-owned Deep Agents SDK assembly layer for DBA Assistant."""

from dba_assistant.deep_agent_integration.agent_factory import build_phase2_agent
from dba_assistant.deep_agent_integration.config import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    ModelConfig,
    ObservabilityConfig,
    ProviderKind,
    REPO_ROOT,
    RuntimeConfig,
    load_app_config,
)
from dba_assistant.deep_agent_integration.model_provider import build_model
from dba_assistant.deep_agent_integration.tool_registry import build_redis_tools

DEFAULT_PROMPT = (
    "Validate the Phase 2 Deep Agents SDK assembly. "
    "Use only read-only Redis tools, summarize the structured findings, and stay within the Phase 2 scope."
)


def run_phase2(prompt: str = DEFAULT_PROMPT) -> str:
    from dba_assistant.deep_agent_integration.run import run_phase2 as _run_phase2

    return _run_phase2(prompt)


def main() -> int:
    from dba_assistant.deep_agent_integration.run import main as _main

    return _main()


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "AppConfig",
    "DEFAULT_PROMPT",
    "build_model",
    "build_phase2_agent",
    "build_redis_tools",
    "ModelConfig",
    "ObservabilityConfig",
    "ProviderKind",
    "REPO_ROOT",
    "RuntimeConfig",
    "main",
    "load_app_config",
    "run_phase2",
]
