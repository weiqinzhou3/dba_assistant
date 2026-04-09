from __future__ import annotations

import logging
from time import perf_counter

from dba_assistant.core.analyzer.types import AnalysisResult
from dba_assistant.core.reporter.report_model import AnalysisReport, coerce_analysis_report, render_summary_text
from dba_assistant.core.reporter.types import ReportArtifact, ReportFormat, ReportOutputConfig

logger = logging.getLogger(__name__)


def generate_analysis_report(
    analysis: AnalysisReport | AnalysisResult,
    config: ReportOutputConfig,
) -> ReportArtifact:
    report = coerce_analysis_report(analysis)
    from dba_assistant.core.observability.context import get_current_execution_session

    session = get_current_execution_session()
    report_started = perf_counter()

    _log_mysql_report_render_phase(report, stage="start")

    try:
        if config.format is ReportFormat.SUMMARY:
            content = render_summary_text(report, language=config.language)
            if config.output_path is not None:
                config.output_path.parent.mkdir(parents=True, exist_ok=True)
                config.output_path.write_text(content, encoding="utf-8")
            artifact = ReportArtifact(format=ReportFormat.SUMMARY, output_path=config.output_path, content=content)
            if session is not None:
                session.record_artifact(
                    output_mode=config.mode.value,
                    output_path=artifact.output_path,
                    artifact_id=None,
                    report_metadata=getattr(report, "metadata", {}),
                )
            _log_mysql_report_render_phase(
                report,
                stage="end",
                elapsed_seconds=round(perf_counter() - report_started, 6),
                rows_returned=len(report.sections),
            )
            return artifact

        if config.format is ReportFormat.DOCX:
            from dba_assistant.core.reporter.docx_reporter import DocxReporter

            artifact = DocxReporter().render(report, config)
            if session is not None:
                session.record_artifact(
                    output_mode=config.mode.value,
                    output_path=artifact.output_path,
                    artifact_id=None if artifact.output_path is None else str(artifact.output_path),
                    report_metadata=getattr(report, "metadata", {}),
                )
            _log_mysql_report_render_phase(
                report,
                stage="end",
                elapsed_seconds=round(perf_counter() - report_started, 6),
                rows_returned=len(report.sections),
            )
            return artifact

        raise NotImplementedError(f"Unsupported report format: {config.format}")
    except Exception as exc:  # noqa: BLE001
        _log_mysql_report_render_phase(
            report,
            stage="error",
            elapsed_seconds=round(perf_counter() - report_started, 6),
            error=str(exc),
        )
        raise


def _log_mysql_report_render_phase(
    report: AnalysisReport,
    *,
    stage: str,
    elapsed_seconds: float | None = None,
    rows_returned: int | None = None,
    error: str | None = None,
) -> None:
    metadata = getattr(report, "metadata", {}) or {}
    if metadata.get("route") != "database_backed_analysis":
        return None
    logger.info(
        "mysql analysis phase",
        extra={
            "event_name": "mysql_analysis_phase",
            "query_name": "report_render",
            "stage": stage,
            "mysql_host": metadata.get("mysql_host"),
            "mysql_port": metadata.get("mysql_port"),
            "mysql_database": metadata.get("mysql_database"),
            "mysql_table": metadata.get("mysql_table"),
            "run_id": metadata.get("mysql_run_id"),
            "elapsed_seconds": elapsed_seconds,
            "rows_returned": rows_returned,
            "error": error,
        },
    )
    return None
