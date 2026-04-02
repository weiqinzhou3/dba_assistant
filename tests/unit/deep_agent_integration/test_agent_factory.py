from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.deep_agent_integration.agent_factory import build_phase2_agent
from dba_assistant.deep_agent_integration.config import AppConfig, ModelConfig, ProviderKind, RuntimeConfig


def test_build_phase2_agent_wires_model_tools_and_read_only_instructions(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def fake_build_model(model_config):
        calls["build_model"] = model_config
        return "fake-model"

    def fake_build_redis_tools(connection, adaptor=None):
        calls["build_redis_tools"] = {"connection": connection, "adaptor": adaptor}
        return ["redis_ping", "redis_info"]

    monkeypatch.setattr("dba_assistant.deep_agent_integration.agent_factory.build_model", fake_build_model)
    monkeypatch.setattr("dba_assistant.deep_agent_integration.agent_factory.build_redis_tools", fake_build_redis_tools)

    config = AppConfig(
        model=ModelConfig(
            preset_name="ollama_local",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3:8b",
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
            temperature=0.2,
        ),
        runtime=RuntimeConfig(default_output_mode="summary", redis_socket_timeout=5.0),
    )
    connection = RedisConnectionConfig(host="redis.example", port=6380, db=7)

    agent = build_phase2_agent(config, connection, redis_adaptor="fake-adaptor")

    assert calls["build_model"] is config.model
    assert calls["build_redis_tools"] == {"connection": connection, "adaptor": "fake-adaptor"}
    assert agent.name == "dba-assistant-phase2"
    assert agent.model == "fake-model"
    assert agent.tools == ["redis_ping", "redis_info"]
    assert agent.model_settings.temperature == 0.2
    assert "read-only" in agent.instructions.lower()
