import json
from pathlib import Path

from dba_assistant.core.reporter.docx_reporter import DocxReporter
from dba_assistant.core.observability import bootstrap_observability, reset_observability_state
from dba_assistant.core.reporter.generate_analysis_report import generate_analysis_report
from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock
from dba_assistant.core.reporter.types import ReportArtifact, ReportFormat, ReportOutputConfig
from dba_assistant.deep_agent_integration.config import ObservabilityConfig


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


def test_generate_analysis_report_emits_mysql_report_render_logs(tmp_path: Path) -> None:
    reset_observability_state()
    observability = ObservabilityConfig(
        enabled=True,
        console_enabled=True,
        console_level="WARNING",
        file_level="INFO",
        log_dir=tmp_path / "logs",
        app_log_file="app.log.jsonl",
        audit_log_file="audit.jsonl",
    )
    bootstrap_observability(observability)

    report = AnalysisReport(
        title="Redis RDB 分析报告",
        sections=[ReportSectionModel(id="summary", title="摘要", blocks=[TextBlock(text="ok")])],
        metadata={
            "route": "database_backed_analysis",
            "mysql_host": "db.example",
            "mysql_port": "3306",
            "mysql_database": "analysis_db",
            "mysql_table": "rdb_stage_runtime",
            "mysql_run_id": "run-1",
        },
    )

    generate_analysis_report(report, ReportOutputConfig(format=ReportFormat.SUMMARY))

    records = [
        json.loads(line)
        for line in observability.app_log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    render_records = [
        record
        for record in records
        if record.get("event_name") == "mysql_analysis_phase" and record.get("query_name") == "report_render"
    ]

    assert any(record.get("stage") == "start" for record in render_records)
    assert any(record.get("stage") == "end" for record in render_records)
    assert any(record.get("mysql_table") == "rdb_stage_runtime" for record in render_records)

    reset_observability_state()
