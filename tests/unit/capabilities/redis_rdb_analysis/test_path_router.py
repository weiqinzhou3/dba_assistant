from pathlib import Path

from dba_assistant.capabilities.redis_rdb_analysis.path_router import choose_path
from dba_assistant.capabilities.redis_rdb_analysis.types import InputSourceKind, RdbAnalysisRequest, SampleInput


def test_choose_path_defaults_to_direct_rdb_analysis_for_local_rdb() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
    )

    assert choose_path(request) == "direct_rdb_analysis"


def test_choose_path_uses_preparsed_dataset_analysis_for_precomputed_inputs() -> None:
    request = RdbAnalysisRequest(
        prompt="summarize this exported analysis",
        inputs=[SampleInput(source=Path("/tmp/export.json"), kind=InputSourceKind.PRECOMPUTED)],
    )

    assert choose_path(request) == "preparsed_dataset_analysis"


def test_choose_path_uses_preparsed_dataset_for_preparsed_mysql_inputs() -> None:
    request = RdbAnalysisRequest(
        prompt="summarize this mysql dataset",
        inputs=[SampleInput(source="mysql:preparsed_keys", kind=InputSourceKind.PREPARSED_MYSQL)],
        mysql_table="preparsed_keys",
    )

    assert choose_path(request) == "preparsed_dataset_analysis"


def test_choose_path_uses_database_backed_analysis_for_explicit_mysql_staging_request() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb via mysql staging",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
    )

    assert choose_path(request) == "database_backed_analysis"


def test_choose_path_uses_database_backed_analysis_for_explicit_mysql_request() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb via mysql",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
    )

    assert choose_path(request) == "database_backed_analysis"


def test_choose_path_honors_explicit_path_mode_override() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
        path_mode="3b",
    )

    assert choose_path(request) == "preparsed_dataset_analysis"


def test_choose_path_honors_explicit_formal_route_override() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
        path_mode="legacy_sql_pipeline",
    )

    assert choose_path(request) == "database_backed_analysis"


def test_choose_path_honors_legacy_alias_route_override() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
        path_mode="legacy_sql_pipeline",
    )

    assert choose_path(request) == "database_backed_analysis"


def test_choose_path_ignores_unsupported_path_mode_and_falls_back() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
        path_mode="unsupported_mode",
    )

    assert choose_path(request) == "direct_rdb_analysis"
