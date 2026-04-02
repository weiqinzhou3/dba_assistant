"""Plain-text summary reporter for Phase 1."""

from __future__ import annotations

from dba_assistant.core.analyzer.types import AnalysisResult
from dba_assistant.core.reporter.report_model import AnalysisReport, coerce_analysis_report, render_summary_text
from dba_assistant.core.reporter.types import IReporter, ReportArtifact, ReportFormat, ReportOutputConfig


class SummaryReporter(IReporter[AnalysisResult | AnalysisReport]):
    def render(self, analysis: AnalysisResult | AnalysisReport, config: ReportOutputConfig) -> ReportArtifact:
        if isinstance(analysis, AnalysisResult):
            content = self._render_legacy_text(analysis)
        else:
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

    def _render_legacy_text(self, analysis: AnalysisResult) -> str:
        lines = [analysis.title, "=" * len(analysis.title), "", analysis.summary, ""]

        if analysis.metadata:
            lines.append("Metadata")
            lines.append("--------")
            for key, value in sorted(analysis.metadata.items()):
                lines.append(f"- {key}: {value}")
            lines.append("")

        if analysis.risk_summary:
            lines.append("Risk Summary")
            lines.append("------------")
            for key, value in sorted(analysis.risk_summary.items()):
                lines.append(f"- {key}: {value}")
            lines.append("")

        for section in analysis.sections:
            lines.append(section.title)
            lines.append("-" * len(section.title))
            lines.append(section.summary)
            lines.append("")
            lines.extend(section.paragraphs)
            if section.paragraphs:
                lines.append("")
            for table in section.tables:
                lines.append(table.title)
                lines.append(", ".join(table.columns))
                for row in table.rows:
                    lines.append(", ".join(row))
                lines.append("")

        return "\n".join(lines).strip() + "\n"
