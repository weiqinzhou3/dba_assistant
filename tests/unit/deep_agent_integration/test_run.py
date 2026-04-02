from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.deep_agent_integration import run as run_module
from dba_assistant.deep_agent_integration.config import AppConfig, ModelConfig, ProviderKind


def test_run_phase2_loads_config_builds_agent_and_returns_final_output(monkeypatch) -> None:
    model_config = ModelConfig(
        preset_name="dashscope_cn_qwen35_flash",
        provider_kind=ProviderKind.OPENAI_COMPATIBLE,
        model_name="qwen3.5-flash",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="sk-cn",
        api_key_env="DASHSCOPE_API_KEY",
        temperature=0.0,
        max_turns=4,
        tracing_disabled=True,
    )
    config = AppConfig(
        model=model_config,
        redis=RedisConnectionConfig(host="redis.example", port=6380, db=7),
    )

    build_calls: list[object] = []
    run_calls: dict[str, object] = {}

    def fake_load_app_config():
        build_calls.append("load_app_config")
        return config

    def fake_build_phase2_agent(loaded_config, redis_adaptor=None):
        build_calls.append(("build_phase2_agent", loaded_config, redis_adaptor))
        return "fake-agent"

    def fake_run_sync(starting_agent, input, *, max_turns=10, **kwargs):
        run_calls["starting_agent"] = starting_agent
        run_calls["input"] = input
        run_calls["max_turns"] = max_turns
        run_calls["kwargs"] = kwargs

        class Result:
            final_output = {"summary": "phase2 ok"}

        return Result()

    monkeypatch.setattr(run_module, "load_app_config", fake_load_app_config)
    monkeypatch.setattr(run_module, "build_phase2_agent", fake_build_phase2_agent)
    monkeypatch.setattr(run_module.Runner, "run_sync", fake_run_sync)

    assert run_module.run_phase2() == "{'summary': 'phase2 ok'}"
    assert build_calls == [
        "load_app_config",
        ("build_phase2_agent", config, None),
    ]
    assert run_calls == {
        "starting_agent": "fake-agent",
        "input": run_module.DEFAULT_PROMPT,
        "max_turns": 4,
        "kwargs": {},
    }
