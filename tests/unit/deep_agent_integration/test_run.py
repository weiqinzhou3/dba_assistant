from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.deep_agent_integration import run as run_module
from dba_assistant.deep_agent_integration.config import AppConfig, ModelConfig, ProviderKind, RuntimeConfig


def test_run_phase2_request_uses_runner_and_returns_final_output(monkeypatch) -> None:
    config = AppConfig(
        model=ModelConfig(
            preset_name="ollama_local",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3:8b",
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
            max_turns=4,
        ),
        runtime=RuntimeConfig(default_output_mode="summary", redis_socket_timeout=5.0),
    )
    connection = RedisConnectionConfig(host="redis.example", port=6380, db=7)
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        run_module,
        "build_phase2_agent",
        lambda cfg, conn, redis_adaptor=None: ("agent", cfg, conn, redis_adaptor),
    )

    def fake_run_sync(starting_agent, input, *, max_turns=10, **kwargs):
        calls["starting_agent"] = starting_agent
        calls["input"] = input
        calls["max_turns"] = max_turns

        class Result:
            final_output = {"summary": "phase2 ok"}

        return Result()

    monkeypatch.setattr(run_module.Runner, "run_sync", fake_run_sync)

    result = run_module.run_phase2_request("inspect redis", config=config, redis_connection=connection)

    assert result == "{'summary': 'phase2 ok'}"
    assert calls["input"] == "inspect redis"
    assert calls["max_turns"] == 4


def test_main_prints_run_phase2_output(monkeypatch, capsys) -> None:
    monkeypatch.setattr(run_module, "run_phase2", lambda prompt=run_module.DEFAULT_PROMPT: "phase2 ok")

    assert run_module.main() == 0

    captured = capsys.readouterr()
    assert captured.out == "phase2 ok\n"
    assert captured.err == ""
