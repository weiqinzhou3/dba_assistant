from __future__ import annotations

from agents import Runner

from dba_assistant.deep_agent_integration.agent_factory import build_phase2_agent
from dba_assistant.deep_agent_integration.config import load_app_config


DEFAULT_PROMPT = (
    "Validate the Phase 2 Deep Agent SDK assembly. "
    "Use only read-only Redis tools, summarize the structured findings, and stay within the Phase 2 scope."
)


def run_phase2(prompt: str = DEFAULT_PROMPT) -> str:
    config = load_app_config()
    agent = build_phase2_agent(config)
    result = Runner.run_sync(agent, prompt, max_turns=config.model.max_turns)
    return str(result.final_output)
