from pathlib import Path
import textwrap

import pytest

from dba_assistant.deep_agent_integration.config import (
    DEFAULT_CONFIG_PATH,
    REPO_ROOT,
    ProviderKind,
    SUPPORTED_PRESET_NAMES,
    load_app_config,
)


def _write_config(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).strip() + "\n")


def test_load_app_config_reads_repository_default_shape(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        """
        model:
          preset_name: ollama_local
          provider_kind: openai_compatible
          model_name: qwen3:8b
          base_url: http://127.0.0.1:11434/v1
          api_key: ollama
          temperature: 0.1
          max_turns: 9
          tracing_disabled: true
        runtime:
          default_output_mode: summary
          redis_socket_timeout: 6.5
          mysql_stage_batch_size: 4096
          mysql_connect_timeout_seconds: 7.5
          mysql_read_timeout_seconds: 18.0
          mysql_write_timeout_seconds: 35.0
        observability:
          enabled: true
          console_enabled: false
          console_level: ERROR
          file_level: INFO
          log_dir: outputs/custom-logs
          app_log_file: custom-app.jsonl
          audit_log_file: custom-audit.jsonl
        """,
    )

    config = load_app_config(config_path)

    assert DEFAULT_CONFIG_PATH.is_absolute()
    assert DEFAULT_CONFIG_PATH.name == "config.yaml"
    assert DEFAULT_CONFIG_PATH.parent.name == "config"
    assert config.model.preset_name == "ollama_local"
    assert config.model.provider_kind is ProviderKind.OPENAI_COMPATIBLE
    assert config.model.model_name == "qwen3:8b"
    assert config.model.base_url == "http://127.0.0.1:11434/v1"
    assert config.model.api_key == "ollama"
    assert config.runtime.default_output_mode == "summary"
    assert config.runtime.redis_socket_timeout == 6.5
    assert config.runtime.mysql_stage_batch_size == 4096
    assert config.runtime.mysql_connect_timeout_seconds == 7.5
    assert config.runtime.mysql_read_timeout_seconds == 18.0
    assert config.runtime.mysql_write_timeout_seconds == 35.0
    assert config.observability.enabled is True
    assert config.observability.console_enabled is False
    assert config.observability.console_level == "ERROR"
    assert config.observability.file_level == "INFO"
    assert config.observability.log_dir == REPO_ROOT / "outputs" / "custom-logs"
    assert config.observability.app_log_path == REPO_ROOT / "outputs" / "custom-logs" / "custom-app.jsonl"
    assert config.observability.audit_log_path == REPO_ROOT / "outputs" / "custom-logs" / "custom-audit.jsonl"


def test_load_app_config_uses_repo_default_path_outside_repo_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_app_config()

    assert DEFAULT_CONFIG_PATH.is_absolute()
    assert config.model.preset_name in SUPPORTED_PRESET_NAMES
    assert config.model.base_url
    assert config.runtime.default_output_mode


def test_load_app_config_supports_dashscope_preset_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.example.yaml"
    _write_config(
        config_path,
        """
        model:
          preset_name: dashscope_cn
          provider_kind: openai_compatible
          model_name: qwen3.5-flash
          base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
          api_key: replace-with-real-api-key
          temperature: 0.0
          max_turns: 8
          tracing_disabled: true
        runtime:
          default_output_mode: summary
          redis_socket_timeout: 5.0
        """,
    )

    config = load_app_config(config_path)

    assert config.model.preset_name == "dashscope_cn"
    assert config.model.provider_kind is ProviderKind.OPENAI_COMPATIBLE
    assert config.model.model_name == "qwen3.5-flash"
    assert config.model.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert config.model.api_key == "replace-with-real-api-key"
    assert config.observability.log_dir == REPO_ROOT / "outputs" / "logs"
    assert config.observability.app_log_path == REPO_ROOT / "outputs" / "logs" / "app.log.jsonl"
    assert config.observability.audit_log_path == REPO_ROOT / "outputs" / "logs" / "audit.jsonl"


def test_load_app_config_requires_existing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="missing.yaml"):
        load_app_config(tmp_path / "missing.yaml")


def test_load_app_config_requires_model_api_key(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        """
        model:
          preset_name: dashscope_intl
          provider_kind: openai_compatible
          model_name: qwen3.5-flash
          base_url: https://dashscope-intl.aliyuncs.com/compatible-mode/v1
          api_key: ""
        runtime:
          default_output_mode: summary
          redis_socket_timeout: 5.0
        """,
    )

    with pytest.raises(ValueError, match="model.api_key"):
        load_app_config(config_path)


def test_load_app_config_requires_runtime_section(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        """
        model:
          preset_name: ollama_local
          provider_kind: openai_compatible
          model_name: qwen3:8b
          base_url: http://127.0.0.1:11434/v1
          api_key: ollama
        """,
    )

    with pytest.raises(ValueError, match="runtime"):
        load_app_config(config_path)


def test_load_app_config_rejects_bad_root_shape(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        """
        - not
        - a
        - mapping
        """,
    )

    with pytest.raises(ValueError, match="document root"):
        load_app_config(config_path)


def test_load_app_config_supports_absolute_observability_paths(tmp_path: Path) -> None:
    absolute_log_dir = tmp_path / "absolute-logs"
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        f"""
        model:
          preset_name: ollama_local
          provider_kind: openai_compatible
          model_name: qwen3:8b
          base_url: http://127.0.0.1:11434/v1
          api_key: ollama
        runtime:
          default_output_mode: summary
          redis_socket_timeout: 5.0
        observability:
          enabled: true
          console_enabled: true
          console_level: DEBUG
          file_level: INFO
          log_dir: {absolute_log_dir}
          app_log_file: app.jsonl
          audit_log_file: audit.jsonl
        """,
    )

    config = load_app_config(config_path)

    assert config.observability.console_level == "DEBUG"
    assert config.observability.file_level == "INFO"
    assert config.observability.log_dir == absolute_log_dir
    assert config.observability.app_log_path == absolute_log_dir / "app.jsonl"
    assert config.observability.audit_log_path == absolute_log_dir / "audit.jsonl"


def test_load_app_config_uses_reasonable_observability_defaults_when_omitted(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        """
        model:
          preset_name: ollama_local
          provider_kind: openai_compatible
          model_name: qwen3:8b
          base_url: http://127.0.0.1:11434/v1
          api_key: ollama
        runtime:
          default_output_mode: summary
          redis_socket_timeout: 5.0
        """,
    )

    config = load_app_config(config_path)

    assert config.observability.enabled is True
    assert config.observability.console_enabled is True
    assert config.observability.console_level == "WARNING"
    assert config.observability.file_level == "INFO"
    assert config.observability.log_dir == REPO_ROOT / "outputs" / "logs"
    assert config.observability.app_log_path == REPO_ROOT / "outputs" / "logs" / "app.log.jsonl"
    assert config.observability.audit_log_path == REPO_ROOT / "outputs" / "logs" / "audit.jsonl"


def test_load_app_config_uses_mysql_timeout_defaults_when_omitted(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        """
        model:
          preset_name: ollama_local
          provider_kind: openai_compatible
          model_name: qwen3:8b
          base_url: http://127.0.0.1:11434/v1
          api_key: ollama
        runtime:
          default_output_mode: summary
          redis_socket_timeout: 5.0
        """,
    )

    config = load_app_config(config_path)

    assert config.runtime.mysql_stage_batch_size == 2000
    assert config.runtime.mysql_connect_timeout_seconds == 5.0
    assert config.runtime.mysql_read_timeout_seconds == 15.0
    assert config.runtime.mysql_write_timeout_seconds == 30.0


def test_load_app_config_rejects_non_positive_mysql_stage_batch_size(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(
        config_path,
        """
        model:
          preset_name: ollama_local
          provider_kind: openai_compatible
          model_name: qwen3:8b
          base_url: http://127.0.0.1:11434/v1
          api_key: ollama
        runtime:
          default_output_mode: summary
          redis_socket_timeout: 5.0
          mysql_stage_batch_size: 0
        """,
    )

    with pytest.raises(ValueError, match="runtime.mysql_stage_batch_size"):
        load_app_config(config_path)
