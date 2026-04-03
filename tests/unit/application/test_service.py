from pathlib import Path

import pytest

from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock
from dba_assistant.application.service import execute_request
from dba_assistant.core.reporter.types import OutputMode, ReportArtifact, ReportFormat
from dba_assistant.deep_agent_integration.config import AppConfig, ModelConfig, ProviderKind, RuntimeConfig


def test_execute_request_builds_redis_connection_and_calls_phase2_runner(monkeypatch) -> None:
    captured: dict[str, object] = {}

    config = AppConfig(
        model=ModelConfig(
            preset_name="ollama_local",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3:8b",
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
        ),
        runtime=RuntimeConfig(default_output_mode="summary", redis_socket_timeout=6.0),
    )

    request = NormalizedRequest(
        raw_prompt="Use password abc123 to inspect Redis 10.0.0.8:6380 db 2 and give me a summary",
        prompt="Use to inspect Redis 10.0.0.8:6380 db 2 and give me a summary",
        runtime_inputs=RuntimeInputs(redis_host="10.0.0.8", redis_port=6380, redis_db=2, output_mode="summary"),
        secrets=Secrets(redis_password="abc123"),
    )

    def fake_run_phase2_request(prompt, *, config, redis_connection):
        captured["prompt"] = prompt
        captured["config"] = config
        captured["redis_connection"] = redis_connection
        return "phase2 ok"

    monkeypatch.setattr("dba_assistant.application.service.run_phase2_request", fake_run_phase2_request)

    assert execute_request(request, config=config) == "phase2 ok"
    assert captured["prompt"] == "Use to inspect Redis 10.0.0.8:6380 db 2 and give me a summary"
    assert captured["redis_connection"].host == "10.0.0.8"
    assert captured["redis_connection"].port == 6380
    assert captured["redis_connection"].db == 2
    assert captured["redis_connection"].password == "abc123"
    assert captured["redis_connection"].socket_timeout == 6.0


def test_execute_request_runs_phase3_tool_and_renders_summary(monkeypatch) -> None:
    captured: dict[str, object] = {}
    analysis_report = AnalysisReport(
        title="Redis RDB Analysis",
        sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
    )

    config = AppConfig(
        model=ModelConfig(
            preset_name="ollama_local",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3:8b",
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
        ),
        runtime=RuntimeConfig(default_output_mode="summary", redis_socket_timeout=6.0),
    )

    request = NormalizedRequest(
        raw_prompt="analyze this rdb with the rcs profile",
        prompt="analyze this rdb with the rcs profile",
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            input_paths=(Path("/tmp/dump.rdb"),),
        ),
        secrets=Secrets(),
        rdb_overrides=RdbOverrides(
            profile_name="rcs",
            focus_prefixes=("loan:*",),
            top_n={"top_big_keys": 5},
        ),
    )

    def fake_analyze_rdb_tool(
        prompt,
        input_paths,
        *,
        profile_name="generic",
        path_mode="auto",
        profile_overrides=None,
        service=None,
    ):
        captured["prompt"] = prompt
        captured["input_paths"] = input_paths
        captured["profile_name"] = profile_name
        captured["path_mode"] = path_mode
        captured["profile_overrides"] = profile_overrides
        captured["service"] = service
        return analysis_report

    def fake_generate_analysis_report(report, report_config):
        captured["report"] = report
        captured["report_config"] = report_config
        return ReportArtifact(
            format=ReportFormat.SUMMARY,
            output_path=None,
            content="Redis RDB Analysis\n\nSummary\nok",
        )

    monkeypatch.setattr("dba_assistant.application.service.analyze_rdb_tool", fake_analyze_rdb_tool)
    monkeypatch.setattr(
        "dba_assistant.application.service.generate_analysis_report",
        fake_generate_analysis_report,
    )

    assert execute_request(request, config=config) == "Redis RDB Analysis\n\nSummary\nok"
    assert captured["prompt"] == "analyze this rdb with the rcs profile"
    assert captured["input_paths"] == [Path("/tmp/dump.rdb")]
    assert captured["profile_name"] == "rcs"
    assert captured["path_mode"] == "auto"
    assert captured["profile_overrides"] == {
        "focus_prefixes": ("loan:*",),
        "top_n": {"top_big_keys": 5},
    }
    assert captured["report"] is analysis_report
    assert captured["report_config"].format is ReportFormat.SUMMARY
    assert captured["report_config"].mode is OutputMode.SUMMARY
    assert captured["report_config"].template_name == "rdb-analysis"


def test_execute_request_runs_phase3_tool_and_returns_output_path_for_docx(monkeypatch) -> None:
    captured: dict[str, object] = {}
    analysis_report = AnalysisReport(
        title="Redis RDB Analysis",
        sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
    )
    output_path = Path("/tmp/rcs.docx")

    config = AppConfig(
        model=ModelConfig(
            preset_name="ollama_local",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3:8b",
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
        ),
        runtime=RuntimeConfig(default_output_mode="summary", redis_socket_timeout=6.0),
    )

    request = NormalizedRequest(
        raw_prompt="analyze this rdb with the rcs profile",
        prompt="analyze this rdb with the rcs profile",
        runtime_inputs=RuntimeInputs(
            output_mode="report",
            report_format="docx",
            output_path=output_path,
            input_paths=(Path("/tmp/dump.rdb"),),
        ),
        secrets=Secrets(),
        rdb_overrides=RdbOverrides(
            profile_name="rcs",
            focus_prefixes=("loan:*",),
            top_n={"top_big_keys": 5},
        ),
    )

    def fake_analyze_rdb_tool(
        prompt,
        input_paths,
        *,
        profile_name="generic",
        path_mode="auto",
        profile_overrides=None,
        service=None,
    ):
        captured["prompt"] = prompt
        captured["input_paths"] = input_paths
        captured["profile_name"] = profile_name
        captured["path_mode"] = path_mode
        captured["profile_overrides"] = profile_overrides
        captured["service"] = service
        return analysis_report

    def fake_generate_analysis_report(report, report_config):
        captured["report"] = report
        captured["report_config"] = report_config
        return ReportArtifact(
            format=ReportFormat.DOCX,
            output_path=report_config.output_path,
            content=None,
        )

    monkeypatch.setattr("dba_assistant.application.service.analyze_rdb_tool", fake_analyze_rdb_tool)
    monkeypatch.setattr(
        "dba_assistant.application.service.generate_analysis_report",
        fake_generate_analysis_report,
    )

    assert execute_request(request, config=config) == str(output_path)
    assert captured["prompt"] == "analyze this rdb with the rcs profile"
    assert captured["input_paths"] == [Path("/tmp/dump.rdb")]
    assert captured["profile_name"] == "rcs"
    assert captured["path_mode"] == "auto"
    assert captured["profile_overrides"] == {
        "focus_prefixes": ("loan:*",),
        "top_n": {"top_big_keys": 5},
    }
    assert captured["report"] is analysis_report
    assert captured["report_config"].format is ReportFormat.DOCX
    assert captured["report_config"].mode is OutputMode.REPORT
    assert captured["report_config"].output_path == output_path
    assert captured["report_config"].template_name == "rdb-analysis"


def test_execute_request_passes_route_name_to_phase3_tool(monkeypatch) -> None:
    captured: dict[str, object] = {}
    analysis_report = AnalysisReport(
        title="Redis RDB Analysis",
        sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
    )

    config = AppConfig(
        model=ModelConfig(
            preset_name="ollama_local",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3:8b",
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
        ),
        runtime=RuntimeConfig(default_output_mode="summary", redis_socket_timeout=6.0),
    )

    request = NormalizedRequest(
        raw_prompt="analyze this rdb via mysql",
        prompt="analyze this rdb via mysql",
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            input_paths=(Path("/tmp/dump.rdb"),),
        ),
        secrets=Secrets(),
        rdb_overrides=RdbOverrides(
            profile_name="generic",
            route_name="legacy_sql_pipeline",
        ),
    )

    def fake_analyze_rdb_tool(
        prompt,
        input_paths,
        *,
        profile_name="generic",
        path_mode="auto",
        profile_overrides=None,
        service=None,
    ):
        captured["path_mode"] = path_mode
        return analysis_report

    def fake_generate_analysis_report(report, report_config):
        return ReportArtifact(
            format=ReportFormat.SUMMARY,
            output_path=None,
            content="Redis RDB Analysis\n\nSummary\nok",
        )

    monkeypatch.setattr("dba_assistant.application.service.analyze_rdb_tool", fake_analyze_rdb_tool)
    monkeypatch.setattr(
        "dba_assistant.application.service.generate_analysis_report",
        fake_generate_analysis_report,
    )

    assert execute_request(request, config=config) == "Redis RDB Analysis\n\nSummary\nok"
    assert captured["path_mode"] == "legacy_sql_pipeline"


def test_execute_request_rejects_remote_rdb_prompt_in_phase2_boundary(monkeypatch) -> None:
    config = AppConfig(
        model=ModelConfig(
            preset_name="ollama_local",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3:8b",
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
        ),
        runtime=RuntimeConfig(default_output_mode="summary", redis_socket_timeout=6.0),
    )

    request = NormalizedRequest(
        raw_prompt="Analyze the latest RDB from redis.example:6379 and confirm before fetching",
        prompt="Analyze the latest RDB from redis.example:6379 and confirm before fetching",
        runtime_inputs=RuntimeInputs(redis_host="redis.example", redis_port=6379, output_mode="summary"),
        secrets=Secrets(),
    )

    monkeypatch.setattr(
        "dba_assistant.application.service.run_phase2_request",
        lambda *args, **kwargs: pytest.fail("remote RDB prompts must not fall through to Phase 2"),
    )

    with pytest.raises(ValueError, match="Remote RDB acquisition"):
        execute_request(request, config=config)


def test_execute_request_requires_output_path_for_docx(monkeypatch) -> None:
    analysis_report = AnalysisReport(
        title="Redis RDB Analysis",
        sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
    )

    config = AppConfig(
        model=ModelConfig(
            preset_name="ollama_local",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model_name="qwen3:8b",
            base_url="http://127.0.0.1:11434/v1",
            api_key="ollama",
        ),
        runtime=RuntimeConfig(default_output_mode="summary", redis_socket_timeout=6.0),
    )

    request = NormalizedRequest(
        raw_prompt="analyze this rdb and output docx",
        prompt="analyze this rdb and output docx",
        runtime_inputs=RuntimeInputs(
            output_mode="report",
            report_format="docx",
            input_paths=(Path("/tmp/dump.rdb"),),
        ),
        secrets=Secrets(),
        rdb_overrides=RdbOverrides(profile_name="generic"),
    )

    monkeypatch.setattr("dba_assistant.application.service.analyze_rdb_tool", lambda *args, **kwargs: analysis_report)
    monkeypatch.setattr(
        "dba_assistant.application.service.generate_analysis_report",
        lambda *args, **kwargs: pytest.fail("docx rendering should not start without an output path"),
    )

    with pytest.raises(ValueError, match="requires an output path"):
        execute_request(request, config=config)
