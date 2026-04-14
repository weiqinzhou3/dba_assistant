from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from dba_assistant.application.request_models import (
    DEFAULT_MYSQL_DATABASE,
    DEFAULT_MYSQL_STAGE_BATCH_SIZE,
)
from dba_assistant.core.reporter.output_path_policy import ensure_report_output_path
from dba_assistant.core.reporter.types import OutputMode, ReportFormat, ReportOutputConfig


def render_analysis_output(
    analysis,
    *,
    runtime_inputs,
    output_mode: str,
    report_format: str,
    output_path: Path | None,
) -> str:
    from dba_assistant.core.reporter.generate_analysis_report import (
        generate_analysis_report as _generate,
    )

    effective_runtime_inputs = ensure_report_output_path(
        replace(
            runtime_inputs,
            output_mode=output_mode,
            report_format=report_format,
            output_path=output_path,
        ),
        report_format,
    )
    fmt = ReportFormat.SUMMARY if report_format == "summary" else ReportFormat.DOCX
    if fmt is ReportFormat.DOCX and effective_runtime_inputs.output_path is None:
        return "Error: DOCX output requires an output path."

    config = ReportOutputConfig(
        mode=OutputMode.SUMMARY if output_mode == "summary" else OutputMode.REPORT,
        format=fmt,
        output_path=effective_runtime_inputs.output_path,
        template_name="rdb-analysis",
        language=getattr(analysis, "language", "zh-CN"),
    )
    artifact = _generate(analysis, config)
    if artifact.content is not None:
        return artifact.content
    if artifact.output_path is not None:
        return str(artifact.output_path)
    return "Analysis complete but no output generated."


def append_mysql_runtime_note(content: str, *, analysis) -> str:
    metadata = getattr(analysis, "metadata", None)
    if not isinstance(metadata, dict):
        return content
    if metadata.get("route") != "database_backed_analysis":
        return content
    database_name = str(metadata.get("mysql_database") or "").strip() or DEFAULT_MYSQL_DATABASE
    table_name = str(metadata.get("mysql_table") or "").strip() or "unknown"
    staged_rows = str(metadata.get("mysql_staged_rows") or "0")
    batch_size = str(metadata.get("mysql_stage_batch_size") or DEFAULT_MYSQL_STAGE_BATCH_SIZE)
    cleanup_mode = str(metadata.get("mysql_cleanup_mode") or "retain")
    progress = str(metadata.get("mysql_progress") or "").strip()
    lines = [
        "[MySQL-backed staging]",
        f"database={database_name}",
        f"table={table_name}",
        f"staged_rows={staged_rows}",
        f"batch_size={batch_size}",
        "shared_table_mode=yes",
        "full_table_reload=disabled",
        f"cleanup_mode={cleanup_mode}",
    ]
    if progress:
        lines.append(f"progress={progress}")
    note = "\n".join(lines)
    if note in content:
        return content
    return f"{content}\n\n{note}"
