from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from dba_assistant.capabilities.redis_rdb_analysis.collectors.path_c_direct_parser_collector import (
    PathCDirectParserCollector,
)
from dba_assistant.capabilities.redis_rdb_analysis.types import NormalizedRdbDataset


class PathAMySQLBackedCollector:
    """Stage parsed rows into MySQL, then reload a preparsed dataset."""

    def __init__(
        self,
        *,
        parser: Callable[[Path], list[dict[str, object]]],
        stage_rows_to_mysql: Callable[[str, list[dict[str, object]]], object],
        load_preparsed_dataset_from_mysql: Callable[[str], object],
    ) -> None:
        self._parser = parser
        self._stage_rows_to_mysql = stage_rows_to_mysql
        self._load_preparsed_dataset_from_mysql = load_preparsed_dataset_from_mysql

    def collect(self, paths: list[Path]) -> NormalizedRdbDataset:
        rows_by_path: dict[Path, list[dict[str, object]]] = {}

        for index, path in enumerate(paths, start=1):
            table_name = _build_table_name(path, index)
            rows = self._parser(path)
            self._stage_rows_to_mysql(table_name, rows)
            rows_by_path[path] = _extract_rows(
                self._load_preparsed_dataset_from_mysql(table_name),
            )

        bridge = PathCDirectParserCollector(parser=lambda path: rows_by_path[path])
        return bridge.collect(paths)


def _build_table_name(path: Path, index: int) -> str:
    stem = "".join(char if char.isalnum() else "_" for char in path.stem).strip("_") or "sample"
    return f"rdb_stage_{stem}_{index}_{uuid4().hex[:8]}"


def _extract_rows(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, str):
        payload = json.loads(payload)

    if not isinstance(payload, dict):
        raise ValueError("MySQL dataset loader must return a mapping or JSON object.")

    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("MySQL dataset loader payload must contain a list under 'rows'.")

    return [dict(row) for row in rows]
