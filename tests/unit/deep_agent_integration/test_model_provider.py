import pytest

from dba_assistant.deep_agent_integration.config import ModelConfig, ProviderKind
from dba_assistant.deep_agent_integration import model_provider


def test_build_model_uses_async_openai_and_chat_completions(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *, api_key: str, base_url: str) -> None:
            calls["client"] = {"api_key": api_key, "base_url": base_url}

    class FakeModel:
        def __init__(self, *, model: str, openai_client: object) -> None:
            calls["model"] = {"model": model, "openai_client": openai_client}

    monkeypatch.setattr(model_provider, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(model_provider, "OpenAIChatCompletionsModel", FakeModel)
    monkeypatch.setattr(model_provider, "set_tracing_disabled", lambda disabled: calls.setdefault("tracing", disabled))

    config = ModelConfig(
        preset_name="dashscope_cn_qwen35_flash",
        provider_kind=ProviderKind.OPENAI_COMPATIBLE,
        model_name="qwen3.5-flash",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="sk-cn",
        tracing_disabled=True,
    )

    result = model_provider.build_model(config)

    assert calls["client"] == {
        "api_key": "sk-cn",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    }
    assert calls["model"]["model"] == "qwen3.5-flash"
    assert calls["tracing"] is True
    assert isinstance(result, FakeModel)


def test_build_model_rejects_unknown_provider_kind() -> None:
    config = ModelConfig(
        preset_name="bad",
        provider_kind="bad-provider",  # type: ignore[arg-type]
        model_name="bad-model",
        base_url="https://example.com/v1",
        api_key="sk-test",
    )

    with pytest.raises(ValueError, match="Unsupported provider kind"):
        model_provider.build_model(config)
