from __future__ import annotations

from pathlib import Path

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.application.request_models import NormalizedRequest
from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock
from dba_assistant.core.reporter.types import ReportFormat, ReportOutputConfig
from dba_assistant.deep_agent_integration.config import AppConfig
from dba_assistant.deep_agent_integration.run import run_phase2_request
from dba_assistant.tools.analyze_rdb import analyze_rdb_tool
from dba_assistant.tools.generate_analysis_report import generate_analysis_report


def execute_request(request: NormalizedRequest, *, config: AppConfig) -> str:
    if request.runtime_inputs.input_paths:
        analysis_result = analyze_rdb_tool(
            request.prompt,
            list(request.runtime_inputs.input_paths),
            profile_name=request.rdb_overrides.profile_name or "generic",
            profile_overrides=_build_profile_overrides(request),
        )
        artifact = generate_analysis_report(
            _build_phase3_summary_report(
                analysis_result,
                input_paths=request.runtime_inputs.input_paths,
            ),
            ReportOutputConfig(format=ReportFormat.SUMMARY),
        )
        return artifact.content or ""

    if not request.runtime_inputs.redis_host:
        raise ValueError("Phase 2 requires a Redis host in the normalized request.")

    redis_connection = RedisConnectionConfig(
        host=request.runtime_inputs.redis_host,
        port=request.runtime_inputs.redis_port,
        db=request.runtime_inputs.redis_db,
        password=request.secrets.redis_password,
        socket_timeout=config.runtime.redis_socket_timeout,
    )
    return run_phase2_request(
        request.prompt,
        config=config,
        redis_connection=redis_connection,
    )


def _build_profile_overrides(request: NormalizedRequest) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if request.rdb_overrides.focus_prefixes:
        overrides["focus_prefixes"] = request.rdb_overrides.focus_prefixes
    if request.rdb_overrides.top_n:
        overrides["top_n"] = dict(request.rdb_overrides.top_n)
    return overrides


def _build_phase3_summary_report(
    analysis_result: dict[str, object],
    *,
    input_paths: tuple[Path, ...],
) -> AnalysisReport:
    path_name = str(analysis_result.get("path", "3c"))
    profile_name = str(analysis_result.get("profile", "generic"))
    input_labels = ", ".join(path.name for path in input_paths)

    return AnalysisReport(
        title="Redis RDB Analysis",
        summary=(
            f"Analyzed {len(input_paths)} local RDB input(s) through path {path_name} "
            f"using the {profile_name} profile."
        ),
        sections=[
            ReportSectionModel(
                id="analysis_results",
                title="Analysis Results",
                blocks=[
                    TextBlock(text=f"Path: {path_name}"),
                    TextBlock(text=f"Profile: {profile_name}"),
                    TextBlock(text=f"Inputs: {input_labels}"),
                ],
            )
        ],
        metadata={
            "input_count": str(len(input_paths)),
            "path": path_name,
            "profile": profile_name,
        },
    )
