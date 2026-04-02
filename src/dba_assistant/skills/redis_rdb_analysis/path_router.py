from __future__ import annotations

from dba_assistant.skills.redis_rdb_analysis.types import InputSourceKind, RdbAnalysisRequest

_EXPLICIT_PATHS = frozenset({"3a", "3b", "3c"})
_MYSQL_PATH_HINTS = ("mysql staging", "sql-style", "sql style")


def choose_path(request: RdbAnalysisRequest) -> str:
    if request.path_mode in _EXPLICIT_PATHS:
        return request.path_mode

    if any(sample.kind is InputSourceKind.PRECOMPUTED for sample in request.inputs):
        return "3b"

    prompt = request.prompt.lower()
    if any(hint in prompt for hint in _MYSQL_PATH_HINTS):
        return "3a"

    return "3c"
