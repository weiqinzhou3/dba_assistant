from pathlib import Path

from dba_assistant.application.request_models import RuntimeInputs
from dba_assistant.core.reporter.output_path_policy import (
    default_report_output_path,
    ensure_report_output_path,
    infer_report_format_alias,
)


def test_infer_report_format_alias_maps_word_to_docx() -> None:
    assert infer_report_format_alias("word") == "docx"
    assert infer_report_format_alias("Word 文件") == "docx"
    assert infer_report_format_alias("docx/word") == "docx"


def test_default_report_output_path_uses_outputs_directory_and_docx_suffix(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "dba_assistant.core.reporter.output_path_policy._timestamp_slug",
        lambda: "20260406_123456",
    )

    path = default_report_output_path("docx", base_dir=tmp_path / "outputs")

    assert path == tmp_path / "outputs" / "dba_assistant_report_20260406_123456.docx"
    assert path.parent.exists()
    assert path.suffix == ".docx"


def test_default_report_output_path_avoids_overwriting_existing_file(tmp_path, monkeypatch) -> None:
    base_dir = tmp_path / "outputs"
    base_dir.mkdir()
    existing = base_dir / "dba_assistant_report_20260406_123456.docx"
    existing.write_text("taken", encoding="utf-8")

    monkeypatch.setattr(
        "dba_assistant.core.reporter.output_path_policy._timestamp_slug",
        lambda: "20260406_123456",
    )

    path = default_report_output_path("docx", base_dir=base_dir)

    assert path == base_dir / "dba_assistant_report_20260406_123456_2.docx"


def test_ensure_report_output_path_generates_docx_path_when_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "dba_assistant.core.reporter.output_path_policy.default_report_output_path",
        lambda format, base_dir=None: tmp_path / "outputs" / "auto.docx",
    )

    runtime_inputs = RuntimeInputs(output_mode="report", report_format="docx")

    updated = ensure_report_output_path(runtime_inputs, "docx")

    assert updated.output_path == tmp_path / "outputs" / "auto.docx"


def test_ensure_report_output_path_keeps_existing_prompt_path() -> None:
    runtime_inputs = RuntimeInputs(
        output_mode="report",
        report_format="docx",
        output_path=Path("/tmp/from-prompt.docx"),
    )

    updated = ensure_report_output_path(runtime_inputs, "docx")

    assert updated.output_path == Path("/tmp/from-prompt.docx")


def test_ensure_report_output_path_leaves_summary_requests_unchanged() -> None:
    runtime_inputs = RuntimeInputs(output_mode="summary", report_format=None, output_path=None)

    updated = ensure_report_output_path(runtime_inputs, "summary")

    assert updated.output_path is None
