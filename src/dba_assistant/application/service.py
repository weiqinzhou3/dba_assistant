"""Application service helpers.

After the thin-CLI refactoring, business routing is handled by the
orchestrator (Deep Agent capability selection).  This module retains
shared helper functions used by orchestrator tools.
"""
from __future__ import annotations

from dba_assistant.application.request_models import NormalizedRequest
from dba_assistant.core.reporter.types import OutputMode, ReportFormat, ReportOutputConfig


def build_profile_overrides(request: NormalizedRequest) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if request.rdb_overrides.focus_prefixes:
        overrides["focus_prefixes"] = request.rdb_overrides.focus_prefixes
    if request.rdb_overrides.focus_only:
        overrides["focus_only"] = True
    if request.rdb_overrides.top_n:
        overrides["top_n"] = dict(request.rdb_overrides.top_n)
    return overrides


def build_report_output_config(request: NormalizedRequest) -> ReportOutputConfig:
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
