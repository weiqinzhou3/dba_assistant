import json
from pathlib import Path

import dba_assistant.tools as tools
from dba_assistant.core.reporter.generate_analysis_report import (
    generate_analysis_report as core_generate_analysis_report,
)
from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock
from dba_assistant.skills.redis_rdb_analysis.types import InputSourceKind
from dba_assistant.tools.analyze_rdb import analyze_rdb_tool
from dba_assistant.tools.generate_analysis_report import generate_analysis_report


def test_analyze_rdb_tool_uses_generic_profile_by_default(tmp_path: Path) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    report = AnalysisReport(
        title="Redis RDB Analysis",
        sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
    )
    captured: dict[str, object] = {}

    def fake_service(request):
        captured["request"] = request
        return report

    result = analyze_rdb_tool(
        prompt="analyze this rdb",
        input_paths=[source],
        service=fake_service,
    )

    assert result is report
    assert captured["request"].inputs[0].source == source
    assert captured["request"].inputs[0].kind is InputSourceKind.LOCAL_RDB


def test_analyze_rdb_tool_handles_explicit_mysql_local_prompt(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    rows = json.loads(Path("tests/fixtures/rdb/direct/sample_key_records.json").read_text(encoding="utf-8"))
    monkeypatch.setattr("dba_assistant.skills.redis_rdb_analysis.service._parse_rdb_rows", lambda _path: rows)

    result = analyze_rdb_tool(
        prompt="analyze this rdb via mysql",
        input_paths=[source],
    )

    assert result.title == "Redis RDB Analysis"
    assert result.metadata["route"] == "legacy_sql_pipeline"
    assert result.metadata["path"] == "3a"
    assert result.metadata["profile"] == "generic"
    assert any(section.id == "top_big_keys" for section in result.sections)


def test_tools_package_exports_phase3_entry_points() -> None:
    assert tools.analyze_rdb_tool is analyze_rdb_tool
    assert tools.generate_analysis_report is generate_analysis_report
    assert generate_analysis_report is core_generate_analysis_report
