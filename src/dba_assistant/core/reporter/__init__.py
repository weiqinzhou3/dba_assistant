"""Reporter layer contracts and implementations."""

from dba_assistant.core.reporter.docx_reporter import DocxReporter
from dba_assistant.core.reporter.html_reporter import HtmlReporter
from dba_assistant.core.reporter.generate_analysis_report import generate_analysis_report
from dba_assistant.core.reporter.pdf_reporter import PdfReporter
from dba_assistant.core.reporter.report_model import (
    AnalysisReport,
    ReportSectionModel,
    TableBlock,
    TextBlock,
    coerce_analysis_report,
    render_summary_text,
)
from dba_assistant.core.reporter.summary_reporter import SummaryReporter
from dba_assistant.core.reporter.types import (
    IReporter,
    OutputMode,
    ReportArtifact,
    ReportFormat,
    ReportOutputConfig,
)

__all__ = [
    "DocxReporter",
    "HtmlReporter",
    "IReporter",
    "OutputMode",
    "PdfReporter",
    "ReportArtifact",
    "ReportFormat",
    "ReportOutputConfig",
    "AnalysisReport",
    "coerce_analysis_report",
    "ReportSectionModel",
    "SummaryReporter",
    "TableBlock",
    "TextBlock",
    "render_summary_text",
    "generate_analysis_report",
]
