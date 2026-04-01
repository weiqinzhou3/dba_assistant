"""Interface-only HTML reporter placeholder for Phase 1."""

from dba_assistant.core.analyzer.types import AnalysisResult
from dba_assistant.core.reporter.types import IReporter, ReportArtifact, ReportOutputConfig


class HtmlReporter(IReporter[AnalysisResult]):
    def render(self, analysis: AnalysisResult, config: ReportOutputConfig) -> ReportArtifact:
        raise NotImplementedError("HTML reporting is defined at interface level only in Phase 1.")
