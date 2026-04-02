import pytest

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig as SharedRedisConnectionConfig
from dba_assistant.deep_agent_integration.config import (
    DEFAULT_MODEL_PRESET,
    ProviderKind,
    load_app_config,
)


@pytest.fixture(autouse=True)
def clear_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DASHSCOPE_API_KEY",
        "DBA_MODEL_PRESET",
        "DBA_MODEL_NAME",
        "DBA_MODEL_BASE_URL",
        "DBA_MODEL_API_KEY",
        "DBA_MODEL_API_KEY_ENV",
        "DBA_MODEL_TEMPERATURE",
        "DBA_MODEL_MAX_TURNS",
        "DBA_MODEL_TRACING_DISABLED",
        "DBA_REDIS_HOST",
        "DBA_REDIS_PORT",
        "DBA_REDIS_DB",
        "DBA_REDIS_USERNAME",
        "DBA_REDIS_PASSWORD",
        "DBA_REDIS_SOCKET_TIMEOUT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_load_app_config_uses_dashscope_cn_preset_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-cn")
    monkeypatch.setenv("DBA_MODEL_NAME", "   ")
    monkeypatch.setenv("DBA_MODEL_BASE_URL", " \t ")

    config = load_app_config()

    assert DEFAULT_MODEL_PRESET == "dashscope_cn_qwen35_flash"
    assert config.model.provider_kind is ProviderKind.OPENAI_COMPATIBLE
    assert config.model.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert config.model.model_name == "qwen3.5-flash"
    assert config.model.api_key == "sk-cn"
    assert config.redis.host == "127.0.0.1"
    assert config.redis.port == 6379
    assert isinstance(config.redis, SharedRedisConnectionConfig)
    assert config.redis.__class__ is SharedRedisConnectionConfig


def test_load_app_config_supports_ollama_without_external_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DBA_MODEL_PRESET", "ollama_local")
    monkeypatch.setenv("DBA_MODEL_NAME", "qwen3:8b")

    config = load_app_config()

    assert config.model.base_url == "http://127.0.0.1:11434/v1"
    assert config.model.model_name == "qwen3:8b"
    assert config.model.api_key == "ollama"


def test_custom_openai_compatible_requires_base_url_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DBA_MODEL_PRESET", "custom_openai_compatible")
    monkeypatch.setenv("DBA_MODEL_API_KEY", "sk-custom")
    monkeypatch.setenv("DBA_MODEL_BASE_URL", "   ")

    with pytest.raises(ValueError, match="DBA_MODEL_BASE_URL"):
        load_app_config()


def test_custom_openai_compatible_requires_model_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DBA_MODEL_PRESET", "custom_openai_compatible")
    monkeypatch.setenv("DBA_MODEL_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("DBA_MODEL_API_KEY", "sk-custom")
    monkeypatch.setenv("DBA_MODEL_NAME", "   ")

    with pytest.raises(ValueError, match="DBA_MODEL_NAME"):
        load_app_config()
