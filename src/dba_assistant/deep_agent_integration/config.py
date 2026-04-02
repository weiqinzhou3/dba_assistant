from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("config/config.yaml")

SUPPORTED_PRESET_NAMES = frozenset(
    {
        "dashscope_cn",
        "dashscope_cn_qwen35_flash",
        "dashscope_intl",
        "dashscope_intl_qwen35_flash_free",
        "ollama_local",
        "custom_openai_compatible",
    }
)


class ProviderKind(str, Enum):
    OPENAI_COMPATIBLE = "openai_compatible"


@dataclass(frozen=True)
class ModelConfig:
    preset_name: str
    provider_kind: ProviderKind
    model_name: str
    base_url: str
    api_key: str
    temperature: float = 0.0
    max_turns: int = 8
    tracing_disabled: bool = True


@dataclass(frozen=True)
class RuntimeConfig:
    default_output_mode: str = "summary"
    redis_socket_timeout: float = 5.0


@dataclass(frozen=True)
class AppConfig:
    model: ModelConfig
    runtime: RuntimeConfig


def load_app_config(config_path: str | Path | None = None) -> AppConfig:
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    document = _load_yaml_document(path)
    return AppConfig(
        model=_load_model_config(_require_mapping(document, "model")),
        runtime=_load_runtime_config(_require_mapping(document, "runtime")),
    )


def _load_yaml_document(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Config file must contain a mapping at the document root: {path}")
    return loaded


def _load_model_config(data: dict[str, Any]) -> ModelConfig:
    preset_name = _require_string(data, "preset_name", "model")
    if preset_name not in SUPPORTED_PRESET_NAMES:
        supported = ", ".join(sorted(SUPPORTED_PRESET_NAMES))
        raise ValueError(f"Unsupported model.preset_name: {preset_name}. Supported presets: {supported}.")

    provider_kind = ProviderKind(_require_string(data, "provider_kind", "model"))
    api_key = _require_string(data, "api_key", "model")

    return ModelConfig(
        preset_name=preset_name,
        provider_kind=provider_kind,
        model_name=_require_string(data, "model_name", "model"),
        base_url=_require_string(data, "base_url", "model"),
        api_key=api_key,
        temperature=float(data.get("temperature", 0.0)),
        max_turns=int(data.get("max_turns", 8)),
        tracing_disabled=bool(data.get("tracing_disabled", True)),
    )


def _load_runtime_config(data: dict[str, Any]) -> RuntimeConfig:
    return RuntimeConfig(
        default_output_mode=_require_string(data, "default_output_mode", "runtime"),
        redis_socket_timeout=float(data.get("redis_socket_timeout", 5.0)),
    )


def _require_mapping(document: dict[str, Any], field: str) -> dict[str, Any]:
    value = document.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"Config section {field} must be a mapping.")
    return value


def _require_string(data: dict[str, Any], field: str, section: str) -> str:
    value = data.get(field)
    if value is None:
        raise ValueError(f"Config field {section}.{field} is required.")

    value = str(value).strip()
    if not value:
        raise ValueError(f"Config field {section}.{field} is required.")

    return value
