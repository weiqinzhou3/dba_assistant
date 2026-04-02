# Phase 2 CLI and Config Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the environment-variable-first Phase 2 configuration with repository-owned YAML config, add a thin prompt-first CLI for local debugging, and introduce a normalized request/application layer that future GUI and API work can reuse.

**Architecture:** Keep the project agent-shaped. Add a YAML-backed config loader plus a small application layer that normalizes raw prompt input into `prompt`, `runtime_inputs`, and `secrets` before calling the existing Deep Agent SDK assembly. The CLI remains a thin presentation shell and must not contain business logic that future GUI/API surfaces would need to duplicate.

**Tech Stack:** Python 3.11, pytest, argparse, PyYAML, openai-agents, redis-py, dataclasses, regex-based prompt parsing

---

## File Structure Map

**Modify existing files:**

- Modify: `pyproject.toml`
- Modify: `src/dba_assistant/README.md`
- Modify: `src/dba_assistant/deep_agent_integration/README.md`
- Modify: `src/dba_assistant/deep_agent_integration/__init__.py`
- Modify: `src/dba_assistant/deep_agent_integration/config.py`
- Modify: `src/dba_assistant/deep_agent_integration/agent_factory.py`
- Modify: `src/dba_assistant/deep_agent_integration/run.py`
- Modify: `tests/unit/deep_agent_integration/test_config.py`
- Modify: `tests/unit/deep_agent_integration/test_agent_factory.py`
- Modify: `tests/unit/deep_agent_integration/test_run.py`
- Modify: `docs/phases/phase-2.md`
- Modify: `docs/phase-2-model-configuration-pitfalls.md`

**Create configuration files:**

- Create: `config/config.yaml`
- Create: `config/config.example.yaml`

**Create application-layer files:**

- Create: `src/dba_assistant/application/__init__.py`
- Create: `src/dba_assistant/application/README.md`
- Create: `src/dba_assistant/application/request_models.py`
- Create: `src/dba_assistant/application/prompt_parser.py`
- Create: `src/dba_assistant/application/service.py`

**Create CLI files:**

- Create: `src/dba_assistant/cli.py`

**Create tests:**

- Create: `tests/unit/application/test_prompt_parser.py`
- Create: `tests/unit/application/test_service.py`
- Create: `tests/unit/test_cli.py`

### Task 1: Replace Environment Variables With YAML Configuration

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/dba_assistant/deep_agent_integration/__init__.py`
- Modify: `src/dba_assistant/deep_agent_integration/config.py`
- Modify: `tests/unit/deep_agent_integration/test_config.py`
- Create: `config/config.yaml`
- Create: `config/config.example.yaml`

- [ ] **Step 1: Write the failing tests for YAML-backed config loading**

```python
# tests/unit/deep_agent_integration/test_config.py
from pathlib import Path
import textwrap

import pytest

from dba_assistant.deep_agent_integration.config import (
    DEFAULT_CONFIG_PATH,
    ProviderKind,
    load_app_config,
)


def test_load_app_config_reads_yaml_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        textwrap.dedent(
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
            """
        ).strip()
        + "\n"
    )

    config = load_app_config(config_path)

    assert DEFAULT_CONFIG_PATH == Path("config/config.yaml")
    assert config.model.provider_kind is ProviderKind.OPENAI_COMPATIBLE
    assert config.model.model_name == "qwen3:8b"
    assert config.model.api_key == "ollama"
    assert config.runtime.default_output_mode == "summary"
    assert config.runtime.redis_socket_timeout == 6.5


def test_load_app_config_requires_model_api_key(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        textwrap.dedent(
            """
            model:
              preset_name: dashscope_cn_qwen35_flash
              provider_kind: openai_compatible
              model_name: qwen3.5-flash
              base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
              api_key: ""
            runtime:
              default_output_mode: summary
              redis_socket_timeout: 5.0
            """
        ).strip()
        + "\n"
    )

    with pytest.raises(ValueError, match="model.api_key"):
        load_app_config(config_path)


def test_load_app_config_requires_existing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_app_config(tmp_path / "missing.yaml")
```

- [ ] **Step 2: Run the config tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/unit/deep_agent_integration/test_config.py`

Expected: FAIL because `load_app_config()` still expects environment variables, has no `DEFAULT_CONFIG_PATH`, and has no `runtime` config section.

- [ ] **Step 3: Add YAML support, config files, and the new config loader**

```toml
# pyproject.toml
[project]
name = "dba-assistant"
version = "0.1.0"
description = "Phase-oriented scaffold for the DBA Assistant project."
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "openai-agents",
    "PyYAML>=6,<7",
    "python-docx>=1.1,<2",
    "redis>=5",
]

[project.scripts]
dba-assistant = "dba_assistant.cli:main"
```

```python
# src/dba_assistant/deep_agent_integration/config.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path("config/config.yaml")


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
    model_data = _require_mapping(document, "model")
    runtime_data = _require_mapping(document, "runtime")
    return AppConfig(
        model=_load_model_config(model_data),
        runtime=_load_runtime_config(runtime_data),
    )


def _load_yaml_document(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text())
    if not isinstance(loaded, dict):
        raise ValueError(f"Config file must contain a mapping at the document root: {path}")
    return loaded


def _load_model_config(data: dict[str, Any]) -> ModelConfig:
    api_key = str(data.get("api_key", "")).strip()
    if not api_key:
        raise ValueError("Config field model.api_key is required.")

    return ModelConfig(
        preset_name=str(data.get("preset_name", "")).strip(),
        provider_kind=ProviderKind(str(data.get("provider_kind", "openai_compatible")).strip()),
        model_name=_require_string(data, "model_name", "model"),
        base_url=_require_string(data, "base_url", "model"),
        api_key=api_key,
        temperature=float(data.get("temperature", 0.0)),
        max_turns=int(data.get("max_turns", 8)),
        tracing_disabled=bool(data.get("tracing_disabled", True)),
    )


def _load_runtime_config(data: dict[str, Any]) -> RuntimeConfig:
    return RuntimeConfig(
        default_output_mode=str(data.get("default_output_mode", "summary")).strip() or "summary",
        redis_socket_timeout=float(data.get("redis_socket_timeout", 5.0)),
    )


def _require_mapping(document: dict[str, Any], field: str) -> dict[str, Any]:
    value = document.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"Config section {field} must be a mapping.")
    return value


def _require_string(data: dict[str, Any], field: str, section: str) -> str:
    value = str(data.get(field, "")).strip()
    if not value:
        raise ValueError(f"Config field {section}.{field} is required.")
    return value
```

```python
# src/dba_assistant/deep_agent_integration/__init__.py
"""Repository-owned Deep Agent SDK assembly layer for DBA Assistant."""

from dba_assistant.deep_agent_integration.config import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    ModelConfig,
    ProviderKind,
    RuntimeConfig,
    load_app_config,
)
from dba_assistant.deep_agent_integration.model_provider import build_model
from dba_assistant.deep_agent_integration.tool_registry import build_redis_tools


DEFAULT_PROMPT = (
    "Validate the Phase 2 Deep Agent SDK assembly. "
    "Use only read-only Redis tools, summarize the structured findings, and stay within the Phase 2 scope."
)


def run_phase2(prompt: str = DEFAULT_PROMPT) -> str:
    from dba_assistant.deep_agent_integration.run import run_phase2 as _run_phase2

    return _run_phase2(prompt)


def main() -> int:
    from dba_assistant.deep_agent_integration.run import main as _main

    return _main()


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "AppConfig",
    "DEFAULT_PROMPT",
    "RuntimeConfig",
    "build_model",
    "build_redis_tools",
    "ModelConfig",
    "ProviderKind",
    "load_app_config",
    "main",
    "run_phase2",
]
```

```yaml
# config/config.yaml
model:
  preset_name: ollama_local
  provider_kind: openai_compatible
  model_name: qwen3:8b
  base_url: http://127.0.0.1:11434/v1
  api_key: ollama
  temperature: 0.0
  max_turns: 8
  tracing_disabled: true
runtime:
  default_output_mode: summary
  redis_socket_timeout: 5.0
```

```yaml
# config/config.example.yaml
model:
  preset_name: dashscope_cn_qwen35_flash
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
```

- [ ] **Step 4: Run the config tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/unit/deep_agent_integration/test_config.py`

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit the YAML config foundation**

```bash
git add pyproject.toml config/config.yaml config/config.example.yaml src/dba_assistant/deep_agent_integration/__init__.py src/dba_assistant/deep_agent_integration/config.py tests/unit/deep_agent_integration/test_config.py
git commit -m "feat: add yaml-backed phase 2 config"
```

### Task 2: Add Normalized Request Models and Prompt Parsing

**Files:**
- Create: `src/dba_assistant/application/__init__.py`
- Create: `src/dba_assistant/application/README.md`
- Create: `src/dba_assistant/application/request_models.py`
- Create: `src/dba_assistant/application/prompt_parser.py`
- Create: `tests/unit/application/test_prompt_parser.py`

- [ ] **Step 1: Write the failing tests for prompt normalization**

```python
# tests/unit/application/test_prompt_parser.py
from dba_assistant.application.prompt_parser import normalize_raw_request


def test_normalize_raw_request_extracts_runtime_inputs_and_secrets() -> None:
    request = normalize_raw_request(
        "Use password abc123 to inspect Redis 10.0.0.8:6380 db 2 and give me a summary",
        default_output_mode="summary",
    )

    assert request.raw_prompt == "Use password abc123 to inspect Redis 10.0.0.8:6380 db 2 and give me a summary"
    assert request.prompt == "Use to inspect Redis 10.0.0.8:6380 db 2 and give me a summary"
    assert request.runtime_inputs.redis_host == "10.0.0.8"
    assert request.runtime_inputs.redis_port == 6380
    assert request.runtime_inputs.redis_db == 2
    assert request.runtime_inputs.output_mode == "summary"
    assert request.secrets.redis_password == "abc123"


def test_normalize_raw_request_uses_default_output_mode_when_unspecified() -> None:
    request = normalize_raw_request(
        "Inspect Redis 10.0.0.9:6379",
        default_output_mode="summary",
    )

    assert request.runtime_inputs.redis_host == "10.0.0.9"
    assert request.runtime_inputs.redis_port == 6379
    assert request.runtime_inputs.output_mode == "summary"
    assert request.secrets.redis_password is None
```

- [ ] **Step 2: Run the prompt parser tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/unit/application/test_prompt_parser.py`

Expected: FAIL because the `application` package and parser do not exist yet.

- [ ] **Step 3: Add the normalized request models and deterministic parser**

```python
# src/dba_assistant/application/request_models.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeInputs:
    redis_host: str | None = None
    redis_port: int = 6379
    redis_db: int = 0
    output_mode: str = "summary"


@dataclass(frozen=True)
class Secrets:
    redis_password: str | None = None


@dataclass(frozen=True)
class NormalizedRequest:
    raw_prompt: str
    prompt: str
    runtime_inputs: RuntimeInputs
    secrets: Secrets
```

```python
# src/dba_assistant/application/prompt_parser.py
from __future__ import annotations

import re

from dba_assistant.application.request_models import NormalizedRequest, RuntimeInputs, Secrets


PASSWORD_PATTERN = re.compile(r"(?i)\\bpassword(?:\\s+is)?\\s+(?P<password>[^\\s,;]+)")
HOST_PORT_PATTERN = re.compile(r"\\b(?P<host>(?:\\d{1,3}\\.){3}\\d{1,3})(?::(?P<port>\\d{1,5}))?\\b")
DB_PATTERN = re.compile(r"(?i)\\bdb\\s+(?P<db>\\d+)\\b")


def normalize_raw_request(raw_prompt: str, *, default_output_mode: str) -> NormalizedRequest:
    password_match = PASSWORD_PATTERN.search(raw_prompt)
    host_match = HOST_PORT_PATTERN.search(raw_prompt)
    db_match = DB_PATTERN.search(raw_prompt)

    redis_host = host_match.group("host") if host_match else None
    redis_port = int(host_match.group("port") or "6379") if host_match else 6379
    redis_db = int(db_match.group("db")) if db_match else 0
    redis_password = password_match.group("password") if password_match else None

    cleaned_prompt = PASSWORD_PATTERN.sub("", raw_prompt)
    cleaned_prompt = re.sub(r"\\s+", " ", cleaned_prompt).strip()

    output_mode = "report" if "report" in raw_prompt.lower() else default_output_mode

    return NormalizedRequest(
        raw_prompt=raw_prompt,
        prompt=cleaned_prompt,
        runtime_inputs=RuntimeInputs(
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
            output_mode=output_mode,
        ),
        secrets=Secrets(redis_password=redis_password),
    )
```

```python
# src/dba_assistant/application/__init__.py
"""Application-facing request normalization and execution layer."""

from dba_assistant.application.prompt_parser import normalize_raw_request
from dba_assistant.application.request_models import NormalizedRequest, RuntimeInputs, Secrets

__all__ = [
    "NormalizedRequest",
    "RuntimeInputs",
    "Secrets",
    "normalize_raw_request",
]
```

```markdown
# src/dba_assistant/application/README.md

This package holds the presentation-neutral application layer for DBA Assistant.

It exists so that CLI, future GUI, and future API entry points can all share:

- raw request normalization
- structured runtime input handling
- secret separation
- application service orchestration
```

- [ ] **Step 4: Run the prompt parser tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/unit/application/test_prompt_parser.py`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit the request normalization layer**

```bash
git add src/dba_assistant/application/__init__.py src/dba_assistant/application/README.md src/dba_assistant/application/request_models.py src/dba_assistant/application/prompt_parser.py tests/unit/application/test_prompt_parser.py
git commit -m "feat: add phase 2 request normalization"
```

### Task 3: Add the Thin CLI and Application Service

**Files:**
- Create: `src/dba_assistant/application/service.py`
- Create: `src/dba_assistant/cli.py`
- Modify: `src/dba_assistant/deep_agent_integration/agent_factory.py`
- Modify: `src/dba_assistant/deep_agent_integration/run.py`
- Modify: `tests/unit/deep_agent_integration/test_agent_factory.py`
- Modify: `tests/unit/deep_agent_integration/test_run.py`
- Create: `tests/unit/application/test_service.py`
- Create: `tests/unit/test_cli.py`

- [ ] **Step 1: Write the failing tests for the application service, agent wiring, and CLI**

```python
# tests/unit/application/test_service.py
from dba_assistant.application.request_models import NormalizedRequest, RuntimeInputs, Secrets
from dba_assistant.application.service import execute_request
from dba_assistant.deep_agent_integration.config import AppConfig, ModelConfig, ProviderKind, RuntimeConfig


def test_execute_request_builds_redis_connection_and_calls_phase2_runner(monkeypatch) -> None:
    captured: dict[str, object] = {}

    config = AppConfig(
        model=ModelConfig(
            preset_name="ollama_local",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3:8b",
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
        ),
        runtime=RuntimeConfig(default_output_mode="summary", redis_socket_timeout=6.0),
    )

    request = NormalizedRequest(
        raw_prompt="Use password abc123 to inspect Redis 10.0.0.8:6380 db 2 and give me a summary",
        prompt="Use to inspect Redis 10.0.0.8:6380 db 2 and give me a summary",
        runtime_inputs=RuntimeInputs(redis_host="10.0.0.8", redis_port=6380, redis_db=2, output_mode="summary"),
        secrets=Secrets(redis_password="abc123"),
    )

    def fake_run_phase2_request(prompt, *, config, redis_connection):
        captured["prompt"] = prompt
        captured["config"] = config
        captured["redis_connection"] = redis_connection
        return "phase2 ok"

    monkeypatch.setattr("dba_assistant.application.service.run_phase2_request", fake_run_phase2_request)

    assert execute_request(request, config=config) == "phase2 ok"
    assert captured["prompt"] == "Use to inspect Redis 10.0.0.8:6380 db 2 and give me a summary"
    assert captured["redis_connection"].host == "10.0.0.8"
    assert captured["redis_connection"].port == 6380
    assert captured["redis_connection"].db == 2
    assert captured["redis_connection"].password == "abc123"
    assert captured["redis_connection"].socket_timeout == 6.0
```

```python
# tests/unit/deep_agent_integration/test_agent_factory.py
from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.deep_agent_integration.agent_factory import build_phase2_agent
from dba_assistant.deep_agent_integration.config import AppConfig, ModelConfig, ProviderKind, RuntimeConfig


def test_build_phase2_agent_wires_model_tools_and_read_only_instructions(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def fake_build_model(model_config):
        calls["build_model"] = model_config
        return "fake-model"

    def fake_build_redis_tools(connection, adaptor=None):
        calls["build_redis_tools"] = {"connection": connection, "adaptor": adaptor}
        return ["redis_ping", "redis_info"]

    monkeypatch.setattr("dba_assistant.deep_agent_integration.agent_factory.build_model", fake_build_model)
    monkeypatch.setattr("dba_assistant.deep_agent_integration.agent_factory.build_redis_tools", fake_build_redis_tools)

    config = AppConfig(
        model=ModelConfig(
            preset_name="ollama_local",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3:8b",
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
            temperature=0.2,
        ),
        runtime=RuntimeConfig(default_output_mode="summary", redis_socket_timeout=5.0),
    )
    connection = RedisConnectionConfig(host="redis.example", port=6380, db=7)

    agent = build_phase2_agent(config, connection, redis_adaptor="fake-adaptor")

    assert calls["build_model"] is config.model
    assert calls["build_redis_tools"] == {"connection": connection, "adaptor": "fake-adaptor"}
    assert agent.model == "fake-model"
    assert agent.model_settings.temperature == 0.2
    assert "read-only" in agent.instructions.lower()
```

```python
# tests/unit/deep_agent_integration/test_run.py
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

    monkeypatch.setattr(run_module, "build_phase2_agent", lambda cfg, conn, redis_adaptor=None: ("agent", cfg, conn, redis_adaptor))

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
```

```python
# tests/unit/test_cli.py
from dba_assistant import cli


def test_cli_ask_loads_config_normalizes_request_and_prints_result(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_app_config", lambda config_path=None: "CONFIG")
    monkeypatch.setattr(cli, "normalize_raw_request", lambda raw_prompt, default_output_mode: "REQUEST")
    monkeypatch.setattr(cli, "execute_request", lambda request, *, config: "phase2 ok")

    exit_code = cli.main(["ask", "Use password abc123 to inspect Redis 10.0.0.8:6379 and give me a summary"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == "phase2 ok\n"
```

- [ ] **Step 2: Run the service and CLI tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/unit/application/test_service.py tests/unit/deep_agent_integration/test_agent_factory.py tests/unit/deep_agent_integration/test_run.py tests/unit/test_cli.py`

Expected: FAIL because there is no application service, `build_phase2_agent()` still captures Redis from config, and the CLI module does not exist.

- [ ] **Step 3: Implement the application service, CLI, and assembly refactor**

```python
# src/dba_assistant/application/service.py
from __future__ import annotations

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.application.request_models import NormalizedRequest
from dba_assistant.deep_agent_integration.config import AppConfig
from dba_assistant.deep_agent_integration.run import run_phase2_request


def execute_request(request: NormalizedRequest, *, config: AppConfig) -> str:
    if not request.runtime_inputs.redis_host:
        raise ValueError("Phase 2 requires a Redis host in the normalized request.")

    redis_connection = RedisConnectionConfig(
        host=request.runtime_inputs.redis_host,
        port=request.runtime_inputs.redis_port,
        db=request.runtime_inputs.redis_db,
        password=request.secrets.redis_password,
        socket_timeout=config.runtime.redis_socket_timeout,
    )

    return run_phase2_request(
        request.prompt,
        config=config,
        redis_connection=redis_connection,
    )
```

```python
# src/dba_assistant/deep_agent_integration/agent_factory.py
from __future__ import annotations

from agents import Agent, ModelSettings

from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig
from dba_assistant.deep_agent_integration.config import AppConfig
from dba_assistant.deep_agent_integration.model_provider import build_model
from dba_assistant.deep_agent_integration.tool_registry import build_redis_tools


def build_phase2_agent(
    config: AppConfig,
    redis_connection: RedisConnectionConfig,
    redis_adaptor: RedisAdaptor | None = None,
) -> Agent:
    model = build_model(config.model)
    tools = build_redis_tools(redis_connection, adaptor=redis_adaptor)
    return Agent(
        name="dba-assistant-phase2",
        instructions=(
            "You are the Phase 2 integration-validation agent for DBA Assistant. "
            "Use only the provided read-only Redis tools. "
            "Do not attempt writes, destructive actions, SSH, MySQL, or custom runtime behavior. "
            "Summarize the structured tool outputs plainly."
        ),
        model=model,
        tools=tools,
        model_settings=ModelSettings(temperature=config.model.temperature),
    )
```

```python
# src/dba_assistant/deep_agent_integration/run.py
from __future__ import annotations

from agents import Runner

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.deep_agent_integration import DEFAULT_PROMPT
from dba_assistant.deep_agent_integration.agent_factory import build_phase2_agent
from dba_assistant.deep_agent_integration.config import AppConfig, load_app_config
from dba_assistant.application.prompt_parser import normalize_raw_request
from dba_assistant.application.service import execute_request


def run_phase2_request(
    prompt: str,
    *,
    config: AppConfig,
    redis_connection: RedisConnectionConfig,
) -> str:
    agent = build_phase2_agent(config, redis_connection)
    result = Runner.run_sync(agent, prompt, max_turns=config.model.max_turns)
    return str(result.final_output)


def run_phase2(prompt: str = DEFAULT_PROMPT) -> str:
    config = load_app_config()
    request = normalize_raw_request(prompt, default_output_mode=config.runtime.default_output_mode)
    return execute_request(request, config=config)


def main() -> int:
    print(run_phase2())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

```python
# src/dba_assistant/cli.py
from __future__ import annotations

import argparse

from dba_assistant.application.prompt_parser import normalize_raw_request
from dba_assistant.application.service import execute_request
from dba_assistant.deep_agent_integration.config import load_app_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dba-assistant")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("prompt")
    ask_parser.add_argument("--config", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "ask":
        config = load_app_config(args.config)
        request = normalize_raw_request(
            args.prompt,
            default_output_mode=config.runtime.default_output_mode,
        )
        print(execute_request(request, config=config))
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2
```

- [ ] **Step 4: Run the service and CLI tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/unit/application/test_service.py tests/unit/deep_agent_integration/test_agent_factory.py tests/unit/deep_agent_integration/test_run.py tests/unit/test_cli.py`

Expected: PASS with `4 passed`.

- [ ] **Step 5: Run the broader application/runtime tests**

Run: `.venv/bin/python -m pytest -q tests/unit/application/test_prompt_parser.py tests/unit/application/test_service.py tests/unit/deep_agent_integration tests/unit/test_cli.py`

Expected: PASS with all tests green.

- [ ] **Step 6: Commit the prompt-first CLI correction**

```bash
git add src/dba_assistant/application/__init__.py src/dba_assistant/application/README.md src/dba_assistant/application/request_models.py src/dba_assistant/application/prompt_parser.py src/dba_assistant/application/service.py src/dba_assistant/cli.py src/dba_assistant/deep_agent_integration/agent_factory.py src/dba_assistant/deep_agent_integration/run.py tests/unit/application/test_prompt_parser.py tests/unit/application/test_service.py tests/unit/deep_agent_integration/test_agent_factory.py tests/unit/deep_agent_integration/test_run.py tests/unit/test_cli.py
git commit -m "feat: add prompt-first phase 2 cli"
```

### Task 4: Align Docs and Run Full Verification

**Files:**
- Modify: `src/dba_assistant/README.md`
- Modify: `src/dba_assistant/deep_agent_integration/README.md`
- Modify: `docs/phases/phase-2.md`
- Modify: `docs/phase-2-model-configuration-pitfalls.md`

- [ ] **Step 1: Update the docs to match the corrected Phase 2 shape**

```markdown
# src/dba_assistant/README.md

# dba_assistant Package

This is the production package root for DBA Assistant.

Delivered surfaces currently include the Phase 1 shared collector and reporter foundation,
the Phase 2 `deep_agent_integration/` assembly layer, and the thin prompt-first CLI plus
application normalization layer used for local debugging.

Other phase-owned areas under this root remain limited to the scoped implementations
delivered in their respective phases.
```

```markdown
# src/dba_assistant/deep_agent_integration/README.md

# deep_agent_integration

This package contains the repository-owned Deep Agent SDK assembly layer.

It is not a custom runtime framework and it is not the CLI presentation layer.

Its responsibilities are limited to:

- loading static application configuration
- building provider-compatible model objects
- registering model-visible tools
- constructing the minimal Phase 2 agent
- invoking the Runner for normalized requests
```

```markdown
# docs/phases/phase-2.md

## Delivered Scope

2. Provider-capable model configuration
   - Uses repository-owned `config.yaml` instead of environment-variable-first loading.
   - Keeps model/provider configuration centralized in the integration layer.

4. Bounded Redis tool registration and minimal validation entry points
   - Registers a small, read-only Redis tool set.
   - Builds a minimal integration-validation agent that summarizes structured Redis results.
   - Exposes a thin prompt-first CLI for local debugging.
   - Keeps the CLI thin so future GUI and API surfaces can reuse the same application contract.
```

```markdown
# docs/phase-2-model-configuration-pitfalls.md

## Additional Pitfall

- `config/config.yaml` is now the static source of truth for model configuration.
- Do not reintroduce environment-variable-only config loading for normal repository usage.
- Dynamic targets and secrets still belong to normalized runtime requests, not static config.
```

- [ ] **Step 2: Run the full Phase 1 + corrected Phase 2 verification suite**

Run: `.venv/bin/python -m pytest -q tests/unit/core/reporter/test_docx_reporter.py tests/unit/core/reporter/test_report_types.py tests/unit/core/reporter/test_template_specs.py tests/unit/core/reporter/test_summary_reporter.py tests/unit/core/collector/test_offline_collector.py tests/unit/core/collector/test_remote_collector.py tests/unit/adaptors/test_redis_adaptor.py tests/unit/deep_agent_integration/test_config.py tests/unit/deep_agent_integration/test_model_provider.py tests/unit/deep_agent_integration/test_tool_registry.py tests/unit/deep_agent_integration/test_agent_factory.py tests/unit/deep_agent_integration/test_run.py tests/unit/application/test_prompt_parser.py tests/unit/application/test_service.py tests/unit/test_cli.py tests/unit/skills/redis_inspection_report/collectors/test_remote_redis_collector.py`

Expected: PASS with all tests green.

- [ ] **Step 3: Run git diff validation**

Run: `git diff --check`

Expected: PASS with no whitespace or conflict-marker issues.

- [ ] **Step 4: Commit the doc and verification alignment**

```bash
git add src/dba_assistant/README.md src/dba_assistant/deep_agent_integration/README.md docs/phases/phase-2.md docs/phase-2-model-configuration-pitfalls.md
git commit -m "docs: finalize phase 2 cli correction"
```

- [ ] **Step 5: Verify the branch is clean**

Run: `git status -sb`

Expected: clean working tree on the feature branch.

## Self-Review

**Spec coverage:** The plan covers YAML-backed static config, a thin prompt-first CLI, secret extraction before agent execution, a normalized request contract, an application service above `deep_agent_integration`, and forward compatibility with future GUI/API work.

**Placeholder scan:** The plan does not use `TODO`, `TBD`, or deferred placeholders inside the tasks. Later-phase GUI and API work remain out of scope because the approved spec explicitly keeps them out of this correction.

**Type consistency:** The plan uses one `AppConfig` root, one `RuntimeConfig` for static defaults, one `NormalizedRequest` contract, one deterministic prompt parser, and one `execute_request()` application entry path across CLI and Deep Agent SDK assembly.
