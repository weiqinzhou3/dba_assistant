from __future__ import annotations

from dataclasses import dataclass, make_dataclass
from enum import Enum
import os

from dba_assistant.adaptors import redis_adaptor


class ProviderKind(str, Enum):
    OPENAI_COMPATIBLE = "openai_compatible"


try:
    from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
except ImportError:
    RedisConnectionConfig = make_dataclass(
        "RedisConnectionConfig",
        [
            ("host", str),
            ("port", int),
            ("db", int, 0),
            ("username", str | None, None),
            ("password", str | None, None),
            ("socket_timeout", float, 5.0),
        ],
        frozen=True,
    )
    redis_adaptor.RedisConnectionConfig = RedisConnectionConfig


@dataclass(frozen=True)
class ModelConfig:
    preset_name: str
    provider_kind: ProviderKind
    model_name: str
    base_url: str
    api_key: str
    api_key_env: str | None
    temperature: float = 0.0
    max_turns: int = 8
    tracing_disabled: bool = True


@dataclass(frozen=True)
class AppConfig:
    model: ModelConfig
    redis: RedisConnectionConfig


DEFAULT_MODEL_PRESET = "dashscope_cn_qwen35_flash"
MODEL_PRESETS = {
    "dashscope_cn_qwen35_flash": {
        "provider_kind": ProviderKind.OPENAI_COMPATIBLE,
        "model_name": "qwen3.5-flash",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "default_api_key": "",
    },
    "dashscope_intl_qwen35_flash_free": {
        "provider_kind": ProviderKind.OPENAI_COMPATIBLE,
        "model_name": "qwen3.5-flash",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "default_api_key": "",
    },
    "ollama_local": {
        "provider_kind": ProviderKind.OPENAI_COMPATIBLE,
        "model_name": "qwen3:8b",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key_env": None,
        "default_api_key": "ollama",
    },
}


def load_app_config() -> AppConfig:
    return AppConfig(
        model=load_model_config(),
        redis=load_redis_connection_config(),
    )


def load_model_config() -> ModelConfig:
    preset_name = os.getenv("DBA_MODEL_PRESET", DEFAULT_MODEL_PRESET)
    if preset_name == "custom_openai_compatible":
        return _load_custom_openai_compatible()

    if preset_name not in MODEL_PRESETS:
        raise ValueError(f"Unsupported DBA_MODEL_PRESET: {preset_name}")

    preset = MODEL_PRESETS[preset_name]
    api_key_env = os.getenv("DBA_MODEL_API_KEY_ENV") or preset["api_key_env"]
    api_key = os.getenv("DBA_MODEL_API_KEY")
    if not api_key and api_key_env:
        api_key = os.getenv(api_key_env)
    if not api_key:
        api_key = preset["default_api_key"]

    if not api_key:
        raise ValueError(f"Missing API key for preset {preset_name}. Set {api_key_env}.")

    return ModelConfig(
        preset_name=preset_name,
        provider_kind=preset["provider_kind"],
        model_name=os.getenv("DBA_MODEL_NAME", preset["model_name"]),
        base_url=os.getenv("DBA_MODEL_BASE_URL", preset["base_url"]),
        api_key=api_key,
        api_key_env=api_key_env,
        temperature=float(os.getenv("DBA_MODEL_TEMPERATURE", "0.0")),
        max_turns=int(os.getenv("DBA_MODEL_MAX_TURNS", "8")),
        tracing_disabled=_read_bool("DBA_MODEL_TRACING_DISABLED", default=True),
    )


def _load_custom_openai_compatible() -> ModelConfig:
    base_url = os.getenv("DBA_MODEL_BASE_URL")
    model_name = os.getenv("DBA_MODEL_NAME")
    api_key_env = os.getenv("DBA_MODEL_API_KEY_ENV")
    api_key = os.getenv("DBA_MODEL_API_KEY")

    if not base_url:
        raise ValueError("DBA_MODEL_BASE_URL is required for custom_openai_compatible.")
    if not model_name:
        raise ValueError("DBA_MODEL_NAME is required for custom_openai_compatible.")
    if not api_key and api_key_env:
        api_key = os.getenv(api_key_env)
    if not api_key:
        raise ValueError("DBA_MODEL_API_KEY or DBA_MODEL_API_KEY_ENV is required for custom_openai_compatible.")

    return ModelConfig(
        preset_name="custom_openai_compatible",
        provider_kind=ProviderKind.OPENAI_COMPATIBLE,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        api_key_env=api_key_env,
        temperature=float(os.getenv("DBA_MODEL_TEMPERATURE", "0.0")),
        max_turns=int(os.getenv("DBA_MODEL_MAX_TURNS", "8")),
        tracing_disabled=_read_bool("DBA_MODEL_TRACING_DISABLED", default=True),
    )


def load_redis_connection_config() -> RedisConnectionConfig:
    return RedisConnectionConfig(
        host=os.getenv("DBA_REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("DBA_REDIS_PORT", "6379")),
        db=int(os.getenv("DBA_REDIS_DB", "0")),
        username=os.getenv("DBA_REDIS_USERNAME") or None,
        password=os.getenv("DBA_REDIS_PASSWORD") or None,
        socket_timeout=float(os.getenv("DBA_REDIS_SOCKET_TIMEOUT", "5.0")),
    )


def _read_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
