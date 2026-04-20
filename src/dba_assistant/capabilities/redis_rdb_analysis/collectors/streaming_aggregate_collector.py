from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import queue
import sys
import threading
from time import perf_counter
from typing import Any

from dba_assistant.capabilities.redis_rdb_analysis.analyzers.big_keys import (
    BoundedBigKeyHeap,
    BigKeyAccumulator,
)
from dba_assistant.capabilities.redis_rdb_analysis.collectors.row_value_coercion import (
    _coerce_bool,
    _coerce_required_int,
)
from dba_assistant.capabilities.redis_rdb_analysis.types import EffectiveProfile
from dba_assistant.core.observability.rdb_diagnostics import emit_rdb_phase
from dba_assistant.parsers.rdb_parser_strategy import StreamedRowsResult

logger = logging.getLogger(__name__)
DEFAULT_STREAM_IDLE_TIMEOUT_SECONDS = 300.0
STREAM_IDLE_TIMEOUT_ENV = "DBA_ASSISTANT_RDB_STREAM_IDLE_TIMEOUT_SECONDS"


class RdbStreamIdleTimeout(TimeoutError):
    def __init__(
        self,
        message: str,
        *,
        path: Path,
        parser_strategy: str,
        rows_processed: int,
        idle_timeout_seconds: float,
    ) -> None:
        super().__init__(message)
        self.path = path
        self.parser_strategy = parser_strategy
        self.rows_processed = rows_processed
        self.idle_timeout_seconds = idle_timeout_seconds


@dataclass(frozen=True)
class StreamingAggregationResult:
    analysis_result: dict[str, dict[str, object]]
    metadata: dict[str, str]


@dataclass
class _FocusedPrefixState:
    prefix: str
    matched_key_count: int = 0
    total_size_bytes: int = 0
    with_expiration: int = 0
    without_expiration: int = 0
    key_type_breakdown: Counter[str] = field(default_factory=Counter)
    top_keys: BoundedBigKeyHeap | None = None


class StreamingAnalysisPipeline:
    def __init__(self, *, profile: EffectiveProfile) -> None:
        self._profile = profile
        self._top_n_map = dict(profile.top_n)
        self._big_keys = BigKeyAccumulator(top_n=self._top_n_map)
        self._focus_states = {
            prefix: _FocusedPrefixState(
                prefix=prefix,
                top_keys=BoundedBigKeyHeap(
                    self._top_n_map.get(
                        "focused_prefix_top_keys",
                        self._top_n_map.get("top_big_keys", 100),
                    )
                ),
            )
            for prefix in profile.focus_prefixes
        }
        self._loan_big_keys = BoundedBigKeyHeap(self._top_n_map.get("top_big_keys", 100))
        self._total_keys = 0
        self._total_bytes = 0
        self._expired_count = 0
        self._persistent_count = 0
        self._key_type_counts: dict[str, int] = defaultdict(int)
        self._key_type_bytes: dict[str, int] = defaultdict(int)
        self._prefix_counts: dict[str, int] = defaultdict(int)
        self._prefix_bytes: dict[str, int] = defaultdict(int)

    @property
    def rows_processed(self) -> int:
        return self._total_keys

    def consume_row(self, row: dict[str, object]) -> None:
        key_name = str(row["key_name"])
        key_type = str(row["key_type"])
        size_bytes = _coerce_required_int(row.get("size_bytes"), "size_bytes")
        has_expiration = _coerce_bool(row.get("has_expiration"))
        
        prefix_label = _prefix_label(key_name)

        self._total_keys += 1
        self._total_bytes += size_bytes
        if has_expiration:
            self._expired_count += 1
        else:
            self._persistent_count += 1

        self._key_type_counts[key_type] += 1
        self._key_type_bytes[key_type] += size_bytes
        self._prefix_counts[prefix_label] += 1
        self._prefix_bytes[prefix_label] += size_bytes
        
        self._big_keys.add(
            key_name=key_name,
            key_type=key_type,
            size_bytes=size_bytes,
        )

        if self._profile.name.lower() == "rcs" and key_name.startswith("loan:"):
            self._loan_big_keys.push(
                key_name=key_name,
                key_type=key_type,
                size_bytes=size_bytes,
            )

        for focus_prefix, state in self._focus_states.items():
            if not _matches_prefix(key_name, focus_prefix):
                continue
            state.matched_key_count += 1
            state.total_size_bytes += size_bytes
            if has_expiration:
                state.with_expiration += 1
            else:
                state.without_expiration += 1
            state.key_type_breakdown[key_type] += 1
            if state.top_keys is not None:
                state.top_keys.push(
                    key_name=key_name,
                    key_type=key_type,
                    size_bytes=size_bytes,
                )

    def build_analysis_result(self, *, sample_rows: list[list[str]]) -> dict[str, dict[str, object]]:
        overall_summary = {
            "total_samples": len(sample_rows),
            "total_keys": self._total_keys,
            "total_bytes": self._total_bytes,
        }

        key_type_rows = [
            [key_type, str(self._key_type_counts[key_type]), str(self._key_type_bytes[key_type])]
            for key_type in self._key_type_counts
        ]
        key_type_rows.sort(
            key=lambda row: (-int(row[1]), -int(row[2]), row[0]),
        )

        key_type_memory_rows = [
            [key_type, str(self._key_type_bytes[key_type])]
            for key_type in self._key_type_bytes
        ]
        key_type_memory_rows.sort(key=lambda row: (-int(row[1]), row[0]))

        prefix_rows = [
            [prefix, str(self._prefix_counts[prefix]), str(self._prefix_bytes[prefix])]
            for prefix in self._prefix_counts
        ]
        prefix_rows.sort(key=lambda row: (-int(row[1]), -int(row[2]), row[0]))
        prefix_limit = int(self._top_n_map.get("prefix_top", 20))

        prefix_expiration_rows: list[list[str]] = []
        focused_sections: list[dict[str, Any]] = []
        for focus_prefix in self._profile.focus_prefixes:
            state = self._focus_states[focus_prefix]
            total = state.with_expiration + state.without_expiration
            prefix_expiration_rows.append(
                [
                    focus_prefix,
                    str(state.with_expiration),
                    str(state.without_expiration),
                    str(total),
                ]
            )
            summary_text = (
                f"前缀 {focus_prefix} 共匹配 {state.matched_key_count} 个键，累计内存占用 {state.total_size_bytes} 字节。"
                if state.matched_key_count
                else f"前缀 {focus_prefix} 未匹配到符合条件的键。"
            )
            focused_sections.append(
                {
                    "prefix": focus_prefix,
                    "matched_key_count": state.matched_key_count,
                    "total_size_bytes": state.total_size_bytes,
                    "key_type_breakdown": dict(state.key_type_breakdown),
                    "top_keys": [] if state.top_keys is None else state.top_keys.rows(include_type=True),
                    "expiration_stats": {
                        "with_expiration": state.with_expiration,
                        "without_expiration": state.without_expiration,
                    },
                    "summary_text": summary_text,
                    "limit": self._top_n_map.get(
                        "focused_prefix_top_keys",
                        self._top_n_map.get("top_big_keys", 100),
                    ),
                }
            )

        return {
            "executive_summary": overall_summary,
            "background": {
                "profile_name": self._profile.name,
                "focus_prefix_count": len(self._profile.focus_prefixes),
            },
            "analysis_results": overall_summary,
            "sample_overview": {
                "sample_rows": sample_rows,
            },
            "overall_summary": overall_summary,
            "key_type_summary": {
                "counts": dict(self._key_type_counts),
                "memory_bytes": dict(self._key_type_bytes),
                "rows": key_type_rows,
            },
            "key_type_memory_breakdown": {
                "rows": key_type_memory_rows,
            },
            "expiration_summary": {
                "expired_count": self._expired_count,
                "persistent_count": self._persistent_count,
            },
            "non_expiration_summary": {
                "persistent_count": self._persistent_count,
            },
            "prefix_top_summary": {
                "rows": prefix_rows[:prefix_limit],
            },
            "prefix_expiration_breakdown": {
                "rows": prefix_expiration_rows,
            },
            **self._big_keys.render_sections(),
            "focused_prefix_analysis": {
                "sections": focused_sections,
            },
            "loan_prefix_detail": {
                "rows": self._loan_big_keys.rows(include_type=True),
            },
            "conclusions": {},
        }


class StreamingAggregateCollector:
    def __init__(
        self,
        *,
        stream_parser: Callable[[Path], StreamedRowsResult],
        profile: EffectiveProfile,
        progress_log_interval: int = 100_000,
        stream_idle_timeout_seconds: float | None = None,
    ) -> None:
        self._stream_parser = stream_parser
        self._profile = profile
        self._progress_log_interval = progress_log_interval
        self._stream_idle_timeout_seconds = (
            _stream_idle_timeout_seconds()
            if stream_idle_timeout_seconds is None
            else stream_idle_timeout_seconds
        )

    def collect(self, paths: list[Path]) -> StreamingAggregationResult:
        pipeline = StreamingAnalysisPipeline(profile=self._profile)
        sample_rows: list[list[str]] = []
        progress: list[str] = []
        parser_strategies: list[str] = []
        parser_binaries: list[str] = []
        total_start = perf_counter()

        for index, path in enumerate(paths, start=1):
            streamed = self._stream_parser(path)
            parser_strategies.append(streamed.strategy_name)
            if streamed.strategy_detail:
                parser_binaries.append(streamed.strategy_detail)

            sample_rows.append([path.stem or f"sample-{index}", "local_rdb", str(path)])
            file_start = perf_counter()
            file_rows = 0
            next_progress_mark = self._progress_log_interval
            emit_rdb_phase(
                logger,
                "rdb_stream_file_collect_start",
                path=str(path),
                parser_strategy=streamed.strategy_name,
                parser_binary=streamed.strategy_detail,
                total_rows=pipeline.rows_processed,
                peak_memory_bytes_estimate=_peak_memory_bytes_estimate(),
            )
            
            # Real-time console reporting setup
            for row in _iter_rows_with_idle_timeout(
                streamed.rows,
                idle_timeout_seconds=self._stream_idle_timeout_seconds,
                path=path,
                parser_strategy=streamed.strategy_name,
                rows_processed=lambda: file_rows,
            ):
                pipeline.consume_row(dict(row))
                file_rows += 1
                
                if file_rows % 10_000 == 0:
                    elapsed = perf_counter() - file_start
                    rps = file_rows / elapsed if elapsed > 0 else 0
                    sys.stderr.write(
                        f"\r[RDB Streaming] Processed {file_rows:,} rows | Speed: {rps:,.0f} rows/s | Mem: {_peak_memory_human()}"
                    )
                    sys.stderr.flush()

                if file_rows >= next_progress_mark:
                    logger.info(
                        "streaming aggregate progress",
                        extra={
                            "event_name": "redis_rdb_stream_progress",
                            "path": str(path),
                            "parser_strategy": streamed.strategy_name,
                            "rows_processed": file_rows,
                            "peak_memory_bytes_estimate": _peak_memory_bytes_estimate(),
                        },
                    )
                    next_progress_mark += self._progress_log_interval
            
            sys.stderr.write("\n")
            sys.stderr.flush()

            file_elapsed = perf_counter() - file_start
            file_rows_per_second = file_rows / file_elapsed if file_elapsed > 0 else 0.0
            emit_rdb_phase(
                logger,
                "rdb_stream_file_collect_loop_end",
                path=str(path),
                parser_strategy=streamed.strategy_name,
                parser_binary=streamed.strategy_detail,
                rows_processed=file_rows,
                total_rows=pipeline.rows_processed,
                elapsed_seconds=round(file_elapsed, 6),
                peak_memory_bytes_estimate=_peak_memory_bytes_estimate(),
            )
            progress.append(
                f"path={path} rows={file_rows} elapsed={file_elapsed:.3f}s rows_per_sec={file_rows_per_second:.2f}"
            )

        total_elapsed = perf_counter() - total_start
        total_rows = pipeline.rows_processed
        total_rows_per_second = total_rows / total_elapsed if total_elapsed > 0 else 0.0
        peak_memory = _peak_memory_bytes_estimate()
        
        metadata = {
            "analysis_mode": "streaming_summary",
            "rows_processed": str(total_rows),
            "rows_per_second": f"{total_rows_per_second:.2f}",
            "elapsed_seconds_parse_aggregate": f"{total_elapsed:.3f}",
            "parser_strategy": ",".join(parser_strategies) if parser_strategies else "",
            "streaming_progress": " | ".join(progress),
        }
        if parser_binaries:
            metadata["parser_binary"] = ",".join(parser_binaries)
        if peak_memory is not None:
            metadata["peak_memory_bytes_estimate"] = str(peak_memory)

        build_started = perf_counter()
        emit_rdb_phase(
            logger,
            "rdb_build_analysis_result_start",
            total_rows=total_rows,
            elapsed_seconds=round(total_elapsed, 6),
            parser_strategy=metadata["parser_strategy"],
            peak_memory_bytes_estimate=peak_memory,
        )
        analysis_result = pipeline.build_analysis_result(sample_rows=sample_rows)
        emit_rdb_phase(
            logger,
            "rdb_build_analysis_result_end",
            total_rows=total_rows,
            elapsed_seconds=round(perf_counter() - build_started, 6),
            parser_strategy=metadata["parser_strategy"],
            peak_memory_bytes_estimate=_peak_memory_bytes_estimate(),
        )

        return StreamingAggregationResult(
            analysis_result=analysis_result,
            metadata=metadata,
        )


def _prefix_label(key_name: str) -> str:
    if ":" in key_name:
        return f"{key_name.split(':', 1)[0]}:*"
    return f"{key_name}:*"


def _matches_prefix(key_name: str, prefix: str) -> bool:
    if prefix.endswith("*"):
        return key_name.startswith(prefix[:-1])
    return key_name == prefix


def _iter_rows_with_idle_timeout(
    rows,
    *,
    idle_timeout_seconds: float,
    path: Path,
    parser_strategy: str,
    rows_processed: Callable[[], int],
):
    sentinel = object()
    row_queue: queue.Queue[object] = queue.Queue(maxsize=1024)
    stop_event = threading.Event()
    row_iter = iter(rows)

    def produce_rows() -> None:
        try:
            for row in row_iter:
                if stop_event.is_set():
                    break
                row_queue.put(row)
        except Exception as exc:  # noqa: BLE001
            row_queue.put(exc)
        finally:
            row_queue.put(sentinel)

    producer = threading.Thread(target=produce_rows, daemon=True)
    producer.start()

    while True:
        try:
            item = row_queue.get(timeout=idle_timeout_seconds)
        except queue.Empty as exc:
            stop_event.set()
            _close_row_iterator(row_iter, path=path, parser_strategy=parser_strategy)
            processed = rows_processed()
            emit_rdb_phase(
                logger,
                "rdb_stream_collect_idle_timeout",
                path=str(path),
                parser_strategy=parser_strategy,
                rows_processed=processed,
                idle_timeout_seconds=idle_timeout_seconds,
                producer_alive=producer.is_alive(),
                peak_memory_bytes_estimate=_peak_memory_bytes_estimate(),
            )
            raise RdbStreamIdleTimeout(
                f"RDB stream produced no rows for {idle_timeout_seconds:.3f}s "
                f"while reading {path} after {processed} rows",
                path=path,
                parser_strategy=parser_strategy,
                rows_processed=processed,
                idle_timeout_seconds=idle_timeout_seconds,
            ) from exc
        if item is sentinel:
            break
        if isinstance(item, Exception):
            raise item
        yield item


def _close_row_iterator(row_iter, *, path: Path, parser_strategy: str) -> None:
    close = getattr(row_iter, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception as exc:  # noqa: BLE001
        logger.info(
            "rdb stream iterator close failed",
            extra={
                "event_name": "redis_rdb_analysis_phase",
                "phase": "rdb_stream_iterator_close_failed",
                "path": str(path),
                "parser_strategy": parser_strategy,
                "error": str(exc),
            },
        )


def _peak_memory_human() -> str:
    bytes_val = _peak_memory_bytes_estimate()
    if bytes_val is None:
        return "N/A"
    
    val = float(bytes_val)
    for unit in ["B", "KB", "MB", "GB"]:
        if val < 1024:
            return f"{val:.1f} {unit}"
        val /= 1024
    return f"{val:.1f} TB"


def _stream_idle_timeout_seconds() -> float:
    raw_value = os.getenv(STREAM_IDLE_TIMEOUT_ENV, "").strip()
    if not raw_value:
        return DEFAULT_STREAM_IDLE_TIMEOUT_SECONDS
    try:
        parsed = float(raw_value)
    except ValueError:
        return DEFAULT_STREAM_IDLE_TIMEOUT_SECONDS
    if parsed <= 0:
        return DEFAULT_STREAM_IDLE_TIMEOUT_SECONDS
    return parsed


def _peak_memory_bytes_estimate() -> int | None:
    try:
        import resource
        raw_value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except Exception:  # noqa: BLE001
        return None
    if sys.platform == "darwin":
        return raw_value
    return raw_value * 1024
