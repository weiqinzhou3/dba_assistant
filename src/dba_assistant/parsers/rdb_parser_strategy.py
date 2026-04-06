from __future__ import annotations

import csv
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Iterator, Protocol


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
    ) -> None:
        self._runner = runner
        self._binary_path = binary_path or _resolve_hdt_rdb_binary()
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
        with tempfile.TemporaryDirectory(prefix="dba-assistant-rdb-json-", dir="/tmp") as tmpdir:
            output_path = Path(tmpdir) / "dump.json"
            os.mkfifo(output_path)
            error_box: dict[str, Exception] = {}

            def writer() -> None:
                try:
                    self._run_cli(["-c", "json", "-o", str(output_path), str(path)])
                except Exception as exc:  # noqa: BLE001
                    error_box["error"] = exc

            writer_thread = threading.Thread(target=writer, daemon=True)
            writer_thread.start()
            try:
                with output_path.open("r", encoding="utf-8") as handle:
                    yield from _iter_json_array_objects(handle)
            finally:
                writer_thread.join()
                if "error" in error_box:
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
        with tempfile.TemporaryDirectory(prefix="dba-assistant-rdb-csv-") as tmpdir:
            output_path = Path(tmpdir) / "report.csv"
            self._run_cli([*args, "-o", str(output_path), str(path)])
            with output_path.open("r", encoding="utf-8", newline="") as handle:
                return list(csv.DictReader(handle))

    def _run_cli(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        completed = self._runner(
            [str(self._binary_path), *args],
            check=False,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"HDT3213/rdb command failed: {detail}")
        return completed


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


@lru_cache(maxsize=1)
def build_default_rdb_parser_strategy() -> CompositeRdbParserStrategy:
    strategies: list[RdbParserStrategy] = []
    try:
        strategies.append(HdtRdbCliStrategy())
    except FileNotFoundError:
        pass
    strategies.append(LegacyRdbtoolsStrategy())
    return CompositeRdbParserStrategy(strategies)


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
