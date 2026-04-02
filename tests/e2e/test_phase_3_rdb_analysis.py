from pathlib import Path
from types import SimpleNamespace

from dba_assistant.cli import main
from dba_assistant.core.reporter.report_model import AnalysisReport, ReportSectionModel, TextBlock


def test_cli_rdb_command_emits_summary(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"))
    captured: dict[str, object] = {}
    analysis_report = AnalysisReport(
        title="Redis RDB Analysis",
        sections=[ReportSectionModel(id="summary", title="Summary", blocks=[TextBlock(text="ok")])],
    )

    monkeypatch.setattr("dba_assistant.cli.load_app_config", lambda config_path=None: config)

    def fake_analyze_rdb_tool(
        prompt,
        input_paths,
        *,
        profile_name="generic",
        profile_overrides=None,
        service=None,
    ):
        captured["prompt"] = prompt
        captured["input_paths"] = input_paths
        captured["profile_name"] = profile_name
        captured["profile_overrides"] = profile_overrides
        captured["service"] = service
        return analysis_report

    monkeypatch.setattr(
        "dba_assistant.application.service.analyze_rdb_tool",
        fake_analyze_rdb_tool,
    )

    exit_code = main(["ask", "analyze this rdb with summary", "--input", str(source)])

    assert exit_code == 0
    assert captured["prompt"] == "analyze this rdb with summary"
    assert captured["input_paths"] == [source]
    output = capsys.readouterr().out
    assert "Redis RDB Analysis" in output
    assert "Summary" in output
    assert "ok" in output
