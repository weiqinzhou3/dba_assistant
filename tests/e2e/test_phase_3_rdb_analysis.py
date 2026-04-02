from pathlib import Path
from types import SimpleNamespace

from dba_assistant.cli import main
from dba_assistant.core.reporter.types import ReportArtifact, ReportFormat


def test_cli_rdb_command_emits_summary(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"))
    captured: dict[str, object] = {}

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
        return {"path": "3c", "profile": profile_name}

    def fake_generate_analysis_report(report, report_config):
        captured["report"] = report
        captured["report_config"] = report_config
        return ReportArtifact(
            format=ReportFormat.SUMMARY,
            output_path=None,
            content="Redis RDB Analysis\n\nSummary\nok",
        )

    monkeypatch.setattr(
        "dba_assistant.application.service.analyze_rdb_tool",
        fake_analyze_rdb_tool,
    )
    monkeypatch.setattr(
        "dba_assistant.application.service.generate_analysis_report",
        fake_generate_analysis_report,
    )

    exit_code = main(["ask", "analyze this rdb with summary", "--input", str(source)])

    assert exit_code == 0
    assert captured["prompt"] == "analyze this rdb with summary"
    assert captured["input_paths"] == [source]
    assert captured["report"].title == "Redis RDB Analysis"
    assert "Redis RDB Analysis" in capsys.readouterr().out
