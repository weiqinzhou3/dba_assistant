"""Plain-text summary reporter for Phase 1."""

from __future__ import annotations

from dba_assistant.core.analyzer.types import AnalysisResult
from dba_assistant.core.reporter.generate_analysis_report import generate_analysis_report
from dba_assistant.core.reporter.types import IReporter, ReportArtifact, ReportFormat, ReportOutputConfig


class SummaryReporter(IReporter[AnalysisResult]):
    def render(self, analysis: AnalysisResult, config: ReportOutputConfig) -> ReportArtifact:
        artifact = generate_analysis_report(analysis, config)
        if artifact.format is not ReportFormat.SUMMARY:
            raise ValueError("SummaryReporter must render summary output.")
        return artifact
