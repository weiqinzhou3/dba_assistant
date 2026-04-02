from __future__ import annotations

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.application.request_models import NormalizedRequest
from dba_assistant.deep_agent_integration.config import AppConfig
from dba_assistant.deep_agent_integration.run import run_phase2_request


def execute_request(request: NormalizedRequest, *, config: AppConfig) -> str:
    if not request.runtime_inputs.redis_host:
        raise ValueError("Phase 2 requires a Redis host in the normalized request.")

    redis_connection = RedisConnectionConfig(
        host=request.runtime_inputs.redis_host,
        port=request.runtime_inputs.redis_port,
        db=request.runtime_inputs.redis_db,
        password=request.secrets.redis_password,
        socket_timeout=config.runtime.redis_socket_timeout,
    )
    return run_phase2_request(
        request.prompt,
        config=config,
        redis_connection=redis_connection,
    )
