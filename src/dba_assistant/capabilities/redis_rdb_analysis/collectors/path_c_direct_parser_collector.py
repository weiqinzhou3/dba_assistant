from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from dba_assistant.capabilities.redis_rdb_analysis.collectors.row_value_coercion import (
    _coerce_bool,
    _coerce_optional_int,
    _coerce_required_int,
)
from dba_assistant.capabilities.redis_rdb_analysis.types import (
    InputSourceKind,
    KeyRecord,
    NormalizedRdbDataset,
    SampleInput,
)


class PathCDirectParserCollector:
    def __init__(self, parser: Callable[[Path], list[dict[str, object]]]) -> None:
        self._parser = parser

    def collect(self, paths: list[Path]) -> NormalizedRdbDataset:
        samples: list[SampleInput] = []
        records: list[KeyRecord] = []

        for index, path in enumerate(paths, start=1):
            sample_id = f"sample-{index}"
            samples.append(SampleInput(source=path, kind=InputSourceKind.LOCAL_RDB, label=path.stem))

            for row in self._parser(path):
                key_name = str(row["key_name"])
                records.append(
                    KeyRecord(
                        sample_id=sample_id,
                        key_name=key_name,
                        key_type=str(row["key_type"]),
                        size_bytes=_coerce_required_int(row.get("size_bytes"), "size_bytes"),
                        has_expiration=_coerce_bool(row.get("has_expiration")),
                        ttl_seconds=_coerce_optional_int(row.get("ttl_seconds")),
                        prefix_segments=_infer_prefix_segments(key_name),
                    )
                )

        return NormalizedRdbDataset(samples=samples, records=records)


def _infer_prefix_segments(key_name: str) -> tuple[str, ...]:
    parts = [part for part in key_name.split(":") if part]
    if len(parts) <= 1:
        return ()
    return tuple(parts[:-1])
