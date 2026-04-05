from pathlib import Path
from types import SimpleNamespace

from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
from dba_assistant.deep_agent_integration.config import AppConfig, ModelConfig, ProviderKind, RuntimeConfig
from dba_assistant.interface.hitl import AutoApproveHandler
from dba_assistant.orchestrator import agent as agent_module
from dba_assistant.capabilities.redis_rdb_analysis.remote_input import RemoteRedisDiscoveryError


def _make_config() -> AppConfig:
    return AppConfig(
        model=ModelConfig(
            preset_name="ollama_local",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3:8b",
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
        ),
        runtime=RuntimeConfig(default_output_mode="summary", redis_socket_timeout=5.0),
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

    request = _make_request()
    config = _make_config()
    handler = AutoApproveHandler()

    result = agent_module.run_orchestrated(request, config=config, approval_handler=handler)

    assert result == "analysis done"
    assert "messages" in captured["payload"]
    user_msg = captured["payload"]["messages"][0]["content"]
    assert "analyze rdb" in user_msg
    assert "/tmp/dump.rdb" in user_msg
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
    assert "cache:*" in msg


def test_build_unified_agent_wires_tools_and_model(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(agent_module, "build_model", lambda mc: "fake-model")
    monkeypatch.setattr(agent_module, "build_runtime_backend", lambda: "fake-backend")
    monkeypatch.setattr(agent_module, "get_memory_sources", lambda: ["/AGENTS.md"])
    monkeypatch.setattr(agent_module, "get_skill_sources", lambda: ["/skills"])
    monkeypatch.setattr(agent_module, "build_runtime_checkpointer", lambda: "fake-checkpointer")
    monkeypatch.setattr(
        agent_module,
        "build_all_tools",
        lambda req, connection=None, mysql_connection=None, remote_rdb_state=None: ["tool1", "tool2"],
    )

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
    assert captured["memory"] == ["/AGENTS.md"]
    assert captured["skills"] == ["/skills"]
    assert captured["checkpointer"] == "fake-checkpointer"
    assert captured["interrupt_on"]["fetch_remote_rdb_via_ssh"]["allowed_decisions"] == [
        "approve",
        "reject",
    ]
    assert "fetch_and_analyze_remote_rdb" not in captured["interrupt_on"]
    assert "read-only" in captured["system_prompt"].lower()
    assert "do not ask the user for dir/dbfilename first" in captured["system_prompt"].lower()


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

    request = _make_request()
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

    request = _make_request()
    config = _make_config()

    result = agent_module.run_orchestrated(
        request,
        config=config,
        approval_handler=AutoApproveHandler(approve=False),
    )

    assert "denied" in result.lower()


def test_build_remote_rdb_interrupt_description_includes_path_source(monkeypatch) -> None:
    request = _make_request(
        runtime_inputs=RuntimeInputs(
            redis_host="redis.example",
            redis_port=6379,
            ssh_host="ssh.example",
            ssh_port=2222,
            output_mode="summary",
        ),
        rdb_overrides=RdbOverrides(profile_name="generic"),
    )

    def fake_resolve(tool_args):
        return {
            "redis_dir": "/data/redis/data",
            "dbfilename": "actual.rdb",
            "remote_rdb_path": "/data/redis/data/actual.rdb",
            "remote_rdb_path_source": "discovered",
            "acquisition_mode": "fresh_snapshot",
            "bgsave_required": "yes",
            "discovery_status": "succeeded",
        }

    description = agent_module._build_remote_rdb_interrupt_description(
        request,
        path_resolution_resolver=fake_resolve,
    )

    text = description(
        {"args": {"profile_name": "rcs"}},
        None,
        None,
    )

    assert "/data/redis/data/actual.rdb" in text
    assert "/data/redis/data" in text
    assert "actual.rdb" in text
    assert "remote_rdb_path_source: discovered" in text
    assert "fresh_snapshot" in text
    assert "BGSAVE" in text
    assert "Discovery status: succeeded" in text


def test_build_remote_rdb_interrupt_description_reports_real_discovery_failure() -> None:
    request = _make_request(
        runtime_inputs=RuntimeInputs(
            redis_host="192.168.23.54",
            redis_port=6379,
            ssh_host="192.168.23.54",
            ssh_port=22,
            ssh_username="root",
            output_mode="summary",
            require_fresh_rdb_snapshot=True,
        ),
        secrets=Secrets(redis_password="123456", ssh_password="root"),
    )

    def fake_resolve(tool_args):
        return {
            "discovery_status": "failed",
            "discovery_error_stage": "config_get(dir)",
            "discovery_error_kind": "permission_denied",
            "discovery_error_message": "CONFIG GET dir not permitted by ACL",
            "remote_rdb_path": "",
            "remote_rdb_path_source": "unresolved",
            "acquisition_mode": "fresh_snapshot",
            "bgsave_required": "blocked",
        }

    description = agent_module._build_remote_rdb_interrupt_description(
        request,
        path_resolution_resolver=fake_resolve,
    )

    text = description({"args": {"acquisition_mode": "fresh_snapshot"}}, None, None)

    assert "Discovery status: failed" in text
    assert "Discovery failure stage: config_get(dir)" in text
    assert "Discovery failure kind: permission_denied" in text
    assert "CONFIG GET dir not permitted by ACL" in text
    assert "BGSAVE required: blocked" in text
    assert "Redis dir: unresolved" not in text
    assert "Redis dbfilename: unresolved" not in text


def test_remote_rdb_path_resolution_resolver_discovers_path_when_no_override(monkeypatch) -> None:
    request = _make_request(
        runtime_inputs=RuntimeInputs(
            redis_host="redis.example",
            redis_port=6379,
            output_mode="summary",
        )
    )
    connection = agent_module._build_connection(request, _make_config())

    class FakeRedisAdaptor:
        pass

    monkeypatch.setattr(agent_module, "RedisAdaptor", lambda: FakeRedisAdaptor())
    monkeypatch.setattr(
        agent_module,
        "discover_remote_rdb_snapshot",
        lambda adaptor, connection, remote_rdb_state=None: {
            "redis_dir": "/data/redis/data",
            "dbfilename": "dump.rdb",
            "rdb_path": "/data/redis/data/dump.rdb",
            "rdb_path_source": "discovered",
        },
    )

    resolver = agent_module._make_remote_rdb_path_resolution_resolver(
        request,
        connection=connection,
        remote_rdb_state={},
    )
    resolution = resolver({})

    assert resolution["redis_dir"] == "/data/redis/data"
    assert resolution["dbfilename"] == "dump.rdb"
    assert resolution["remote_rdb_path"] == "/data/redis/data/dump.rdb"
    assert resolution["remote_rdb_path_source"] == "discovered"
    assert resolution["discovery_status"] == "succeeded"


def test_remote_rdb_path_resolution_resolver_surfaces_discovery_failure(monkeypatch) -> None:
    request = _make_request(
        runtime_inputs=RuntimeInputs(
            redis_host="redis.example",
            redis_port=6379,
            ssh_host="ssh.example",
            ssh_port=22,
            ssh_username="root",
            output_mode="summary",
            require_fresh_rdb_snapshot=True,
        ),
        secrets=Secrets(redis_password="secret", ssh_password="root"),
    )
    connection = agent_module._build_connection(request, _make_config())

    class FakeRedisAdaptor:
        pass

    monkeypatch.setattr(agent_module, "RedisAdaptor", lambda: FakeRedisAdaptor())
    monkeypatch.setattr(
        agent_module,
        "discover_remote_rdb_snapshot",
        lambda adaptor, connection, remote_rdb_state=None: (_ for _ in ()).throw(
            RemoteRedisDiscoveryError(
                kind="authentication_failed",
                stage="ping",
                message="authentication_failed: invalid username-password pair or user is disabled",
            )
        ),
    )

    resolver = agent_module._make_remote_rdb_path_resolution_resolver(
        request,
        connection=connection,
        remote_rdb_state={},
    )
    resolution = resolver({"acquisition_mode": "fresh_snapshot"})

    assert resolution["discovery_status"] == "failed"
    assert resolution["discovery_error_stage"] == "ping"
    assert resolution["discovery_error_kind"] == "authentication_failed"
    assert "invalid username-password pair" in resolution["discovery_error_message"]
    assert resolution["bgsave_required"] == "blocked"
