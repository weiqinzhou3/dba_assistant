"""Plain-text summary reporter for Phase 1."""

from __future__ import annotations

from dba_assistant.core.analyzer.types import AnalysisResult
from dba_assistant.core.reporter.report_model import AnalysisReport, coerce_analysis_report, render_summary_text
from dba_assistant.core.reporter.types import IReporter, ReportArtifact, ReportFormat, ReportOutputConfig


class SummaryReporter(IReporter[AnalysisResult | AnalysisReport]):
    def render(self, analysis: AnalysisResult | AnalysisReport, config: ReportOutputConfig) -> ReportArtifact:
        report = coerce_analysis_report(analysis)
        content = render_summary_text(report)
        if config.output_path is not None:
            config.output_path.parent.mkdir(parents=True, exist_ok=True)
            config.output_path.write_text(content, encoding="utf-8")
        return ReportArtifact(
            format=ReportFormat.SUMMARY,
            output_path=config.output_path,
            content=content,
        )
