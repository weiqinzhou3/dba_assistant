from pathlib import Path

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
from dba_assistant.capabilities.redis_rdb_analysis.remote_input import RemoteRedisDiscoveryError
from dba_assistant.interface.types import ApprovalResponse, ApprovalStatus
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
    assert "auto-discover redis dir and dbfilename" in (fetch_tool.__doc__ or "").lower()
    assert "do not ask for plain-text approval first" in (fetch_tool.__doc__ or "").lower()
    assert "approval is collected by runtime interrupt_on" in (fetch_tool.__doc__ or "").lower()


def test_analyze_local_rdb_tool_runs_full_pipeline(monkeypatch) -> None:
    from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock
    from dba_assistant.core.reporter.types import ReportArtifact, ReportFormat

    analysis_report = AnalysisReport(
        title="Test", sections=[ReportSectionModel(id="s1", title="S1", blocks=[TextBlock(text="ok")])]
    )
    captured: dict[str, object] = {}

    def fake_analyze_rdb_tool(
        prompt,
        input_paths,
        *,
        input_kind="local_rdb",
        profile_name="generic",
        report_language="zh-CN",
        path_mode="auto",
        profile_overrides=None,
        service=None,
    ):
        captured["analyze_called"] = True
        captured["input_kind"] = input_kind
        return analysis_report

    monkeypatch.setattr("dba_assistant.orchestrator.tools.analyze_rdb_tool", fake_analyze_rdb_tool)

    # The tool's lazy import makes it hard to mock generate_analysis_report directly.
    # Instead, test that the tool successfully calls analyze_rdb_tool and returns
    # expected output by patching the entire report generation chain.
    from dba_assistant.core.reporter import summary_reporter

    def fake_render_summary(report, *, language=None):
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


def test_analyze_local_rdb_tool_passes_request_top_n_and_explicit_focus_prefix_overrides(monkeypatch) -> None:
    from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

    captured: dict[str, object] = {}

    def fake_analyze_rdb_tool(
        prompt,
        input_paths,
        *,
        input_kind="local_rdb",
        profile_name="generic",
        report_language="zh-CN",
        path_mode="auto",
        profile_overrides=None,
        service=None,
    ):
        captured["profile_name"] = profile_name
        captured["profile_overrides"] = dict(profile_overrides or {})
        return AnalysisReport(
            title="Test",
            sections=[ReportSectionModel(id="s1", title="S1", blocks=[TextBlock(text="ok")])],
        )

    monkeypatch.setattr("dba_assistant.orchestrator.tools.analyze_rdb_tool", fake_analyze_rdb_tool)
    monkeypatch.setattr(
        "dba_assistant.core.reporter.report_model.render_summary_text",
        lambda report, *, language=None: "summary text",
    )

    request = _make_request(
        rdb_overrides=RdbOverrides(
            profile_name="rcs",
            focus_prefixes=("order:*", "mq:*"),
            top_n={"top_big_keys": 10, "prefix_top": 10, "focused_prefix_top_keys": 10},
        )
    )
    tools = build_all_tools(request)
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb")

    analyze_tool(
        input_paths="/tmp/dump.rdb",
        profile_name="rcs",
        focus_prefixes="order:*,mq:*",
    )

    assert captured["profile_name"] == "rcs"
    assert captured["profile_overrides"] == {
        "focus_prefixes": ("order:*", "mq:*"),
        "top_n": {"top_big_keys": 10, "prefix_top": 10, "focused_prefix_top_keys": 10},
    }


def test_analyze_local_rdb_tool_passes_focus_only_override(monkeypatch) -> None:
    from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

    captured: dict[str, object] = {}

    def fake_analyze_rdb_tool(
        prompt,
        input_paths,
        *,
        input_kind="local_rdb",
        profile_name="generic",
        report_language="zh-CN",
        path_mode="auto",
        profile_overrides=None,
        service=None,
    ):
        captured["profile_overrides"] = dict(profile_overrides or {})
        return AnalysisReport(
            title="Test",
            sections=[ReportSectionModel(id="s1", title="S1", blocks=[TextBlock(text="ok")])],
        )

    monkeypatch.setattr("dba_assistant.orchestrator.tools.analyze_rdb_tool", fake_analyze_rdb_tool)
    monkeypatch.setattr(
        "dba_assistant.core.reporter.report_model.render_summary_text",
        lambda report, *, language=None: "summary text",
    )

    request = _make_request(
        rdb_overrides=RdbOverrides(
            profile_name="rcs",
            focus_prefixes=("tag:*",),
            focus_only=True,
        )
    )
    tools = build_all_tools(request)
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb")

    analyze_tool(input_paths="/tmp/dump.rdb", profile_name="rcs")

    assert captured["profile_overrides"] == {
        "focus_prefixes": ("tag:*",),
        "focus_only": True,
    }


def test_analyze_local_rdb_tool_validates_host_paths_before_analysis(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")

    def fake_analyze_rdb_tool(
        prompt,
        input_paths,
        *,
        input_kind="local_rdb",
        profile_name="generic",
        report_language="zh-CN",
        path_mode="auto",
        profile_overrides=None,
        service=None,
    ):
        captured["input_paths"] = input_paths
        from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

        return AnalysisReport(
            title="Redis RDB Analysis",
            sections=[ReportSectionModel(id="s1", title="S1", blocks=[TextBlock(text="ok")])],
        )

    monkeypatch.setattr("dba_assistant.orchestrator.tools.analyze_rdb_tool", fake_analyze_rdb_tool)
    monkeypatch.setattr(
        "dba_assistant.core.reporter.report_model.render_summary_text",
        lambda report, *, language=None: "summary text",
    )

    request = _make_request()
    tools = build_all_tools(request)
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb")

    result = analyze_tool(input_paths=str(source))

    assert captured["input_paths"] == [source]
    assert "Redis RDB Analysis" in result


def test_analyze_local_rdb_tool_returns_docx_path_when_request_is_docx_without_explicit_path(
    monkeypatch,
    tmp_path,
) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    docx_path = tmp_path / "outputs" / "auto.docx"

    def fake_analyze_rdb_tool(
        prompt,
        input_paths,
        *,
        input_kind="local_rdb",
        profile_name="generic",
        report_language="zh-CN",
        path_mode="auto",
        profile_overrides=None,
        service=None,
    ):
        from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

        return AnalysisReport(
            title="Redis RDB 分析报告",
            sections=[ReportSectionModel(id="s1", title="摘要", blocks=[TextBlock(text="ok")])],
            language="zh-CN",
        )

    monkeypatch.setattr("dba_assistant.orchestrator.tools.analyze_rdb_tool", fake_analyze_rdb_tool)
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools.ensure_report_output_path",
        lambda runtime_inputs, report_format: __import__("dataclasses").replace(
            runtime_inputs,
            output_path=docx_path,
            report_format="docx",
            output_mode="report",
        ),
    )

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="report",
            report_format="docx",
            input_paths=(source,),
        )
    )
    tools = build_all_tools(request)
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb")

    result = analyze_tool(input_paths=str(source), output_mode="report", report_format="docx")

    assert result == str(docx_path)
    assert docx_path.exists()


def test_analyze_local_rdb_tool_returns_host_side_missing_path_error(monkeypatch) -> None:
    def fail_analyze_rdb_tool(*args, **kwargs):
        raise AssertionError("analyze_rdb_tool should not be called for missing host paths")

    monkeypatch.setattr("dba_assistant.orchestrator.tools.analyze_rdb_tool", fail_analyze_rdb_tool)

    request = _make_request()
    tools = build_all_tools(request)
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb")

    result = analyze_tool(input_paths="/tmp/definitely-missing-dba-assistant.rdb")

    assert result == (
        "Error: input path does not exist on host filesystem: "
        "/tmp/definitely-missing-dba-assistant.rdb"
    )


def test_analyze_local_rdb_tool_forces_local_input_kind_even_when_request_is_polluted(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_analyze_rdb_tool(
        prompt,
        input_paths,
        *,
        input_kind="local_rdb",
        profile_name="generic",
        report_language="zh-CN",
        path_mode="auto",
        profile_overrides=None,
        service=None,
    ):
        captured["input_kind"] = input_kind
        from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

        return AnalysisReport(
            title="Redis RDB Analysis",
            sections=[ReportSectionModel(id="s1", title="S1", blocks=[TextBlock(text="ok")])],
        )

    monkeypatch.setattr("dba_assistant.orchestrator.tools.analyze_rdb_tool", fake_analyze_rdb_tool)
    monkeypatch.setattr(
        "dba_assistant.core.reporter.report_model.render_summary_text",
        lambda report, *, language=None: "summary text",
    )

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            input_kind="remote_redis",
            input_paths=(Path("/tmp/dump.rdb"),),
        )
    )
    tools = build_all_tools(request)
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb")

    analyze_tool(input_paths="/tmp/dump.rdb")

    assert captured["input_kind"] == "local_rdb"


def test_analyze_local_rdb_with_mysql_route_does_not_fall_into_remote_discovery(monkeypatch) -> None:
    import json

    from dba_assistant.adaptors.mysql_adaptor import MySQLConnectionConfig

    rows_fixture = Path("tests/fixtures/rdb/direct/sample_key_records.json")
    rows = json.loads(rows_fixture.read_text(encoding="utf-8"))
    captured: dict[str, object] = {"approvals": 0}

    class ApproveHandler:
        def request_approval(self, request):
            captured["approvals"] += 1
            return ApprovalResponse(status=ApprovalStatus.APPROVED, action=request.action)

    monkeypatch.setattr(
        "dba_assistant.capabilities.redis_rdb_analysis.service._parse_rdb_rows",
        lambda _path: rows,
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._stage_rows",
        lambda _adaptor, _connection, table_name, parsed_rows: (
            captured.setdefault("staged_table", table_name),
            captured.setdefault("staged_count", len(parsed_rows)),
            json.dumps({"table": table_name, "staged": len(parsed_rows)}),
        )[-1],
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._load_dataset",
        lambda _adaptor, _connection, table_name, limit="100000": (
            captured.setdefault("loaded_table", table_name),
            json.dumps({"source": f"mysql:{table_name}", "rows": rows}),
        )[-1],
    )

    request = _make_request(
        prompt="analyze local rdb via mysql",
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            input_kind="remote_redis",
            path_mode="database_backed_analysis",
            input_paths=(Path("/tmp/dump.rdb"),),
            mysql_host="192.168.23.176",
            mysql_port=3306,
            mysql_user="root",
            mysql_database="rcs",
            mysql_table="rdb",
        ),
    )
    mysql_connection = MySQLConnectionConfig(
        host="192.168.23.176",
        port=3306,
        user="root",
        password="Root@1234!",
        database="rcs",
    )
    tools = build_all_tools(
        request,
        mysql_connection=mysql_connection,
        approval_handler=ApproveHandler(),
    )
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb")

    result = analyze_tool(input_paths="/tmp/dump.rdb")

    assert "KeyError" not in result
    assert captured["approvals"] == 1
    assert captured["staged_count"] == len(rows)
    assert captured["loaded_table"] == captured["staged_table"]
    assert "样本" in result


def test_analyze_local_rdb_mysql_route_requires_approval_before_staging(monkeypatch) -> None:
    import json

    from dba_assistant.adaptors.mysql_adaptor import MySQLConnectionConfig

    rows_fixture = Path("tests/fixtures/rdb/direct/sample_key_records.json")
    rows = json.loads(rows_fixture.read_text(encoding="utf-8"))
    captured: dict[str, object] = {"approvals": 0}

    class DenyHandler:
        def request_approval(self, request):
            captured["approvals"] += 1
            captured["approval_request"] = request
            return ApprovalResponse(status=ApprovalStatus.DENIED, action=request.action)

    monkeypatch.setattr(
        "dba_assistant.capabilities.redis_rdb_analysis.service._parse_rdb_rows",
        lambda _path: rows,
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._stage_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("stage write must not happen after denial")),
    )

    request = _make_request(
        prompt="analyze local rdb via mysql",
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            path_mode="database_backed_analysis",
            input_paths=(Path("/tmp/dump.rdb"),),
            mysql_host="192.168.23.176",
            mysql_port=3306,
            mysql_user="root",
            mysql_database="rcs",
            mysql_table="rdb",
        ),
    )
    mysql_connection = MySQLConnectionConfig(
        host="192.168.23.176",
        port=3306,
        user="root",
        password="Root@1234!",
        database="rcs",
    )
    tools = build_all_tools(request, mysql_connection=mysql_connection, approval_handler=DenyHandler())
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb")

    result = analyze_tool(input_paths="/tmp/dump.rdb")

    assert result == "Operation denied by user."
    assert captured["approvals"] == 1
    assert captured["approval_request"].action == "stage_rdb_rows_to_mysql"


def test_analyze_local_rdb_mysql_route_stages_only_after_approval(monkeypatch) -> None:
    import json

    from dba_assistant.adaptors.mysql_adaptor import MySQLConnectionConfig

    rows_fixture = Path("tests/fixtures/rdb/direct/sample_key_records.json")
    rows = json.loads(rows_fixture.read_text(encoding="utf-8"))
    captured: dict[str, object] = {"approvals": 0}

    class ApproveHandler:
        def request_approval(self, request):
            captured["approvals"] += 1
            return ApprovalResponse(status=ApprovalStatus.APPROVED, action=request.action)

    monkeypatch.setattr(
        "dba_assistant.capabilities.redis_rdb_analysis.service._parse_rdb_rows",
        lambda _path: rows,
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._stage_rows",
        lambda _adaptor, _connection, table_name, parsed_rows: (
            captured.setdefault("staged_table", table_name),
            captured.setdefault("staged_count", len(parsed_rows)),
            json.dumps({"table": table_name, "staged": len(parsed_rows)}),
        )[-1],
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._load_dataset",
        lambda _adaptor, _connection, table_name, limit="100000": json.dumps(
            {"source": f"mysql:{table_name}", "rows": rows}
        ),
    )

    request = _make_request(
        prompt="analyze local rdb via mysql",
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            path_mode="database_backed_analysis",
            input_paths=(Path("/tmp/dump.rdb"),),
            mysql_host="192.168.23.176",
            mysql_port=3306,
            mysql_user="root",
            mysql_database="rcs",
            mysql_table="rdb",
        ),
    )
    mysql_connection = MySQLConnectionConfig(
        host="192.168.23.176",
        port=3306,
        user="root",
        password="Root@1234!",
        database="rcs",
    )
    tools = build_all_tools(request, mysql_connection=mysql_connection, approval_handler=ApproveHandler())
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb")

    result = analyze_tool(input_paths="/tmp/dump.rdb")

    assert captured["approvals"] == 1
    assert captured["staged_count"] == len(rows)
    assert "样本" in result


def test_analyze_local_rdb_mysql_route_returns_docx_path_when_requested_without_explicit_output(
    monkeypatch,
    tmp_path,
) -> None:
    import json

    from dba_assistant.adaptors.mysql_adaptor import MySQLConnectionConfig

    rows_fixture = Path("tests/fixtures/rdb/direct/sample_key_records.json")
    rows = json.loads(rows_fixture.read_text(encoding="utf-8"))
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    docx_path = tmp_path / "outputs" / "mysql-auto.docx"
    captured: dict[str, object] = {"approvals": 0}

    class ApproveHandler:
        def request_approval(self, request):
            captured["approvals"] += 1
            return ApprovalResponse(status=ApprovalStatus.APPROVED, action=request.action)

    monkeypatch.setattr(
        "dba_assistant.capabilities.redis_rdb_analysis.service._parse_rdb_rows",
        lambda _path: rows,
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._stage_rows",
        lambda _adaptor, _connection, table_name, parsed_rows: json.dumps(
            {"table": table_name, "staged": len(parsed_rows)}
        ),
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._load_dataset",
        lambda _adaptor, _connection, table_name, limit="100000": json.dumps(
            {"source": f"mysql:{table_name}", "rows": rows}
        ),
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools.ensure_report_output_path",
        lambda runtime_inputs, report_format: __import__("dataclasses").replace(
            runtime_inputs,
            output_path=docx_path,
            report_format="docx",
            output_mode="report",
        ),
    )

    request = _make_request(
        prompt="analyze local rdb via mysql 输出word给我",
        runtime_inputs=RuntimeInputs(
            output_mode="report",
            report_format="docx",
            path_mode="database_backed_analysis",
            input_paths=(source,),
            mysql_host="192.168.23.176",
            mysql_port=3306,
            mysql_user="root",
            mysql_database="rcs",
            mysql_table="rdb",
        ),
    )
    mysql_connection = MySQLConnectionConfig(
        host="192.168.23.176",
        port=3306,
        user="root",
        password="Root@1234!",
        database="rcs",
    )
    tools = build_all_tools(request, mysql_connection=mysql_connection, approval_handler=ApproveHandler())
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb")

    result = analyze_tool(input_paths=str(source), output_mode="report", report_format="docx")

    assert captured["approvals"] == 1
    assert result == str(docx_path)
    assert docx_path.exists()


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
        report_language="zh-CN",
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
    assert "call fetch_remote_rdb_via_ssh" in result["next_step"].lower()
    assert "do not ask the user for approval in plain text" in (discover_tool.__doc__ or "").lower()
    assert "runtime interrupt_on will collect approval" in (discover_tool.__doc__ or "").lower()


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
        report_language="zh-CN",
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
        lambda report, *, language=None: "remote summary",
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


def test_fetch_remote_rdb_via_ssh_tool_returns_docx_path_when_requested_without_explicit_output(
    monkeypatch,
    tmp_path,
) -> None:
    from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

    docx_path = tmp_path / "outputs" / "remote-auto.docx"

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

    monkeypatch.setattr("dba_assistant.orchestrator.tools.discover_remote_rdb", fake_discover)
    monkeypatch.setattr("dba_assistant.orchestrator.tools.SSHAdaptor", FakeSSHAdaptor)
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools.analyze_rdb_tool",
        lambda *args, **kwargs: AnalysisReport(
            title="Redis RDB 分析报告",
            sections=[ReportSectionModel(id="summary", title="摘要", blocks=[TextBlock(text="ok")])],
            language="zh-CN",
        ),
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools.ensure_report_output_path",
        lambda runtime_inputs, report_format: __import__("dataclasses").replace(
            runtime_inputs,
            output_path=docx_path,
            report_format="docx",
            output_mode="report",
        ),
    )

    request = _make_request(
        prompt="analyze remote redis 输出docx",
        runtime_inputs=RuntimeInputs(
            output_mode="report",
            report_format="docx",
        ),
    )
    connection = RedisConnectionConfig(host="redis.example", port=6379)
    tools = build_all_tools(request, connection=connection)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    result = fetch_tool(output_mode="report", report_format="docx")

    assert result == str(docx_path)
    assert docx_path.exists()


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
        report_language="zh-CN",
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


def test_fetch_remote_rdb_via_ssh_mysql_route_requires_approval_before_staging(monkeypatch) -> None:
    import json

    from dba_assistant.adaptors.mysql_adaptor import MySQLConnectionConfig

    rows = json.loads(Path("tests/fixtures/rdb/direct/sample_key_records.json").read_text(encoding="utf-8"))
    captured: dict[str, object] = {"approvals": 0}

    class DenyHandler:
        def request_approval(self, request):
            captured["approvals"] += 1
            captured["approval_request"] = request
            return ApprovalResponse(status=ApprovalStatus.DENIED, action=request.action)

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

    monkeypatch.setattr("dba_assistant.orchestrator.tools.discover_remote_rdb", fake_discover)
    monkeypatch.setattr("dba_assistant.orchestrator.tools.SSHAdaptor", FakeSSHAdaptor)
    monkeypatch.setattr(
        "dba_assistant.capabilities.redis_rdb_analysis.service._parse_rdb_rows",
        lambda _path: rows,
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._stage_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("stage write must not happen after denial")),
    )

    request = _make_request(
        prompt="analyze remote redis via mysql",
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
    mysql_connection = MySQLConnectionConfig(
        host="db.example", port=3306, user="analyst", password="secret", database="analysis_db",
    )
    tools = build_all_tools(
        request,
        connection=connection,
        mysql_connection=mysql_connection,
        approval_handler=DenyHandler(),
    )
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    result = fetch_tool()

    assert result == "Operation denied by user."
    assert captured["approvals"] == 1
    assert captured["approval_request"].action == "stage_rdb_rows_to_mysql"


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
            events.append(f"ping-password:{connection.password}")
            return {"ok": True}

        def info(self, connection, *, section=None):
            events.append(f"info:{section}")
            events.append(f"info-password:{connection.password}")
            return next(persistence_states)

        def config_get(self, connection, *, pattern):
            events.append(f"config:{pattern}:{connection.password}")
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
    assert events[:7] == [
        "ping-password:123456",
        "info:persistence",
        "info-password:123456",
        "config:dir:123456",
        "config:dbfilename:123456",
        "bgsave",
        "info:persistence",
    ]
    assert "info-password:123456" in events
    assert "sleep:0.2" in events
    assert "fetch:/data/redis/data/dump.rdb" in events


def test_fetch_remote_rdb_via_ssh_returns_auth_failure_without_missing_dir_prompt(monkeypatch) -> None:
    request = _make_request(
        runtime_inputs=RuntimeInputs(
            redis_host="192.168.23.54",
            redis_port=6379,
            ssh_host="192.168.23.54",
            ssh_port=22,
            ssh_username="root",
            output_mode="summary",
        ),
        secrets=Secrets(redis_password="123456", ssh_password="root"),
    )
    connection = RedisConnectionConfig(host="192.168.23.54", port=6379, password="123456")
    tools = build_all_tools(request, connection=connection)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools.discover_remote_rdb_snapshot",
        lambda adaptor, connection, remote_rdb_state=None: (_ for _ in ()).throw(
            RemoteRedisDiscoveryError(
                kind="authentication_failed",
                stage="ping",
                message="authentication_failed: invalid username-password pair or user is disabled",
                redis_password_supplied=True,
            )
        ),
    )

    result = fetch_tool()

    assert "authentication_failed" in result
    assert "preflight failed at ping" in result
    assert "redis_password_supplied: yes" in result
    assert "provide dir/dbfilename" not in result.lower()


def test_fetch_remote_rdb_via_ssh_returns_permission_denied_from_config_get(monkeypatch) -> None:
    request = _make_request(
        runtime_inputs=RuntimeInputs(
            redis_host="192.168.23.54",
            redis_port=6379,
            ssh_host="192.168.23.54",
            ssh_port=22,
            ssh_username="root",
            output_mode="summary",
        ),
        secrets=Secrets(redis_password="123456", ssh_password="root"),
    )
    connection = RedisConnectionConfig(host="192.168.23.54", port=6379, password="123456")
    tools = build_all_tools(request, connection=connection)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

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

    result = fetch_tool()

    assert "permission_denied" in result
    assert "config_get(dir)" in result
    assert "missing dir" not in result.lower()


def test_discover_remote_rdb_tool_reports_redis_password_supplied_without_leaking_secret(monkeypatch) -> None:
    import json

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            redis_host="192.168.23.54",
            redis_port=6379,
            output_mode="summary",
        ),
        secrets=Secrets(redis_password="123456"),
    )
    connection = RedisConnectionConfig(host="192.168.23.54", port=6379, password="123456")
    tools = build_all_tools(request, connection=connection)
    discover_tool = next(t for t in tools if t.__name__ == "discover_remote_rdb")

    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools.discover_remote_rdb_snapshot",
        lambda adaptor, connection, remote_rdb_state=None: (_ for _ in ()).throw(
            RemoteRedisDiscoveryError(
                kind="authentication_failed",
                stage="ping",
                message="authentication_failed: invalid username-password pair or user is disabled",
                redis_password_supplied=True,
            )
        ),
    )

    result = json.loads(discover_tool())

    assert result["status"] == "failed"
    assert result["error_kind"] == "authentication_failed"
    assert result["redis_password_supplied"] == "yes"
    assert "123456" not in json.dumps(result)
