from pathlib import Path
import json

import pytest

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
from dba_assistant.capabilities.redis_rdb_analysis.remote_input import RemoteRedisDiscoveryError
from dba_assistant.core.observability import bootstrap_observability, reset_observability_state
from dba_assistant.deep_agent_integration.config import ModelConfig, ObservabilityConfig, ProviderKind
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


def _make_config():
    return type(
        "Config",
        (),
        {
            "model": ModelConfig(
                preset_name="ollama_local",
                provider_kind=ProviderKind.OPENAI_COMPATIBLE,
                model_name="qwen3:8b",
                base_url="http://127.0.0.1:11434/v1",
                api_key="ollama",
            ),
            "runtime": type("Runtime", (), {})(),
        },
    )()


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
    assert "collect_offline_inspection_dataset" not in names
    assert "redis_inspection_log_candidates" not in names
    assert "review_redis_log_candidates" not in names
    assert "render_redis_inspection_report" not in names
    assert "redis_inspection_report" not in names
    assert "discover_remote_rdb" in names
    assert "ensure_remote_rdb_snapshot" in names
    assert "fetch_remote_rdb_via_ssh" in names
    assert "mysql_read_query" in names
    assert "stage_rdb_rows_to_mysql" in names


def test_inspection_request_exposes_only_inspection_and_readonly_redis_tools(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "inspection"
    evidence_dir.mkdir()
    request = _make_request(
        prompt="生成 Redis 巡检报告",
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            input_kind="redis_inspection",
            input_paths=(evidence_dir,),
        ),
    )

    tools = build_all_tools(request)
    names = {t.__name__ for t in tools}

    assert {
        "redis_ping",
        "redis_info",
        "redis_config_get",
        "redis_slowlog_get",
        "redis_client_list",
        "redis_cluster_info",
        "redis_cluster_nodes",
        "collect_offline_inspection_dataset",
        "redis_inspection_log_candidates",
        "review_redis_log_candidates",
        "render_redis_inspection_report",
        "redis_inspection_report",
    }.issubset(names)
    assert "stage_local_rdb_to_mysql" not in names
    assert "stage_rdb_rows_to_mysql" not in names
    assert "analyze_staged_rdb" not in names
    assert "load_preparsed_dataset_from_mysql" not in names
    assert "analyze_preparsed_dataset" not in names
    assert "analyze_local_rdb_stream" not in names
    assert "discover_remote_rdb" not in names
    assert "ensure_remote_rdb_snapshot" not in names
    assert "fetch_remote_rdb_via_ssh" not in names
    assert "mysql_read_query" not in names


def test_rdb_request_keeps_rdb_mysql_and_remote_rdb_tools() -> None:
    request = _make_request(
        prompt="analyze this RDB through MySQL staging if needed",
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            input_kind="local_rdb",
            input_paths=(Path("/tmp/dump.rdb"),),
        ),
    )

    tools = build_all_tools(request)
    names = {t.__name__ for t in tools}

    assert "inspect_local_rdb" in names
    assert "analyze_local_rdb_stream" in names
    assert "stage_local_rdb_to_mysql" in names
    assert "stage_rdb_rows_to_mysql" in names
    assert "analyze_staged_rdb" in names
    assert "load_preparsed_dataset_from_mysql" in names
    assert "analyze_preparsed_dataset" in names
    assert "discover_remote_rdb" in names
    assert "ensure_remote_rdb_snapshot" in names
    assert "fetch_remote_rdb_via_ssh" in names
    assert "collect_offline_inspection_dataset" not in names


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
    assert "collect_offline_inspection_dataset" not in names
    assert "redis_inspection_log_candidates" not in names
    assert "review_redis_log_candidates" not in names
    assert "render_redis_inspection_report" not in names
    assert "redis_inspection_report" not in names
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
    sample_message = candidates_payload["preview"][0]["samples"][0]["raw_message"]
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
                    "supporting_samples": [sample_message],
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
    assert candidates_payload["log_candidates_handle"].startswith("inspection_log_candidates_")
    assert "Redis 日志显示 OOM" in result
    assert "问题概览与整改优先级" in result


def test_offline_inspection_uses_explicit_review_tool_before_render(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "inspection"
    source.mkdir()
    (source / "info.txt").write_text(
        "redis_version:7.0.15\nrole:master\ntcp_port:6379\ncluster_state:ok\n",
        encoding="utf-8",
    )
    (source / "redis.log").write_text(
        "2026-04-14 09:00:00 # OOM command not allowed when used memory > 'maxmemory'\n",
        encoding="utf-8",
    )

    review_calls: list[dict[str, object]] = []

    def fake_review(log_candidates_json, *, model, focus_topics="", report_language="zh-CN"):
        payload = json.loads(log_candidates_json)
        candidate = payload["clusters"][0]["log_candidates"][0]
        sample = candidate["raw_message"]
        review_calls.append(
            {
                "log_candidates_json": log_candidates_json,
                "model": model,
                "focus_topics": focus_topics,
                "report_language": report_language,
            }
        )
        return json.dumps(
            {
                "issues": [
                    {
                        "cluster_id": payload["clusters"][0]["cluster_id"],
                        "cluster_name": payload["clusters"][0]["cluster_name"],
                        "issue_name": "Redis 日志显示 OOM",
                        "is_anomalous": True,
                        "severity": "high",
                        "why": "review tool judged OOM as anomalous.",
                        "affected_nodes": [candidate["node_id"]],
                        "supporting_samples": [sample],
                        "recommendation": "检查 maxmemory 与淘汰策略。",
                        "merge_key": "oom-memory-pressure",
                        "category": "log",
                        "confidence": "high",
                    }
                ]
            }
        )

    monkeypatch.setattr("dba_assistant.orchestrator.tools._review_redis_log_candidates", fake_review)
    monkeypatch.setattr("dba_assistant.orchestrator.tools.build_model", lambda model_config: "review-model")

    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    tools = build_all_tools(request, config=_make_config())
    collect_tool = next(t for t in tools if t.__name__ == "collect_offline_inspection_dataset")
    candidates_tool = next(t for t in tools if t.__name__ == "redis_inspection_log_candidates")
    review_tool = next(t for t in tools if t.__name__ == "review_redis_log_candidates")
    render_tool = next(t for t in tools if t.__name__ == "render_redis_inspection_report")

    collect_payload = json.loads(
        collect_tool(
            input_paths=str(source),
            log_start_time="2026-04-01 00:00:00",
            log_end_time="2026-04-30 23:59:59",
        )
    )
    candidates_summary = json.loads(candidates_tool(dataset_handle=collect_payload["dataset_handle"]))
    reviewed_json = review_tool(
        log_candidates_handle=candidates_summary["log_candidates_handle"],
        report_language="zh-CN",
    )
    result = render_tool(
        dataset_handle=collect_payload["dataset_handle"],
        reviewed_log_issues_json=reviewed_json,
        output_mode="summary",
        report_format="summary",
    )

    assert review_calls[0]["model"] == "review-model"
    assert json.loads(review_calls[0]["log_candidates_json"])["clusters"][0]["log_candidates"]
    assert "clusters" not in candidates_summary
    assert candidates_summary["candidate_count"] == 1
    assert "Redis 日志显示 OOM" in result
    assert "问题概览与整改优先级" in result
    assert "风险与整改建议" in result
    assert "review tool judged OOM as anomalous" in result


def test_review_redis_log_candidates_tool_does_not_call_generic_filesystem_tools(
    monkeypatch,
    tmp_path: Path,
) -> None:
    called = {"review": False}

    def fake_review(log_candidates_json, *, model, focus_topics="", report_language="zh-CN"):
        called["review"] = True
        return '{"issues": []}'

    def forbidden(*_args, **_kwargs):
        raise AssertionError("review tool must not use generic filesystem tools")

    monkeypatch.setattr("dba_assistant.orchestrator.tools._review_redis_log_candidates", fake_review)
    monkeypatch.setattr("dba_assistant.orchestrator.tools.build_model", lambda model_config: "review-model")
    for name in ("ls", "glob", "grep", "read_file"):
        monkeypatch.setitem(build_all_tools.__globals__, name, forbidden)

    source = tmp_path / "inspection"
    source.mkdir()
    (source / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")
    (source / "redis.log").write_text("2026-04-14 09:00:00 # OOM command not allowed\n", encoding="utf-8")

    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    tools = build_all_tools(request, config=_make_config())
    candidates_tool = next(t for t in tools if t.__name__ == "redis_inspection_log_candidates")
    review_tool = next(t for t in tools if t.__name__ == "review_redis_log_candidates")
    candidates_summary = json.loads(
        candidates_tool(
            input_paths=str(source),
            log_start_time="2026-04-01 00:00:00",
            log_end_time="2026-04-30 23:59:59",
        )
    )

    result = json.loads(review_tool(log_candidates_handle=candidates_summary["log_candidates_handle"]))

    assert called["review"] is True
    assert result == {"issues": []}


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

    assert payload["log_candidates_handle"].startswith("inspection_log_candidates_")
    assert payload["candidate_count"] == 1
    assert payload["preview"][0]["samples"][0]["candidate_signal"] == "oom_signal"
    assert "clusters" not in payload


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


def test_redis_inspection_log_candidates_tool_returns_handle_and_neutral_preview(tmp_path: Path) -> None:
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

    candidate = payload["preview"][0]["samples"][0]
    assert payload["log_candidates_handle"].startswith("inspection_log_candidates_")
    assert payload["cluster_count"] == 1
    assert payload["candidate_count"] == 1
    assert candidate["candidate_signal"] == "persistence_signal"
    assert "clusters" not in payload
    assert "abnormal" not in json.dumps(payload).lower()


def test_review_handle_path_loads_full_payload_and_schema_from_skill_asset(
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
    schema_path = Path("skills/redis-inspection-report/assets/log_issue_schema.json")
    expected_schema = json.loads(schema_path.read_text(encoding="utf-8"))

    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    captured: dict[str, object] = {}

    def fake_review(log_candidates_json, *, model, focus_topics="", report_language="zh-CN"):
        captured["payload"] = json.loads(log_candidates_json)
        return '{"issues": []}'

    monkeypatch.setattr("dba_assistant.orchestrator.tools._review_redis_log_candidates", fake_review)
    monkeypatch.setattr("dba_assistant.orchestrator.tools.build_model", lambda model_config: "review-model")

    tools = build_all_tools(request, config=_make_config())
    candidates_tool = next(t for t in tools if t.__name__ == "redis_inspection_log_candidates")
    review_tool = next(t for t in tools if t.__name__ == "review_redis_log_candidates")

    summary = json.loads(
        candidates_tool(
            input_paths=str(source),
            log_start_time="2026-04-01 00:00:00",
            log_end_time="2026-04-30 23:59:59",
        )
    )
    review_tool(log_candidates_handle=summary["log_candidates_handle"])

    assert captured["payload"]["review_output_schema"] == expected_schema
    assert captured["payload"]["clusters"][0]["log_candidates"][0]["candidate_signal"] == "oom_signal"


def test_log_candidates_summary_avoids_returning_large_raw_payload(tmp_path: Path) -> None:
    source = tmp_path / "inspection"
    source.mkdir()
    (source / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")
    (source / "redis.log").write_text(
        "\n".join(
            f"2026-04-14 09:00:{index:02d} # OOM command not allowed huge-event-{index}"
            for index in range(60)
        ),
        encoding="utf-8",
    )

    request = _make_request(runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=()))
    candidates_tool = next(t for t in build_all_tools(request) if t.__name__ == "redis_inspection_log_candidates")

    raw_result = candidates_tool(
        input_paths=str(source),
        log_start_time="2026-04-01 00:00:00",
        log_end_time="2026-04-30 23:59:59",
    )
    payload = json.loads(raw_result)

    assert payload["candidate_count"] == 60
    assert payload["log_candidates_handle"].startswith("inspection_log_candidates_")
    assert "huge-event-59" not in raw_result
    assert len(raw_result) < 5000


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
    dataset = RedisInspectionOfflineCollector().collect(
        RedisInspectionOfflineInput(sources=(source,), log_time_window_days=30)
    )
    report = analyze_inspection_dataset(dataset)
    problem_section = next(section for section in report.sections if section.id == "problem_overview__priority")
    problem_table = next(block for block in problem_section.blocks if hasattr(block, "columns"))

    assert problem_table.title == "优先级速览"
    assert problem_table.columns == ["序号", "集群", "风险等级", "关键问题"]


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


def test_redis_inspection_report_docx_without_output_path_uses_runtime_artifact_dir(
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
    artifact_dir = tmp_path / "configured-artifacts"
    default_path = artifact_dir / "dba_assistant_redis_inspection_20260414_010203.docx"
    default_path.unlink(missing_ok=True)

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            input_paths=(),
            artifact_dir=artifact_dir,
        )
    )
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
    artifact_dir = tmp_path / "configured-artifacts"
    expected_docx = artifact_dir / "dba_assistant_report_20260414_010203.docx"
    monkeypatch.setattr(
        "dba_assistant.core.reporter.output_path_policy._timestamp_slug",
        lambda: "20260414_010203",
    )

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

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="report",
            report_format="docx",
            input_paths=(source,),
            artifact_dir=artifact_dir,
        )
    )
    tools = build_all_tools(request)
    analyze_tool = next(t for t in tools if t.__name__ == "analyze_local_rdb_stream")

    result = analyze_tool(input_paths=str(source), output_mode="report", report_format="docx")

    assert result == str(expected_docx)
    assert expected_docx.exists()


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


def test_fetch_remote_rdb_via_ssh_without_local_directory_uses_runtime_evidence_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    evidence_dir = tmp_path / "configured-evidence"

    class FakeSSHAdaptor:
        def fetch_file(self, config, remote_path, local_path):
            captured["remote_path"] = remote_path
            captured["local_path"] = local_path
            local_path.write_text("fixture", encoding="utf-8")
            return local_path

    monkeypatch.setattr("dba_assistant.orchestrator.tools.SSHAdaptor", FakeSSHAdaptor)

    request = _make_request(
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            ssh_host="ssh.example",
            ssh_port=2222,
            ssh_username="root",
            evidence_dir=evidence_dir,
        ),
        secrets=Secrets(ssh_password="secret"),
    )
    tools = build_all_tools(request)
    fetch_tool = next(t for t in tools if t.__name__ == "fetch_remote_rdb_via_ssh")

    result = Path(fetch_tool(remote_rdb_path="/data/dump.rdb"))

    assert result == captured["local_path"]
    assert result.parent.parent == evidence_dir
    assert result.name == "dump.rdb"
    assert result.exists()
    assert captured["remote_path"] == "/data/dump.rdb"


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
