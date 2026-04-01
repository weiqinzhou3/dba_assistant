"""Interface-only PDF reporter placeholder for Phase 1."""

from dba_assistant.core.analyzer.types import AnalysisResult
from dba_assistant.core.reporter.types import IReporter, ReportArtifact, ReportOutputConfig


class PdfReporter(IReporter[AnalysisResult]):
    def render(self, analysis: AnalysisResult, config: ReportOutputConfig) -> ReportArtifact:
        raise NotImplementedError("PDF reporting is defined at interface level only in Phase 1.")
