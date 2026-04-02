import json
from pathlib import Path

from dba_assistant.core.reporter.report_model import AnalysisReport
from dba_assistant.skills.redis_rdb_analysis.service import analyze_rdb
from dba_assistant.skills.redis_rdb_analysis.types import (
    AnalysisStatus,
    ConfirmationRequest,
    InputSourceKind,
    RdbAnalysisRequest,
    SampleInput,
)


def test_analyze_rdb_returns_confirmation_request_for_remote_redis_without_confirmation() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze latest rdb",
        inputs=[SampleInput(source="10.0.0.8:6379", kind=InputSourceKind.REMOTE_REDIS)],
    )

    result = analyze_rdb(
        request,
        profile=None,
        remote_discovery=lambda *_args, **_kwargs: {"rdb_path": "/data/redis/dump.rdb"},
    )

    assert isinstance(result, ConfirmationRequest)
    assert result.status is AnalysisStatus.CONFIRMATION_REQUIRED
    assert result.required_action == "fetch_existing"
    assert "/data/redis/dump.rdb" in result.message


def test_analyze_rdb_returns_analysis_report_for_local_inputs(monkeypatch) -> None:
    rows = json.loads(Path("tests/fixtures/rdb/direct/sample_key_records.json").read_text(encoding="utf-8"))
    request = RdbAnalysisRequest(
        prompt="analyze this rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
    )
    monkeypatch.setattr("dba_assistant.skills.redis_rdb_analysis.service._parse_rdb_rows", lambda _path: rows)

    result = analyze_rdb(
        request,
        profile=None,
        remote_discovery=lambda *_args, **_kwargs: {"rdb_path": "/data/redis/dump.rdb"},
    )

    assert isinstance(result, AnalysisReport)
    assert result.title == "Redis RDB Analysis"
    assert result.metadata["profile"] == "generic"
    assert any(section.id == "top_big_keys" for section in result.sections)


def test_analyze_rdb_returns_analysis_report_for_precomputed_inputs() -> None:
    request = RdbAnalysisRequest(
        prompt="summarize this exported analysis",
        inputs=[
            SampleInput(
                source=Path("tests/fixtures/rdb/precomputed/sample_precomputed_rows.json"),
                kind=InputSourceKind.PRECOMPUTED,
            )
        ],
    )

    result = analyze_rdb(
        request,
        profile=None,
        remote_discovery=lambda *_args, **_kwargs: {"rdb_path": "/data/redis/dump.rdb"},
    )

    assert isinstance(result, AnalysisReport)
    assert result.title == "Redis RDB Analysis"
    assert result.metadata["profile"] == "generic"
    assert any(section.id == "sample_overview" for section in result.sections)
