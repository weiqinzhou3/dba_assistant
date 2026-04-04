from __future__ import annotations

import json
from collections.abc import Callable

from dba_assistant.skills.redis_rdb_analysis.types import (
    InputSourceKind,
    KeyRecord,
    NormalizedRdbDataset,
    RdbAnalysisRequest,
    SampleInput,
)


class PathBMySQLPreparsedCollector:
    """Load a preparsed dataset from MySQL and normalize it for phase 3.1 analysis."""

    def __init__(
        self,
        *,
        load_preparsed_dataset_from_mysql: Callable[[str], object] | None = None,
        mysql_read_query: Callable[[str], object] | None = None,
    ) -> None:
        self._load_preparsed_dataset_from_mysql = load_preparsed_dataset_from_mysql
        self._mysql_read_query = mysql_read_query

    def collect(self, request: RdbAnalysisRequest) -> NormalizedRdbDataset:
        rows = _load_mysql_rows(
            request,
            load_preparsed_dataset_from_mysql=self._load_preparsed_dataset_from_mysql,
            mysql_read_query=self._mysql_read_query,
        )
        source = request.mysql_table or request.mysql_query or "mysql:dataset"
        sample_id = "sample-1"
        return NormalizedRdbDataset(
            samples=[
                SampleInput(
                    source=source,
                    kind=InputSourceKind.PREPARSED_MYSQL,
                    label=request.mysql_table or "mysql-query",
                )
            ],
            records=[
                KeyRecord(
                    sample_id=sample_id,
                    key_name=str(row["key_name"]),
                    key_type=str(row["key_type"]),
                    size_bytes=int(row["size_bytes"]),
                    has_expiration=bool(row["has_expiration"]),
                    ttl_seconds=_coerce_optional_int(row.get("ttl_seconds")),
                    prefix_segments=_infer_prefix_segments(str(row["key_name"])),
                )
                for row in rows
            ],
        )


def _load_mysql_rows(
    request: RdbAnalysisRequest,
    *,
    load_preparsed_dataset_from_mysql: Callable[[str], object] | None,
    mysql_read_query: Callable[[str], object] | None,
) -> list[dict[str, object]]:
    if request.mysql_table:
        if load_preparsed_dataset_from_mysql is None:
            raise ValueError("preparsed_mysql analysis requires MySQL dataset loading support.")
        payload = load_preparsed_dataset_from_mysql(request.mysql_table)
        return _extract_rows(payload)

    if request.mysql_query:
        if mysql_read_query is None:
            raise ValueError("preparsed_mysql query analysis requires MySQL read-query support.")
        payload = mysql_read_query(request.mysql_query)
        return _extract_rows(payload)

    raise ValueError("preparsed_mysql analysis requires mysql_table or mysql_query.")


def _extract_rows(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, str):
        payload = json.loads(payload)

    if isinstance(payload, list):
        return [dict(row) for row in payload]

    if isinstance(payload, dict):
        rows = payload.get("rows")
        if isinstance(rows, list):
            return [dict(row) for row in rows]

    raise ValueError("MySQL preparsed dataset payload must be a JSON list or mapping with 'rows'.")


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _infer_prefix_segments(key_name: str) -> tuple[str, ...]:
    parts = [part for part in key_name.split(":") if part]
    if len(parts) <= 1:
        return ()
    return tuple(parts[:-1])
