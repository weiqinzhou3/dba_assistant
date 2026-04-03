from __future__ import annotations

from pathlib import Path
from typing import Callable

from dba_assistant.skills.redis_rdb_analysis.service import analyze_rdb
from dba_assistant.skills.redis_rdb_analysis.types import InputSourceKind, RdbAnalysisRequest, SampleInput


def analyze_rdb_tool(
    prompt: str,
    input_paths: list[Path],
    *,
    profile_name: str = "generic",
    path_mode: str = "auto",
    profile_overrides: dict[str, object] | None = None,
    service: Callable[[RdbAnalysisRequest], object] | None = None,
):
    request = RdbAnalysisRequest(
        prompt=prompt,
        inputs=[SampleInput(source=path, kind=InputSourceKind.LOCAL_RDB) for path in input_paths],
        profile_name=profile_name,
        path_mode=path_mode,
        profile_overrides=dict(profile_overrides or {}),
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
