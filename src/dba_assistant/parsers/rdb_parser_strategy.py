from __future__ import annotations

import csv
import codecs
import json
import logging
import os
import queue
import select
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Iterable, Iterator, Protocol

from dba_assistant.core.runtime_paths import DEFAULT_TEMP_DIR, ensure_directory

logger = logging.getLogger(__name__)

DEFAULT_HDT_FIFO_IDLE_TIMEOUT_SECONDS = 300.0
HDT_IDLE_TIMEOUT_ENV = "DBA_ASSISTANT_HDT_FIFO_IDLE_TIMEOUT_SECONDS"
PARSER_OVERRIDE_ENV = "DBA_ASSISTANT_RDB_PARSER"


@dataclass(frozen=True)
class FlamegraphSpec:
    command: tuple[str, ...]
    url: str


@dataclass(frozen=True)
class ParsedRowsResult:
    rows: list[dict[str, object]]
    strategy_name: str
    strategy_detail: str | None = None


@dataclass(frozen=True)
class StreamedRowsResult:
    rows: Iterable[dict[str, object]]
    strategy_name: str
    strategy_detail: str | None = None


class RdbParserStrategy(Protocol):
    def parse_rows(self, path: Path) -> list[dict[str, object]]:
        ...

    def parse_rows_result(self, path: Path) -> ParsedRowsResult:
        ...

    def stream_rows_result(self, path: Path) -> StreamedRowsResult:
        ...


class HdtRdbCliStrategy:
    def __init__(
        self,
        *,
        binary_path: Path | None = None,
        runner=subprocess.run,
        fifo_idle_timeout_seconds: float | None = None,
        writer_join_timeout_seconds: float = 5.0,
    ) -> None:
        self._runner = runner
        self._binary_path = binary_path or _resolve_hdt_rdb_binary()
        self._fifo_idle_timeout_seconds = (
            _hdt_fifo_idle_timeout_seconds()
            if fifo_idle_timeout_seconds is None
            else fifo_idle_timeout_seconds
        )
        self._writer_join_timeout_seconds = writer_join_timeout_seconds
        if self._binary_path is None:
            raise FileNotFoundError(
                "HDT3213/rdb binary not found. Set DBA_ASSISTANT_HDT_RDB_BIN or install the rdb CLI."
            )

    def parse_rows(self, path: Path) -> list[dict[str, object]]:
        return self.parse_rows_result(path).rows

    def parse_rows_result(self, path: Path) -> ParsedRowsResult:
        rows: list[dict[str, object]] = []
        for obj in self.export_json(path):
            normalized = _normalize_hdt_json_object(obj)
            if normalized is not None:
                rows.append(normalized)
        return ParsedRowsResult(
            rows=rows,
            strategy_name=type(self).__name__,
            strategy_detail=str(self._binary_path),
        )

    def stream_rows_result(self, path: Path) -> StreamedRowsResult:
        def rows() -> Iterator[dict[str, object]]:
            for obj in self.export_json(path):
                normalized = _normalize_hdt_json_object(obj)
                if normalized is not None:
                    yield normalized

        return StreamedRowsResult(
            rows=rows(),
            strategy_name=type(self).__name__,
            strategy_detail=str(self._binary_path),
        )

    def export_json(self, path: Path) -> Iterator[dict[str, object]]:
        with tempfile.TemporaryDirectory(
            prefix="dba-assistant-rdb-json-",
            dir=str(ensure_directory(DEFAULT_TEMP_DIR)),
        ) as tmpdir:
            output_path = Path(tmpdir) / "dump.json"
            os.mkfifo(output_path)
            error_box: dict[str, Exception] = {}
            process_box: dict[str, subprocess.Popen] = {}

            def writer() -> None:
                try:
                    # Modify _run_cli to return the process or handle it here
                    cmd = [str(self._binary_path), "-c", "json", "-o", str(output_path), str(path)]
                    logger.info(
                        "hdt rdb cli start",
                        extra={
                            "event_name": "hdt_rdb_cli_start",
                            "command": _format_command(cmd),
                            "path": str(path),
                            "fifo_path": str(output_path),
                        },
                    )
                    p = subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    process_box["p"] = p
                    logger.info(
                        "hdt rdb cli process started",
                        extra={
                            "event_name": "hdt_rdb_cli_process_started",
                            "pid": getattr(p, "pid", None),
                            "path": str(path),
                            "fifo_path": str(output_path),
                        },
                    )
                    exit_code = p.wait()
                    logger.info(
                        "hdt rdb cli exit",
                        extra={
                            "event_name": "hdt_rdb_cli_exit",
                            "pid": getattr(p, "pid", None),
                            "exit_code": exit_code,
                            "path": str(path),
                            "fifo_path": str(output_path),
                        },
                    )
                    if exit_code != 0:
                        raise RuntimeError(f"rdb command failed with {exit_code}")
                except Exception as exc:  # noqa: BLE001
                    error_box["error"] = exc

            writer_thread = threading.Thread(target=writer, daemon=True)
            writer_thread.start()
            fifo_state: dict[str, object] = {"read_eof": False}
            try:
                chunks = _iter_fifo_text_chunks(
                    output_path,
                    process_box=process_box,
                    error_box=error_box,
                    idle_timeout_seconds=self._fifo_idle_timeout_seconds,
                    path=path,
                    fifo_state=fifo_state,
                )
                yield from _iter_json_array_objects(_TextChunkHandle(chunks))
            finally:
                p = process_box.get("p")
                poll_result = None if p is None else p.poll()
                logger.info(
                    "hdt rdb finally enter",
                    extra={
                        "event_name": "hdt_rdb_finally_enter",
                        "path": str(path),
                        "fifo_path": str(output_path),
                        "pid": None if p is None else getattr(p, "pid", None),
                        "poll_result": poll_result,
                    },
                )
                logger.info(
                    "hdt rdb fifo read status",
                    extra={
                        "event_name": "hdt_rdb_fifo_read_status",
                        "path": str(path),
                        "fifo_path": str(output_path),
                        "read_eof": bool(fifo_state.get("read_eof")),
                    },
                )
                # Force kill the process if still running to unblock FIFO
                if p and p.poll() is None:
                    logger.info(
                        "hdt rdb process terminate",
                        extra={
                            "event_name": "hdt_rdb_process_terminate",
                            "path": str(path),
                            "fifo_path": str(output_path),
                            "pid": getattr(p, "pid", None),
                        },
                    )
                    p.terminate()
                logger.info(
                    "hdt rdb writer join start",
                    extra={
                        "event_name": "hdt_rdb_writer_join_start",
                        "path": str(path),
                        "fifo_path": str(output_path),
                        "pid": None if p is None else getattr(p, "pid", None),
                    },
                )
                writer_thread.join(timeout=self._writer_join_timeout_seconds)
                logger.info(
                    "hdt rdb writer join end",
                    extra={
                        "event_name": "hdt_rdb_writer_join_end",
                        "path": str(path),
                        "fifo_path": str(output_path),
                        "pid": None if p is None else getattr(p, "pid", None),
                        "writer_alive": writer_thread.is_alive(),
                        "exit_code": None if p is None else p.poll(),
                    },
                )
                if sys.exc_info()[1] is None and "error" in error_box:
                    raise error_box["error"]

    def find_biggest_keys(self, path: Path, *, limit: int = 10) -> list[dict[str, object]]:
        rows = self._run_csv_command(path, ["-c", "bigkey", "-n", str(limit)])
        return [
            {
                "database": int(row["database"]),
                "key_name": row["key"],
                "key_type": row["type"],
                "size_bytes": int(row["size"]),
                "size_readable": row["size_readable"],
                "element_count": int(row["element_count"]),
            }
            for row in rows
        ]

    def analyze_prefixes(
        self,
        path: Path,
        *,
        limit: int = 10,
        max_depth: int = 0,
    ) -> list[dict[str, object]]:
        args = ["-c", "prefix", "-n", str(limit)]
        if max_depth > 0:
            args.extend(["-max-depth", str(max_depth)])
        rows = self._run_csv_command(path, args)
        return [
            {
                "database": int(row["database"]),
                "prefix": row["prefix"],
                "size_bytes": int(row["size"]),
                "size_readable": row["size_readable"],
                "key_count": int(row["key_count"]),
            }
            for row in rows
        ]

    def build_flamegraph_spec(
        self,
        path: Path,
        *,
        port: int = 16379,
        separators: tuple[str, ...] = (":",),
    ) -> FlamegraphSpec:
        command = [str(self._binary_path), "-c", "flamegraph", "-port", str(port)]
        for separator in separators:
            command.extend(["-sep", separator])
        command.append(str(path))
        return FlamegraphSpec(command=tuple(command), url=f"http://localhost:{port}/flamegraph")

    def _run_csv_command(self, path: Path, args: list[str]) -> list[dict[str, str]]:
        with tempfile.TemporaryDirectory(
            prefix="dba-assistant-rdb-csv-",
            dir=str(ensure_directory(DEFAULT_TEMP_DIR)),
        ) as tmpdir:
            output_path = Path(tmpdir) / "report.csv"
            # Ensure output flag is used correctly
            full_args = list(args)
            if "-o" not in full_args:
                full_args.extend(["-o", str(output_path)])
            full_args.append(str(path))
            
            self._run_cli(full_args)
            with output_path.open("r", encoding="utf-8", newline="") as handle:
                return list(csv.DictReader(handle))

    def _run_cli(self, args: list[str]) -> None:
        """Run the CLI binary without capturing output to avoid pipe deadlocks."""
        # Using DEVNULL for both stdout and stderr because the main data 
        # is being redirected to a file or FIFO via the '-o' argument.
        # This prevents the sub-process from blocking on a full pipe buffer.
        process = subprocess.Popen(
            [str(self._binary_path), *args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        exit_code = process.wait()
        if exit_code != 0:
            raise RuntimeError(f"HDT3213/rdb command failed with exit code {exit_code}")


class LegacyRdbtoolsStrategy:
    def parse_rows(self, path: Path) -> list[dict[str, object]]:
        return self.parse_rows_result(path).rows

    def parse_rows_result(self, path: Path) -> ParsedRowsResult:
        return ParsedRowsResult(
            rows=list(self.stream_rows_result(path).rows),
            strategy_name=type(self).__name__,
        )

    def stream_rows_result(self, path: Path) -> StreamedRowsResult:
        from rdbtools import MemoryCallback, RdbParser

        sentinel = object()
        row_queue: queue.Queue[object] = queue.Queue(maxsize=1024)
        error_box: dict[str, Exception] = {}

        class QueueingStream:
            def next_record(self, record) -> None:
                if record.key is None:
                    return
                row_queue.put(
                    {
                        "key_name": str(record.key),
                        "key_type": str(record.type),
                        "size_bytes": int(record.bytes),
                        "has_expiration": record.expiry is not None,
                        "ttl_seconds": _ttl_seconds(record.expiry),
                    }
                )

        def parse() -> None:
            try:
                parser = RdbParser(MemoryCallback(QueueingStream(), 64))
                parser.parse(str(path))
            except Exception as exc:  # noqa: BLE001
                error_box["error"] = exc
            finally:
                row_queue.put(sentinel)

        parser_thread = threading.Thread(target=parse, daemon=True)
        parser_thread.start()

        def rows() -> Iterator[dict[str, object]]:
            while True:
                item = row_queue.get()
                if item is sentinel:
                    break
                yield dict(item)
            parser_thread.join()
            if "error" in error_box:
                raise error_box["error"]

        return StreamedRowsResult(
            rows=rows(),
            strategy_name=type(self).__name__,
        )


class CompositeRdbParserStrategy:
    def __init__(self, strategies: list[RdbParserStrategy]) -> None:
        self._strategies = strategies

    def parse_rows(self, path: Path) -> list[dict[str, object]]:
        return self.parse_rows_result(path).rows

    def parse_rows_result(self, path: Path) -> ParsedRowsResult:
        errors: list[str] = []
        for strategy in self._strategies:
            try:
                return strategy.parse_rows_result(path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(strategy).__name__}: {exc}")
        raise RuntimeError("All RDB parser strategies failed: " + " | ".join(errors))

    def stream_rows_result(self, path: Path) -> StreamedRowsResult:
        errors: list[str] = []
        for strategy in self._strategies:
            try:
                return strategy.stream_rows_result(path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(strategy).__name__}: {exc}")
        raise RuntimeError("All RDB parser strategies failed: " + " | ".join(errors))


def build_default_rdb_parser_strategy() -> CompositeRdbParserStrategy:
    return _build_default_rdb_parser_strategy((os.getenv(PARSER_OVERRIDE_ENV) or "").strip().lower())


@lru_cache(maxsize=8)
def _build_default_rdb_parser_strategy(parser_override: str) -> CompositeRdbParserStrategy:
    strategies: list[RdbParserStrategy] = []
    if parser_override in {"legacy", "rdbtools", "legacy_rdbtools"}:
        logger.info(
            "forcing legacy rdb parser",
            extra={
                "event_name": "rdb_parser_strategy_override",
                "parser_override": parser_override,
                "parser_strategy": "LegacyRdbtoolsStrategy",
            },
        )
    else:
        try:
            strategies.append(HdtRdbCliStrategy())
        except FileNotFoundError:
            pass
    strategies.append(LegacyRdbtoolsStrategy())
    return CompositeRdbParserStrategy(strategies)


build_default_rdb_parser_strategy.cache_clear = _build_default_rdb_parser_strategy.cache_clear  # type: ignore[attr-defined]


def _normalize_hdt_json_object(obj: object) -> dict[str, object] | None:
    if not isinstance(obj, dict):
        return None

    key_name = obj.get("key")
    key_type = str(obj.get("type", ""))
    if not key_name or key_type in {"aux", "functions"}:
        return None

    expiration = obj.get("expiration")
    return {
        "key_name": str(key_name),
        "key_type": key_type,
        "size_bytes": int(obj.get("size", 0)),
        "has_expiration": expiration is not None,
        "ttl_seconds": _ttl_seconds_from_json(expiration),
    }


def _ttl_seconds_from_json(expiration: object) -> int | None:
    if expiration is None:
        return None
    if isinstance(expiration, (int, float)):
        expiry = datetime.fromtimestamp(float(expiration), tz=timezone.utc)
    else:
        text = str(expiration).strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        expiry = datetime.fromisoformat(normalized)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
    return max(0, int((expiry - datetime.now(timezone.utc)).total_seconds()))


def _resolve_hdt_rdb_binary() -> Path | None:
    candidates: list[Path] = []
    configured = os.getenv("DBA_ASSISTANT_HDT_RDB_BIN")
    if configured:
        candidates.append(Path(configured).expanduser().resolve())

    repo_root = _find_repo_root(Path(__file__).resolve())
    if repo_root is not None:
        candidates.append(repo_root / ".tools/bin/rdb")

    path_candidate = shutil.which("rdb")
    if path_candidate:
        candidates.append(Path(path_candidate).resolve())

    for candidate in candidates:
        if candidate.exists() and _looks_like_hdt_rdb(candidate):
            return candidate.resolve()
    return None


def _find_repo_root(start: Path) -> Path | None:
    for candidate in (start.parent, *start.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "src").exists():
            return candidate
    return None


def _looks_like_hdt_rdb(candidate: Path) -> bool:
    try:
        completed = subprocess.run(
            [str(candidate), "-h"],
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError:
        return False

    output = "\n".join(filter(None, [completed.stdout, completed.stderr]))
    markers = (
        "Usage of",
        "command for rdb: json",
        "-show-global-meta",
        "-max-depth",
        "-port",
    )
    return all(marker in output for marker in markers)


def _hdt_fifo_idle_timeout_seconds() -> float:
    raw_value = os.getenv(HDT_IDLE_TIMEOUT_ENV, "").strip()
    if not raw_value:
        return DEFAULT_HDT_FIFO_IDLE_TIMEOUT_SECONDS
    try:
        parsed = float(raw_value)
    except ValueError:
        return DEFAULT_HDT_FIFO_IDLE_TIMEOUT_SECONDS
    if parsed <= 0:
        return DEFAULT_HDT_FIFO_IDLE_TIMEOUT_SECONDS
    return parsed


def _format_command(cmd: list[str]) -> str:
    return " ".join(cmd)


class _TextChunkHandle:
    def __init__(self, chunks: Iterable[str]) -> None:
        self._chunks = iter(chunks)

    def read(self, _size: int = -1) -> str:
        try:
            return next(self._chunks)
        except StopIteration:
            return ""


def _iter_fifo_text_chunks(
    fifo_path: Path,
    *,
    process_box: dict[str, subprocess.Popen],
    error_box: dict[str, Exception],
    idle_timeout_seconds: float,
    path: Path,
    fifo_state: dict[str, object] | None = None,
) -> Iterator[str]:
    fd: int | None = None
    decoder = codecs.getincrementaldecoder("utf-8")()
    last_activity = perf_counter()
    read_eof = False
    try:
        fd = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        logger.info(
            "hdt rdb fifo opened",
            extra={
                "event_name": "hdt_rdb_fifo_opened",
                "path": str(path),
                "fifo_path": str(fifo_path),
            },
        )
        while True:
            wait_seconds = min(1.0, max(0.001, idle_timeout_seconds))
            readable, _, _ = select.select([fd], [], [], wait_seconds)
            if readable:
                data = os.read(fd, 65536)
                if data:
                    last_activity = perf_counter()
                    text = decoder.decode(data)
                    if text:
                        yield text
                    continue
                read_eof = True
                if fifo_state is not None:
                    fifo_state["read_eof"] = True
                tail = decoder.decode(b"", final=True)
                if tail:
                    yield tail
                logger.info(
                    "hdt rdb fifo eof",
                    extra={
                        "event_name": "hdt_rdb_fifo_eof",
                        "path": str(path),
                        "fifo_path": str(fifo_path),
                        "exit_code": _process_exit_code(process_box),
                    },
                )
                break

            if "error" in error_box:
                raise error_box["error"]

            idle_elapsed = perf_counter() - last_activity
            if idle_elapsed >= idle_timeout_seconds:
                logger.error(
                    "hdt rdb fifo idle timeout",
                    extra={
                        "event_name": "hdt_rdb_fifo_idle_timeout",
                        "path": str(path),
                        "fifo_path": str(fifo_path),
                        "idle_timeout_seconds": idle_timeout_seconds,
                        "idle_elapsed_seconds": round(idle_elapsed, 6),
                        "exit_code": _process_exit_code(process_box),
                    },
                )
                raise TimeoutError(
                    f"HDT RDB JSON stream idle for {idle_timeout_seconds:.3f}s while reading {path}"
                )
    finally:
        if fd is not None:
            os.close(fd)
        if not read_eof:
            logger.info(
                "hdt rdb fifo closed before eof",
                extra={
                    "event_name": "hdt_rdb_fifo_closed_before_eof",
                    "path": str(path),
                    "fifo_path": str(fifo_path),
                    "exit_code": _process_exit_code(process_box),
                },
            )


def _process_exit_code(process_box: dict[str, subprocess.Popen]) -> int | None:
    process = process_box.get("p")
    if process is None:
        return None
    return process.poll()


class _MemoryRecordStream:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def next_record(self, record) -> None:
        if record.key is None:
            return

        self.rows.append(
            {
                "key_name": str(record.key),
                "key_type": str(record.type),
                "size_bytes": int(record.bytes),
                "has_expiration": record.expiry is not None,
                "ttl_seconds": _ttl_seconds(record.expiry),
            }
        )


def _ttl_seconds(expiry: object) -> int | None:
    if expiry is None:
        return None
    if isinstance(expiry, datetime):
        normalized = expiry if expiry.tzinfo is not None else expiry.replace(tzinfo=timezone.utc)
        return max(0, int((normalized - datetime.now(timezone.utc)).total_seconds()))
    return int(expiry)


def _iter_json_array_objects(handle) -> Iterator[dict[str, object]]:
    decoder = json.JSONDecoder()
    buffer = ""
    in_array = False
    array_complete = False

    while True:
        chunk = handle.read(65536)
        if chunk:
            buffer += chunk
        elif not buffer.strip():
            break

        position = 0
        length = len(buffer)
        while position < length:
            while position < length and buffer[position].isspace():
                position += 1
            if position >= length:
                break
            token = buffer[position]
            if not in_array:
                if token != "[":
                    if chunk:
                        break
                    raise ValueError("Invalid HDT JSON payload: expected '[' at array start.")
                in_array = True
                position += 1
                continue
            if token == ",":
                position += 1
                continue
            if token == "]":
                array_complete = True
                position += 1
                while position < length and buffer[position].isspace():
                    position += 1
                buffer = buffer[position:]
                position = 0
                length = len(buffer)
                break
            try:
                obj, end = decoder.raw_decode(buffer, position)
            except json.JSONDecodeError:
                if chunk:
                    break
                raise
            if not isinstance(obj, dict):
                raise ValueError("Invalid HDT JSON payload: expected JSON objects in array.")
            yield obj
            position = end
        buffer = buffer[position:]
        if array_complete:
            break
        if not chunk and buffer.strip():
            raise ValueError("Invalid HDT JSON payload: unterminated JSON array.")
