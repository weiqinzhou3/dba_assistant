from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class FlamegraphSpec:
    command: tuple[str, ...]
    url: str


class RdbParserStrategy(Protocol):
    def parse_rows(self, path: Path) -> list[dict[str, object]]:
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
        payload = self.export_json(path)
        rows: list[dict[str, object]] = []
        for obj in payload:
            normalized = _normalize_hdt_json_object(obj)
            if normalized is not None:
                rows.append(normalized)
        return rows

    def export_json(self, path: Path) -> list[dict[str, object]]:
        with tempfile.TemporaryDirectory(prefix="dba-assistant-rdb-json-") as tmpdir:
            output_path = Path(tmpdir) / "dump.json"
            self._run_cli(["-c", "json", "-o", str(output_path), str(path)])
            return json.loads(output_path.read_text(encoding="utf-8"))

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
        from rdbtools import MemoryCallback, RdbParser

        stream = _MemoryRecordStream()
        parser = RdbParser(MemoryCallback(stream, 64))
        parser.parse(str(path))
        return stream.rows


class CompositeRdbParserStrategy:
    def __init__(self, strategies: list[RdbParserStrategy]) -> None:
        self._strategies = strategies

    def parse_rows(self, path: Path) -> list[dict[str, object]]:
        errors: list[str] = []
        for strategy in self._strategies:
            try:
                return strategy.parse_rows(path)
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
        candidates.append(Path(configured))

    repo_root = Path(__file__).resolve().parents[4]
    candidates.append(repo_root / ".tools/bin/rdb")

    path_candidate = shutil.which("rdb")
    if path_candidate:
        candidates.append(Path(path_candidate))

    for candidate in candidates:
        if candidate.exists() and _looks_like_hdt_rdb(candidate):
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
