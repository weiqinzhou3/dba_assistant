from pathlib import Path

from dba_assistant.deep_agent_integration.config import AppConfig, ModelConfig, ProviderKind, RuntimeConfig
from dba_assistant.interface import adapter as adapter_module
from dba_assistant.interface.hitl import AutoApproveHandler
from dba_assistant.interface.types import InterfaceRequest
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


def test_handle_request_prefers_explicit_local_rdb_path_over_repo_fixture_suggestions(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_analyze_local_rdb(**kwargs):
        captured["tool_kwargs"] = kwargs
        return "host tool used for /tmp/dump.rdb"

    def fake_build_all_tools(request, connection=None, mysql_connection=None, remote_rdb_state=None):
        fake_analyze_local_rdb.__name__ = "analyze_local_rdb"
        return [fake_analyze_local_rdb]

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: _make_config())
    monkeypatch.setattr(agent_module, "build_all_tools", fake_build_all_tools)
    monkeypatch.setattr(
        agent_module,
        "build_unified_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("repository fixture exploration should not happen for explicit local RDB paths")
        ),
    )

    result = adapter_module.handle_request(
        InterfaceRequest(
            prompt=(
                "请帮我分析本地rdb文件，传入MySQL中分析。rdb文件在：/tmp/dump.rdb ， "
                "MySQL信息如下：192.168.23.176:3306，用户名root，密码Root@1234! ，"
                "使用数据库rcs，表名叫rdb吧。"
            ),
        ),
        approval_handler=AutoApproveHandler(),
    )

    assert result == "host tool used for /tmp/dump.rdb"
    assert captured["tool_kwargs"]["input_paths"] == "/tmp/dump.rdb"
    assert "tests/fixtures/rdb" not in result
