from __future__ import annotations

from dba_assistant.capabilities.redis_rdb_analysis.types import (
    DATABASE_BACKED_ANALYSIS,
    DIRECT_RDB_ANALYSIS,
    InputSourceKind,
    PREPARSED_DATASET_ANALYSIS,
    RdbAnalysisRequest,
    normalize_route_name,
)

_CANONICAL_ROUTES = frozenset(
    {
        DATABASE_BACKED_ANALYSIS,
        PREPARSED_DATASET_ANALYSIS,
        DIRECT_RDB_ANALYSIS,
    }
)
_MYSQL_PATH_HINTS = ("mysql", "sql-style", "sql style")


def choose_path(request: RdbAnalysisRequest) -> str:
    if request.path_mode != "auto":
        normalized_path = normalize_route_name(request.path_mode)
        if normalized_path in _CANONICAL_ROUTES:
            return normalized_path

    if any(
        sample.kind in {InputSourceKind.PRECOMPUTED, InputSourceKind.PREPARSED_MYSQL}
        for sample in request.inputs
    ):
        return PREPARSED_DATASET_ANALYSIS

    prompt = request.prompt.lower()
    if any(hint in prompt for hint in _MYSQL_PATH_HINTS):
        return DATABASE_BACKED_ANALYSIS

    return DIRECT_RDB_ANALYSIS
