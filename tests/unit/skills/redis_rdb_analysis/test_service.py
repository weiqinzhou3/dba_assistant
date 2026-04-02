from pathlib import Path

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


def test_analyze_rdb_returns_summary_for_local_inputs() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
    )

    result = analyze_rdb(
        request,
        profile=None,
        remote_discovery=lambda *_args, **_kwargs: {"rdb_path": "/data/redis/dump.rdb"},
    )

    assert result["path"] == "3c"
    assert result["profile"] == "generic"
