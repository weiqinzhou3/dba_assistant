from pathlib import Path

from dba_assistant.core.analyzer.types import AnalysisResult, ReportSection, TableModel
from dba_assistant.core.reporter.types import OutputMode, ReportFormat, ReportOutputConfig


def test_report_output_config_defaults_to_docx_report_mode(tmp_path: Path) -> None:
    config = ReportOutputConfig(output_path=tmp_path / "report.docx")

    assert config.mode is OutputMode.REPORT
    assert config.format is ReportFormat.DOCX
    assert config.output_path == tmp_path / "report.docx"


def test_analysis_result_preserves_nested_sections_and_tables() -> None:
    table = TableModel(
        title="Top Keys",
        columns=["Key", "Bytes"],
        rows=[["user:1", "128"]],
    )
    section = ReportSection(
        title="Largest Keys",
        summary="Largest keys in the dataset",
        paragraphs=["The dataset is dominated by user session keys."],
        tables=[table],
    )
    analysis = AnalysisResult(
        title="Redis RDB Analysis",
        summary="No urgent risk found.",
        sections=[section],
        metadata={"environment": "prod"},
        risk_summary={"warning": 1},
    )

    assert analysis.sections[0].tables[0].rows[0][1] == "128"
    assert analysis.metadata["environment"] == "prod"
    assert analysis.risk_summary["warning"] == 1
