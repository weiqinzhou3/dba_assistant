from dba_assistant.core.reporter.generate_analysis_report import generate_analysis_report
from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock
from dba_assistant.core.reporter.types import ReportFormat, ReportOutputConfig


def test_generate_analysis_report_returns_summary_artifact() -> None:
    report = AnalysisReport(
        title="Redis RDB Analysis",
        sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
    )

    artifact = generate_analysis_report(report, ReportOutputConfig(format=ReportFormat.SUMMARY))

    assert artifact.content == "Redis RDB Analysis\n\nSummary\nok"
