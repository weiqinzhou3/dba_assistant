from __future__ import annotations

from dba_assistant.core.analyzer.types import AnalysisResult
from dba_assistant.core.observability import get_current_execution_session
from dba_assistant.core.reporter.report_model import AnalysisReport, coerce_analysis_report, render_summary_text
from dba_assistant.core.reporter.types import ReportArtifact, ReportFormat, ReportOutputConfig


def generate_analysis_report(
    analysis: AnalysisReport | AnalysisResult,
    config: ReportOutputConfig,
) -> ReportArtifact:
    report = coerce_analysis_report(analysis)
    session = get_current_execution_session()

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
        return artifact

    raise NotImplementedError(f"Unsupported report format: {config.format}")
