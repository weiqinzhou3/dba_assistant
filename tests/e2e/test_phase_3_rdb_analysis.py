from pathlib import Path
from types import SimpleNamespace

from dba_assistant.cli import main


def test_cli_prompt_first_docx_request_is_passed_through_execute_request(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"))
    captured: dict[str, object] = {}

    monkeypatch.setattr("dba_assistant.cli.load_app_config", lambda config_path=None: config)

    def fake_execute_request(request, *, config):
        captured["request"] = request
        captured["config"] = config
        return "docx ok"

    monkeypatch.setattr("dba_assistant.cli.execute_request", fake_execute_request)

    exit_code = main(
        [
            "ask",
            "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx",
            "--input",
            str(source),
        ]
    )

    assert exit_code == 0
    request = captured["request"]
    assert request.prompt == "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx"
    assert request.runtime_inputs.input_paths == (source,)
    assert request.rdb_overrides.profile_name == "rcs"
    assert request.runtime_inputs.output_mode == "report"
    assert request.runtime_inputs.report_format == "docx"
    assert request.runtime_inputs.output_path == Path("/tmp/rcs.docx")
    output = capsys.readouterr().out
    assert output == "docx ok\n"


def test_cli_explicit_overrides_win_over_prompt_derived_phase3_intent(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"))
    captured: dict[str, object] = {}
    override_path = tmp_path / "override-summary.txt"

    monkeypatch.setattr("dba_assistant.cli.load_app_config", lambda config_path=None: config)

    def fake_execute_request(request, *, config):
        captured["request"] = request
        captured["config"] = config
        return "summary ok"

    monkeypatch.setattr("dba_assistant.cli.execute_request", fake_execute_request)

    exit_code = main(
        [
            "ask",
            "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx",
            "--input",
            str(source),
            "--profile",
            "generic",
            "--report-format",
            "summary",
            "--output",
            str(override_path),
        ]
    )

    assert exit_code == 0
    request = captured["request"]
    assert request.rdb_overrides.profile_name == "generic"
    assert request.runtime_inputs.output_mode == "summary"
    assert request.runtime_inputs.report_format is None
    assert request.runtime_inputs.output_path == override_path
    assert request.runtime_inputs.input_paths == (source,)
    assert capsys.readouterr().out == "summary ok\n"
