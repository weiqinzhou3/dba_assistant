from dba_assistant.core.reporter.docx_reporter import DocxReporter
from dba_assistant.core.reporter.generate_analysis_report import generate_analysis_report
from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock
from dba_assistant.core.reporter.types import ReportArtifact, ReportFormat, ReportOutputConfig


def test_generate_analysis_report_returns_summary_artifact() -> None:
    report = AnalysisReport(
        title="Redis RDB 分析报告",
        sections=[ReportSectionModel(id="summary", title="摘要", blocks=[TextBlock(text="ok")])],
    )

    artifact = generate_analysis_report(report, ReportOutputConfig(format=ReportFormat.SUMMARY))

    assert artifact.content == "Redis RDB 分析报告\n\n摘要\nok"


def test_generate_analysis_report_delegates_docx_rendering(monkeypatch) -> None:
    report = AnalysisReport(
        title="Redis RDB Analysis",
        sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
    )
    config = ReportOutputConfig(format=ReportFormat.DOCX, output_path=None)

    calls: dict[str, object] = {}

    def fake_render(self, analysis, render_config):
        calls["analysis"] = analysis
        calls["config"] = render_config
        return ReportArtifact(format=ReportFormat.DOCX, output_path=None, content=None)

    monkeypatch.setattr(DocxReporter, "render", fake_render)

    artifact = generate_analysis_report(report, config)

    assert calls["analysis"] is report
    assert calls["config"] is config
    assert artifact.format is ReportFormat.DOCX
