"""Minimal docx reporter for Phase 1."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

from docx import Document

from dba_assistant.core.analyzer.types import AnalysisResult
from dba_assistant.core.reporter.report_model import AnalysisReport, TableBlock, TextBlock, coerce_analysis_report
from dba_assistant.core.reporter.types import IReporter, ReportArtifact, ReportFormat, ReportOutputConfig


class DocxReporter(IReporter[AnalysisResult | AnalysisReport]):
    def __init__(self, repository_root: Path | None = None) -> None:
        self.repository_root = repository_root or Path(__file__).resolve().parents[4]

    def render(self, analysis: AnalysisResult | AnalysisReport, config: ReportOutputConfig) -> ReportArtifact:
        if config.output_path is None:
            raise ValueError("DocxReporter requires an output_path.")

        template_name = config.template_name or "rdb-analysis"
        template = self._load_module(
            self.repository_root / "templates" / "reports" / template_name / "template_spec.py",
            f"{template_name.replace('-', '_')}_template",
        ).TEMPLATE
        cover_module = self._load_module(
            self.repository_root / "templates" / "reports" / "shared" / "cover.py",
            "shared_cover",
        )
        disclaimer_module = self._load_module(
            self.repository_root / "templates" / "reports" / "shared" / "disclaimer.py",
            "shared_disclaimer",
        )
        table_style_module = self._load_module(
            self.repository_root / "templates" / "reports" / "shared" / "table_styles.py",
            "shared_table_styles",
        )

        cover = cover_module.build_cover_spec(
            title=template["cover_title"],
            subtitle=template["cover_subtitle"],
        )

        document = Document()
        document.add_heading(cover.title, level=0)
        if cover.subtitle:
            document.add_paragraph(cover.subtitle)

        document.add_heading(template["summary_heading"], level=1)
        if isinstance(analysis, AnalysisResult):
            self._render_legacy_analysis_result(document, analysis, cover.metadata_order, template, disclaimer_module, table_style_module.DEFAULT_DOCX_TABLE_STYLE)
        else:
            report = coerce_analysis_report(analysis)
            self._render_analysis_report(document, report, cover.metadata_order, template, disclaimer_module, table_style_module.DEFAULT_DOCX_TABLE_STYLE)

        config.output_path.parent.mkdir(parents=True, exist_ok=True)
        document.save(config.output_path)
        return ReportArtifact(format=ReportFormat.DOCX, output_path=config.output_path, content=None)

    def _render_legacy_analysis_result(
        self,
        document: Document,
        analysis: AnalysisResult,
        metadata_order,
        template,
        disclaimer_module,
        table_style: str,
    ) -> None:
        for key in metadata_order:
            if key in analysis.metadata:
                document.add_paragraph(f"{key}: {analysis.metadata[key]}")

        if analysis.summary:
            document.add_paragraph(analysis.summary)

        self._render_legacy_sections(document, analysis.sections, table_style)

        if template["include_disclaimer"]:
            document.add_heading(disclaimer_module.DISCLAIMER_TITLE, level=1)
            for paragraph in disclaimer_module.DISCLAIMER_PARAGRAPHS:
                document.add_paragraph(paragraph)

    def _render_analysis_report(
        self,
        document: Document,
        report: AnalysisReport,
        metadata_order,
        template,
        disclaimer_module,
        table_style: str,
    ) -> None:
        for key in metadata_order:
            if key in report.metadata:
                document.add_paragraph(f"{key}: {report.metadata[key]}")

        if report.summary:
            document.add_paragraph(report.summary)

        self._render_sections(document, report.sections, table_style)

        if template["include_disclaimer"]:
            document.add_heading(disclaimer_module.DISCLAIMER_TITLE, level=1)
            for paragraph in disclaimer_module.DISCLAIMER_PARAGRAPHS:
                document.add_paragraph(paragraph)

    def _render_sections(self, document: Document, sections, table_style: str) -> None:
        for section in sections:
            document.add_heading(section.title, level=1)
            for block in section.blocks:
                if isinstance(block, TextBlock):
                    document.add_paragraph(block.text)
                    continue
                if not isinstance(block, TableBlock):
                    raise TypeError(f"Unsupported block type: {type(block)!r}")
                document.add_paragraph(block.title)
                docx_table = document.add_table(rows=1, cols=len(block.columns))
                docx_table.style = table_style
                for index, column in enumerate(block.columns):
                    docx_table.rows[0].cells[index].text = column
                for row in block.rows:
                    cells = docx_table.add_row().cells
                    for index, value in enumerate(row):
                        cells[index].text = value

    def _render_legacy_sections(self, document: Document, sections, table_style: str) -> None:
        for section in sections:
            document.add_heading(section.title, level=1)
            document.add_paragraph(section.summary)
            for paragraph in section.paragraphs:
                document.add_paragraph(paragraph)
            for table in section.tables:
                document.add_paragraph(table.title)
                docx_table = document.add_table(rows=1, cols=len(table.columns))
                docx_table.style = table_style
                for index, column in enumerate(table.columns):
                    docx_table.rows[0].cells[index].text = column
                for row in table.rows:
                    cells = docx_table.add_row().cells
                    for index, value in enumerate(row):
                        cells[index].text = value

    def _load_module(self, path: Path, module_name: str) -> ModuleType:
        spec = spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load module at {path}")
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
