from pathlib import Path
import json

import pytest
import yaml

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
from dba_assistant.capabilities.redis_rdb_analysis.remote_input import RemoteRedisDiscoveryError
from dba_assistant.core.observability import bootstrap_observability, reset_observability_state
from dba_assistant.deep_agent_integration.config import ObservabilityConfig
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


def _streamed_rows(rows: list[dict[str, object]]):
    from dba_assistant.parsers.rdb_parser_strategy import StreamedRowsResult

    return StreamedRowsResult(rows=iter(rows), strategy_name="test-stream")


def _mysql_analysis_payload(*, sample_rows: list[list[str]]) -> dict[str, object]:
    return {
        "executive_summary": {"total_samples": len(sample_rows), "total_keys": 1, "total_bytes": 123},
        "background": {"profile_name": "generic", "focus_prefix_count": 0},
        "analysis_results": {"total_samples": len(sample_rows), "total_keys": 1, "total_bytes": 123},
        "sample_overview": {"sample_rows": sample_rows},
        "overall_summary": {"total_samples": len(sample_rows), "total_keys": 1, "total_bytes": 123},
        "key_type_summary": {
            "counts": {"string": 1},
            "memory_bytes": {"string": 123},
            "rows": [["string", "1", "123"]],
        },
        "key_type_memory_breakdown": {"rows": [["string", "123"]]},
        "expiration_summary": {"expired_count": 0, "persistent_count": 1},
        "non_expiration_summary": {"persistent_count": 1},
        "prefix_top_summary": {"rows": [["cache:*", "1", "123"]]},
        "prefix_expiration_breakdown": {"rows": []},
        "top_big_keys": {"limit": 100, "rows": [["cache:1", "string", "123"]]},
        "top_string_keys": {"limit": 100, "rows": [["cache:1", "123"]]},
        "top_hash_keys": {"limit": 100, "rows": []},
        "top_list_keys": {"limit": 100, "rows": []},
        "top_set_keys": {"limit": 100, "rows": []},
        "top_zset_keys": {"limit": 100, "rows": []},
        "top_stream_keys": {"limit": 100, "rows": []},
        "top_other_keys": {"limit": 100, "rows": []},
        "focused_prefix_analysis": {"sections": []},
        "conclusions": {},
    }


def test_build_all_tools_includes_local_rdb_without_connection() -> None:
    request = _make_request()
    tools = build_all_tools(request)
    names = [t.__name__ for t in tools]
    assert "analyze_local_rdb_stream" in names
    assert "analyze_preparsed_dataset" in names
    assert "redis_ping" in names
    assert "collect_offline_inspection_dataset" in names
    assert "redis_inspection_log_candidates" in names
    assert "render_redis_inspection_report" in names
    assert "redis_inspection_report" in names
    assert "discover_remote_rdb" in names
    assert "ensure_remote_rdb_snapshot" in names
    assert "fetch_remote_rdb_via_ssh" in names
    assert "mysql_read_query" in names
    assert "stage_rdb_rows_to_mysql" in names


def test_build_all_tools_includes_redis_tools_with_connection() -> None:
    request = _make_request()
    connection = RedisConnectionConfig(host="redis.example", port=6379)
    tools = build_all_tools(request, connection=connection)
    names = [t.__name__ for t in tools]
    assert "analyze_local_rdb_stream" in names
    assert "redis_ping" in names
    assert "redis_info" in names
    assert "redis_config_get" in names
    assert "redis_slowlog_get" in names
    assert "redis_client_list" in names
    assert "redis_cluster_info" in names
    assert "redis_cluster_nodes" in names
    assert "collect_offline_inspection_dataset" in names
    assert "redis_inspection_log_candidates" in names
    assert "render_redis_inspection_report" in names
    assert "redis_inspection_report" in names
    assert "discover_remote_rdb" in names
    assert "ensure_remote_rdb_snapshot" in names
    assert "fetch_remote_rdb_via_ssh" in names
    assert "fetch_and_analyze_remote_rdb" not in names


def test_report_tool_descriptions_do_not_require_model_invented_output_path() -> None:
    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    tools = build_all_tools(request)

    inspection_tool = next(t for t in tools if t.__name__ == "render_redis_inspection_report")
    rdb_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb_stream")

    assert "output_path (file path, required for docx)" not in (inspection_tool.__doc__ or "").lower()
    assert "output_path (file path, required for docx)" not in (rdb_tool.__doc__ or "").lower()
    assert "omit output_path to use runtime default" in (inspection_tool.__doc__ or "").lower()
    assert "omit output_path to use runtime default" in (rdb_tool.__doc__ or "").lower()


def test_collect_offline_inspection_dataset_validates_paths_before_collection() -> None:
    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    tools = build_all_tools(request)
    collect_tool = next(t for t in tools if t.__name__ == "collect_offline_inspection_dataset")

    result = collect_tool(input_paths="/tmp/definitely-missing-inspection-bundle")

    assert result == (
        "Error: input path does not exist on host filesystem: "
        "/tmp/definitely-missing-inspection-bundle"
    )


def test_offline_inspection_uses_collect_review_then_render_tools(tmp_path: Path) -> None:
    source = tmp_path / "inspection"
    source.mkdir()
    (source / "info.txt").write_text(
        "\n".join(
            [
                "redis_version:7.0.15",
                "role:master",
                "tcp_port:6379",
                "cluster_enabled:1",
                "cluster_state:ok",
                "used_memory:100",
                "maxmemory:1000",
            ]
        ),
        encoding="utf-8",
    )
    (source / "redis.log").write_text(
        "2026-04-14 09:00:00 # OOM command not allowed when used memory > 'maxmemory'\n",
        encoding="utf-8",
    )

    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    tools = build_all_tools(request)
    collect_tool = next(t for t in tools if t.__name__ == "collect_offline_inspection_dataset")
    candidates_tool = next(t for t in tools if t.__name__ == "redis_inspection_log_candidates")
    render_tool = next(t for t in tools if t.__name__ == "render_redis_inspection_report")

    collect_payload = json.loads(
        collect_tool(
            input_paths=str(source),
            log_start_time="2026-04-01 00:00:00",
            log_end_time="2026-04-30 23:59:59",
        )
    )
    candidates_payload = json.loads(
        candidates_tool(
            dataset_handle=collect_payload["dataset_handle"],
        )
    )
    reviewed_payload = json.dumps(
        {
            "issues": [
                {
                    "cluster_id": collect_payload["clusters"][0]["cluster_id"],
                    "cluster_name": collect_payload["clusters"][0]["cluster_name"],
                    "issue_name": "Redis 日志显示 OOM",
                    "is_anomalous": True,
                    "severity": "high",
                    "why": "LLM reviewed OOM as memory pressure evidence.",
                    "affected_nodes": [collect_payload["clusters"][0]["nodes"][0]["node_id"]],
                    "supporting_samples": [candidates_payload["clusters"][0]["log_candidates"][0]["raw_message"]],
                    "recommendation": "检查 maxmemory、业务写入峰值和淘汰策略。",
                    "merge_key": "oom-memory-pressure",
                    "category": "log",
                    "confidence": "high",
                }
            ]
        }
    )

    result = render_tool(
        dataset_handle=collect_payload["dataset_handle"],
        reviewed_log_issues_json=reviewed_payload,
        output_mode="summary",
        report_format="summary",
    )

    assert collect_payload["dataset_handle"].startswith("inspection_dataset_")
    assert "Redis 日志显示 OOM" in result
    assert "问题概览与整改优先级" in result


def test_log_candidates_tool_uses_dataset_handle_without_recollecting(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "inspection"
    source.mkdir()
    (source / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")
    (source / "redis.log").write_text(
        "2026-04-14 09:00:00 # OOM command not allowed\n",
        encoding="utf-8",
    )

    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    tools = build_all_tools(request)
    collect_tool = next(t for t in tools if t.__name__ == "collect_offline_inspection_dataset")
    candidates_tool = next(t for t in tools if t.__name__ == "redis_inspection_log_candidates")
    handle = json.loads(collect_tool(input_paths=str(source)))["dataset_handle"]

    def fail_recollect(*args, **kwargs):
        raise AssertionError("dataset_handle path must not recollect raw evidence")

    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._collect_offline_log_review_payload",
        fail_recollect,
    )

    payload = json.loads(candidates_tool(dataset_handle=handle))

    assert payload["clusters"][0]["log_candidates"][0]["candidate_signal"] == "oom_signal"
    assert payload["review_output_schema"]["properties"]["issues"]["type"] == "array"


def test_collect_summary_includes_log_candidate_presence_and_total(tmp_path: Path) -> None:
    source = tmp_path / "inspection"
    source.mkdir()
    (source / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")
    (source / "redis.log").write_text(
        "2026-04-14 09:00:00 # OOM command not allowed\n",
        encoding="utf-8",
    )

    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    collect_tool = next(t for t in build_all_tools(request) if t.__name__ == "collect_offline_inspection_dataset")

    payload = json.loads(collect_tool(input_paths=str(source)))

    assert payload["has_log_candidates"] is True
    assert payload["total_log_candidate_count"] == 1


def test_redis_inspection_log_candidates_tool_returns_neutral_review_payload(tmp_path: Path) -> None:
    source = tmp_path / "inspection"
    source.mkdir()
    (source / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")
    (source / "redis.log").write_text(
        "2026-04-14 09:00:00 # Background append only file rewriting terminated with success\n",
        encoding="utf-8",
    )

    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    candidates_tool = next(t for t in build_all_tools(request) if t.__name__ == "redis_inspection_log_candidates")

    payload = json.loads(
        candidates_tool(
            input_paths=str(source),
            log_start_time="2026-04-01 00:00:00",
            log_end_time="2026-04-30 23:59:59",
        )
    )

    candidate = payload["clusters"][0]["log_candidates"][0]
    assert candidate["candidate_signal"] == "persistence_signal"
    assert "review_output_schema" in payload
    assert "abnormal" not in json.dumps(payload).lower()


def test_log_candidates_tool_loads_review_schema_from_skill_asset(tmp_path: Path) -> None:
    source = tmp_path / "inspection"
    source.mkdir()
    (source / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")
    (source / "redis.log").write_text(
        "2026-04-14 09:00:00 # OOM command not allowed\n",
        encoding="utf-8",
    )
    schema_path = Path("skills/redis-inspection-report/assets/log_issue_schema.json")
    expected_schema = json.loads(schema_path.read_text(encoding="utf-8"))

    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    candidates_tool = next(t for t in build_all_tools(request) if t.__name__ == "redis_inspection_log_candidates")

    payload = json.loads(
        candidates_tool(
            input_paths=str(source),
            log_start_time="2026-04-01 00:00:00",
            log_end_time="2026-04-30 23:59:59",
        )
    )

    assert payload["review_output_schema"] == expected_schema


def test_collect_offline_inspection_dataset_applies_explicit_log_time_window(tmp_path: Path) -> None:
    source = tmp_path / "inspection"
    source.mkdir()
    (source / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")

    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    tools = build_all_tools(request)
    collect_tool = next(t for t in tools if t.__name__ == "collect_offline_inspection_dataset")
    payload = json.loads(
        collect_tool(
            input_paths=str(source),
            log_time_window_days=7,
            log_start_time="2026-04-01T00:00:00+08:00",
            log_end_time="2026-04-08T00:00:00+08:00",
        )
    )

    assert payload["input_sources"] == [str(source)]
    assert payload["log_time_window"] == {
        "log_time_window_days": 7,
        "log_start_time": "2026-04-01T00:00:00+08:00",
        "log_end_time": "2026-04-08T00:00:00+08:00",
    }


def test_collect_offline_inspection_dataset_applies_skill_default_30_day_log_window(
    tmp_path: Path,
) -> None:
    source = tmp_path / "inspection"
    source.mkdir()
    (source / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")

    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    collect_tool = next(t for t in build_all_tools(request) if t.__name__ == "collect_offline_inspection_dataset")

    payload = json.loads(collect_tool(input_paths=str(source)))

    assert payload["log_time_window"] == {
        "log_time_window_days": 30,
        "log_start_time": None,
        "log_end_time": None,
    }


def test_problem_overview_columns_come_from_skill_table_schema_asset(tmp_path: Path) -> None:
    from dba_assistant.capabilities.redis_inspection_report.analyzer import analyze_inspection_dataset
    from dba_assistant.capabilities.redis_inspection_report.collectors.offline_evidence_collector import (
        RedisInspectionOfflineCollector,
        RedisInspectionOfflineInput,
    )

    source = tmp_path / "inspection"
    source.mkdir()
    (source / "info.txt").write_text(
        "redis_version:7.0.15\nrole:master\ntcp_port:6379\nused_memory:920\nmaxmemory:1000\n",
        encoding="utf-8",
    )
    expected_columns = yaml.safe_load(
        Path("skills/redis-inspection-report/assets/table_schemas.yaml").read_text(encoding="utf-8")
    )["problem_overview"]["columns"]

    dataset = RedisInspectionOfflineCollector().collect(
        RedisInspectionOfflineInput(sources=(source,), log_time_window_days=30)
    )
    report = analyze_inspection_dataset(dataset)
    problem_section = next(section for section in report.sections if section.id == "problem_overview")
    problem_table = next(block for block in problem_section.blocks if hasattr(block, "columns"))

    assert problem_table.columns == expected_columns


def test_render_redis_inspection_report_consumes_dataset_handle(
    tmp_path: Path,
) -> None:
    source = tmp_path / "inspection"
    source.mkdir()
    (source / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")

    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    tools = build_all_tools(request)
    collect_tool = next(t for t in tools if t.__name__ == "collect_offline_inspection_dataset")
    inspection_tool = next(t for t in tools if t.__name__ == "render_redis_inspection_report")
    handle = json.loads(collect_tool(input_paths=str(source)))["dataset_handle"]

    result = inspection_tool(
        dataset_handle=handle,
        log_time_window_days=7,
        output_mode="summary",
        report_format="summary",
    )

    assert "inspection" in result.lower()


def test_redis_inspection_report_docx_without_output_path_defaults_to_tmp(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "inspection"
    source.mkdir()
    (source / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")
    monkeypatch.setattr(
        "dba_assistant.core.reporter.output_path_policy._timestamp_slug",
        lambda: "20260414_010203",
    )
    default_path = Path("/tmp/dba_assistant_redis_inspection_20260414_010203.docx")
    default_path.unlink(missing_ok=True)

    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    tools = build_all_tools(request)
    collect_tool = next(t for t in tools if t.__name__ == "collect_offline_inspection_dataset")
    inspection_tool = next(t for t in tools if t.__name__ == "render_redis_inspection_report")
    handle = json.loads(collect_tool(input_paths=str(source)))["dataset_handle"]

    result = inspection_tool(dataset_handle=handle, output_mode="report", report_format="docx")

    assert result == str(default_path)
    assert Path(result).exists()


def test_redis_inspection_report_tool_passes_reviewed_log_issues_json(
    tmp_path: Path,
) -> None:
    source = tmp_path / "inspection"
    source.mkdir()
    (source / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")

    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    tools = build_all_tools(request)
    collect_tool = next(t for t in tools if t.__name__ == "collect_offline_inspection_dataset")
    inspection_tool = next(t for t in tools if t.__name__ == "render_redis_inspection_report")
    collect_payload = json.loads(collect_tool(input_paths=str(source)))
    handle = collect_payload["dataset_handle"]
    cluster = collect_payload["clusters"][0]
    node_id = cluster["nodes"][0]["node_id"]
    reviewed_payload = json.dumps(
        {
            "issues": [
                {
                    "cluster_id": cluster["cluster_id"],
                    "cluster_name": cluster["cluster_name"],
                    "issue_name": "OOM",
                    "is_anomalous": True,
                    "severity": "high",
                    "why": "reviewed",
                    "affected_nodes": [node_id],
                    "supporting_samples": ["OOM"],
                    "recommendation": "fix",
                    "merge_key": "oom",
                    "category": "log",
                    "confidence": "high",
                }
            ]
        }
    )

    result = inspection_tool(
        dataset_handle=handle,
        reviewed_log_issues_json=reviewed_payload,
        output_mode="summary",
        report_format="summary",
    )

    assert "OOM" in result
    assert "reviewed" in result


def test_render_redis_inspection_report_live_readonly_path_still_available(monkeypatch) -> None:
    from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock

    captured: dict[str, object] = {}

    def fake_analyze_remote_inspection(connection, *, language="zh-CN"):
        captured["host"] = connection.host
        captured["port"] = connection.port
        return AnalysisReport(
            title="Redis 巡检报告",
            sections=[ReportSectionModel(id="summary", title="摘要", blocks=[TextBlock(text="live ok")])],
            metadata={"route": "online_inspection"},
            language=language,
        )

    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._analyze_remote_inspection",
        fake_analyze_remote_inspection,
    )
    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    connection = RedisConnectionConfig(host="redis.example", port=6380)
    render_tool = next(
        t for t in build_all_tools(request, connection=connection)
        if t.__name__ == "render_redis_inspection_report"
    )

    result = render_tool(redis_port=6380, output_mode="summary", report_format="summary")

    assert "live ok" in result
    assert captured == {"host": "redis.example", "port": 6380}


def test_fetch_remote_rdb_via_ssh_tool_does_not_expose_ssh_secret_parameters() -> None:
    request = _make_request()
    connection = RedisConnectionConfig(host="redis.example", port=6379)
    tools = build_all_tools(request, connection=connection)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    annotations = getattr(fetch_tool, "__annotations__", {})

    assert "ssh_password" not in annotations
    assert "ssh_username" in annotations
    assert "remote_rdb_path" in annotations
    assert "do not ask for plain-text approval first" in (fetch_tool.__doc__ or "").lower()
    assert "approval is collected by runtime interrupt_on" in (fetch_tool.__doc__ or "").lower()


def test_analyze_local_rdb_tool_runs_full_pipeline(monkeypatch, tmp_path: Path) -> None:
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
        mysql_host=None,
        mysql_stage_batch_size=None,
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
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb_stream")
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")

    result = analyze_tool(input_paths=str(source), profile_name="generic")
    assert captured["analyze_called"]
    assert "summary" in result.lower() or "text" in result.lower() or len(result) > 0


def test_analyze_local_rdb_tool_passes_request_top_n_and_explicit_focus_prefix_overrides(
    monkeypatch,
    tmp_path: Path,
) -> None:
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
        mysql_host=None,
        mysql_stage_batch_size=None,
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
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb_stream")
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")

    analyze_tool(
        input_paths=str(source),
        profile_name="rcs",
        focus_prefixes="order:*,mq:*",
    )

    assert captured["profile_name"] == "rcs"
    assert captured["profile_overrides"] == {
        "focus_prefixes": ("order:*", "mq:*"),
        "top_n": {"top_big_keys": 10, "prefix_top": 10, "focused_prefix_top_keys": 10},
    }


def test_analyze_local_rdb_tool_passes_focus_only_override(monkeypatch, tmp_path: Path) -> None:
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
        mysql_host=None,
        mysql_stage_batch_size=None,
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
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb_stream")
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")

    analyze_tool(input_paths=str(source), profile_name="rcs")

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
        mysql_host=None,
        mysql_stage_batch_size=None,
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
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb_stream")

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
        mysql_host=None,
        mysql_stage_batch_size=None,
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
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb_stream")

    result = analyze_tool(input_paths=str(source), output_mode="report", report_format="docx")

    assert result == str(docx_path)
    assert docx_path.exists()


def test_analyze_local_rdb_tool_returns_host_side_missing_path_error(monkeypatch) -> None:
    def fail_analyze_rdb_tool(*args, **kwargs):
        raise AssertionError("analyze_rdb_tool should not be called for missing host paths")

    monkeypatch.setattr("dba_assistant.orchestrator.tools.analyze_rdb_tool", fail_analyze_rdb_tool)

    request = _make_request()
    tools = build_all_tools(request)
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb_stream")

    result = analyze_tool(input_paths="/tmp/definitely-missing-dba-assistant.rdb")

    assert result == (
        "Error: input path does not exist on host filesystem: "
        "/tmp/definitely-missing-dba-assistant.rdb"
    )


def test_make_phase3_analysis_service_does_not_json_round_trip_database_backed_rows(
    monkeypatch,
) -> None:
    from dba_assistant.adaptors.mysql_adaptor import MySQLAdaptor, MySQLConnectionConfig
    from dba_assistant.capabilities.redis_rdb_analysis.types import (
        InputSourceKind,
        RdbAnalysisRequest,
        SampleInput,
    )
    from dba_assistant.interface.hitl import AutoApproveHandler

    request = _make_request(
        prompt="analyze this rdb via mysql",
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            path_mode="database_backed_analysis",
            input_paths=(Path("/tmp/dump.rdb"),),
            mysql_host="db.example",
            mysql_database="analysis_db",
        ),
    )
    mysql_connection = MySQLConnectionConfig(
        host="db.example",
        port=3306,
        user="root",
        password="secret",
        database="analysis_db",
    )
    service = build_all_tools.__globals__["_make_phase3_analysis_service"](
        request=request,
        mysql_adaptor=MySQLAdaptor(connect=lambda **_kw: object()),
        mysql_connection=mysql_connection,
        approval_handler=AutoApproveHandler(approve=True),
    )

    monkeypatch.setattr(
        "dba_assistant.capabilities.redis_rdb_analysis.service._stream_rdb_rows",
        lambda _path: __import__("dba_assistant.parsers.rdb_parser_strategy", fromlist=["StreamedRowsResult"]).StreamedRowsResult(
            rows=iter(
                [
                    {
                        "key_name": "cache:1",
                        "key_type": "string",
                        "size_bytes": 123,
                        "has_expiration": False,
                        "ttl_seconds": None,
                    }
                ]
            ),
            strategy_name="test-stream",
        ),
    )
    monkeypatch.setattr(
        "dba_assistant.capabilities.redis_rdb_analysis.service._parse_rdb_rows",
        lambda _path: [
            {
                "key_name": "cache:1",
                "key_type": "string",
                "size_bytes": 123,
                "has_expiration": False,
                "ttl_seconds": None,
            }
        ],
    )

    original_dumps = build_all_tools.__globals__["json"].dumps

    def fail_large_json(value, *args, **kwargs):
        if isinstance(value, (list, dict)):
            raise AssertionError("database_backed_analysis should not JSON-round-trip full row payloads")
        return original_dumps(value, *args, **kwargs)

    monkeypatch.setattr("dba_assistant.orchestrator.tools._database_exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("dba_assistant.orchestrator.tools._table_exists", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._insert_staging_batch",
        lambda _adaptor, _session, *, source_file, rows: len(rows),
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._analyze_staged",
        lambda _adaptor, _session, *, profile, sample_rows: {
            "executive_summary": {"total_samples": 1, "total_keys": 1, "total_bytes": 123},
            "background": {"profile_name": profile.name, "focus_prefix_count": 0},
            "analysis_results": {"total_samples": 1, "total_keys": 1, "total_bytes": 123},
            "sample_overview": {"sample_rows": sample_rows},
            "overall_summary": {"total_samples": 1, "total_keys": 1, "total_bytes": 123},
            "key_type_summary": {
                "counts": {"string": 1},
                "memory_bytes": {"string": 123},
                "rows": [["string", "1", "123"]],
            },
            "key_type_memory_breakdown": {"rows": [["string", "123"]]},
            "expiration_summary": {"expired_count": 0, "persistent_count": 1},
            "non_expiration_summary": {"persistent_count": 1},
            "prefix_top_summary": {"rows": [["cache:*", "1", "123"]]},
            "prefix_expiration_breakdown": {"rows": []},
            "top_big_keys": {"limit": 100, "rows": [["cache:1", "string", "123"]]},
            "top_string_keys": {"limit": 100, "rows": [["cache:1", "123"]]},
            "top_hash_keys": {"limit": 100, "rows": []},
            "top_list_keys": {"limit": 100, "rows": []},
            "top_set_keys": {"limit": 100, "rows": []},
            "top_zset_keys": {"limit": 100, "rows": []},
            "top_stream_keys": {"limit": 100, "rows": []},
            "top_other_keys": {"limit": 100, "rows": []},
            "focused_prefix_analysis": {"sections": []},
            "conclusions": {},
        },
    )
    monkeypatch.setattr("dba_assistant.orchestrator.tools.json.dumps", fail_large_json)

    analysis = service(
        RdbAnalysisRequest(
            prompt="analyze this rdb via mysql",
            inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
            path_mode="database_backed_analysis",
        )
    )

    assert analysis.metadata["route"] == "database_backed_analysis"
    assert analysis.metadata["mysql_full_table_reload"] == "disabled"


def test_analyze_local_rdb_tool_forces_local_input_kind_even_when_request_is_polluted(
    monkeypatch,
    tmp_path: Path,
) -> None:
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
        mysql_host=None,
        mysql_stage_batch_size=None,
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
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb_stream")
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")

    analyze_tool(input_paths=str(source))

    assert captured["input_kind"] == "local_rdb"


def test_stage_rdb_rows_to_mysql_tool_does_not_repeat_approval_for_same_session(monkeypatch) -> None:
    from dba_assistant.adaptors.mysql_adaptor import MySQLConnectionConfig

    captured: dict[str, object] = {"approvals": 0, "created_database": 0, "created_table": 0, "writes": 0}

    class ApproveHandler:
        def request_approval(self, request):
            captured["approvals"] += 1
            return ApprovalResponse(status=ApprovalStatus.APPROVED, action=request.action)

    def mark_created_database(*_args, **_kwargs):
        captured["created_database"] += 1
        return 1

    def mark_created_table(*_args, **_kwargs):
        captured["created_table"] += 1
        return 1

    def mark_write(*_args, **_kwargs):
        captured["writes"] += 1
        return 1

    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._database_exists",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._table_exists",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr("dba_assistant.orchestrator.tools._create_database", mark_created_database)
    monkeypatch.setattr("dba_assistant.orchestrator.tools._create_staging_table", mark_created_table)
    monkeypatch.setattr("dba_assistant.orchestrator.tools._insert_staging_batch", mark_write)

    request = _make_request(
        prompt="stage rows via mysql",
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            mysql_host="192.168.23.176",
            mysql_port=3306,
            mysql_user="root",
            mysql_database="rcs",
            mysql_table="rdb_stage",
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
    stage_tool = next(t for t in tools if t.__name__ == "stage_rdb_rows_to_mysql")

    stage_tool("rdb_stage", '[{"key_name":"a","key_type":"string","size_bytes":1}]', run_id="same-run")
    stage_tool("rdb_stage", '[{"key_name":"b","key_type":"string","size_bytes":2}]', run_id="same-run")

    assert captured["approvals"] == 1
    assert captured["created_database"] == 1
    assert captured["created_table"] == 1
    assert captured["writes"] == 2


def test_stage_rdb_rows_to_mysql_tool_returns_clear_error_when_session_approval_is_denied(
    monkeypatch,
) -> None:
    from dba_assistant.adaptors.mysql_adaptor import MySQLConnectionConfig

    captured: dict[str, object] = {"approvals": 0}

    class DenyHandler:
        def request_approval(self, request):
            captured["approvals"] += 1
            captured["approval_request"] = request
            return ApprovalResponse(status=ApprovalStatus.DENIED, action=request.action)

    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._database_exists",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._table_exists",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._create_database",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("must not create database after denial")
        ),
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._create_staging_table",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("must not create table after denial")
        ),
    )
    monkeypatch.setattr(
        "dba_assistant.orchestrator.tools._insert_staging_batch",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("must not write after denial")
        ),
    )

    request = _make_request(
        prompt="stage rows via mysql",
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            mysql_host="192.168.23.176",
            mysql_port=3306,
            mysql_user="root",
            mysql_database="rcs",
            mysql_table="rdb_stage",
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
    stage_tool = next(t for t in tools if t.__name__ == "stage_rdb_rows_to_mysql")

    with pytest.raises(PermissionError, match="refused MySQL staging write"):
        stage_tool("rdb_stage", '[{"key_name":"a","key_type":"string","size_bytes":1}]', run_id="same-run")

    assert captured["approvals"] == 1
    assert captured["approval_request"].action == "stage_rdb_rows_to_mysql"


def test_prepare_mysql_staging_session_emits_session_and_ddl_phase_logs(
    tmp_path,
    monkeypatch,
) -> None:
    from dba_assistant.adaptors.mysql_adaptor import MySQLConnectionConfig
    from dba_assistant.orchestrator import tools as tools_module

    reset_observability_state()
    observability = ObservabilityConfig(
        enabled=True,
        console_enabled=True,
        console_level="WARNING",
        file_level="INFO",
        log_dir=tmp_path / "logs",
        app_log_file="app.log.jsonl",
        audit_log_file="audit.jsonl",
    )
    bootstrap_observability(observability)

    monkeypatch.setattr("dba_assistant.orchestrator.tools._create_database", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr("dba_assistant.orchestrator.tools._create_staging_table", lambda *_args, **_kwargs: 1)

    config = MySQLConnectionConfig(
        host="192.168.23.176",
        port=3306,
        user="root",
        password="Root@1234!",
        database="analysis_db",
    )
    plan = tools_module.MySQLStagingTargetPlan(
        database_name="analysis_db",
        table_name="rdb_stage_runtime",
        defaulted_database=False,
        defaulted_table=False,
        will_create_database=True,
        will_create_table=True,
    )

    session = tools_module._prepare_mysql_staging_session(
        object(),
        config,
        plan=plan,
        run_id="run-1",
        batch_size=4096,
    )

    assert session.table_name == "rdb_stage_runtime"
    records = [
        json.loads(line)
        for line in observability.app_log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    phase_records = [
        record
        for record in records
        if record.get("event_name") == "mysql_staging_phase"
    ]
    stages = {record.get("stage") for record in phase_records}

    assert "session_start" in stages
    assert "create_database_start" in stages
    assert "create_database_end" in stages
    assert "create_table_start" in stages
    assert "create_table_end" in stages
    assert "session_ready" in stages
    assert any(record.get("mysql_host") == "192.168.23.176" for record in phase_records)
    assert any(record.get("mysql_port") == 3306 for record in phase_records)
    assert any(record.get("mysql_database") == "analysis_db" for record in phase_records)
    assert any(record.get("mysql_table") == "rdb_stage_runtime" for record in phase_records)
    assert any(record.get("mysql_stage_batch_size") == 4096 for record in phase_records)

    reset_observability_state()


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
        mysql_host=None,
        mysql_stage_batch_size=None,
        mysql_database=None,
        mysql_table=None,
        mysql_query=None,
        service=None,
    ):
        captured["input_paths"] = input_paths
        captured["input_kind"] = input_kind
        captured["mysql_database"] = mysql_database
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
    assert captured["mysql_database"] == "analysis_db"
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
    tools = build_all_tools(request)
    discover_tool = next(t for t in tools if t.__name__ == "discover_remote_rdb")

    result = json.loads(discover_tool(redis_host="redis.example", redis_port=6379, redis_db=0))
    assert result["redis_host"] == "redis.example"
    assert result["redis_port"] == 6379
    assert result["redis_db"] == 0
    assert result["redis_dir"] == "/data"
    assert result["dbfilename"] == "dump.rdb"
    assert result["rdb_path"] == "/data/dump.rdb"
    assert result["rdb_path_source"] == "discovered"
    assert result["approval_required"] is True
    assert "call ensure_remote_rdb_snapshot next" in (discover_tool.__doc__ or "").lower()


def test_resolve_remote_rdb_fetch_plan_prefers_explicit_override() -> None:
    resolution = resolve_remote_rdb_fetch_plan(
        {"rdb_path": "/data/discovered.rdb", "rdb_path_source": "discovered"},
        remote_rdb_path="/tmp/override.rdb",
    )

    assert resolution == {
        "remote_rdb_path": "/tmp/override.rdb",
        "remote_rdb_path_source": "user_override",
    }


def test_resolve_remote_rdb_fetch_plan_uses_discovered_path_when_no_override() -> None:
    resolution = resolve_remote_rdb_fetch_plan(
        {"rdb_path": "/data/discovered.rdb", "rdb_path_source": "discovered"},
    )

    assert resolution == {
        "remote_rdb_path": "/data/discovered.rdb",
        "remote_rdb_path_source": "discovered",
    }


def test_fetch_remote_rdb_via_ssh_tool_fetches_only(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeSSHAdaptor:
        def fetch_file(self, config, remote_path, local_path):
            captured["ssh_config"] = config
            captured["remote_path"] = remote_path
            local_path.write_text("fixture", encoding="utf-8")
            return local_path

    monkeypatch.setattr("dba_assistant.orchestrator.tools.SSHAdaptor", FakeSSHAdaptor)

    request = _make_request(
        secrets=Secrets(ssh_password="ssh-secret"),
    )
    tools = build_all_tools(request)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    result = Path(
        fetch_tool(
            remote_rdb_path="/data/dump.rdb",
            ssh_host="ssh.example",
            ssh_port=2222,
            ssh_username="root",
            local_directory=str(tmp_path),
        )
    )

    assert result == tmp_path / "dump.rdb"
    assert result.exists()
    assert captured["remote_path"] == "/data/dump.rdb"
    assert captured["ssh_config"].host == "ssh.example"
    assert captured["ssh_config"].port == 2222
    assert captured["ssh_config"].username == "root"
    assert captured["ssh_config"].password == "ssh-secret"


def test_fetch_remote_rdb_via_ssh_tool_uses_request_ssh_context_when_args_omitted(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeSSHAdaptor:
        def fetch_file(self, config, remote_path, local_path):
            captured["ssh_config"] = config
            captured["remote_path"] = remote_path
            local_path.write_text("fixture", encoding="utf-8")
            return local_path

    monkeypatch.setattr("dba_assistant.orchestrator.tools.SSHAdaptor", FakeSSHAdaptor)

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            ssh_host="ssh.example",
            ssh_port=2222,
            ssh_username="root",
        ),
        secrets=Secrets(ssh_password="secret"),
    )
    tools = build_all_tools(request)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    fetch_tool(remote_rdb_path="/data/dump.rdb", local_directory=str(tmp_path))

    assert captured["remote_path"] == "/data/dump.rdb"
    assert captured["ssh_config"].host == "ssh.example"
    assert captured["ssh_config"].port == 2222
    assert captured["ssh_config"].username == "root"
    assert captured["ssh_config"].password == "secret"


def test_fetch_remote_rdb_via_ssh_uses_ssh_secret_not_redis_secret(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    class FakeSSHAdaptor:
        def fetch_file(self, config, remote_path, local_path):
            captured["ssh_config"] = config
            local_path.write_text("fixture", encoding="utf-8")
            return local_path

    monkeypatch.setattr("dba_assistant.orchestrator.tools.SSHAdaptor", FakeSSHAdaptor)

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            ssh_host="192.168.23.54",
            ssh_username="root",
        ),
        secrets=Secrets(redis_password="123456", ssh_password="root"),
    )
    tools = build_all_tools(request)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    fetch_tool(remote_rdb_path="/data/redis/data/dump.rdb", local_directory=str(tmp_path))

    assert captured["ssh_config"].username == "root"
    assert captured["ssh_config"].password == "root"


def test_fetch_remote_rdb_via_ssh_returns_error_without_remote_rdb_path() -> None:
    request = _make_request(
        runtime_inputs=RuntimeInputs(ssh_host="ssh.example", ssh_username="root"),
        secrets=Secrets(ssh_password="root"),
    )
    tools = build_all_tools(request)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    result = fetch_tool(remote_rdb_path="")

    assert "remote_rdb_path is required" in result.lower()


def test_ensure_remote_rdb_snapshot_tool_generates_latest_snapshot(monkeypatch) -> None:
    import json

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

    monkeypatch.setattr("dba_assistant.orchestrator.tools.RedisAdaptor", lambda: FakeRedisAdaptor())
    monkeypatch.setattr("dba_assistant.orchestrator.tools.time.sleep", lambda seconds: events.append(f"sleep:{seconds}"))

    request = _make_request(
        secrets=Secrets(redis_password="123456"),
    )
    tools = build_all_tools(request)
    ensure_tool = next(t for t in tools if t.__name__ == "ensure_remote_rdb_snapshot")

    result = json.loads(
        ensure_tool(
            redis_host="redis.example",
            redis_port=6379,
            redis_db=0,
            remote_rdb_path="/data/redis/data/dump.rdb",
        )
    )

    assert result["status"] == "succeeded"
    assert result["lastsave"] == 200
    assert result["bgsave_in_progress"] == 0
    assert result["rdb_path"] == "/data/redis/data/dump.rdb"
    assert events[:7] == [
        "ping-password:123456",
        "info:persistence",
        "info-password:123456",
        "config:dir:123456",
        "config:dbfilename:123456",
        "bgsave",
        "info:persistence",
    ]


def test_discover_remote_rdb_tool_reports_redis_password_supplied_without_leaking_secret(monkeypatch) -> None:
    import json

    request = _make_request(
        secrets=Secrets(redis_password="123456"),
    )
    tools = build_all_tools(request)
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

    result = json.loads(discover_tool(redis_host="192.168.23.54", redis_port=6379, redis_db=0))

    assert result["status"] == "failed"
    assert result["error_kind"] == "authentication_failed"
    assert result["redis_password_supplied"] == "yes"
    assert "123456" not in json.dumps(result)
