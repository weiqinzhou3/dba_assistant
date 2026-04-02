from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.deep_agent_integration.agent_factory import build_phase2_agent
from dba_assistant.deep_agent_integration.config import AppConfig, ModelConfig, ProviderKind


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

    model_config = ModelConfig(
        preset_name="dashscope_cn_qwen35_flash",
        provider_kind=ProviderKind.OPENAI_COMPATIBLE,
        model_name="qwen3.5-flash",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="sk-cn",
        api_key_env="DASHSCOPE_API_KEY",
        temperature=0.2,
        max_turns=6,
        tracing_disabled=True,
    )
    redis_config = RedisConnectionConfig(host="redis.example", port=6380, db=7)
    config = AppConfig(model=model_config, redis=redis_config)

    agent = build_phase2_agent(config, redis_adaptor="fake-adaptor")

    assert calls["build_model"] is model_config
    assert calls["build_redis_tools"] == {"connection": redis_config, "adaptor": "fake-adaptor"}
    assert agent.name == "dba-assistant-phase2"
    assert agent.model == "fake-model"
    assert agent.tools == ["redis_ping", "redis_info"]
    assert agent.model_settings.temperature == 0.2
    assert "read-only" in agent.instructions.lower()
    assert "redis" in agent.instructions.lower()
    assert "write" in agent.instructions.lower()
