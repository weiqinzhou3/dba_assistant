from dba_assistant.application.request_models import NormalizedRequest, RuntimeInputs, Secrets
from dba_assistant.application.service import execute_request
from dba_assistant.deep_agent_integration.config import AppConfig, ModelConfig, ProviderKind, RuntimeConfig


def test_execute_request_builds_redis_connection_and_calls_phase2_runner(monkeypatch) -> None:
    captured: dict[str, object] = {}

    config = AppConfig(
        model=ModelConfig(
            preset_name="ollama_local",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3:8b",
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
        ),
        runtime=RuntimeConfig(default_output_mode="summary", redis_socket_timeout=6.0),
    )

    request = NormalizedRequest(
        raw_prompt="Use password abc123 to inspect Redis 10.0.0.8:6380 db 2 and give me a summary",
        prompt="Use to inspect Redis 10.0.0.8:6380 db 2 and give me a summary",
        runtime_inputs=RuntimeInputs(redis_host="10.0.0.8", redis_port=6380, redis_db=2, output_mode="summary"),
        secrets=Secrets(redis_password="abc123"),
    )

    def fake_run_phase2_request(prompt, *, config, redis_connection):
        captured["prompt"] = prompt
        captured["config"] = config
        captured["redis_connection"] = redis_connection
        return "phase2 ok"

    monkeypatch.setattr("dba_assistant.application.service.run_phase2_request", fake_run_phase2_request)

    assert execute_request(request, config=config) == "phase2 ok"
    assert captured["prompt"] == "Use to inspect Redis 10.0.0.8:6380 db 2 and give me a summary"
    assert captured["redis_connection"].host == "10.0.0.8"
    assert captured["redis_connection"].port == 6380
    assert captured["redis_connection"].db == 2
    assert captured["redis_connection"].password == "abc123"
    assert captured["redis_connection"].socket_timeout == 6.0
