"""E2E tests for Phase 3 RDB analysis through the thin CLI.

These tests verify that CLI args flow correctly through the interface adapter
and that normalization + overrides produce the expected NormalizedRequest.
"""
from pathlib import Path
from types import SimpleNamespace

from dba_assistant.cli import main
from dba_assistant.interface import adapter as adapter_module


def test_cli_prompt_first_docx_request_is_passed_through_interface_adapter(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"))
    captured: dict[str, object] = {}

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)

    def fake_run_orchestrated(normalized, *, config, approval_handler):
        captured["normalized"] = normalized
        return "docx ok"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    exit_code = main(
        [
            "ask",
            "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx",
            "--input",
            str(source),
        ]
    )

    assert exit_code == 0
    request = captured["normalized"]
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

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)

    def fake_run_orchestrated(normalized, *, config, approval_handler):
        captured["normalized"] = normalized
        return "summary ok"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

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
    request = captured["normalized"]
    assert request.rdb_overrides.profile_name == "generic"
    assert request.runtime_inputs.output_mode == "summary"
    assert request.runtime_inputs.report_format is None
    assert request.runtime_inputs.output_path == override_path
    assert request.runtime_inputs.input_paths == (source,)
    assert capsys.readouterr().out == "summary ok\n"
