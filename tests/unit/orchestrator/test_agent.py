from pathlib import Path
from types import SimpleNamespace

from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
from dba_assistant.core.observability import start_execution_session
from dba_assistant.deep_agent_integration.config import (
    AgentConfig,
    AppConfig,
    FilesystemBackendConfig,
    ModelConfig,
    PathsConfig,
    ProviderKind,
    RuntimeConfig,
)
from dba_assistant.interface.hitl import AutoApproveHandler
from dba_assistant.interface.types import InterfaceSurface
from dba_assistant.orchestrator import agent as agent_module


def _make_config(*, filesystem_root: Path | None = None) -> AppConfig:
    filesystem_root = filesystem_root or Path("/agent-root")
    return AppConfig(
        model=ModelConfig(
            preset_name="ollama_local",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3:8b",
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
        ),
        runtime=RuntimeConfig(default_output_mode="summary", redis_socket_timeout=5.0),
        agent=AgentConfig(
            filesystem_backend=FilesystemBackendConfig(
                kind="filesystem",
                root_dir=filesystem_root,
                virtual_mode=False,
            )
        ),
        paths=PathsConfig(
            artifact_dir=filesystem_root / "artifacts",
            evidence_dir=filesystem_root / "evidence",
            temp_dir=filesystem_root / "tmp",
        ),
    )


def _make_request(**overrides) -> NormalizedRequest:
    defaults = dict(
        raw_prompt="analyze rdb",
        prompt="analyze rdb",
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            input_paths=(Path("/tmp/dump.rdb"),),
        ),
        secrets=Secrets(),
        rdb_overrides=RdbOverrides(profile_name="generic"),
    )
    defaults.update(overrides)
    return NormalizedRequest(**defaults)


def test_run_orchestrated_invokes_agent_and_returns_output(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeAgent:
        def invoke(self, payload, config=None):
            captured["payload"] = payload
            captured["config"] = config
            return {"messages": [{"role": "assistant", "content": "analysis done"}]}

    monkeypatch.setattr(
        agent_module,
        "build_unified_agent",
        lambda request, config, approval_handler: FakeAgent(),
    )

    request = _make_request(
        runtime_inputs=RuntimeInputs(output_mode="summary"),
    )
    config = _make_config()
    handler = AutoApproveHandler()

    result = agent_module.run_orchestrated(request, config=config, approval_handler=handler)

    assert result == "analysis done"
    assert "messages" in captured["payload"]
    user_msg = captured["payload"]["messages"][0]["content"]
    assert "analyze rdb" in user_msg
    assert "Output: summary / summary" in user_msg
    assert captured["config"]["configurable"]["thread_id"]


def test_build_user_message_includes_context() -> None:
    request = _make_request(
        runtime_inputs=RuntimeInputs(
            redis_host="redis.example",
            redis_port=6379,
            input_kind="preparsed_mysql",
            path_mode="preparsed_dataset_analysis",
            ssh_host="ssh.example",
            ssh_port=2222,
            ssh_username="root",
            require_fresh_rdb_snapshot=True,
            mysql_host="db.example",
            mysql_port=3306,
            mysql_user="analyst",
            mysql_database="analysis_db",
            mysql_table="preparsed_keys",
            mysql_query="SELECT * FROM preparsed_keys",
            output_mode="report",
            report_format="docx",
            output_path=Path("/tmp/out.docx"),
            input_paths=(Path("/tmp/dump.rdb"),),
            filesystem_root_dir=Path("/configured-agent-root"),
            artifact_dir=Path("/configured-agent-root/artifacts"),
            evidence_dir=Path("/configured-agent-root/evidence"),
        ),
        secrets=Secrets(redis_password="secret", ssh_password="ssh-secret"),
        rdb_overrides=RdbOverrides(
            profile_name="rcs",
            focus_prefixes=("cache:*", "session:*"),
        ),
    )

    msg = agent_module._build_user_message(request)

    assert "analyze rdb" in msg
    assert "/tmp/dump.rdb" in msg
    assert "preparsed_mysql" in msg
    assert "preparsed_dataset_analysis" in msg
    assert "redis.example:6379" in msg
    assert "ssh.example:2222" in msg
    assert "secure context" in msg
    assert "fresh_snapshot" in msg
    assert "db.example:3306" in msg
    assert "preparsed_keys" in msg
    assert "SELECT * FROM preparsed_keys" in msg
    assert "rcs" in msg
    assert "report / docx" in msg
    assert "/tmp/out.docx" in msg
    assert "Agent filesystem backend root: /configured-agent-root" in msg
    assert "Artifact directory: /configured-agent-root/artifacts" in msg
    assert "Evidence directory: /configured-agent-root/evidence" in msg
    assert "cache:*" in msg


def test_build_unified_agent_wires_tools_and_model(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(agent_module, "build_model", lambda mc: "fake-model")
    def fake_build_runtime_backend(filesystem_backend_config):
        captured["filesystem_backend_config"] = filesystem_backend_config
        return "fake-backend"

    monkeypatch.setattr(agent_module, "build_runtime_backend", fake_build_runtime_backend)
    monkeypatch.setattr(agent_module, "get_memory_sources", lambda: ["/AGENTS.md"])
    monkeypatch.setattr(agent_module, "get_skill_sources", lambda: ["/skills"])
    monkeypatch.setattr(agent_module, "build_runtime_checkpointer", lambda: "fake-checkpointer")
    monkeypatch.setattr(
        agent_module,
        "build_all_tools",
        lambda req, config=None, connection=None, mysql_connection=None, remote_rdb_state=None, approval_handler=None: ["tool1", "tool2"],
    )
    monkeypatch.setattr(agent_module, "_load_system_prompt", lambda: "prompt from file")

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs)
        return "fake-agent"

    monkeypatch.setattr(agent_module, "create_deep_agent", fake_create_deep_agent)

    request = _make_request()
    config = _make_config()
    handler = AutoApproveHandler()

    agent = agent_module.build_unified_agent(request, config, handler)

    assert agent == "fake-agent"
    assert captured["name"] == "dba-assistant"
    assert captured["model"] == "fake-model"
    assert captured["tools"] == ["tool1", "tool2"]
    assert captured["backend"] == "fake-backend"
    assert captured["filesystem_backend_config"] == config.agent.filesystem_backend
    assert captured["memory"] == ["/AGENTS.md"]
    assert captured["skills"] == ["/skills"]
    assert captured["checkpointer"] == "fake-checkpointer"
    assert captured["interrupt_on"]["ensure_remote_rdb_snapshot"]["allowed_decisions"] == [
        "approve",
        "reject",
    ]
    assert captured["interrupt_on"]["fetch_remote_rdb_via_ssh"]["allowed_decisions"] == [
        "approve",
        "reject",
    ]
    assert captured["interrupt_on"]["stage_local_rdb_to_mysql"]["allowed_decisions"] == [
        "approve",
        "reject",
    ]
    assert "fetch_and_analyze_remote_rdb" not in captured["interrupt_on"]
    assert captured["system_prompt"] == "prompt from file"


def test_load_system_prompt_reads_external_file(monkeypatch, tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("external prompt", encoding="utf-8")
    monkeypatch.setattr(agent_module, "SYSTEM_PROMPT_PATH", prompt_path)
    agent_module._load_system_prompt.cache_clear()

    try:
        assert agent_module._load_system_prompt() == "external prompt"
    finally:
        agent_module._load_system_prompt.cache_clear()


def test_run_orchestrated_returns_docx_artifact_path_when_contract_is_satisfied(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "report.docx"
    output_path.write_text("docx-placeholder", encoding="utf-8")

    class FakeAgent:
        def invoke(self, payload, config=None):
            session = agent_module.get_current_execution_session()
            assert session is not None
            session.record_tool_result(
                tool_name="analyze_local_rdb_stream",
                tool_args_summary={"report_format": "docx", "output_path": str(output_path)},
                status="success",
                started_at="2026-04-10T00:00:00+00:00",
                ended_at="2026-04-10T00:00:01+00:00",
                duration_ms=1,
            )
            session.record_artifact(
                output_mode="report",
                output_path=output_path,
                artifact_id="artifact-1",
                report_metadata={"route": "direct_rdb_analysis"},
            )
            return {"messages": [{"role": "assistant", "content": "inline summary"}]}

    monkeypatch.setattr(
        agent_module,
        "build_unified_agent",
        lambda request, config, approval_handler: FakeAgent(),
    )

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="report",
            report_format="docx",
            output_path=output_path,
            input_paths=(Path("/tmp/dump.rdb"),),
        ),
    )

    with start_execution_session(
        interface_surface=InterfaceSurface.CLI,
        normalized_request=request,
        raw_request_summary={},
    ):
        result = agent_module.run_orchestrated(
            request,
            config=_make_config(),
            approval_handler=AutoApproveHandler(),
        )

    assert result == str(output_path)


def test_run_orchestrated_fails_when_docx_contract_is_selected_but_no_artifact_exists(
    monkeypatch,
) -> None:
    class FakeAgent:
        def invoke(self, payload, config=None):
            session = agent_module.get_current_execution_session()
            assert session is not None
            session.record_tool_result(
                tool_name="analyze_local_rdb_stream",
                tool_args_summary={"report_format": "docx", "output_path": "/tmp/missing.docx"},
                status="success",
                started_at="2026-04-10T00:00:00+00:00",
                ended_at="2026-04-10T00:00:01+00:00",
                duration_ms=1,
            )
            return {"messages": [{"role": "assistant", "content": "inline summary"}]}

    monkeypatch.setattr(
        agent_module,
        "build_unified_agent",
        lambda request, config, approval_handler: FakeAgent(),
    )

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="report",
            report_format="docx",
            output_path=Path("/tmp/missing.docx"),
            input_paths=(Path("/tmp/dump.rdb"),),
        ),
    )

    with start_execution_session(
        interface_surface=InterfaceSurface.CLI,
        normalized_request=request,
        raw_request_summary={},
    ):
        result = agent_module.run_orchestrated(
            request,
            config=_make_config(),
            approval_handler=AutoApproveHandler(),
        )

    assert "artifact contract violated" in result.lower()


def test_run_orchestrated_approves_interrupt_and_resumes(monkeypatch) -> None:
    captured: dict[str, object] = {"calls": 0}

    class FakeInterrupt:
        def __init__(self, value):
            self.value = value

    class FakeAgent:
        def invoke(self, payload, config=None):
            captured["calls"] += 1
            if captured["calls"] == 1:
                return {
                    "__interrupt__": [
                        FakeInterrupt(
                            {
                                "action_requests": [
                                    {
                                        "name": "fetch_remote_rdb_via_ssh",
                                        "args": {"profile_name": "rcs"},
                                        "description": "Fetch remote RDB for approval",
                                    }
                                ],
                                "review_configs": [
                                    {
                                        "action_name": "fetch_remote_rdb_via_ssh",
                                        "allowed_decisions": ["approve", "reject"],
                                    }
                                ],
                            }
                        )
                    ]
                }
            captured["resume_payload"] = payload
            captured["resume_config"] = config
            return {"messages": [{"role": "assistant", "content": "analysis done"}]}

    monkeypatch.setattr(
        agent_module,
        "build_unified_agent",
        lambda request, config, approval_handler: FakeAgent(),
    )

    request = _make_request(
        runtime_inputs=RuntimeInputs(output_mode="summary"),
    )
    config = _make_config()

    result = agent_module.run_orchestrated(
        request,
        config=config,
        approval_handler=AutoApproveHandler(approve=True),
    )

    assert result == "analysis done"
    assert captured["calls"] == 2
    resume = captured["resume_payload"].resume
    assert resume["decisions"] == [{"type": "approve"}]
    assert captured["resume_config"]["configurable"]["thread_id"]


def test_run_orchestrated_returns_denial_message_when_interrupt_rejected(monkeypatch) -> None:
    class FakeInterrupt:
        def __init__(self, value):
            self.value = value

    class FakeAgent:
        def invoke(self, payload, config=None):
            return {
                "__interrupt__": [
                    FakeInterrupt(
                        {
                            "action_requests": [
                                {
                                    "name": "fetch_remote_rdb_via_ssh",
                                    "args": {},
                                    "description": "Fetch remote RDB for approval",
                                }
                            ],
                            "review_configs": [
                                {
                                    "action_name": "fetch_remote_rdb_via_ssh",
                                    "allowed_decisions": ["approve", "reject"],
                                }
                            ],
                        }
                    )
                ]
            }

    monkeypatch.setattr(
        agent_module,
        "build_unified_agent",
        lambda request, config, approval_handler: FakeAgent(),
    )

    request = _make_request(
        runtime_inputs=RuntimeInputs(output_mode="summary"),
    )
    config = _make_config()

    result = agent_module.run_orchestrated(
        request,
        config=config,
        approval_handler=AutoApproveHandler(approve=False),
    )

    assert "denied" in result.lower()


def test_run_orchestrated_resumes_with_fallback_when_mysql_staging_interrupt_rejected(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {"calls": 0}

    class FakeInterrupt:
        def __init__(self, value):
            self.value = value

    class FakeAgent:
        def invoke(self, payload, config=None):
            captured["calls"] += 1
            if captured["calls"] == 1:
                return {
                    "__interrupt__": [
                        FakeInterrupt(
                            {
                                "action_requests": [
                                    {
                                        "name": "stage_local_rdb_to_mysql",
                                        "args": {
                                            "input_paths": "/tmp/large.rdb",
                                            "mysql_host": "127.0.0.1",
                                            "mysql_table": "rdb_stage",
                                        },
                                        "description": "Stage local RDB into MySQL for approval",
                                    }
                                ],
                                "review_configs": [
                                    {
                                        "action_name": "stage_local_rdb_to_mysql",
                                        "allowed_decisions": ["approve", "reject"],
                                    }
                                ],
                            }
                        )
                    ]
                }
            captured["resume_payload"] = payload
            return {
                "messages": [
                    {
                        "role": "assistant",
                        "content": "User rejected MySQL staging; falling back to streaming analysis.",
                    }
                ]
            }

    monkeypatch.setattr(
        agent_module,
        "build_unified_agent",
        lambda request, config, approval_handler: FakeAgent(),
    )

    request = _make_request(
        runtime_inputs=RuntimeInputs(output_mode="summary"),
    )

    result = agent_module.run_orchestrated(
        request,
        config=_make_config(),
        approval_handler=AutoApproveHandler(approve=False),
    )

    assert "falling back to streaming analysis" in result.lower()
    assert captured["calls"] == 2
    assert captured["resume_payload"].resume["decisions"] == [{"type": "reject"}]


def test_run_orchestrated_forces_runtime_approval_instead_of_returning_plain_text_question(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {"calls": 0}

    class FakeInterrupt:
        def __init__(self, value):
            self.value = value

    class FakeAgent:
        def __init__(self) -> None:
            self._dba_remote_rdb_state = {
                "discovery": {
                    "rdb_path": "/data/redis/data/dump.rdb",
                    "requires_confirmation": True,
                }
            }

        def invoke(self, payload, config=None):
            captured["calls"] += 1
            if captured["calls"] == 1:
                captured["first_payload"] = payload
                return {
                    "messages": [
                        {
                            "role": "assistant",
                            "content": (
                                "Good! I've discovered the remote RDB location. "
                                "Now I need your approval. Do you approve proceeding?"
                            ),
                        }
                    ]
                }
            if captured["calls"] == 2:
                captured["second_payload"] = payload
                return {
                    "__interrupt__": [
                        FakeInterrupt(
                            {
                                "action_requests": [
                                    {
                                        "name": "fetch_remote_rdb_via_ssh",
                                        "args": {"acquisition_mode": "existing"},
                                        "description": "Fetch remote RDB for approval",
                                    }
                                ],
                                "review_configs": [
                                    {
                                        "action_name": "fetch_remote_rdb_via_ssh",
                                        "allowed_decisions": ["approve", "reject"],
                                    }
                                ],
                            }
                        )
                    ]
                }
            captured["resume_payload"] = payload
            return {"messages": [{"role": "assistant", "content": "analysis done"}]}

    monkeypatch.setattr(
        agent_module,
        "build_unified_agent",
        lambda request, config, approval_handler: FakeAgent(),
    )

    result = agent_module.run_orchestrated(
        _make_request(
            runtime_inputs=RuntimeInputs(
                redis_host="192.168.23.54",
                redis_port=6379,
                ssh_host="192.168.23.54",
                ssh_port=22,
                ssh_username="root",
                output_mode="summary",
            ),
            secrets=Secrets(redis_password="123456", ssh_password="root"),
        ),
        config=_make_config(),
        approval_handler=AutoApproveHandler(approve=True),
    )

    assert result == "analysis done"
    assert captured["calls"] == 3
    second_message = captured["second_payload"]["messages"][0]["content"]
    assert "call fetch_remote_rdb_via_ssh now" in second_message.lower()


def test_run_orchestrated_returns_policy_error_when_model_keeps_plain_text_approval_prompt(
    monkeypatch,
) -> None:
    class FakeAgent:
        def __init__(self) -> None:
            self._dba_remote_rdb_state = {
                "discovery": {
                    "rdb_path": "/data/redis/data/dump.rdb",
                    "requires_confirmation": True,
                }
            }
            self.calls = 0

        def invoke(self, payload, config=None):
            self.calls += 1
            return {
                "messages": [
                    {
                        "role": "assistant",
                        "content": "Please confirm whether I should proceed. Do you approve?",
                    }
                ]
            }

    monkeypatch.setattr(
        agent_module,
        "build_unified_agent",
        lambda request, config, approval_handler: FakeAgent(),
    )

    result = agent_module.run_orchestrated(
        _make_request(
            runtime_inputs=RuntimeInputs(
                redis_host="192.168.23.54",
                redis_port=6379,
                ssh_host="192.168.23.54",
                ssh_port=22,
                ssh_username="root",
                output_mode="summary",
            ),
            secrets=Secrets(redis_password="123456", ssh_password="root"),
        ),
        config=_make_config(),
        approval_handler=AutoApproveHandler(approve=True),
    )

    assert "policy violation" in result.lower()
    assert "do you approve" not in result.lower()


def test_build_remote_rdb_interrupt_description_uses_tool_args() -> None:
    request = _make_request(
        runtime_inputs=RuntimeInputs(
            ssh_host="ssh.example",
            ssh_port=2222,
            output_mode="summary",
        ),
        rdb_overrides=RdbOverrides(profile_name="generic"),
    )

    description = agent_module._build_remote_rdb_interrupt_description(
        request,
    )

    text = description(
        {
            "args": {
                "remote_rdb_path": "/data/redis/data/actual.rdb",
                "ssh_host": "192.168.23.54",
                "ssh_port": 22,
                "ssh_username": "root",
                "local_directory": "/tmp",
            }
        },
        None,
        None,
    )

    assert "/data/redis/data/actual.rdb" in text
    assert "192.168.23.54:22" in text
    assert "root" in text
    assert "/tmp" in text


def test_build_remote_snapshot_interrupt_description_uses_tool_args() -> None:
    request = _make_request(
        runtime_inputs=RuntimeInputs(
            redis_host="192.168.23.54",
            redis_port=6379,
            output_mode="summary",
        ),
        secrets=Secrets(redis_password="123456"),
    )

    description = agent_module._build_remote_snapshot_interrupt_description(request)
    text = description(
        {
            "args": {
                "redis_host": "192.168.23.54",
                "redis_port": 6379,
                "redis_db": 0,
                "remote_rdb_path": "/data/redis/dump.rdb",
            }
        },
        None,
        None,
    )

    assert "192.168.23.54:6379" in text
    assert "Redis DB: 0" in text
    assert "/data/redis/dump.rdb" in text
    assert "BGSAVE" in text


def test_build_connection_threads_redis_password_into_connection() -> None:
    request = _make_request(
        runtime_inputs=RuntimeInputs(
            redis_host="192.168.23.54",
            redis_port=6379,
            redis_db=3,
            output_mode="summary",
        ),
        secrets=Secrets(redis_password="123456"),
    )

    connection = agent_module._build_connection(request, _make_config())

    assert connection is not None
    assert connection.host == "192.168.23.54"
    assert connection.port == 6379
    assert connection.db == 3
    assert connection.password == "123456"


def test_build_connection_uses_loopback_defaults_for_remote_redis_context() -> None:
    request = _make_request(
        prompt="inspect local redis",
        runtime_inputs=RuntimeInputs(
            input_kind="remote_redis",
            output_mode="summary",
        ),
    )

    connection = agent_module._build_connection(request, _make_config())

    assert connection is not None
    assert connection.host == "127.0.0.1"
    assert connection.port == 6379
    assert connection.db == 0


def test_build_mysql_connection_uses_defaults_for_database_backed_analysis() -> None:
    request = _make_request(
        prompt="analyze this rdb via mysql",
        runtime_inputs=RuntimeInputs(
            path_mode="database_backed_analysis",
            input_paths=(Path("/tmp/dump.rdb"),),
            output_mode="summary",
        ),
    )

    connection = agent_module._build_mysql_connection(request, _make_config())

    assert connection is not None
    assert connection.host == "127.0.0.1"
    assert connection.port == 3306
    assert connection.user == "root"
    assert connection.database == "dba_assistant_staging"
    assert connection.connect_timeout_seconds == 5.0
    assert connection.read_timeout_seconds == 15.0
    assert connection.write_timeout_seconds == 30.0
