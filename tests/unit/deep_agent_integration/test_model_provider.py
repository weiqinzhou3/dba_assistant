import pytest

from dba_assistant.deep_agent_integration.config import ModelConfig, ProviderKind
from dba_assistant.deep_agent_integration import model_provider


def test_build_model_uses_chat_openai_for_openai_compatible_provider(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs) -> None:
            calls["kwargs"] = kwargs

    monkeypatch.setattr(model_provider, "ChatOpenAI", FakeChatOpenAI)

    config = ModelConfig(
        preset_name="dashscope_cn_qwen35_flash",
        provider_kind=ProviderKind.OPENAI_COMPATIBLE,
        model_name="qwen3.5-flash",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="sk-cn",
        temperature=0.2,
        tracing_disabled=True,
    )

    result = model_provider.build_model(config)

    assert calls["kwargs"] == {
        "model": "qwen3.5-flash",
        "api_key": "sk-cn",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "temperature": 0.2,
        "stream_usage": False,
    }
    assert isinstance(result, FakeChatOpenAI)


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
