"""Tests for application service helpers (post-refactoring).

The routing logic has moved to the orchestrator.  These tests verify the
helper functions retained in service.py.
"""
from pathlib import Path

import pytest

from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
from dba_assistant.application.service import build_profile_overrides, build_report_output_config
from dba_assistant.core.reporter.types import OutputMode, ReportFormat


def test_build_profile_overrides_extracts_focus_scope_and_top_n() -> None:
    request = NormalizedRequest(
        raw_prompt="test",
        prompt="test",
        runtime_inputs=RuntimeInputs(output_mode="summary"),
        secrets=Secrets(),
        rdb_overrides=RdbOverrides(
            focus_prefixes=("loan:*", "cache:*"),
            focus_only=True,
            top_n={"top_big_keys": 5},
        ),
    )
    overrides = build_profile_overrides(request)
    assert overrides == {
        "focus_prefixes": ("loan:*", "cache:*"),
        "focus_only": True,
        "top_n": {"top_big_keys": 5},
    }


def test_build_profile_overrides_empty_when_no_overrides() -> None:
    request = NormalizedRequest(
        raw_prompt="test",
        prompt="test",
        runtime_inputs=RuntimeInputs(output_mode="summary"),
        secrets=Secrets(),
        rdb_overrides=RdbOverrides(),
    )
    assert build_profile_overrides(request) == {}


def test_build_report_output_config_summary() -> None:
    request = NormalizedRequest(
        raw_prompt="test",
        prompt="test",
        runtime_inputs=RuntimeInputs(output_mode="summary"),
        secrets=Secrets(),
    )
    config = build_report_output_config(request)
    assert config.format is ReportFormat.SUMMARY
    assert config.mode is OutputMode.SUMMARY


def test_build_report_output_config_docx_requires_output_path() -> None:
    request = NormalizedRequest(
        raw_prompt="test",
        prompt="test",
        runtime_inputs=RuntimeInputs(output_mode="report", report_format="docx"),
        secrets=Secrets(),
    )
    with pytest.raises(ValueError, match="requires an output path"):
        build_report_output_config(request)


def test_build_report_output_config_docx_with_path() -> None:
    request = NormalizedRequest(
        raw_prompt="test",
        prompt="test",
        runtime_inputs=RuntimeInputs(
            output_mode="report",
            report_format="docx",
            output_path=Path("/tmp/out.docx"),
        ),
        secrets=Secrets(),
    )
    config = build_report_output_config(request)
    assert config.format is ReportFormat.DOCX
    assert config.mode is OutputMode.REPORT
    assert config.output_path == Path("/tmp/out.docx")
