from __future__ import annotations

from dba_assistant.core.analyzer.types import AnalysisResult
from dba_assistant.core.reporter.report_model import AnalysisReport, coerce_analysis_report, render_summary_text
from dba_assistant.core.reporter.types import ReportArtifact, ReportFormat, ReportOutputConfig


def generate_analysis_report(
    analysis: AnalysisReport | AnalysisResult,
    config: ReportOutputConfig,
) -> ReportArtifact:
    report = coerce_analysis_report(analysis)

    if config.format is ReportFormat.SUMMARY:
        content = render_summary_text(report, language=config.language)
        if config.output_path is not None:
            config.output_path.parent.mkdir(parents=True, exist_ok=True)
            config.output_path.write_text(content, encoding="utf-8")
        return ReportArtifact(format=ReportFormat.SUMMARY, output_path=config.output_path, content=content)

    if config.format is ReportFormat.DOCX:
        from dba_assistant.core.reporter.docx_reporter import DocxReporter

        return DocxReporter().render(report, config)

    raise NotImplementedError(f"Unsupported report format: {config.format}")
