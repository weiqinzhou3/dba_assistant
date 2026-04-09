from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
import inspect
import logging
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from dba_assistant.application.request_models import DEFAULT_MYSQL_STAGE_BATCH_SIZE, build_default_mysql_table_name

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MySQLStagingResult:
    table_name: str
    run_id: str
    row_count: int
    batch_size: int
    source_files: tuple[str, ...]
    mysql_host: str | None = None
    mysql_port: int | None = None
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
        mysql_target_host: str | None = None,
        mysql_target_port: int | None = None,
        mysql_target_database: str | None = None,
    ) -> None:
        normalized_batch_size = int(batch_size)
        if normalized_batch_size <= 0:
            raise ValueError("MySQL staging batch_size must be > 0.")
        self._stream_parser = stream_parser
        self._stage_rows_to_mysql = stage_rows_to_mysql
        self._table_name = table_name
        self._batch_size = normalized_batch_size
        self._mysql_target_host = mysql_target_host
        self._mysql_target_port = mysql_target_port
        self._mysql_target_database = mysql_target_database

    def collect(self, paths: list[Path]) -> MySQLStagingResult:
        table_name = self._table_name or build_default_mysql_table_name()
        run_id = uuid4().hex[:12]
        row_count = 0
        progress: list[str] = []
        batch_progress: list[str] = []
        metadata: dict[str, object] = {}
        started = perf_counter()
        global_batch_number = 0

        for index, path in enumerate(paths, start=1):
            file_batch_number = 0
            file_rows = 0
            for batch in _batched(self._stream_parser(path), self._batch_size):
                file_batch_number += 1
                global_batch_number += 1
                batch_rows = len(batch)
                next_cumulative_rows = row_count + batch_rows
                self._log_phase(
                    stage="batch_start",
                    metadata=metadata,
                    table_name=table_name,
                    batch_number=global_batch_number,
                    batch_rows=batch_rows,
                    cumulative_rows=row_count,
                    elapsed_seconds=round(perf_counter() - started, 6),
                    source_file=str(path),
                    run_id=run_id,
                )
                file_rows += len(batch)
                try:
                    payload = _call_stage_rows_to_mysql(
                        self._stage_rows_to_mysql,
                        table_name,
                        batch,
                        source_file=str(path),
                        run_id=run_id,
                        batch_number=global_batch_number,
                        cumulative_rows=next_cumulative_rows,
                    )
                except Exception as exc:  # noqa: BLE001
                    self._log_phase(
                        stage="batch_error",
                        metadata=metadata,
                        table_name=table_name,
                        batch_number=global_batch_number,
                        batch_rows=batch_rows,
                        cumulative_rows=row_count,
                        elapsed_seconds=round(perf_counter() - started, 6),
                        source_file=str(path),
                        run_id=run_id,
                        error=str(exc),
                    )
                    raise
                if isinstance(payload, dict):
                    metadata.update(payload)
                row_count = next_cumulative_rows
                self._log_phase(
                    stage="batch_end",
                    metadata=metadata,
                    table_name=table_name,
                    batch_number=global_batch_number,
                    batch_rows=batch_rows,
                    cumulative_rows=row_count,
                    elapsed_seconds=round(perf_counter() - started, 6),
                    source_file=str(path),
                    run_id=run_id,
                )
                batch_progress.append(
                    f"batch {global_batch_number} source={path} rows={batch_rows} cumulative_rows={row_count} batch_size={self._batch_size}"
                )
            progress.append(
                f"file {index}/{len(paths)} source={path} rows={file_rows} batches={file_batch_number} batch_size={self._batch_size}"
            )

        self._log_phase(
            stage="staging_complete",
            metadata=metadata,
            table_name=table_name,
            batch_number=global_batch_number,
            batch_rows=0,
            cumulative_rows=row_count,
            elapsed_seconds=round(perf_counter() - started, 6),
            run_id=run_id,
        )

        return MySQLStagingResult(
            table_name=table_name,
            run_id=run_id,
            row_count=row_count,
            batch_size=self._batch_size,
            source_files=tuple(str(path) for path in paths),
            mysql_host=_as_optional_str(metadata.get("mysql_host")) or self._mysql_target_host,
            mysql_port=_as_optional_int(metadata.get("mysql_port")) or self._mysql_target_port,
            database_name=_as_optional_str(metadata.get("database")),
            created_database=bool(metadata.get("created_database")),
            created_table=bool(metadata.get("created_table")),
            defaulted_database=bool(metadata.get("defaulted_database")),
            defaulted_table=bool(metadata.get("defaulted_table")),
            cleanup_mode=_as_optional_str(metadata.get("cleanup_mode")) or "retain",
            progress=tuple(progress + batch_progress),
        )

    def _log_phase(
        self,
        *,
        stage: str,
        metadata: dict[str, object],
        table_name: str,
        batch_number: int | None,
        batch_rows: int | None,
        cumulative_rows: int | None,
        elapsed_seconds: float,
        source_file: str | None = None,
        run_id: str | None = None,
        error: str | None = None,
    ) -> None:
        logger.info(
            "mysql staging phase",
            extra={
                "event_name": "mysql_staging_phase",
                "stage": stage,
                "mysql_host": _as_optional_str(metadata.get("mysql_host")) or self._mysql_target_host,
                "mysql_port": _as_optional_int(metadata.get("mysql_port")) or self._mysql_target_port,
                "mysql_database": _as_optional_str(metadata.get("database")) or self._mysql_target_database,
                "mysql_table": _as_optional_str(metadata.get("table")) or table_name,
                "mysql_stage_batch_size": self._batch_size,
                "batch_number": batch_number,
                "batch_rows": batch_rows,
                "cumulative_rows": cumulative_rows,
                "elapsed_seconds": elapsed_seconds,
                "source_file": source_file,
                "run_id": run_id,
                "error": error,
            },
        )
        return None


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


def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _call_stage_rows_to_mysql(
    stage_rows_to_mysql: Callable[..., object],
    table_name: str,
    rows: list[dict[str, object]],
    *,
    source_file: str,
    run_id: str,
    batch_number: int,
    cumulative_rows: int,
) -> object:
    kwargs: dict[str, object] = {
        "source_file": source_file,
        "run_id": run_id,
    }
    if _callable_accepts_keyword(stage_rows_to_mysql, "batch_number"):
        kwargs["batch_number"] = batch_number
    if _callable_accepts_keyword(stage_rows_to_mysql, "cumulative_rows"):
        kwargs["cumulative_rows"] = cumulative_rows
    return stage_rows_to_mysql(table_name, rows, **kwargs)


def _callable_accepts_keyword(func: Callable[..., object], keyword: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            return True
    return keyword in signature.parameters
