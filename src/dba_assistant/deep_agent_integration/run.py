from __future__ import annotations

from uuid import uuid4

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.application.prompt_parser import normalize_raw_request
from dba_assistant.deep_agent_integration import DEFAULT_PROMPT
from dba_assistant.deep_agent_integration.agent_factory import build_phase2_agent
from dba_assistant.deep_agent_integration.config import AppConfig, load_app_config
from dba_assistant.deep_agent_integration.runtime_support import extract_agent_output


def run_phase2_request(
    prompt: str,
    *,
    config: AppConfig,
    redis_connection: RedisConnectionConfig,
) -> str:
    agent = build_phase2_agent(config, redis_connection)
    result = agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"configurable": {"thread_id": f"phase2-{uuid4()}"}},
    )
    return extract_agent_output(result)


def run_phase2(prompt: str = DEFAULT_PROMPT) -> str:
    config = load_app_config()
    request = normalize_raw_request(
        prompt,
        default_output_mode=config.runtime.default_output_mode,
    )
    if request.runtime_inputs.redis_host is None:
        raise ValueError(
            "Phase 2 standalone runner requires a Redis target in the prompt. "
            "Use the main CLI (`dba-assistant ask <prompt>`) for unified Deep Agent orchestration."
        )
    return run_phase2_request(
        request.prompt,
        config=config,
        redis_connection=RedisConnectionConfig(
            host=request.runtime_inputs.redis_host,
            port=request.runtime_inputs.redis_port,
            db=request.runtime_inputs.redis_db,
            password=request.secrets.redis_password,
            socket_timeout=config.runtime.redis_socket_timeout,
        ),
    )


def main() -> int:
    print(run_phase2())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
