from pathlib import Path

from docx import Document

from dba_assistant.core.analyzer.types import AnalysisResult, ReportSection, TableModel
from dba_assistant.core.reporter.docx_reporter import DocxReporter
from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock
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
        metadata={"environment": "prod", "generated_at": "2026-04-01"},
        risk_summary={"warning": 1},
    )


def test_docx_reporter_creates_a_minimal_report_document(tmp_path: Path) -> None:
    output_path = tmp_path / "rdb-analysis.docx"

    artifact = DocxReporter().render(
        build_analysis(),
        ReportOutputConfig(
            output_path=output_path,
            mode=OutputMode.REPORT,
            format=ReportFormat.DOCX,
            template_name="rdb-analysis",
        ),
    )

    document = Document(output_path)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)

    assert artifact.output_path == output_path
    assert output_path.exists()
    assert "Redis RDB Analysis Report" in text
    assert "Largest Keys" in text
    assert "Risk Summary" not in text
    assert len(document.tables) == 1


def test_docx_reporter_supports_generic_analysis_report(tmp_path: Path) -> None:
    output_path = tmp_path / "generic-report.docx"
    report = AnalysisReport(
        title="Redis RDB Analysis",
        summary="No urgent risk found.",
        sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
    )

    artifact = DocxReporter().render(
        report,
        ReportOutputConfig(
            output_path=output_path,
            mode=OutputMode.REPORT,
            format=ReportFormat.DOCX,
            template_name="rdb-analysis",
        ),
    )

    document = Document(output_path)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)

    assert artifact.output_path == output_path
    assert "Redis RDB Analysis" in text
    assert "Summary" in text
