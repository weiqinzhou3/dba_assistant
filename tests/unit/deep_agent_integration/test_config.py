from pathlib import Path
import textwrap

import pytest

from dba_assistant.deep_agent_integration.config import (
    DEFAULT_CONFIG_PATH,
    ProviderKind,
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
        """,
    )

    config = load_app_config(config_path)

    assert DEFAULT_CONFIG_PATH == Path("config/config.yaml")
    assert config.model.preset_name == "ollama_local"
    assert config.model.provider_kind is ProviderKind.OPENAI_COMPATIBLE
    assert config.model.model_name == "qwen3:8b"
    assert config.model.base_url == "http://127.0.0.1:11434/v1"
    assert config.model.api_key == "ollama"
    assert config.runtime.default_output_mode == "summary"
    assert config.runtime.redis_socket_timeout == 6.5


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
