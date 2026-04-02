from __future__ import annotations

from agents import Runner

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.application.prompt_parser import normalize_raw_request
from dba_assistant.deep_agent_integration import DEFAULT_PROMPT
from dba_assistant.deep_agent_integration.agent_factory import build_phase2_agent
from dba_assistant.deep_agent_integration.config import AppConfig, load_app_config


def run_phase2_request(
    prompt: str,
    *,
    config: AppConfig,
    redis_connection: RedisConnectionConfig,
) -> str:
    agent = build_phase2_agent(config, redis_connection)
    result = Runner.run_sync(agent, prompt, max_turns=config.model.max_turns)
    return str(result.final_output)


def run_phase2(prompt: str = DEFAULT_PROMPT) -> str:
    config = load_app_config()
    request = normalize_raw_request(
        prompt,
        default_output_mode=config.runtime.default_output_mode,
    )
    from dba_assistant.application.service import execute_request

    return execute_request(request, config=config)


def main() -> int:
    print(run_phase2())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
