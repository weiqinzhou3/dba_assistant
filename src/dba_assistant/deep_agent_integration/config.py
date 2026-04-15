from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from dba_assistant.core.runtime_paths import (
    DEFAULT_AGENT_WORKSPACE_ROOT,
    DEFAULT_ARTIFACT_DIR,
    DEFAULT_EVIDENCE_DIR,
    DEFAULT_TEMP_DIR,
    REPO_ROOT,
)

DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "config.yaml"
DEFAULT_MYSQL_STAGE_BATCH_SIZE = 2000

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
    mysql_stage_batch_size: int = DEFAULT_MYSQL_STAGE_BATCH_SIZE
    mysql_connect_timeout_seconds: float = 5.0
    mysql_read_timeout_seconds: float = 15.0
    mysql_write_timeout_seconds: float = 30.0
    cli_streaming: bool = False


@dataclass(frozen=True)
class FilesystemBackendConfig:
    kind: str = "filesystem"
    root_dir: Path = DEFAULT_AGENT_WORKSPACE_ROOT
    virtual_mode: bool = True


@dataclass(frozen=True)
class AgentConfig:
    filesystem_backend: FilesystemBackendConfig = field(default_factory=FilesystemBackendConfig)


@dataclass(frozen=True)
class PathsConfig:
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR
    temp_dir: Path = DEFAULT_TEMP_DIR


@dataclass(frozen=True)
class ObservabilityConfig:
    enabled: bool = True
    console_enabled: bool = True
    console_level: str = "WARNING"
    file_level: str = "INFO"
    log_dir: Path = REPO_ROOT / "outputs" / "logs"
    app_log_file: str = "app.log.jsonl"
    audit_log_file: str = "audit.jsonl"

    @property
    def app_log_path(self) -> Path:
        return self.log_dir / self.app_log_file

    @property
    def audit_log_path(self) -> Path:
        return self.log_dir / self.audit_log_file


@dataclass(frozen=True)
class AppConfig:
    model: ModelConfig
    runtime: RuntimeConfig
    agent: AgentConfig = field(default_factory=AgentConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)


def load_app_config(config_path: str | Path | None = None) -> AppConfig:
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    document = _load_yaml_document(path)
    agent = _load_agent_config(_optional_mapping(document, "agent"))
    return AppConfig(
        model=_load_model_config(_require_mapping(document, "model")),
        runtime=_load_runtime_config(_require_mapping(document, "runtime")),
        agent=agent,
        paths=_load_paths_config(_optional_mapping(document, "paths"), agent.filesystem_backend.root_dir),
        observability=_load_observability_config(_optional_mapping(document, "observability")),
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
        mysql_stage_batch_size=_require_positive_int(
            data.get("mysql_stage_batch_size", DEFAULT_MYSQL_STAGE_BATCH_SIZE),
            "runtime.mysql_stage_batch_size",
        ),
        mysql_connect_timeout_seconds=float(data.get("mysql_connect_timeout_seconds", 5.0)),
        mysql_read_timeout_seconds=float(data.get("mysql_read_timeout_seconds", 15.0)),
        mysql_write_timeout_seconds=float(data.get("mysql_write_timeout_seconds", 30.0)),
        cli_streaming=_optional_bool(data, "cli_streaming", False),
    )


def _load_agent_config(data: dict[str, Any] | None) -> AgentConfig:
    data = data or {}
    backend_data = data.get("filesystem_backend", {})
    if backend_data is None:
        backend_data = {}
    if not isinstance(backend_data, dict):
        raise ValueError("Config section agent.filesystem_backend must be a mapping.")
    kind = _optional_string(backend_data, "kind", "filesystem")
    if kind != "filesystem":
        raise ValueError("Config field agent.filesystem_backend.kind must be 'filesystem'.")
    return AgentConfig(
        filesystem_backend=FilesystemBackendConfig(
            kind=kind,
            root_dir=_resolve_repo_path(backend_data.get("root_dir", DEFAULT_AGENT_WORKSPACE_ROOT)),
            virtual_mode=_optional_bool(backend_data, "virtual_mode", True),
        )
    )


def _load_paths_config(data: dict[str, Any] | None, backend_root: Path) -> PathsConfig:
    data = data or {}
    return PathsConfig(
        artifact_dir=_resolve_repo_path(data.get("artifact_dir", backend_root / "artifacts")),
        evidence_dir=_resolve_repo_path(data.get("evidence_dir", backend_root / "evidence")),
        temp_dir=_resolve_repo_path(data.get("temp_dir", backend_root / "tmp")),
    )


def _load_observability_config(data: dict[str, Any] | None) -> ObservabilityConfig:
    data = data or {}
    legacy_level = _optional_string(data, "level", "").upper()
    return ObservabilityConfig(
        enabled=bool(data.get("enabled", True)),
        console_enabled=bool(data.get("console_enabled", True)),
        console_level=_optional_string(
            data,
            "console_level",
            legacy_level or "WARNING",
        ).upper(),
        file_level=_optional_string(
            data,
            "file_level",
            legacy_level or "INFO",
        ).upper(),
        log_dir=_resolve_repo_path(data.get("log_dir", "outputs/logs")),
        app_log_file=_optional_string(data, "app_log_file", "app.log.jsonl"),
        audit_log_file=_optional_string(data, "audit_log_file", "audit.jsonl"),
    )


def _require_mapping(document: dict[str, Any], field: str) -> dict[str, Any]:
    value = document.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"Config section {field} must be a mapping.")
    return value


def _optional_mapping(document: dict[str, Any], field: str) -> dict[str, Any] | None:
    value = document.get(field)
    if value is None:
        return None
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


def _optional_string(data: dict[str, Any], field: str, default: str) -> str:
    value = data.get(field, default)
    value = str(value).strip()
    return value or default


def _optional_bool(data: dict[str, Any], field: str, default: bool) -> bool:
    value = data.get(field, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "on"}:
            return True
        if normalized in {"false", "no", "0", "off"}:
            return False
    raise ValueError(f"Config field {field} must be a boolean.")


def _resolve_repo_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _require_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Config field {field_name} must be an integer.")
    if value <= 0:
        raise ValueError(f"Config field {field_name} must be > 0.")
    return value
