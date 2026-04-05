from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from dba_assistant.capabilities.redis_rdb_analysis.collectors.path_c_direct_parser_collector import (
    PathCDirectParserCollector,
)
from dba_assistant.capabilities.redis_rdb_analysis.types import InputSourceKind, NormalizedRdbDataset


class PathBPrecomputedCollector:
    def collect(self, paths: list[Path]) -> NormalizedRdbDataset:
        rows_by_path = {path: _load_rows(path) for path in paths}
        bridge = PathCDirectParserCollector(parser=lambda path: rows_by_path[path])
        dataset = bridge.collect(paths)
        return NormalizedRdbDataset(
            samples=[replace(sample, kind=InputSourceKind.PRECOMPUTED) for sample in dataset.samples],
            records=dataset.records,
        )


def _load_rows(path: Path) -> list[dict[str, object]]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        raise ValueError(f"Precomputed analysis file must contain a JSON list: {path}")

    rows: list[dict[str, object]] = []
    for index, row in enumerate(loaded, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Precomputed analysis row {index} must be a JSON object: {path}")
        rows.append(row)

    return rows
