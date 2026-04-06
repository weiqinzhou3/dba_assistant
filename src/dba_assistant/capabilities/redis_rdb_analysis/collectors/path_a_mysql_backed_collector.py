from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from dba_assistant.application.request_models import (
    DEFAULT_MYSQL_STAGE_BATCH_SIZE,
    build_default_mysql_table_name,
)


@dataclass(frozen=True)
class MySQLStagingResult:
    table_name: str
    run_id: str
    row_count: int
    batch_size: int
    source_files: tuple[str, ...]
    database_name: str | None = None
    created_database: bool = False
    created_table: bool = False
    defaulted_database: bool = False
    defaulted_table: bool = False
    cleanup_mode: str = "retain"
    progress: tuple[str, ...] = ()


class PathAMySQLBackedCollector:
    """Stage parsed rows into one shared MySQL table using bounded batches."""

    def __init__(
        self,
        *,
        stream_parser: Callable[[Path], Iterable[dict[str, object]]],
        stage_rows_to_mysql: Callable[..., object],
        table_name: str | None = None,
        batch_size: int = DEFAULT_MYSQL_STAGE_BATCH_SIZE,
    ) -> None:
        self._stream_parser = stream_parser
        self._stage_rows_to_mysql = stage_rows_to_mysql
        self._table_name = table_name
        self._batch_size = batch_size

    def collect(self, paths: list[Path]) -> MySQLStagingResult:
        table_name = self._table_name or build_default_mysql_table_name()
        run_id = uuid4().hex[:12]
        row_count = 0
        progress: list[str] = []
        metadata: dict[str, object] = {}

        for index, path in enumerate(paths, start=1):
            batch_number = 0
            file_rows = 0
            for batch in _batched(self._stream_parser(path), self._batch_size):
                batch_number += 1
                file_rows += len(batch)
                row_count += len(batch)
                payload = self._stage_rows_to_mysql(
                    table_name,
                    batch,
                    source_file=str(path),
                    run_id=run_id,
                )
                if isinstance(payload, dict):
                    metadata.update(payload)
            progress.append(
                f"file {index}/{len(paths)} source={path} rows={file_rows} batches={batch_number}"
            )

        return MySQLStagingResult(
            table_name=table_name,
            run_id=run_id,
            row_count=row_count,
            batch_size=self._batch_size,
            source_files=tuple(str(path) for path in paths),
            database_name=_as_optional_str(metadata.get("database")),
            created_database=bool(metadata.get("created_database")),
            created_table=bool(metadata.get("created_table")),
            defaulted_database=bool(metadata.get("defaulted_database")),
            defaulted_table=bool(metadata.get("defaulted_table")),
            cleanup_mode=_as_optional_str(metadata.get("cleanup_mode")) or "retain",
            progress=tuple(progress),
        )


def _batched(
    rows: Iterable[dict[str, object]],
    batch_size: int,
) -> Iterator[list[dict[str, object]]]:
    batch: list[dict[str, object]] = []
    for row in rows:
        batch.append(dict(row))
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
