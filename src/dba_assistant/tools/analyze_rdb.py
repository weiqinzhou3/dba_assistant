from __future__ import annotations

from pathlib import Path
from typing import Callable

from dba_assistant.capabilities.redis_rdb_analysis.service import analyze_rdb
from dba_assistant.capabilities.redis_rdb_analysis.types import InputSourceKind, RdbAnalysisRequest, SampleInput


_INPUT_KIND_MAP: dict[str, InputSourceKind] = {
    "local_rdb": InputSourceKind.LOCAL_RDB,
    "precomputed": InputSourceKind.PRECOMPUTED,
    "preparsed_mysql": InputSourceKind.PREPARSED_MYSQL,
    "remote_redis": InputSourceKind.REMOTE_REDIS,
}


def analyze_rdb_tool(
    prompt: str,
    input_paths: list[Path | str],
    *,
    input_kind: str = "local_rdb",
    profile_name: str = "generic",
    report_language: str = "zh-CN",
    path_mode: str = "auto",
    profile_overrides: dict[str, object] | None = None,
    mysql_host: str | None = None,
    mysql_port: int | None = None,
    mysql_database: str | None = None,
    mysql_table: str | None = None,
    mysql_query: str | None = None,
    mysql_stage_batch_size: int | None = None,
    service: Callable[[RdbAnalysisRequest], object] | None = None,
):
    source_kind = _INPUT_KIND_MAP.get(input_kind, InputSourceKind.LOCAL_RDB)
    request = RdbAnalysisRequest(
        prompt=prompt,
        inputs=[SampleInput(source=path, kind=source_kind) for path in input_paths],
        profile_name=profile_name,
        report_language=report_language,
        path_mode=path_mode,
        profile_overrides=dict(profile_overrides or {}),
        mysql_host=mysql_host,
        mysql_port=mysql_port,
        mysql_database=mysql_database,
        mysql_table=mysql_table,
        mysql_query=mysql_query,
        mysql_stage_batch_size=mysql_stage_batch_size,
    )
    runner = service or _run_phase3_analysis
    return runner(request)


def _run_phase3_analysis(request: RdbAnalysisRequest):
    return analyze_rdb(
        request,
        profile=None,
        remote_discovery=lambda *_args, **_kwargs: {},
    )


__all__ = ["analyze_rdb_tool"]
