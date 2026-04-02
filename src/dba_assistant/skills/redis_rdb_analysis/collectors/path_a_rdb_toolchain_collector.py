from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from dba_assistant.skills.redis_rdb_analysis.collectors.path_c_direct_parser_collector import (
    PathCDirectParserCollector,
)
from dba_assistant.skills.redis_rdb_analysis.types import NormalizedRdbDataset


class PathARdbToolchainCollector:
    def __init__(
        self,
        *,
        run_rdb_tools: Callable[[Path], Path],
        mysql_import: Callable[[Path], None],
        fetch_rows: Callable[[], list[dict[str, object]]],
    ) -> None:
        self._run_rdb_tools = run_rdb_tools
        self._mysql_import = mysql_import
        self._fetch_rows = fetch_rows

    def collect(self, paths: list[Path]) -> NormalizedRdbDataset:
        rows_by_path: dict[Path, list[dict[str, object]]] = {}

        for path in paths:
            csv_path = self._run_rdb_tools(path)
            self._mysql_import(csv_path)
            rows_by_path[path] = self._fetch_rows()

        bridge = PathCDirectParserCollector(parser=lambda path: rows_by_path[path])
        return bridge.collect(paths)
