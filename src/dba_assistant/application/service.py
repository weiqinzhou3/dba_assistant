from __future__ import annotations

import re

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.application.request_models import NormalizedRequest
from dba_assistant.core.reporter.types import OutputMode, ReportFormat, ReportOutputConfig
from dba_assistant.deep_agent_integration.config import AppConfig
from dba_assistant.deep_agent_integration.run import run_phase2_request
from dba_assistant.tools.analyze_rdb import analyze_rdb_tool
from dba_assistant.tools.generate_analysis_report import generate_analysis_report

_REMOTE_RDB_PROMPT_PATTERN = re.compile(r"(?i)\brdb\b|快照")


def execute_request(request: NormalizedRequest, *, config: AppConfig) -> str:
    if request.runtime_inputs.input_paths:
        analysis_result = analyze_rdb_tool(
            request.prompt,
            list(request.runtime_inputs.input_paths),
            profile_name=request.rdb_overrides.profile_name or "generic",
            path_mode=request.rdb_overrides.route_name or "auto",
            profile_overrides=_build_profile_overrides(request),
        )
        artifact = generate_analysis_report(
            analysis_result,
            _build_report_output_config(request),
        )
        if artifact.content is not None:
            return artifact.content
        if artifact.output_path is None:
            raise ValueError("Report rendering did not produce content or an output path.")
        return str(artifact.output_path)

    if _is_phase3_remote_rdb_request(request):
        raise ValueError(
            "Remote RDB acquisition is part of the Phase 3 service contract but is not yet wired "
            "through the prompt-first CLI. Provide a local RDB via --input or use a lower-level "
            "Phase 3 service call."
        )

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


def _build_report_output_config(request: NormalizedRequest) -> ReportOutputConfig:
    report_format = _resolve_report_format(request)
    if report_format is ReportFormat.DOCX and request.runtime_inputs.output_path is None:
        raise ValueError("DOCX output requires an output path. Provide one in the prompt or via --output.")
    return ReportOutputConfig(
        mode=OutputMode.SUMMARY if report_format is ReportFormat.SUMMARY else OutputMode.REPORT,
        format=report_format,
        output_path=request.runtime_inputs.output_path,
        template_name="rdb-analysis",
    )


def _resolve_report_format(request: NormalizedRequest) -> ReportFormat:
    if request.runtime_inputs.output_mode == "summary" or request.runtime_inputs.report_format == "summary":
        return ReportFormat.SUMMARY
    return ReportFormat.DOCX


def _is_phase3_remote_rdb_request(request: NormalizedRequest) -> bool:
    return request.runtime_inputs.redis_host is not None and _REMOTE_RDB_PROMPT_PATTERN.search(request.prompt) is not None
