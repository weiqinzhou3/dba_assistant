# Phase 2 Runtime Assembly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the repository-owned Deep Agent SDK assembly layer for DBA Assistant, including provider-capable model configuration, a real read-only Redis direct connection path, and clear provider pitfall documentation.

**Architecture:** Keep `Phase 2` intentionally narrow. Add a repository-owned `deep_agent_integration/` layer that wires config, model provider, tools, agent construction, and run entry without introducing a custom runtime framework. Implement only one real remote path through a bounded Redis adaptor and a single Redis inspection remote collector, while keeping SSH and MySQL live work deferred.

**Tech Stack:** Python 3.11, pytest, openai-agents, redis-py, dataclasses, environment-variable configuration

---

## File Structure Map

**Modify existing files:**

- Modify: `pyproject.toml`
- Modify: `src/dba_assistant/README.md`
- Modify: `src/dba_assistant/adaptors/__init__.py`
- Modify: `src/dba_assistant/adaptors/redis_adaptor.py`
- Modify: `src/dba_assistant/core/collector/remote_collector.py`
- Modify: `src/dba_assistant/skills/redis_inspection_report/collectors/__init__.py`
- Modify: `docs/phases/phase-1.md`
- Modify: `docs/phases/phase-2.md`

**Create Deep Agent SDK assembly files:**

- Create: `src/dba_assistant/deep_agent_integration/__init__.py`
- Create: `src/dba_assistant/deep_agent_integration/README.md`
- Create: `src/dba_assistant/deep_agent_integration/config.py`
- Create: `src/dba_assistant/deep_agent_integration/model_provider.py`
- Create: `src/dba_assistant/deep_agent_integration/tool_registry.py`
- Create: `src/dba_assistant/deep_agent_integration/agent_factory.py`
- Create: `src/dba_assistant/deep_agent_integration/run.py`

**Create remote collector files:**

- Create: `src/dba_assistant/skills/redis_inspection_report/collectors/remote_redis_collector.py`

**Create docs:**

- Create: `docs/phase-2-model-configuration-pitfalls.md`

**Create tests:**

- Create: `tests/unit/deep_agent_integration/test_config.py`
- Create: `tests/unit/deep_agent_integration/test_model_provider.py`
- Create: `tests/unit/adaptors/test_redis_adaptor.py`
- Create: `tests/unit/core/collector/test_remote_collector.py`
- Create: `tests/unit/skills/redis_inspection_report/collectors/test_remote_redis_collector.py`
- Create: `tests/unit/deep_agent_integration/test_tool_registry.py`
- Create: `tests/unit/deep_agent_integration/test_agent_factory.py`
- Create: `tests/unit/deep_agent_integration/test_run.py`

### Task 1: Add Phase 2 Dependencies and the Configuration Layer

**Files:**
- Modify: `pyproject.toml`
- Create: `src/dba_assistant/deep_agent_integration/__init__.py`
- Create: `src/dba_assistant/deep_agent_integration/README.md`
- Create: `src/dba_assistant/deep_agent_integration/config.py`
- Create: `tests/unit/deep_agent_integration/test_config.py`

- [ ] **Step 1: Write the failing tests for provider presets and app config loading**

```python
# tests/unit/deep_agent_integration/test_config.py
import pytest

from dba_assistant.deep_agent_integration.config import (
    DEFAULT_MODEL_PRESET,
    ProviderKind,
    load_app_config,
)


def test_load_app_config_uses_dashscope_cn_preset_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-cn")

    config = load_app_config()

    assert DEFAULT_MODEL_PRESET == "dashscope_cn_qwen35_flash"
    assert config.model.provider_kind is ProviderKind.OPENAI_COMPATIBLE
    assert config.model.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert config.model.model_name == "qwen3.5-flash"
    assert config.model.api_key == "sk-cn"
    assert config.redis.host == "127.0.0.1"
    assert config.redis.port == 6379


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

    with pytest.raises(ValueError, match="DBA_MODEL_BASE_URL"):
        load_app_config()
```

- [ ] **Step 2: Run the config tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/unit/deep_agent_integration/test_config.py`

Expected: FAIL because the `deep_agent_integration` package and config loader do not exist yet.

- [ ] **Step 3: Add the Phase 2 dependencies and implement the configuration layer**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "dba-assistant"
version = "0.1.0"
description = "Phase-oriented scaffold for the DBA Assistant project."
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "openai-agents",
    "python-docx>=1.1,<2",
    "redis>=5",
]

[project.optional-dependencies]
dev = ["pytest>=8,<9"]

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

```python
# src/dba_assistant/deep_agent_integration/__init__.py
"""Repository-owned Deep Agent SDK assembly layer for DBA Assistant."""

from dba_assistant.deep_agent_integration.config import AppConfig, ModelConfig, ProviderKind, load_app_config

__all__ = [
    "AppConfig",
    "ModelConfig",
    "ProviderKind",
    "load_app_config",
]
```

```markdown
# src/dba_assistant/deep_agent_integration/README.md

This package contains the repository-owned Deep Agent SDK assembly layer.

It is not a custom runtime framework.

Its responsibilities are limited to:

- loading application configuration
- building provider-compatible model objects
- registering model-visible tools
- constructing the minimal Phase 2 agent
- exposing a small run entry for smoke validation
```

```python
# src/dba_assistant/deep_agent_integration/config.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig


class ProviderKind(str, Enum):
    OPENAI_COMPATIBLE = "openai_compatible"


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
    api_key_env = preset["api_key_env"]
    if os.getenv("DBA_MODEL_API_KEY_ENV"):
        api_key_env = os.getenv("DBA_MODEL_API_KEY_ENV")

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
```

- [ ] **Step 4: Install dependencies and rerun the config tests**

Run: `.venv/bin/python -m pip install -e '.[dev]' && .venv/bin/python -m pytest -q tests/unit/deep_agent_integration/test_config.py`

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit the config foundation**

```bash
git add pyproject.toml src/dba_assistant/deep_agent_integration/__init__.py src/dba_assistant/deep_agent_integration/README.md src/dba_assistant/deep_agent_integration/config.py tests/unit/deep_agent_integration/test_config.py
git commit -m "feat: add phase 2 config foundation"
```

### Task 2: Implement the OpenAI-Compatible Model Provider

**Files:**
- Modify: `src/dba_assistant/deep_agent_integration/__init__.py`
- Create: `src/dba_assistant/deep_agent_integration/model_provider.py`
- Create: `tests/unit/deep_agent_integration/test_model_provider.py`

- [ ] **Step 1: Write the failing tests for model construction and tracing behavior**

```python
# tests/unit/deep_agent_integration/test_model_provider.py
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
        api_key_env="DASHSCOPE_API_KEY",
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
        api_key_env=None,
    )

    with pytest.raises(ValueError, match="Unsupported provider kind"):
        model_provider.build_model(config)
```

- [ ] **Step 2: Run the model provider tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/unit/deep_agent_integration/test_model_provider.py`

Expected: FAIL because `model_provider.py` does not exist yet.

- [ ] **Step 3: Implement the model provider**

```python
# src/dba_assistant/deep_agent_integration/model_provider.py
from __future__ import annotations

from agents import AsyncOpenAI, OpenAIChatCompletionsModel, set_tracing_disabled

from dba_assistant.deep_agent_integration.config import ModelConfig, ProviderKind


def build_model(config: ModelConfig) -> OpenAIChatCompletionsModel:
    if config.provider_kind is not ProviderKind.OPENAI_COMPATIBLE:
        raise ValueError(f"Unsupported provider kind: {config.provider_kind}")

    set_tracing_disabled(disabled=config.tracing_disabled)
    client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)
    return OpenAIChatCompletionsModel(
        model=config.model_name,
        openai_client=client,
    )
```

- [ ] **Step 4: Run the model provider tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/unit/deep_agent_integration/test_model_provider.py`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit the model provider**

```bash
git add src/dba_assistant/deep_agent_integration/model_provider.py tests/unit/deep_agent_integration/test_model_provider.py
git commit -m "feat: add phase 2 model provider"
```

### Task 3: Implement the Redis Adaptor and Remote Collector Path

**Files:**
- Modify: `src/dba_assistant/adaptors/__init__.py`
- Modify: `src/dba_assistant/adaptors/redis_adaptor.py`
- Modify: `src/dba_assistant/core/collector/remote_collector.py`
- Modify: `src/dba_assistant/skills/redis_inspection_report/collectors/__init__.py`
- Create: `src/dba_assistant/skills/redis_inspection_report/collectors/remote_redis_collector.py`
- Create: `tests/unit/adaptors/test_redis_adaptor.py`
- Create: `tests/unit/core/collector/test_remote_collector.py`
- Create: `tests/unit/skills/redis_inspection_report/collectors/test_remote_redis_collector.py`

- [ ] **Step 1: Write the failing tests for the Redis adaptor and remote collectors**

```python
# tests/unit/adaptors/test_redis_adaptor.py
from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig


class FakeRedisClient:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.closed = False

    def ping(self) -> bool:
        return True

    def info(self, section=None):
        return {"role": "master", "section": section}

    def config_get(self, pattern: str):
        return {"maxmemory": "0", "pattern": pattern}

    def slowlog_get(self, length: int):
        return [{"id": 1, "duration": 99, "length": length}]

    def client_list(self):
        return [{"addr": "127.0.0.1:5000"}]

    def close(self) -> None:
        self.closed = True


def test_redis_adaptor_wraps_read_only_commands() -> None:
    adaptor = RedisAdaptor(client_factory=FakeRedisClient)
    connection = RedisConnectionConfig(host="redis.example", port=6380, password="secret")

    assert adaptor.ping(connection) == {"ok": True}
    assert adaptor.info(connection, section="server")["role"] == "master"
    assert adaptor.config_get(connection, pattern="max*")["pattern"] == "max*"
    assert adaptor.slowlog_get(connection, length=5)[0]["length"] == 5
    assert adaptor.client_list(connection)[0]["addr"] == "127.0.0.1:5000"
```

```python
# tests/unit/core/collector/test_remote_collector.py
import pytest

from dba_assistant.core.collector.remote_collector import RemoteCollector


class EchoRemoteCollector(RemoteCollector[str, str]):
    def collect_readonly(self, collector_input: str) -> str:
        return collector_input.upper()


def test_remote_collector_enforces_readonly_mode() -> None:
    with pytest.raises(ValueError, match="read-only"):
        EchoRemoteCollector(readonly=False)


def test_remote_collector_uses_collect_readonly() -> None:
    collector = EchoRemoteCollector()

    assert collector.collect("redis") == "REDIS"
```

```python
# tests/unit/skills/redis_inspection_report/collectors/test_remote_redis_collector.py
from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.skills.redis_inspection_report.collectors.remote_redis_collector import (
    RedisInspectionRemoteCollector,
    RedisInspectionRemoteInput,
)


class FakeRedisAdaptor:
    def ping(self, connection: RedisConnectionConfig):
        return {"ok": True, "host": connection.host}

    def info(self, connection: RedisConnectionConfig, section=None):
        return {"role": "master", "section": section}

    def config_get(self, connection: RedisConnectionConfig, pattern="*"):
        return {"pattern": pattern}

    def slowlog_get(self, connection: RedisConnectionConfig, length=10):
        return [{"length": length}]

    def client_list(self, connection: RedisConnectionConfig):
        return [{"addr": "127.0.0.1:5000"}]


def test_remote_redis_collector_reads_structured_redis_snapshot() -> None:
    collector = RedisInspectionRemoteCollector(adaptor=FakeRedisAdaptor())
    result = collector.collect(
        RedisInspectionRemoteInput(
            connection=RedisConnectionConfig(host="redis.example"),
            info_section="server",
            config_pattern="max*",
            slowlog_length=5,
        )
    )

    assert result["ping"]["host"] == "redis.example"
    assert result["info"]["section"] == "server"
    assert result["config"]["pattern"] == "max*"
    assert result["slowlog"][0]["length"] == 5
```

- [ ] **Step 2: Run the adaptor and collector tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/unit/adaptors/test_redis_adaptor.py tests/unit/core/collector/test_remote_collector.py tests/unit/skills/redis_inspection_report/collectors/test_remote_redis_collector.py`

Expected: FAIL because the Redis adaptor and Phase 2 remote collector path are not implemented yet.

- [ ] **Step 3: Implement the Redis adaptor and remote collector path**

```python
# src/dba_assistant/adaptors/redis_adaptor.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from redis import Redis


@dataclass(frozen=True)
class RedisConnectionConfig:
    host: str
    port: int = 6379
    db: int = 0
    username: str | None = None
    password: str | None = None
    socket_timeout: float = 5.0


class RedisAdaptor:
    def __init__(self, client_factory: Callable[..., Any] = Redis) -> None:
        self._client_factory = client_factory

    def ping(self, connection: RedisConnectionConfig) -> dict[str, bool]:
        return {"ok": bool(self._run(connection, lambda client: client.ping()))}

    def info(self, connection: RedisConnectionConfig, *, section: str | None = None) -> dict[str, Any]:
        return dict(self._run(connection, lambda client: client.info(section=section)))

    def config_get(self, connection: RedisConnectionConfig, *, pattern: str = "*") -> dict[str, str]:
        return dict(self._run(connection, lambda client: client.config_get(pattern)))

    def slowlog_get(self, connection: RedisConnectionConfig, *, length: int = 10) -> list[dict[str, Any]]:
        return list(self._run(connection, lambda client: client.slowlog_get(length)))

    def client_list(self, connection: RedisConnectionConfig) -> list[dict[str, Any]]:
        return list(self._run(connection, lambda client: client.client_list()))

    def _connect(self, connection: RedisConnectionConfig):
        return self._client_factory(
            host=connection.host,
            port=connection.port,
            db=connection.db,
            username=connection.username,
            password=connection.password,
            socket_timeout=connection.socket_timeout,
            decode_responses=True,
        )

    def _run(self, connection: RedisConnectionConfig, callback):
        client = self._connect(connection)
        try:
            return callback(client)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
```

```python
# src/dba_assistant/adaptors/__init__.py
"""External adaptor package for DBA Assistant."""

from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig

__all__ = ["RedisAdaptor", "RedisConnectionConfig"]
```

```python
# src/dba_assistant/core/collector/remote_collector.py
"""Read-only remote collector base for Phase 2."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from dba_assistant.core.collector.types import ICollector


TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class RemoteCollector(ICollector[TInput, TOutput], Generic[TInput, TOutput], ABC):
    def __init__(self, *, readonly: bool = True) -> None:
        if not readonly:
            raise ValueError("Phase 2 remote collectors must remain read-only.")
        self.readonly = readonly

    def collect(self, collector_input: TInput) -> TOutput:
        return self.collect_readonly(collector_input)

    @abstractmethod
    def collect_readonly(self, collector_input: TInput) -> TOutput:
        raise NotImplementedError
```

```python
# src/dba_assistant/skills/redis_inspection_report/collectors/remote_redis_collector.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig
from dba_assistant.core.collector.remote_collector import RemoteCollector


@dataclass(frozen=True)
class RedisInspectionRemoteInput:
    connection: RedisConnectionConfig
    info_section: str | None = None
    config_pattern: str = "*"
    slowlog_length: int = 10


class RedisInspectionRemoteCollector(RemoteCollector[RedisInspectionRemoteInput, dict[str, Any]]):
    def __init__(self, adaptor: RedisAdaptor | None = None) -> None:
        super().__init__(readonly=True)
        self.adaptor = adaptor or RedisAdaptor()

    def collect_readonly(self, collector_input: RedisInspectionRemoteInput) -> dict[str, Any]:
        connection = collector_input.connection
        return {
            "ping": self.adaptor.ping(connection),
            "info": self.adaptor.info(connection, section=collector_input.info_section),
            "config": self.adaptor.config_get(connection, pattern=collector_input.config_pattern),
            "slowlog": self.adaptor.slowlog_get(connection, length=collector_input.slowlog_length),
            "clients": self.adaptor.client_list(connection),
        }
```

```python
# src/dba_assistant/skills/redis_inspection_report/collectors/__init__.py
"""Collectors for the Redis inspection report skill."""

from dba_assistant.skills.redis_inspection_report.collectors.remote_redis_collector import (
    RedisInspectionRemoteCollector,
    RedisInspectionRemoteInput,
)

__all__ = ["RedisInspectionRemoteCollector", "RedisInspectionRemoteInput"]
```

- [ ] **Step 4: Run the adaptor and collector tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/unit/adaptors/test_redis_adaptor.py tests/unit/core/collector/test_remote_collector.py tests/unit/skills/redis_inspection_report/collectors/test_remote_redis_collector.py`

Expected: PASS with `4 passed`.

- [ ] **Step 5: Commit the remote collection foundation**

```bash
git add src/dba_assistant/adaptors/__init__.py src/dba_assistant/adaptors/redis_adaptor.py src/dba_assistant/core/collector/remote_collector.py src/dba_assistant/skills/redis_inspection_report/collectors/__init__.py src/dba_assistant/skills/redis_inspection_report/collectors/remote_redis_collector.py tests/unit/adaptors/test_redis_adaptor.py tests/unit/core/collector/test_remote_collector.py tests/unit/skills/redis_inspection_report/collectors/test_remote_redis_collector.py
git commit -m "feat: add phase 2 redis remote path"
```

### Task 4: Register Read-Only Tools and Assemble the Phase 2 Agent

**Files:**
- Modify: `src/dba_assistant/deep_agent_integration/__init__.py`
- Create: `src/dba_assistant/deep_agent_integration/tool_registry.py`
- Create: `src/dba_assistant/deep_agent_integration/agent_factory.py`
- Create: `src/dba_assistant/deep_agent_integration/run.py`
- Create: `tests/unit/deep_agent_integration/test_tool_registry.py`
- Create: `tests/unit/deep_agent_integration/test_agent_factory.py`
- Create: `tests/unit/deep_agent_integration/test_run.py`

- [ ] **Step 1: Write the failing tests for tool registration, agent assembly, and run entry**

```python
# tests/unit/deep_agent_integration/test_tool_registry.py
from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.deep_agent_integration import tool_registry


def test_build_redis_tools_returns_the_expected_tool_names(monkeypatch) -> None:
    created = []

    class FakeTool:
        def __init__(self, func):
            self.name = func.__name__
            self.func = func
            created.append(self)

    monkeypatch.setattr(tool_registry, "function_tool", lambda func: FakeTool(func))

    tools = tool_registry.build_redis_tools(
        RedisConnectionConfig(host="redis.example"),
        adaptor=tool_registry.RedisAdaptor(client_factory=lambda **_: None),
    )

    assert [tool.name for tool in tools] == [
        "redis_ping",
        "redis_info",
        "redis_config_get",
        "redis_slowlog_get",
        "redis_client_list",
    ]
```

```python
# tests/unit/deep_agent_integration/test_agent_factory.py
from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.deep_agent_integration.agent_factory import build_phase2_agent
from dba_assistant.deep_agent_integration.config import AppConfig, ModelConfig, ProviderKind
from dba_assistant.deep_agent_integration import agent_factory


def build_config() -> AppConfig:
    return AppConfig(
        model=ModelConfig(
            preset_name="dashscope_cn_qwen35_flash",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3.5-flash",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="sk-test",
            api_key_env="DASHSCOPE_API_KEY",
        ),
        redis=RedisConnectionConfig(host="redis.example"),
    )


def test_build_phase2_agent_wires_model_tools_and_instructions(monkeypatch) -> None:
    captured = {}

    class FakeModelSettings:
        def __init__(self, temperature: float) -> None:
            self.temperature = temperature

    class FakeAgent:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(agent_factory, "build_model", lambda config: "MODEL")
    monkeypatch.setattr(agent_factory, "build_redis_tools", lambda redis, adaptor=None: ["TOOL"])
    monkeypatch.setattr(agent_factory, "ModelSettings", FakeModelSettings)
    monkeypatch.setattr(agent_factory, "Agent", FakeAgent)

    build_phase2_agent(build_config())

    assert captured["model"] == "MODEL"
    assert captured["tools"] == ["TOOL"]
    assert "read-only" in captured["instructions"].lower()
```

```python
# tests/unit/deep_agent_integration/test_run.py
from dba_assistant.deep_agent_integration import run


def test_run_phase2_uses_runner_and_returns_final_output(monkeypatch) -> None:
    class FakeResult:
        final_output = "redis looks healthy"

    monkeypatch.setattr(run, "load_app_config", lambda: "CONFIG")
    monkeypatch.setattr(run, "build_phase2_agent", lambda config: "AGENT")
    monkeypatch.setattr(run.Runner, "run_sync", lambda agent, prompt, max_turns: FakeResult())

    assert run.run_phase2("check redis") == "redis looks healthy"
```

- [ ] **Step 2: Run the assembly tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/unit/deep_agent_integration/test_tool_registry.py tests/unit/deep_agent_integration/test_agent_factory.py tests/unit/deep_agent_integration/test_run.py`

Expected: FAIL because the tool registry, agent factory, and run entry do not exist yet.

- [ ] **Step 3: Implement the tool registry, agent factory, and run entry**

```python
# src/dba_assistant/deep_agent_integration/__init__.py
"""Repository-owned Deep Agent SDK assembly layer for DBA Assistant."""

from dba_assistant.deep_agent_integration.agent_factory import build_phase2_agent
from dba_assistant.deep_agent_integration.config import AppConfig, ModelConfig, ProviderKind, load_app_config
from dba_assistant.deep_agent_integration.run import run_phase2

__all__ = [
    "AppConfig",
    "ModelConfig",
    "ProviderKind",
    "build_phase2_agent",
    "load_app_config",
    "run_phase2",
]
```

```python
# src/dba_assistant/deep_agent_integration/tool_registry.py
from __future__ import annotations

from typing import Any

from agents import function_tool

from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig


def build_redis_tools(
    connection: RedisConnectionConfig,
    *,
    adaptor: RedisAdaptor | None = None,
) -> list[object]:
    redis_adaptor = adaptor or RedisAdaptor()

    @function_tool
    def redis_ping() -> dict[str, bool]:
        """Ping the configured Redis target."""
        return redis_adaptor.ping(connection)

    @function_tool
    def redis_info(section: str | None = None) -> dict[str, Any]:
        """Read Redis INFO for the configured target."""
        return redis_adaptor.info(connection, section=section)

    @function_tool
    def redis_config_get(pattern: str = "*") -> dict[str, str]:
        """Read Redis CONFIG GET for the configured target."""
        return redis_adaptor.config_get(connection, pattern=pattern)

    @function_tool
    def redis_slowlog_get(length: int = 10) -> list[dict[str, Any]]:
        """Read Redis SLOWLOG GET for the configured target."""
        return redis_adaptor.slowlog_get(connection, length=length)

    @function_tool
    def redis_client_list() -> list[dict[str, Any]]:
        """Read Redis CLIENT LIST for the configured target."""
        return redis_adaptor.client_list(connection)

    return [
        redis_ping,
        redis_info,
        redis_config_get,
        redis_slowlog_get,
        redis_client_list,
    ]
```

```python
# src/dba_assistant/deep_agent_integration/agent_factory.py
from __future__ import annotations

from agents import Agent, ModelSettings

from dba_assistant.adaptors.redis_adaptor import RedisAdaptor
from dba_assistant.deep_agent_integration.config import AppConfig
from dba_assistant.deep_agent_integration.model_provider import build_model
from dba_assistant.deep_agent_integration.tool_registry import build_redis_tools


PHASE2_INSTRUCTIONS = """You are DBA Assistant in Phase 2.
Use only the registered read-only Redis tools.
Do not propose or execute write-capable Redis operations.
If configuration is missing or a tool fails, state the limitation directly.
"""


def build_phase2_agent(
    config: AppConfig,
    *,
    redis_adaptor: RedisAdaptor | None = None,
) -> Agent:
    model = build_model(config.model)
    tools = build_redis_tools(config.redis, adaptor=redis_adaptor)
    return Agent(
        name="DBA Assistant Phase 2",
        instructions=PHASE2_INSTRUCTIONS,
        model=model,
        model_settings=ModelSettings(temperature=config.model.temperature),
        tools=tools,
    )
```

```python
# src/dba_assistant/deep_agent_integration/run.py
from __future__ import annotations

from agents import Runner

from dba_assistant.deep_agent_integration.agent_factory import build_phase2_agent
from dba_assistant.deep_agent_integration.config import load_app_config


DEFAULT_PROMPT = "Use the registered read-only Redis tools to summarize the configured Redis target."


def run_phase2(prompt: str = DEFAULT_PROMPT) -> str:
    config = load_app_config()
    agent = build_phase2_agent(config)
    result = Runner.run_sync(agent, prompt, max_turns=config.model.max_turns)
    return str(result.final_output)


if __name__ == "__main__":
    print(run_phase2())
```

- [ ] **Step 4: Run the assembly tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/unit/deep_agent_integration/test_tool_registry.py tests/unit/deep_agent_integration/test_agent_factory.py tests/unit/deep_agent_integration/test_run.py`

Expected: PASS with `3 passed`.

- [ ] **Step 5: Commit the Deep Agent SDK assembly layer**

```bash
git add src/dba_assistant/deep_agent_integration/__init__.py src/dba_assistant/deep_agent_integration/tool_registry.py src/dba_assistant/deep_agent_integration/agent_factory.py src/dba_assistant/deep_agent_integration/run.py tests/unit/deep_agent_integration/test_tool_registry.py tests/unit/deep_agent_integration/test_agent_factory.py tests/unit/deep_agent_integration/test_run.py
git commit -m "feat: add phase 2 deep agent assembly"
```

### Task 5: Update Phase Docs, Pitfall Docs, and Run the Full Verification Suite

**Files:**
- Modify: `src/dba_assistant/README.md`
- Modify: `docs/phases/phase-1.md`
- Modify: `docs/phases/phase-2.md`
- Create: `docs/phase-2-model-configuration-pitfalls.md`

- [ ] **Step 1: Write the documentation changes**

```markdown
# src/dba_assistant/README.md

# dba_assistant Package

This package is the production code root for DBA Assistant.

Implemented package areas:

- `core/`: shared collector, analyzer, and reporter foundations
- `adaptors/`: live integration boundaries, with Redis direct access beginning in Phase 2
- `deep_agent_integration/`: repository-owned Deep Agent SDK assembly layer
- `skills/`: business-skill boundaries that gain implementation phase by phase
- `tools/`: reserved business-tool namespace

Reference-layer material under `src/claude-code-source-code/` and `src/docs/` remains non-production input only.
```

```markdown
# docs/phases/phase-1.md

# Phase 1: Architecture Foundation & Shared Layers

## Status

Delivered

## Goal

Establish the repository structure and deliver the interface definitions and offline implementations for the Collector, Reporter, and Template shared layers.

## Tasks

1. Establish repository directory structure and create `AGENTS.md`.
2. Define Collector interfaces and types.
   - Declare `ICollector<TInput, TOutput>`.
   - Implement an `OfflineCollector` base class that reads local files or directories, validates format, and outputs structured data.
   - Keep the Remote Collector at interface-definition level only.
3. Define Reporter interfaces and types.
   - Declare `IReporter<TAnalysis>`.
   - Implement `DocxReporter` to render analysis results into Word documents based on templates.
   - Implement `SummaryReporter` to format analysis results into terminal-readable structured output.
   - Keep PDF and HTML Reporters at interface-definition level only.
4. Establish the report template system.
   - Create `templates/reports/shared/` and implement shared components such as cover page, risk level styles, disclaimer, and related shared template elements.
   - Analyze historical report samples in `references/report-samples/`, extract content structure, and identify improvement areas.
   - Build initial standard template skeletons for RDB analysis and inspection reports.
5. Establish the reference file isolation directory and create usage-constraint documentation for it.
6. Set up the base testing framework and write unit tests for Collector and Reporter interfaces.

## Acceptance Criteria

- The Collector interface can be called by Skills, and the offline path can read local files and output structured data.
- The Reporter interface can be called by Skills, and at minimum `DocxReporter` and `SummaryReporter` are functional.
- Template skeletons are ready and can render a minimal Word document with a cover page, headings, and tables.
- Tests pass.

## Dependency Notes

- This is the foundation phase for later runtime, skill, and audit work.
- Current repository scaffold status is tracked separately in `docs/phases/current-scaffold-status.md`.
```

```markdown
# docs/phases/phase-2.md

# Phase 2: Runtime Assembly & Remote Collection Foundation

## Status

Delivered

## Goal

Assemble the repository into a minimal Deep Agent SDK application and implement one real read-only Redis remote collection path.

## Tasks

1. Create the repository-owned Deep Agent SDK assembly layer under `src/dba_assistant/deep_agent_integration/`.
2. Implement provider-capable model configuration with a default DashScope China preset plus optional DashScope International and Ollama-compatible presets.
3. Implement a real read-only Redis direct adaptor and one remote collector path built on top of it.
4. Register a bounded set of read-only Redis tools and assemble an integration-validation agent through the SDK.
5. Document provider, region, tracing, and OpenAI-compatible endpoint pitfalls.

## Acceptance Criteria

- The agent can invoke registered read-only Redis tools through Deep Agent SDK.
- The Redis direct adaptor is functional and does not expose write-capable operations.
- Provider preset switching does not require code changes in skills or adaptors.
- The repository does not introduce a custom runtime framework.
- SSH and MySQL live implementations remain deferred.

## Dependency Notes

- Depends on the shared-layer foundations established in Phase 1.
- Current repository scaffold status is tracked separately in `docs/phases/current-scaffold-status.md`.
```

```markdown
# docs/phase-2-model-configuration-pitfalls.md

# Phase 2 Model Configuration Pitfalls

As of 2026-04-01, Phase 2 uses OpenAI-compatible model configuration so the same integration layer can target DashScope and Ollama-style endpoints.

## Pitfall 1: The default China preset is not the free preset

The default preset is `dashscope_cn_qwen35_flash`, which uses:

- base URL: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- model: `qwen3.5-flash`

This preset is chosen for China-region usability, not because it is free.

## Pitfall 2: International free-tier assumptions can expire

The optional preset `dashscope_intl_qwen35_flash_free` exists because Alibaba documents an international free quota path for some new-user scenarios.

That free quota is vendor policy, not repository behavior. Re-check Alibaba pricing and quota policy before depending on it.

## Pitfall 3: Do not hardcode model settings outside the integration layer

`model_name`, `base_url`, API key source, tracing behavior, and max turns must remain in `src/dba_assistant/deep_agent_integration/config.py`.

Do not embed them into:

- skills
- collectors
- adaptors
- report logic

## Pitfall 4: OpenAI-compatible does not mean behavior-identical

DashScope and Ollama can both expose OpenAI-compatible endpoints, but tool-calling details, error payloads, and streaming behavior can still differ.

Treat provider switching as configuration-compatible, not behavior-guaranteed.

## Pitfall 5: Tracing may need special handling

When not using OpenAI Platform credentials, tracing may need to be disabled or replaced according to OpenAI Agents SDK guidance.

Phase 2 defaults tracing to disabled for safer provider portability.
```

- [ ] **Step 2: Run the full Phase 1 + Phase 2 verification suite**

Run: `.venv/bin/python -m pytest -q tests/unit/core/reporter/test_docx_reporter.py tests/unit/core/reporter/test_report_types.py tests/unit/core/reporter/test_template_specs.py tests/unit/core/reporter/test_summary_reporter.py tests/unit/core/collector/test_offline_collector.py tests/unit/deep_agent_integration/test_config.py tests/unit/deep_agent_integration/test_model_provider.py tests/unit/adaptors/test_redis_adaptor.py tests/unit/core/collector/test_remote_collector.py tests/unit/skills/redis_inspection_report/collectors/test_remote_redis_collector.py tests/unit/deep_agent_integration/test_tool_registry.py tests/unit/deep_agent_integration/test_agent_factory.py tests/unit/deep_agent_integration/test_run.py`

Expected: PASS with all tests green.

- [ ] **Step 3: Run git diff validation**

Run: `git diff --check`

Expected: PASS with no whitespace or conflict-marker issues.

- [ ] **Step 4: Commit the docs and final Phase 2 verification baseline**

```bash
git add src/dba_assistant/README.md docs/phases/phase-1.md docs/phases/phase-2.md docs/phase-2-model-configuration-pitfalls.md
git commit -m "docs: finalize phase 2 runtime assembly"
```

- [ ] **Step 5: Verify the feature branch is clean before branch completion**

```bash
git status -sb
```

Expected: working tree clean on the Phase 2 branch after the last commit.

## Self-Review

**Spec coverage:** The plan covers the repository-owned `deep_agent_integration/` layer, OpenAI-compatible model configuration, DashScope China and international presets, Ollama compatibility, a read-only Redis direct adaptor, one real remote collector path, tool registration, a minimal Phase 2 agent, a run entry, and the required phase and pitfall docs.

**Placeholder scan:** The plan does not use `TODO`, `TBD`, or deferred implementation placeholders inside task steps. SSH and MySQL remain deferred only because the approved spec explicitly keeps them out of `Phase 2`.

**Type consistency:** The plan uses one `AppConfig` root, one `ModelConfig` type, one `RedisConnectionConfig` type, one `RemoteCollector.collect_readonly()` contract, and one `build_phase2_agent()` / `run_phase2()` path across all later tasks.
