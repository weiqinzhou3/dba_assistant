from pathlib import Path

from dba_assistant.core.analyzer.types import AnalysisResult, ReportSection, TableModel
from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock
from dba_assistant.core.reporter.summary_reporter import SummaryReporter
from dba_assistant.core.reporter.types import OutputMode, ReportFormat, ReportOutputConfig


def build_analysis() -> AnalysisResult:
    return AnalysisResult(
        title="Redis RDB Analysis",
        summary="No urgent risk found.",
        sections=[
            ReportSection(
                title="Largest Keys",
                summary="Largest keys in the dataset",
                paragraphs=["Two session keys dominate memory usage."],
                tables=[
                    TableModel(
                        title="Top Keys",
                        columns=["Key", "Bytes"],
                        rows=[["session:1", "2048"]],
                    )
                ],
            )
        ],
        metadata={"environment": "prod"},
        risk_summary={"warning": 1},
    )


def test_summary_reporter_returns_rendered_text() -> None:
    artifact = SummaryReporter().render(
        build_analysis(),
        ReportOutputConfig(
            mode=OutputMode.SUMMARY,
            format=ReportFormat.SUMMARY,
            output_path=None,
        ),
    )

    assert artifact.output_path is None
    assert artifact.content is not None
    assert "Redis RDB Analysis" in artifact.content
    assert "Largest Keys" in artifact.content
    assert "session:1" in artifact.content


def test_summary_reporter_can_write_summary_to_a_text_file(tmp_path: Path) -> None:
    output_path = tmp_path / "summary.txt"

    artifact = SummaryReporter().render(
        build_analysis(),
        ReportOutputConfig(
            mode=OutputMode.SUMMARY,
            format=ReportFormat.SUMMARY,
            output_path=output_path,
        ),
    )

    assert artifact.output_path == output_path
    assert output_path.read_text(encoding="utf-8").startswith("Redis RDB Analysis")


def test_summary_reporter_supports_generic_analysis_report() -> None:
    report = AnalysisReport(
        title="Redis RDB Analysis",
        summary="No urgent risk found.",
        sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
    )

    artifact = SummaryReporter().render(
        report,
        ReportOutputConfig(mode=OutputMode.SUMMARY, format=ReportFormat.SUMMARY),
    )

    assert artifact.content is not None
    assert "No urgent risk found." in artifact.content
