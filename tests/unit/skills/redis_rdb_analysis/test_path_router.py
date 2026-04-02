from pathlib import Path

from dba_assistant.skills.redis_rdb_analysis.path_router import choose_path
from dba_assistant.skills.redis_rdb_analysis.types import InputSourceKind, RdbAnalysisRequest, SampleInput


def test_choose_path_defaults_to_3c_for_local_rdb() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
    )

    assert choose_path(request) == "3c"


def test_choose_path_uses_3b_for_precomputed_inputs() -> None:
    request = RdbAnalysisRequest(
        prompt="summarize this exported analysis",
        inputs=[SampleInput(source=Path("/tmp/export.json"), kind=InputSourceKind.PRECOMPUTED)],
    )

    assert choose_path(request) == "3b"


def test_choose_path_uses_3a_for_explicit_mysql_staging_request() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb via mysql staging",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
    )

    assert choose_path(request) == "3a"


def test_choose_path_honors_explicit_path_mode_override() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
        path_mode="3b",
    )

    assert choose_path(request) == "3b"
