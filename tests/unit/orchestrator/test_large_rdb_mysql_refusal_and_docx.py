"""Tests for large-RDB MySQL refusal enforcement and DOCX artifact contract.

Covers:
  1. inspect_local_rdb detects large files and sets session state
  2. User refusal of MySQL latches mysql_staging_refused flag
  3. MySQL-path tools (stage, staged, preparsed) are blocked once refused
  4. ask_user_for_config blocks MySQL questions when refused
  5. analyze_local_rdb_stream respects mysql_staging_refused parameter
  6. No drift to analyze_preparsed_dataset when input is local .rdb
  7. DOCX forcing from prompt detection
  8. DOCX postcondition verifies artifact path
  9. Normal paths (small file, MySQL-backed, remote) are not regressed
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dba_assistant.application.request_models import (
    NormalizedRequest,
    RdbOverrides,
    RuntimeInputs,
    Secrets,
    LARGE_RDB_WARNING_BYTES,
)
from dba_assistant.orchestrator.config_collection_tool import (
    _is_mysql_refusal,
    _is_mysql_related_question,
    make_ask_user_for_config_tool,
)
from dba_assistant.orchestrator.tools import (
    _is_mysql_refusal as tools_is_mysql_refusal,
    _prompt_requests_docx_output,
    _MYSQL_REFUSAL_GUARD_MESSAGE,
    ToolRuntimeContext,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(**overrides) -> NormalizedRequest:
    defaults = dict(
        raw_prompt="test",
        prompt="test",
        runtime_inputs=RuntimeInputs(
            output_mode="summary",
            input_paths=(Path("/tmp/dump.rdb"),),
        ),
        secrets=Secrets(),
        rdb_overrides=RdbOverrides(profile_name="generic"),
    )
    defaults.update(overrides)
    return NormalizedRequest(**defaults)


def _make_context(**overrides) -> ToolRuntimeContext:
    request = overrides.pop("request", _make_request())
    return ToolRuntimeContext(request=request, **overrides)


# ---------------------------------------------------------------------------
# 1. MySQL refusal pattern detection
# ---------------------------------------------------------------------------

class TestMySQLRefusalDetection:
    @pytest.mark.parametrize(
        "text",
        [
            "不要用mysql",
            "不用mysql",
            "不需要mysql",
            "no mysql",
            "No MySQL please",
            "直接分析",
            "skip mysql",
            "without mysql",
            "不要staging",
            "不用数据库",
            "just analyze it",
            "just analyze",
        ],
    )
    def test_refusal_patterns_match(self, text: str) -> None:
        assert _is_mysql_refusal(text), f"Expected refusal detection for: {text}"

    @pytest.mark.parametrize(
        "text",
        [
            "请用mysql分析",
            "yes",
            "好的",
            "analyze this rdb",
            "show me the report",
        ],
    )
    def test_non_refusal_patterns_do_not_match(self, text: str) -> None:
        assert not _is_mysql_refusal(text), f"Unexpected refusal detection for: {text}"


class TestMySQLRelatedQuestion:
    @pytest.mark.parametrize(
        "question",
        [
            "What is your MySQL host?",
            "请提供mysql密码",
            "请提供数据库连接信息",
            "What database should I use?",
            "Do you want staging?",
        ],
    )
    def test_mysql_related_questions_detected(self, question: str) -> None:
        assert _is_mysql_related_question(question)

    @pytest.mark.parametrize(
        "question",
        [
            "What format would you like?",
            "请选择分析方式",
            "Which RDB file?",
        ],
    )
    def test_non_mysql_questions_pass(self, question: str) -> None:
        assert not _is_mysql_related_question(question)


# ---------------------------------------------------------------------------
# 2. DOCX request detection
# ---------------------------------------------------------------------------

class TestDocxRequestDetection:
    @pytest.mark.parametrize(
        "prompt",
        [
            "请帮我分析RDB并输出Word文档",
            "生成DOCX报告",
            "output docx",
            "请生成报告",
            "分析后给我文档",
            "generate a Word report",
        ],
    )
    def test_docx_prompts_detected(self, prompt: str) -> None:
        assert _prompt_requests_docx_output(prompt)

    @pytest.mark.parametrize(
        "prompt",
        [
            "分析这个rdb",
            "show me a summary",
            "analyze the dump",
        ],
    )
    def test_non_docx_prompts_not_detected(self, prompt: str) -> None:
        assert not _prompt_requests_docx_output(prompt)


# ---------------------------------------------------------------------------
# 3. inspect_local_rdb tracks large files in session state
# ---------------------------------------------------------------------------

class TestInspectLocalRdbLargeFileTracking:
    def test_large_file_sets_session_state(self, tmp_path: Path) -> None:
        from dba_assistant.orchestrator.tools import _make_inspect_local_rdb_tool

        large_rdb = tmp_path / "large.rdb"
        with large_rdb.open("wb") as f:
            f.truncate(LARGE_RDB_WARNING_BYTES + 1)

        state: dict[str, Any] = {}
        tool = _make_inspect_local_rdb_tool(state)
        result = json.loads(tool(input_paths=str(large_rdb)))

        assert result[0]["large_file"] is True
        assert state["large_rdb_detected"] is True
        assert str(large_rdb) in state["large_rdb_paths"]

    def test_small_file_does_not_set_large_flag(self, tmp_path: Path) -> None:
        from dba_assistant.orchestrator.tools import _make_inspect_local_rdb_tool

        small_rdb = tmp_path / "small.rdb"
        small_rdb.write_bytes(b"small")

        state: dict[str, Any] = {}
        tool = _make_inspect_local_rdb_tool(state)
        result = json.loads(tool(input_paths=str(small_rdb)))

        assert result[0]["large_file"] is False
        assert "large_rdb_detected" not in state


# ---------------------------------------------------------------------------
# 4. ask_user_for_config blocks MySQL questions when refused
# ---------------------------------------------------------------------------

class TestAskUserForConfigMySQLGuard:
    def test_blocks_mysql_question_when_refused(self) -> None:
        handler = MagicMock()
        state: dict[str, Any] = {"mysql_staging_refused": True}
        tool = make_ask_user_for_config_tool(handler, rdb_session_state=state)

        result = tool(question="What is your MySQL host?")

        assert "declined" in result.lower()
        handler.collect_input.assert_not_called()

    def test_allows_non_mysql_question_when_refused(self) -> None:
        handler = MagicMock()
        handler.collect_input.return_value = "zh-CN"
        state: dict[str, Any] = {"mysql_staging_refused": True}
        tool = make_ask_user_for_config_tool(handler, rdb_session_state=state)

        result = tool(question="What language for the report?")

        assert result == "zh-CN"
        handler.collect_input.assert_called_once()

    def test_detects_refusal_in_user_response_and_latches_flag(self) -> None:
        handler = MagicMock()
        handler.collect_input.return_value = "不要用mysql，直接分析"
        state: dict[str, Any] = {"large_rdb_detected": True}
        tool = make_ask_user_for_config_tool(handler, rdb_session_state=state)

        result = tool(question="Do you want to use MySQL staging?")

        assert result == "不要用mysql，直接分析"
        assert state["mysql_staging_refused"] is True

    def test_no_false_positive_refusal_without_large_rdb(self) -> None:
        handler = MagicMock()
        handler.collect_input.return_value = "no mysql"
        state: dict[str, Any] = {}
        tool = make_ask_user_for_config_tool(handler, rdb_session_state=state)

        tool(question="Do you want MySQL?")

        assert "mysql_staging_refused" not in state


# ---------------------------------------------------------------------------
# 5. MySQL-path tools are guarded when refused
# ---------------------------------------------------------------------------

class TestMySQLPathToolGuards:
    def _build_context(self, prompt: str = "test") -> ToolRuntimeContext:
        return _make_context(request=_make_request(prompt=prompt))

    def test_stage_local_rdb_to_mysql_blocked(self) -> None:
        from dba_assistant.orchestrator.tools import _make_stage_local_rdb_to_mysql_tool

        state: dict[str, Any] = {"mysql_staging_refused": True}
        tool = _make_stage_local_rdb_to_mysql_tool(self._build_context(), state)
        result = tool(input_paths="/tmp/dump.rdb")

        assert result == _MYSQL_REFUSAL_GUARD_MESSAGE

    def test_analyze_staged_rdb_blocked(self) -> None:
        from dba_assistant.orchestrator.tools import _make_analyze_staged_rdb_tool

        state: dict[str, Any] = {"mysql_staging_refused": True}
        tool = _make_analyze_staged_rdb_tool(self._build_context(), state)
        result = tool(mysql_table="rdb_stage_auto_20240101")

        assert result == _MYSQL_REFUSAL_GUARD_MESSAGE

    def test_analyze_preparsed_dataset_blocked(self) -> None:
        from dba_assistant.orchestrator.tools import _make_analyze_preparsed_dataset_tool

        state: dict[str, Any] = {"mysql_staging_refused": True}
        tool = _make_analyze_preparsed_dataset_tool(self._build_context(), state)
        result = tool(input_paths="/tmp/dump.rdb")

        assert result == _MYSQL_REFUSAL_GUARD_MESSAGE

    def test_stage_allowed_when_not_refused(self, tmp_path: Path) -> None:
        """When mysql_staging_refused is not set, the guard is not triggered.

        The tool may still fail for other reasons (e.g. no MySQL connection),
        but the guard message must not appear."""
        from dba_assistant.orchestrator.tools import _make_stage_local_rdb_to_mysql_tool

        rdb = tmp_path / "dump.rdb"
        rdb.write_bytes(b"small")
        state: dict[str, Any] = {}
        tool = _make_stage_local_rdb_to_mysql_tool(self._build_context(), state)
        result = tool(input_paths=str(rdb))

        assert result != _MYSQL_REFUSAL_GUARD_MESSAGE


# ---------------------------------------------------------------------------
# 6. analyze_local_rdb_stream latches mysql_staging_refused
# ---------------------------------------------------------------------------

class TestAnalyzeLocalRdbStreamMySQLRefusal:
    def test_mysql_staging_refused_param_latches_flag(self, tmp_path: Path, monkeypatch) -> None:
        from dba_assistant.orchestrator.tools import _make_analyze_local_rdb_stream_tool

        rdb = tmp_path / "dump.rdb"
        rdb.write_bytes(b"test-data")

        state: dict[str, Any] = {}
        context = _make_context(request=_make_request(prompt="分析这个rdb"))

        tool = _make_analyze_local_rdb_stream_tool(context, state)

        rows = [{"key_name": "k:1", "key_type": "string", "size_bytes": 10,
                 "has_expiration": False, "ttl_seconds": None}]
        monkeypatch.setattr(
            "dba_assistant.capabilities.redis_rdb_analysis.service._stream_rdb_rows",
            lambda _path: __import__(
                "dba_assistant.parsers.rdb_parser_strategy", fromlist=["StreamedRowsResult"]
            ).StreamedRowsResult(rows=iter(rows), strategy_name="test"),
        )

        tool(input_paths=str(rdb), mysql_staging_refused=True)

        assert state["mysql_staging_refused"] is True


# ---------------------------------------------------------------------------
# 7. DOCX forcing from prompt
# ---------------------------------------------------------------------------

class TestDocxForcingFromPrompt:
    def test_analyze_local_rdb_stream_forces_docx_when_prompt_requests_word(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from dba_assistant.orchestrator.tools import _make_analyze_local_rdb_stream_tool

        rdb = tmp_path / "dump.rdb"
        rdb.write_bytes(b"test-data")
        state: dict[str, Any] = {}
        context = _make_context(
            request=_make_request(
                prompt="分析这个RDB并输出Word文档",
                raw_prompt="分析这个RDB并输出Word文档",
                runtime_inputs=RuntimeInputs(
                    output_mode="summary",
                    input_paths=(rdb,),
                    artifact_dir=tmp_path,
                ),
            )
        )
        tool = _make_analyze_local_rdb_stream_tool(context, state)

        rows = [
            {"key_name": "cache:1", "key_type": "string", "size_bytes": 100,
             "has_expiration": False, "ttl_seconds": None},
        ]
        monkeypatch.setattr(
            "dba_assistant.capabilities.redis_rdb_analysis.service._stream_rdb_rows",
            lambda _path: __import__(
                "dba_assistant.parsers.rdb_parser_strategy", fromlist=["StreamedRowsResult"]
            ).StreamedRowsResult(rows=iter(rows), strategy_name="test"),
        )

        # Call WITHOUT explicit output_mode/report_format — the prompt should force DOCX
        result = tool(input_paths=str(rdb))

        assert result.endswith(".docx"), f"Expected .docx path, got: {result}"
        assert Path(result).exists(), f"DOCX file should exist at: {result}"

    def test_summary_returned_when_prompt_does_not_request_docx(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from dba_assistant.orchestrator.tools import _make_analyze_local_rdb_stream_tool

        rdb = tmp_path / "dump.rdb"
        rdb.write_bytes(b"test-data")
        state: dict[str, Any] = {}
        context = _make_context(
            request=_make_request(
                prompt="分析这个RDB",
                raw_prompt="分析这个RDB",
                runtime_inputs=RuntimeInputs(
                    output_mode="summary",
                    input_paths=(rdb,),
                ),
            )
        )
        tool = _make_analyze_local_rdb_stream_tool(context, state)

        rows = [
            {"key_name": "cache:1", "key_type": "string", "size_bytes": 100,
             "has_expiration": False, "ttl_seconds": None},
        ]
        monkeypatch.setattr(
            "dba_assistant.capabilities.redis_rdb_analysis.service._stream_rdb_rows",
            lambda _path: __import__(
                "dba_assistant.parsers.rdb_parser_strategy", fromlist=["StreamedRowsResult"]
            ).StreamedRowsResult(rows=iter(rows), strategy_name="test"),
        )

        result = tool(input_paths=str(rdb))

        # Should be inline summary text, not a docx path
        assert not result.endswith(".docx")
        assert "分析" in result or "analysis" in result.lower() or "本次" in result


# ---------------------------------------------------------------------------
# 8. DOCX postcondition in render_analysis_output
# ---------------------------------------------------------------------------

class TestRenderAnalysisOutputDocxPostcondition:
    def test_returns_docx_path_when_prompt_forces_docx(self, tmp_path: Path) -> None:
        from dba_assistant.core.reporter.report_model import AnalysisReport
        from dba_assistant.orchestrator.report_output import render_analysis_output

        report = AnalysisReport(
            title="Test",
            summary="summary",
            sections=[],
            metadata={"route": "direct_rdb_analysis", "profile": "generic"},
            language="zh-CN",
        )
        result = render_analysis_output(
            report,
            runtime_inputs=RuntimeInputs(artifact_dir=tmp_path),
            output_mode="summary",
            report_format="summary",
            output_path=None,
            prompt="请输出Word文档",
        )

        assert result.endswith(".docx"), f"Expected .docx path, got: {result}"
        assert Path(result).exists()

    def test_summary_when_no_docx_prompt(self) -> None:
        from dba_assistant.core.reporter.report_model import AnalysisReport
        from dba_assistant.orchestrator.report_output import render_analysis_output

        report = AnalysisReport(
            title="Test",
            summary="summary text here",
            sections=[],
            metadata={},
            language="zh-CN",
        )
        result = render_analysis_output(
            report,
            runtime_inputs=RuntimeInputs(),
            output_mode="summary",
            report_format="summary",
            output_path=None,
            prompt="just analyze",
        )

        assert not result.endswith(".docx")

    def test_explicit_docx_format_returns_path(self, tmp_path: Path) -> None:
        from dba_assistant.core.reporter.report_model import AnalysisReport
        from dba_assistant.orchestrator.report_output import render_analysis_output

        report = AnalysisReport(
            title="Test",
            summary="summary",
            sections=[],
            metadata={},
            language="zh-CN",
        )
        result = render_analysis_output(
            report,
            runtime_inputs=RuntimeInputs(artifact_dir=tmp_path),
            output_mode="report",
            report_format="docx",
            output_path=None,
        )

        assert result.endswith(".docx")
        assert Path(result).exists()


# ---------------------------------------------------------------------------
# 9. Full integration: large RDB + refusal + DOCX
# ---------------------------------------------------------------------------

class TestLargeRdbRefusalThenDocxIntegration:
    """Simulates: user has large .rdb, refuses MySQL, wants Word output."""

    def test_full_flow(self, tmp_path: Path, monkeypatch) -> None:
        from dba_assistant.orchestrator.tools import (
            _make_inspect_local_rdb_tool,
            _make_analyze_local_rdb_stream_tool,
            _make_stage_local_rdb_to_mysql_tool,
            _make_analyze_preparsed_dataset_tool,
        )

        # 1. Create a large RDB file
        large_rdb = tmp_path / "large.rdb"
        with large_rdb.open("wb") as f:
            f.truncate(LARGE_RDB_WARNING_BYTES + 1024)

        state: dict[str, Any] = {}
        prompt = "分析这个大RDB文件并输出Word文档"
        context = _make_context(
            request=_make_request(
                prompt=prompt,
                raw_prompt=prompt,
                runtime_inputs=RuntimeInputs(
                    output_mode="summary",
                    input_paths=(large_rdb,),
                    artifact_dir=tmp_path,
                ),
            )
        )

        # 2. inspect_local_rdb detects large file
        inspect_tool = _make_inspect_local_rdb_tool(state)
        inspect_result = json.loads(inspect_tool(input_paths=str(large_rdb)))
        assert inspect_result[0]["large_file"] is True
        assert state["large_rdb_detected"] is True

        # 3. User would see MySQL recommendation, then refuses.
        #    Agent calls analyze_local_rdb_stream with mysql_staging_refused=True.

        rows = [
            {"key_name": "cache:1", "key_type": "string", "size_bytes": 100,
             "has_expiration": False, "ttl_seconds": None},
            {"key_name": "session:1", "key_type": "hash", "size_bytes": 200,
             "has_expiration": True, "ttl_seconds": 60},
        ]
        monkeypatch.setattr(
            "dba_assistant.capabilities.redis_rdb_analysis.service._stream_rdb_rows",
            lambda _path: __import__(
                "dba_assistant.parsers.rdb_parser_strategy", fromlist=["StreamedRowsResult"]
            ).StreamedRowsResult(rows=iter(rows), strategy_name="test"),
        )

        analyze_tool = _make_analyze_local_rdb_stream_tool(context, state)
        result = analyze_tool(
            input_paths=str(large_rdb),
            mysql_staging_refused=True,
        )

        # 4. Should produce DOCX (forced by prompt)
        assert result.endswith(".docx"), f"Expected .docx path, got: {result}"
        assert Path(result).exists()

        # 5. mysql_staging_refused should be latched
        assert state["mysql_staging_refused"] is True

        # 6. MySQL-path tools should now be blocked
        stage_tool = _make_stage_local_rdb_to_mysql_tool(context, state)
        assert stage_tool(input_paths=str(large_rdb)) == _MYSQL_REFUSAL_GUARD_MESSAGE

        preparsed_tool = _make_analyze_preparsed_dataset_tool(context, state)
        assert preparsed_tool(input_paths=str(large_rdb)) == _MYSQL_REFUSAL_GUARD_MESSAGE


# ---------------------------------------------------------------------------
# 10. No regression: small file / normal direct RDB
# ---------------------------------------------------------------------------

class TestSmallFileNoRegression:
    def test_small_file_direct_analysis_works(self, tmp_path: Path, monkeypatch) -> None:
        from dba_assistant.orchestrator.tools import _make_analyze_local_rdb_stream_tool

        rdb = tmp_path / "small.rdb"
        rdb.write_bytes(b"small-data")
        state: dict[str, Any] = {}
        context = _make_context(
            request=_make_request(
                prompt="分析这个rdb",
                runtime_inputs=RuntimeInputs(
                    output_mode="summary",
                    input_paths=(rdb,),
                ),
            )
        )
        tool = _make_analyze_local_rdb_stream_tool(context, state)

        rows = [
            {"key_name": "k:1", "key_type": "string", "size_bytes": 10,
             "has_expiration": False, "ttl_seconds": None},
        ]
        monkeypatch.setattr(
            "dba_assistant.capabilities.redis_rdb_analysis.service._stream_rdb_rows",
            lambda _path: __import__(
                "dba_assistant.parsers.rdb_parser_strategy", fromlist=["StreamedRowsResult"]
            ).StreamedRowsResult(rows=iter(rows), strategy_name="test"),
        )

        result = tool(input_paths=str(rdb))

        # Should succeed with summary text (not an error)
        assert "Error" not in result
        assert "mysql_staging_refused" not in state
