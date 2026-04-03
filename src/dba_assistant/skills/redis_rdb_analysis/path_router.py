from __future__ import annotations

from dba_assistant.skills.redis_rdb_analysis.types import (
    DIRECT_MEMORY_ANALYSIS_ROUTE_NAME,
    InputSourceKind,
    LEGACY_SQL_PIPELINE_ROUTE_NAME,
    PRECOMPUTED_DATASET_ROUTE_NAME,
    RdbAnalysisRequest,
    normalize_route_name,
)

_EXPLICIT_PATHS = frozenset(
    {
        LEGACY_SQL_PIPELINE_ROUTE_NAME,
        PRECOMPUTED_DATASET_ROUTE_NAME,
        DIRECT_MEMORY_ANALYSIS_ROUTE_NAME,
        "3a",
        "3b",
        "3c",
    }
)
_MYSQL_PATH_HINTS = ("mysql", "sql-style", "sql style")


def choose_path(request: RdbAnalysisRequest) -> str:
    if request.path_mode != "auto":
        normalized_path = normalize_route_name(request.path_mode)
        if normalized_path in _EXPLICIT_PATHS:
            return normalized_path
        return normalized_path

    if any(sample.kind is InputSourceKind.PRECOMPUTED for sample in request.inputs):
        return PRECOMPUTED_DATASET_ROUTE_NAME

    prompt = request.prompt.lower()
    if any(hint in prompt for hint in _MYSQL_PATH_HINTS):
        return LEGACY_SQL_PIPELINE_ROUTE_NAME

    return DIRECT_MEMORY_ANALYSIS_ROUTE_NAME
