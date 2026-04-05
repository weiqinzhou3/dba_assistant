from pathlib import Path

from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
from dba_assistant.capabilities.redis_rdb_analysis.remote_input import RemoteRedisDiscoveryError
from dba_assistant.deep_agent_integration.config import AppConfig, ModelConfig, ProviderKind, RuntimeConfig
from dba_assistant.interface.hitl import AutoApproveHandler
from dba_assistant.orchestrator import agent as agent_module


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


def _make_request() -> NormalizedRequest:
    return NormalizedRequest(
        raw_prompt="analyze remote redis",
        prompt="analyze remote redis",
        runtime_inputs=RuntimeInputs(
            redis_host="192.168.23.54",
            redis_port=6379,
            ssh_host="192.168.23.54",
            ssh_port=22,
            ssh_username="root",
            output_mode="summary",
            require_fresh_rdb_snapshot=True,
            input_paths=(Path("/tmp/dump.rdb"),),
        ),
        secrets=Secrets(redis_password="123456", ssh_password="root"),
        rdb_overrides=RdbOverrides(profile_name="generic"),
    )


def test_run_orchestrated_surfaces_real_discovery_failure_through_approval_and_final_output(monkeypatch) -> None:
    approval: dict[str, str] = {}

    class FakeInterrupt:
        def __init__(self, value):
            self.value = value

    monkeypatch.setattr(agent_module, "build_model", lambda mc: "fake-model")
    monkeypatch.setattr(agent_module, "build_runtime_backend", lambda: "fake-backend")
    monkeypatch.setattr(agent_module, "build_runtime_checkpointer", lambda: "fake-checkpointer")
    monkeypatch.setattr(agent_module, "get_memory_sources", lambda: [])
    monkeypatch.setattr(agent_module, "get_skill_sources", lambda: [])
    monkeypatch.setattr(
        agent_module,
        "discover_remote_rdb_snapshot",
        lambda adaptor, connection, remote_rdb_state=None: (_ for _ in ()).throw(
            RemoteRedisDiscoveryError(
                kind="permission_denied",
                stage="config_get(dir)",
                message="permission_denied: CONFIG GET dir not permitted by ACL",
                redis_password_supplied=True,
            )
        ),
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools.discover_remote_rdb_snapshot",
        lambda adaptor, connection, remote_rdb_state=None: (_ for _ in ()).throw(
            RemoteRedisDiscoveryError(
                kind="permission_denied",
                stage="config_get(dir)",
                message="permission_denied: CONFIG GET dir not permitted by ACL",
                redis_password_supplied=True,
            )
        ),
    )

    def fake_create_deep_agent(**kwargs):
        fetch_tool = next(tool for tool in kwargs["tools"] if tool.__name__ == "fetch_remote_rdb_via_ssh")
        description = kwargs["interrupt_on"]["fetch_remote_rdb_via_ssh"]["description"]

        class FakeAgent:
            def __init__(self) -> None:
                self.calls = 0

            def invoke(self, payload, config=None):
                self.calls += 1
                if self.calls == 1:
                    approval["text"] = description(
                        {"args": {"acquisition_mode": "fresh_snapshot"}},
                        None,
                        None,
                    )
                    return {
                        "__interrupt__": [
                            FakeInterrupt(
                                {
                                    "action_requests": [
                                        {
                                            "name": "fetch_remote_rdb_via_ssh",
                                            "args": {"acquisition_mode": "fresh_snapshot"},
                                            "description": approval["text"],
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
                return {
                    "messages": [
                        {
                            "role": "assistant",
                            "content": fetch_tool(acquisition_mode="fresh_snapshot"),
                        }
                    ]
                }

        return FakeAgent()

    monkeypatch.setattr(agent_module, "create_deep_agent", fake_create_deep_agent)

    result = agent_module.run_orchestrated(
        _make_request(),
        config=_make_config(),
        approval_handler=AutoApproveHandler(approve=True),
    )

    assert "permission_denied" in approval["text"]
    assert "Discovery failure stage: config_get(dir)" in approval["text"]
    assert "Redis password supplied: yes" in approval["text"]
    assert "Redis dir: unresolved" not in approval["text"]
    assert "permission_denied" in result
    assert "config_get(dir)" in result
    assert "redis_password_supplied: yes" in result
    assert "provide dir/dbfilename" not in result.lower()
