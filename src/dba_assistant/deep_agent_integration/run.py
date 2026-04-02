from __future__ import annotations

from agents import Runner

from dba_assistant.deep_agent_integration.agent_factory import build_phase2_agent
from dba_assistant.deep_agent_integration.config import load_app_config
from dba_assistant.deep_agent_integration import DEFAULT_PROMPT


def run_phase2(prompt: str = DEFAULT_PROMPT) -> str:
    config = load_app_config()
    agent = build_phase2_agent(config)
    result = Runner.run_sync(agent, prompt, max_turns=config.model.max_turns)
    return str(result.final_output)


def main() -> int:
    print(run_phase2())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
