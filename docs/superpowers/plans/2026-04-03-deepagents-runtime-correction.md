# Deep Agents Runtime Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the repository's incorrect `openai-agents` runtime wiring with a true `deepagents` runtime while preserving the existing DBA Assistant CLI, application contract, and Phase 2/3 business behavior.

**Architecture:** Keep `src/dba_assistant/deep_agent_integration/` as the repository-owned runtime glue layer, but reimplement it around `deepagents.create_deep_agent(...)` and LangChain chat model objects. Preserve prompt-first request flow in `application/`, keep tool boundaries unchanged, and explicitly load repository policy from root `AGENTS.md`.

**Tech Stack:** Python 3.11, `deepagents`, LangChain chat model integrations, PyYAML, pytest, redis-py, python-docx

---

### Task 1: Replace Runtime Dependencies And Fix Config/Test Baseline

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/unit/deep_agent_integration/test_config.py`
- Test: `tests/unit/deep_agent_integration/test_config.py`

- [ ] **Step 1: Write the failing dependency/config expectations**

```python
def test_load_app_config_uses_repo_default_path_outside_repo_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_app_config()

    assert DEFAULT_CONFIG_PATH.is_absolute()
    assert config.model.preset_name == "dashscope_cn_qwen35_flash"
    assert config.runtime.default_output_mode == "summary"
```

```python
def test_project_dependencies_include_deepagents_not_openai_agents() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert '"deepagents"' in pyproject
    assert '"openai-agents"' not in pyproject
```

- [ ] **Step 2: Run test to verify it fails before the dependency swap**

Run:

```bash
.venv/bin/python -m pytest -q tests/unit/deep_agent_integration/test_config.py -v
```

Expected:
- the default-path preset assertion matches the current repository config after correction
- the dependency assertion fails until `pyproject.toml` is updated

- [ ] **Step 3: Update runtime dependencies**

```toml
[project]
dependencies = [
    "deepagents",
    "langchain-openai",
    "PyYAML>=6,<7",
    "python-docx>=1.1,<2",
    "redis>=5",
    "PyMySQL>=1,<2",
    "paramiko>=3,<4",
    "rdbtools>=0.1,<1",
]
```

- [ ] **Step 4: Align config baseline tests with the current repository defaults**

```python
def test_load_app_config_uses_repo_default_path_outside_repo_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_app_config()

    assert DEFAULT_CONFIG_PATH.is_absolute()
    assert config.model.preset_name == "dashscope_cn_qwen35_flash"
    assert config.runtime.default_output_mode == "summary"
```

- [ ] **Step 5: Reinstall the editable environment and rerun the config tests**

Run:

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q tests/unit/deep_agent_integration/test_config.py -v
```

Expected:
- `test_config.py` passes
- the environment now resolves `deepagents` instead of `openai-agents`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/unit/deep_agent_integration/test_config.py
git commit -m "build: replace openai-agents with deepagents"
```

### Task 2: Rebuild The Runtime Glue Around Deep Agents

**Files:**
- Modify: `src/dba_assistant/deep_agent_integration/model_provider.py`
- Modify: `src/dba_assistant/deep_agent_integration/tool_registry.py`
- Modify: `src/dba_assistant/deep_agent_integration/agent_factory.py`
- Modify: `src/dba_assistant/deep_agent_integration/run.py`
- Create or Modify: `src/dba_assistant/deep_agent_integration/README.md`
- Test: `tests/unit/deep_agent_integration/test_model_provider.py`
- Test: `tests/unit/deep_agent_integration/test_tool_registry.py`
- Test: `tests/unit/deep_agent_integration/test_agent_factory.py`
- Test: `tests/unit/deep_agent_integration/test_run.py`

- [ ] **Step 1: Write failing runtime tests for deepagents-shaped behavior**

```python
def test_build_model_returns_langchain_openai_chat_model(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs) -> None:
            calls["kwargs"] = kwargs

    monkeypatch.setattr(model_provider, "ChatOpenAI", FakeChatOpenAI)

    model = model_provider.build_model(
        ModelConfig(
            preset_name="dashscope_cn_qwen35_flash",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3.5-flash",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="sk-cn",
            temperature=0.0,
        )
    )

    assert isinstance(model, FakeChatOpenAI)
    assert calls["kwargs"]["model"] == "qwen3.5-flash"
    assert calls["kwargs"]["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
```

```python
def test_build_phase2_agent_calls_create_deep_agent(monkeypatch) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setattr(agent_factory, "create_deep_agent", lambda **kwargs: calls.setdefault("kwargs", kwargs) or "agent")
    monkeypatch.setattr(agent_factory, "build_model", lambda config: "fake-model")
    monkeypatch.setattr(agent_factory, "build_redis_tools", lambda connection, adaptor=None: ["redis_ping"])

    result = agent_factory.build_phase2_agent(app_config, redis_connection)

    assert result == "agent"
    assert calls["kwargs"]["model"] == "fake-model"
    assert calls["kwargs"]["tools"] == ["redis_ping"]
```

```python
def test_run_phase2_request_invokes_deep_agent(monkeypatch) -> None:
    class FakeAgent:
        def invoke(self, payload):
            assert payload["messages"][0]["role"] == "user"
            return {"messages": [{"role": "assistant", "content": "phase2 ok"}]}

    monkeypatch.setattr(run_module, "build_phase2_agent", lambda *args, **kwargs: FakeAgent())

    result = run_module.run_phase2_request("inspect redis", config=config, redis_connection=connection)

    assert "phase2 ok" in result
```

- [ ] **Step 2: Run the runtime unit tests to capture the red state**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/unit/deep_agent_integration/test_model_provider.py \
  tests/unit/deep_agent_integration/test_tool_registry.py \
  tests/unit/deep_agent_integration/test_agent_factory.py \
  tests/unit/deep_agent_integration/test_run.py -v
```

Expected:
- failures referencing `agents`, `Runner`, `function_tool`, or old model assumptions

- [ ] **Step 3: Implement the deepagents model/provider path**

```python
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

def build_model(config: ModelConfig) -> ChatOpenAI:
    if config.provider_kind is not ProviderKind.OPENAI_COMPATIBLE:
        raise ValueError(f"Unsupported provider kind: {config.provider_kind}")

    return ChatOpenAI(
        model=config.model_name,
        base_url=config.base_url,
        api_key=config.api_key,
        temperature=config.temperature,
        stream_usage=False,
    )
```

- [ ] **Step 4: Implement deepagents agent assembly with explicit repository memory**

```python
def build_phase2_agent(
    config: AppConfig,
    redis_connection: RedisConnectionConfig,
    redis_adaptor: RedisAdaptor | None = None,
):
    model = build_model(config.model)
    tools = build_redis_tools(redis_connection, adaptor=redis_adaptor)
    memory = [str(Path(__file__).resolve().parents[3] / "AGENTS.md")]

    return create_deep_agent(
        model=model,
        tools=tools,
        instructions="You are the Phase 2 integration-validation agent for DBA Assistant. Use only the provided read-only Redis tools.",
        memory=memory,
    )
```

- [ ] **Step 5: Replace `function_tool` wrapping with deepagents-compatible tool callables**

```python
def build_redis_tools(connection: RedisConnectionConfig, adaptor: RedisAdaptor | None = None) -> list:
    redis_adaptor = adaptor or RedisAdaptor()
    return [
        _make_ping_tool(redis_adaptor, connection),
        _make_info_tool(redis_adaptor, connection),
        _make_config_get_tool(redis_adaptor, connection),
        _make_slowlog_get_tool(redis_adaptor, connection),
        _make_client_list_tool(redis_adaptor, connection),
    ]
```

```python
def _make_ping_tool(adaptor: RedisAdaptor, connection: RedisConnectionConfig):
    def redis_ping() -> dict[str, bool]:
        return adaptor.ping(connection)

    redis_ping.__name__ = "redis_ping"
    redis_ping.__doc__ = "Ping Redis and return a structured availability payload."
    return redis_ping
```

- [ ] **Step 6: Replace `Runner.run_sync(...)` with deep agent invocation**

```python
def run_phase2_request(
    prompt: str,
    *,
    config: AppConfig,
    redis_connection: RedisConnectionConfig,
) -> str:
    agent = build_phase2_agent(config, redis_connection)
    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    return _extract_final_text(result)
```

- [ ] **Step 7: Update runtime README to describe deepagents semantics**

```md
# deep_agent_integration

This package contains the repository-owned Deep Agents SDK assembly layer.

Its responsibilities are limited to:

- loading static application configuration
- building provider-compatible LangChain chat models
- registering bounded model-visible tools
- constructing the minimal Deep Agents runtime
- explicitly loading repository policy from `AGENTS.md`
- invoking the deep agent for normalized requests
```

- [ ] **Step 8: Run the runtime unit tests to verify the green state**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/unit/deep_agent_integration/test_model_provider.py \
  tests/unit/deep_agent_integration/test_tool_registry.py \
  tests/unit/deep_agent_integration/test_agent_factory.py \
  tests/unit/deep_agent_integration/test_run.py -v
```

Expected:
- all runtime unit tests pass against `deepagents`

- [ ] **Step 9: Commit**

```bash
git add \
  src/dba_assistant/deep_agent_integration/model_provider.py \
  src/dba_assistant/deep_agent_integration/tool_registry.py \
  src/dba_assistant/deep_agent_integration/agent_factory.py \
  src/dba_assistant/deep_agent_integration/run.py \
  src/dba_assistant/deep_agent_integration/README.md \
  tests/unit/deep_agent_integration/test_model_provider.py \
  tests/unit/deep_agent_integration/test_tool_registry.py \
  tests/unit/deep_agent_integration/test_agent_factory.py \
  tests/unit/deep_agent_integration/test_run.py
git commit -m "refactor: migrate runtime glue to deepagents"
```

### Task 3: Correct Docs And Protect Existing Application Behavior

**Files:**
- Modify: `docs/phases/phase-2.md`
- Modify: `docs/superpowers/specs/2026-04-01-phase-2-runtime-assembly-design.md`
- Modify: `src/dba_assistant/application/service.py` only if runtime extraction changes require it
- Test: `tests/unit/application/`
- Test: `tests/unit/tools/`
- Test: `tests/unit/skills/redis_rdb_analysis/`

- [ ] **Step 1: Write or update regression assertions for the preserved application contract**

```python
def test_execute_request_uses_phase2_runtime_for_redis_requests(monkeypatch) -> None:
    monkeypatch.setattr(service, "run_phase2_request", lambda prompt, **kwargs: "phase2 ok")
    result = service.execute_request(redis_request, config=app_config)
    assert result == "phase2 ok"
```

```python
def test_execute_request_keeps_phase3_local_rdb_path_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(service, "analyze_rdb_tool", lambda *args, **kwargs: {"path": "direct_memory_analysis"})
    monkeypatch.setattr(service, "generate_analysis_report", lambda *args, **kwargs: FakeArtifact(content="summary"))
    assert service.execute_request(rdb_request, config=app_config) == "summary"
```

- [ ] **Step 2: Run the affected application/path tests before doc edits**

Run:

```bash
.venv/bin/python -m pytest -q tests/unit/application tests/unit/tools tests/unit/skills/redis_rdb_analysis -v
```

Expected:
- tests pass or expose any runtime coupling that the migration must keep intact

- [ ] **Step 3: Correct the Phase 2 docs and runtime wording**

Update the docs so they say, in substance:

```md
- The repository uses Deep Agents SDK as the runtime foundation.
- The runtime glue is implemented with `deepagents`, not OpenAI Agents SDK.
- The repository explicitly loads project policy from root `AGENTS.md`.
```

- [ ] **Step 4: Rerun the affected regression suites after the doc/runtime cleanup**

Run:

```bash
.venv/bin/python -m pytest -q tests/unit/application tests/unit/tools tests/unit/skills/redis_rdb_analysis -v
```

Expected:
- preserved application behavior remains green

- [ ] **Step 5: Commit**

```bash
git add \
  docs/phases/phase-2.md \
  docs/superpowers/specs/2026-04-01-phase-2-runtime-assembly-design.md \
  src/dba_assistant/application/service.py
git commit -m "docs: align runtime docs with deepagents"
```

### Task 4: Full Verification And Integration

**Files:**
- Modify: any small follow-up fixes required by verification
- Test: repository-wide suites touched by Phase 2 and Phase 3

- [ ] **Step 1: Run the focused full verification suite**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/unit/deep_agent_integration \
  tests/unit/application \
  tests/unit/tools \
  tests/unit/skills/redis_rdb_analysis
```

Expected:
- all targeted tests pass

- [ ] **Step 2: Run syntax and diff hygiene checks**

Run:

```bash
PYTHONPYCACHEPREFIX=/tmp/dba_assistant_deepagents_pycache .venv/bin/python -m py_compile \
  src/dba_assistant/deep_agent_integration/*.py \
  src/dba_assistant/application/*.py \
  src/dba_assistant/tools/*.py
git diff --check
```

Expected:
- `py_compile` exits `0`
- `git diff --check` prints nothing

- [ ] **Step 3: Run a CLI smoke test that proves prompt-first behavior still works**

Run:

```bash
.venv/bin/dba-assistant ask "按 generic profile 分析这个 rdb，输出 summary" \
  --input tests/fixtures/rdb/precomputed/sample_precomputed_rows.json \
  --profile generic
```

Expected:
- command exits `0`
- output is a summary or expected path-oriented report response

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "test: verify deepagents runtime migration"
```
