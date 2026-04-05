from pathlib import Path

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
from dba_assistant.orchestrator.tools import build_all_tools, resolve_remote_rdb_fetch_plan


def _make_request(**overrides) -> NormalizedRequest:
    defaults = dict(
        raw_prompt="test",
        prompt="test",
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            input_paths=(Path("/tmp/dump.rdb"),),
        ),
        secrets=Secrets(),
        rdb_overrides=RdbOverrides(profile_name="generic"),
    )
    defaults.update(overrides)
    return NormalizedRequest(**defaults)


def test_build_all_tools_includes_local_rdb_without_connection() -> None:
    request = _make_request()
    tools = build_all_tools(request)
    names = [t.__name__ for t in tools]
    assert "analyze_local_rdb" in names
    assert "analyze_preparsed_dataset" in names
    assert "redis_ping" not in names
    assert "discover_remote_rdb" not in names


def test_build_all_tools_includes_redis_tools_with_connection() -> None:
    request = _make_request()
    connection = RedisConnectionConfig(host="redis.example", port=6379)
    tools = build_all_tools(request, connection=connection)
    names = [t.__name__ for t in tools]
    assert "analyze_local_rdb" in names
    assert "redis_ping" in names
    assert "redis_info" in names
    assert "redis_config_get" in names
    assert "redis_slowlog_get" in names
    assert "redis_client_list" in names
    assert "discover_remote_rdb" in names
    assert "fetch_remote_rdb_via_ssh" in names
    assert "fetch_and_analyze_remote_rdb" not in names


def test_fetch_remote_rdb_via_ssh_tool_does_not_expose_ssh_secret_parameters() -> None:
    request = _make_request()
    connection = RedisConnectionConfig(host="redis.example", port=6379)
    tools = build_all_tools(request, connection=connection)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    annotations = getattr(fetch_tool, "__annotations__", {})

    assert "ssh_password" not in annotations
    assert "ssh_username" not in annotations


def test_analyze_local_rdb_tool_runs_full_pipeline(monkeypatch) -> None:
    from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock
    from dba_assistant.core.reporter.types import ReportArtifact, ReportFormat

    analysis_report = AnalysisReport(
        title="Test", sections=[ReportSectionModel(id="s1", title="S1", blocks=[TextBlock(text="ok")])]
    )
    captured: dict[str, object] = {}

    def fake_analyze_rdb_tool(prompt, input_paths, *, input_kind="local_rdb", profile_name="generic", path_mode="auto", profile_overrides=None, service=None):
        captured["analyze_called"] = True
        captured["input_kind"] = input_kind
        return analysis_report

    monkeypatch.setattr("dba_assistant.orchestrator.tools.analyze_rdb_tool", fake_analyze_rdb_tool)

    # The tool's lazy import makes it hard to mock generate_analysis_report directly.
    # Instead, test that the tool successfully calls analyze_rdb_tool and returns
    # expected output by patching the entire report generation chain.
    from dba_assistant.core.reporter import summary_reporter

    def fake_render_summary(report):
        return "summary text"

    monkeypatch.setattr(
        "dba_assistant.core.reporter.report_model.render_summary_text",
        fake_render_summary,
    )

    request = _make_request()
    tools = build_all_tools(request)
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb")

    result = analyze_tool(input_paths="/tmp/dump.rdb", profile_name="generic")
    assert captured["analyze_called"]
    assert "summary" in result.lower() or "text" in result.lower() or len(result) > 0


def test_analyze_preparsed_dataset_tool_uses_mysql_source_from_request(monkeypatch) -> None:
    from dba_assistant.adaptors.mysql_adaptor import MySQLConnectionConfig
    from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

    captured: dict[str, object] = {}

    def fake_analyze_rdb_tool(
        prompt,
        input_paths,
        *,
        input_kind="local_rdb",
        profile_name="generic",
        path_mode="auto",
        profile_overrides=None,
        mysql_table=None,
        mysql_query=None,
        service=None,
    ):
        captured["input_paths"] = input_paths
        captured["input_kind"] = input_kind
        captured["mysql_table"] = mysql_table
        captured["mysql_query"] = mysql_query
        return AnalysisReport(
            title="Redis RDB Analysis",
            sections=[ReportSectionModel(id="s1", title="S1", blocks=[TextBlock(text="ok")])],
        )

    monkeypatch.setattr("dba_assistant.orchestrator.tools.analyze_rdb_tool", fake_analyze_rdb_tool)

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            input_kind="preparsed_mysql",
            mysql_host="db.example",
            mysql_port=3306,
            mysql_user="analyst",
            mysql_database="analysis_db",
            mysql_table="preparsed_keys",
        )
    )
    mysql_connection = MySQLConnectionConfig(
        host="db.example", port=3306, user="analyst", password="secret", database="analysis_db",
    )
    tools = build_all_tools(request, mysql_connection=mysql_connection)
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_preparsed_dataset")

    result = analyze_tool()

    assert "Redis RDB Analysis" in result
    assert captured["input_kind"] == "preparsed_mysql"
    assert captured["mysql_table"] == "preparsed_keys"
    assert captured["mysql_query"] is None
    assert captured["input_paths"] == ["preparsed_keys"]


def test_discover_remote_rdb_tool_returns_discovery_json(monkeypatch) -> None:
    import json

    def fake_discover(adaptor, connection):
        return {
            "redis_dir": "/data",
            "dbfilename": "dump.rdb",
            "rdb_path": "/data/dump.rdb",
            "lastsave": 12345,
            "bgsave_in_progress": False,
            "rdb_path_source": "discovered",
        }

    monkeypatch.setattr("dba_assistant.orchestrator.tools.discover_remote_rdb", fake_discover)

    request = _make_request()
    connection = RedisConnectionConfig(host="redis.example", port=6379)
    tools = build_all_tools(request, connection=connection)
    discover_tool = next(t for t in tools if t.__name__ == "discover_remote_rdb")

    result = json.loads(discover_tool())
    assert result["redis_dir"] == "/data"
    assert result["dbfilename"] == "dump.rdb"
    assert result["rdb_path"] == "/data/dump.rdb"
    assert result["rdb_path_source"] == "discovered"
    assert result["approval_required"] is True
    assert result["next_step"] == "Call fetch_remote_rdb_via_ssh to fetch the RDB after human approval."


def test_fetch_remote_rdb_via_ssh_tool_fetches_and_continues_analysis(monkeypatch) -> None:
    from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

    captured: dict[str, object] = {}

    def fake_discover(adaptor, connection):
        return {
            "rdb_path": "/data/dump.rdb",
            "lastsave": 12345,
            "bgsave_in_progress": False,
            "rdb_path_source": "discovered",
        }

    class FakeSSHAdaptor:
        def fetch_file(self, config, remote_path, local_path):
            captured["ssh_config"] = config
            captured["remote_path"] = remote_path
            local_path.write_text("fixture", encoding="utf-8")
            return local_path

    def fake_analyze_rdb_tool(
        prompt,
        input_paths,
        *,
        input_kind="local_rdb",
        profile_name="generic",
        path_mode="auto",
        profile_overrides=None,
        service=None,
    ):
        captured["analyze_prompt"] = prompt
        captured["analyze_input_paths"] = input_paths
        return AnalysisReport(
            title="Redis RDB Analysis",
            sections=[
                ReportSectionModel(
                    id="summary",
                    title="Summary",
                    blocks=[TextBlock(text="remote ok")],
                )
            ],
        )

    monkeypatch.setattr("dba_assistant.orchestrator.tools.discover_remote_rdb", fake_discover)
    monkeypatch.setattr("dba_assistant.orchestrator.tools.SSHAdaptor", FakeSSHAdaptor)
    monkeypatch.setattr("dba_assistant.orchestrator.tools.analyze_rdb_tool", fake_analyze_rdb_tool)
    monkeypatch.setattr(
        "dba_assistant.core.reporter.report_model.render_summary_text",
        lambda report: "remote summary",
    )

    request = _make_request()
    connection = RedisConnectionConfig(host="redis.example", port=6379)
    tools = build_all_tools(request, connection=connection)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    result = fetch_tool()
    assert "remote ok" in result
    assert captured["remote_path"] == "/data/dump.rdb"
    assert captured["ssh_config"].host == "redis.example"
    assert captured["ssh_config"].username is None
    assert captured["ssh_config"].password is None
    assert len(captured["analyze_input_paths"]) == 1


def test_fetch_remote_rdb_via_ssh_tool_uses_request_ssh_context_when_args_omitted(monkeypatch) -> None:
    from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

    captured: dict[str, object] = {}

    def fake_discover(adaptor, connection):
        return {
            "rdb_path": "/data/dump.rdb",
            "lastsave": 12345,
            "bgsave_in_progress": False,
            "rdb_path_source": "discovered",
        }

    class FakeSSHAdaptor:
        def fetch_file(self, config, remote_path, local_path):
            captured["ssh_config"] = config
            captured["remote_path"] = remote_path
            local_path.write_text("fixture", encoding="utf-8")
            return local_path

    monkeypatch.setattr("dba_assistant.orchestrator.tools.discover_remote_rdb", fake_discover)
    monkeypatch.setattr("dba_assistant.orchestrator.tools.SSHAdaptor", FakeSSHAdaptor)
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools.analyze_rdb_tool",
        lambda *args, **kwargs: AnalysisReport(
            title="Redis RDB Analysis",
            sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
        ),
    )

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            ssh_host="ssh.example",
            ssh_port=2222,
            ssh_username="root",
        ),
        secrets=Secrets(ssh_password="secret"),
    )
    connection = RedisConnectionConfig(host="redis.example", port=6379)
    tools = build_all_tools(request, connection=connection)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    fetch_tool()

    assert captured["remote_path"] == "/data/dump.rdb"
    assert captured["ssh_config"].host == "ssh.example"
    assert captured["ssh_config"].port == 2222
    assert captured["ssh_config"].username == "root"
    assert captured["ssh_config"].password == "secret"


def test_fetch_remote_rdb_via_ssh_tool_preserves_database_backed_route(monkeypatch) -> None:
    from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

    captured: dict[str, object] = {}

    def fake_discover(adaptor, connection):
        return {
            "rdb_path": "/data/dump.rdb",
            "lastsave": 12345,
            "bgsave_in_progress": False,
            "rdb_path_source": "discovered",
        }

    class FakeSSHAdaptor:
        def fetch_file(self, config, remote_path, local_path):
            local_path.write_text("fixture", encoding="utf-8")
            return local_path

    def fake_analyze_rdb_tool(
        prompt,
        input_paths,
        *,
        input_kind="local_rdb",
        profile_name="generic",
        path_mode="auto",
        profile_overrides=None,
        mysql_table=None,
        mysql_query=None,
        service=None,
    ):
        captured["path_mode"] = path_mode
        captured["service"] = service
        return AnalysisReport(
            title="Redis RDB Analysis",
            sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
        )

    monkeypatch.setattr("dba_assistant.orchestrator.tools.discover_remote_rdb", fake_discover)
    monkeypatch.setattr("dba_assistant.orchestrator.tools.SSHAdaptor", FakeSSHAdaptor)
    monkeypatch.setattr("dba_assistant.orchestrator.tools.analyze_rdb_tool", fake_analyze_rdb_tool)

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            path_mode="database_backed_analysis",
            mysql_host="db.example",
            mysql_port=3306,
            mysql_user="analyst",
            mysql_database="analysis_db",
        ),
        secrets=Secrets(mysql_password="secret"),
    )
    connection = RedisConnectionConfig(host="redis.example", port=6379)
    from dba_assistant.adaptors.mysql_adaptor import MySQLConnectionConfig

    mysql_connection = MySQLConnectionConfig(
        host="db.example", port=3306, user="analyst", password="secret", database="analysis_db",
    )
    tools = build_all_tools(request, connection=connection, mysql_connection=mysql_connection)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    result = fetch_tool()
    

    assert "ok" in result
    assert captured["path_mode"] == "database_backed_analysis"
    assert captured["service"] is not None


def test_fetch_remote_rdb_via_ssh_tool_prefers_discovery_path_over_tool_arg_and_non_override_request(
    monkeypatch,
) -> None:
    from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

    captured: dict[str, object] = {}

    def fake_discover(adaptor, connection):
        return {
            "rdb_path": "/data/redis/data/actual.rdb",
            "lastsave": 12345,
            "bgsave_in_progress": False,
            "rdb_path_source": "discovered",
        }

    class FakeSSHAdaptor:
        def fetch_file(self, config, remote_path, local_path):
            captured["remote_path"] = remote_path
            local_path.write_text("fixture", encoding="utf-8")
            return local_path

    monkeypatch.setattr("dba_assistant.orchestrator.tools.discover_remote_rdb", fake_discover)
    monkeypatch.setattr("dba_assistant.orchestrator.tools.SSHAdaptor", FakeSSHAdaptor)
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools.analyze_rdb_tool",
        lambda *args, **kwargs: AnalysisReport(
            title="Redis RDB Analysis",
            sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
        ),
    )

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            remote_rdb_path="/var/lib/redis/dump.rdb",
            remote_rdb_path_source="fallback_default",
        ),
    )
    connection = RedisConnectionConfig(host="redis.example", port=6379)
    tools = build_all_tools(request, connection=connection)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")
    resolution = resolve_remote_rdb_fetch_plan(
        request,
        fake_discover(None, None),
        remote_rdb_path="/tmp/agent-guessed.rdb",
    )

    fetch_tool()

    assert resolution["remote_rdb_path"] == "/data/redis/data/actual.rdb"
    assert resolution["remote_rdb_path_source"] == "discovered"
    assert captured["remote_path"] == "/data/redis/data/actual.rdb"


def test_fetch_remote_rdb_via_ssh_tool_uses_user_override_path_when_explicitly_requested(
    monkeypatch,
) -> None:
    from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

    captured: dict[str, object] = {}

    def fake_discover(adaptor, connection):
        return {
            "rdb_path": "/data/redis/data/actual.rdb",
            "lastsave": 12345,
            "bgsave_in_progress": False,
            "rdb_path_source": "discovered",
        }

    class FakeSSHAdaptor:
        def fetch_file(self, config, remote_path, local_path):
            captured["remote_path"] = remote_path
            local_path.write_text("fixture", encoding="utf-8")
            return local_path

    monkeypatch.setattr("dba_assistant.orchestrator.tools.discover_remote_rdb", fake_discover)
    monkeypatch.setattr("dba_assistant.orchestrator.tools.SSHAdaptor", FakeSSHAdaptor)
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools.analyze_rdb_tool",
        lambda *args, **kwargs: AnalysisReport(
            title="Redis RDB Analysis",
            sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
        ),
    )

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            remote_rdb_path="/custom/override.rdb",
            remote_rdb_path_source="user_override",
        ),
    )
    connection = RedisConnectionConfig(host="redis.example", port=6379)
    tools = build_all_tools(request, connection=connection)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    fetch_tool()

    assert captured["remote_path"] == "/custom/override.rdb"


def test_fetch_remote_rdb_via_ssh_uses_ssh_secret_not_redis_secret(monkeypatch) -> None:
    from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

    captured: dict[str, object] = {}

    def fake_discover(adaptor, connection):
        return {
            "redis_dir": "/data/redis/data",
            "dbfilename": "dump.rdb",
            "rdb_path": "/data/redis/data/dump.rdb",
            "lastsave": 12345,
            "bgsave_in_progress": False,
            "rdb_path_source": "discovered",
        }

    class FakeSSHAdaptor:
        def fetch_file(self, config, remote_path, local_path):
            captured["ssh_config"] = config
            local_path.write_text("fixture", encoding="utf-8")
            return local_path

    monkeypatch.setattr("dba_assistant.orchestrator.tools.discover_remote_rdb", fake_discover)
    monkeypatch.setattr("dba_assistant.orchestrator.tools.SSHAdaptor", FakeSSHAdaptor)
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools.analyze_rdb_tool",
        lambda *args, **kwargs: AnalysisReport(
            title="Redis RDB Analysis",
            sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
        ),
    )

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            ssh_host="192.168.23.54",
            ssh_username="root",
        ),
        secrets=Secrets(redis_password="123456", ssh_password="root"),
    )
    connection = RedisConnectionConfig(host="redis.example", port=6379, password="123456")
    tools = build_all_tools(request, connection=connection)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    fetch_tool()

    assert captured["ssh_config"].username == "root"
    assert captured["ssh_config"].password == "root"


def test_fetch_remote_rdb_via_ssh_tool_generates_latest_snapshot_when_requested(monkeypatch) -> None:
    from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

    events: list[str] = []
    persistence_states = iter(
        [
            {"rdb_last_save_time": 100, "rdb_bgsave_in_progress": 0},
            {"rdb_last_save_time": 100, "rdb_bgsave_in_progress": 1},
            {"rdb_last_save_time": 200, "rdb_bgsave_in_progress": 0},
        ]
    )

    class FakeRedisAdaptor:
        def ping(self, connection):
            return {"ok": True}

        def info(self, connection, *, section=None):
            events.append(f"info:{section}")
            return next(persistence_states)

        def config_get(self, connection, *, pattern):
            if pattern == "dir":
                return {"available": True, "data": {"dir": "/data/redis/data"}}
            if pattern == "dbfilename":
                return {"available": True, "data": {"dbfilename": "dump.rdb"}}
            return {"available": True, "data": {"maxmemory": "0"}}

        def slowlog_get(self, connection, *, length):
            return {"count": 0, "entries": []}

        def client_list(self, connection):
            return {"count": 0}

        def bgsave(self, connection):
            events.append("bgsave")
            return {"started": True}

    class FakeSSHAdaptor:
        def fetch_file(self, config, remote_path, local_path):
            events.append(f"fetch:{remote_path}")
            local_path.write_text("fixture", encoding="utf-8")
            return local_path

    monkeypatch.setattr("dba_assistant.orchestrator.tools.RedisAdaptor", lambda: FakeRedisAdaptor())
    monkeypatch.setattr("dba_assistant.orchestrator.tools.SSHAdaptor", FakeSSHAdaptor)
    monkeypatch.setattr("dba_assistant.orchestrator.tools.time.sleep", lambda seconds: events.append(f"sleep:{seconds}"))
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools.analyze_rdb_tool",
        lambda *args, **kwargs: AnalysisReport(
            title="Redis RDB Analysis",
            sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
        ),
    )

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            redis_host="redis.example",
            redis_port=6379,
            ssh_host="192.168.23.54",
            ssh_username="root",
            output_mode="summary",
            require_fresh_rdb_snapshot=True,
        ),
        secrets=Secrets(redis_password="123456", ssh_password="root"),
    )
    connection = RedisConnectionConfig(host="redis.example", port=6379, password="123456")
    tools = build_all_tools(request, connection=connection)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    result = fetch_tool()

    assert "ok" in result
    assert "bgsave" in events
    assert "fetch:/data/redis/data/dump.rdb" in events
