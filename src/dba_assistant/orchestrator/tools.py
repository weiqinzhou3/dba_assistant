"""Unified tool registry for the orchestrator.

All agent-facing tools are registered here. Tools accept explicit non-sensitive
parameters from the LLM while secrets remain in secure runtime context.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from functools import wraps
import inspect
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from dba_assistant.adaptors.mysql_adaptor import (
    MySQLAdaptor,
    MySQLConnectionConfig,
    MySQLOperationError,
)
from dba_assistant.adaptors.redis_adaptor import (
    RedisAdaptor,
    RedisConnectionConfig,
)
from dba_assistant.adaptors.ssh_adaptor import SSHAdaptor, SSHConnectionConfig
from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides
from dba_assistant.application.request_models import (
    DEFAULT_INSPECTION_LOG_TIME_WINDOW_DAYS,
    DEFAULT_LOOPBACK_HOST,
    DEFAULT_MYSQL_PORT,
    DEFAULT_MYSQL_USER,
    DEFAULT_MYSQL_DATABASE,
    DEFAULT_REDIS_DB,
    DEFAULT_REDIS_PORT,
    LARGE_RDB_WARNING_BYTES,
    build_default_mysql_table_name,
)
from dba_assistant.core.observability import observe_tool_call
from dba_assistant.core.observability.rdb_diagnostics import (
    emit_rdb_phase,
    rdb_phase_event_handler,
)
from dba_assistant.core.reporter.output_path_policy import ensure_report_output_path
from dba_assistant.core.reporter.types import OutputMode, ReportFormat, ReportOutputConfig
from dba_assistant.core.runtime_paths import DEFAULT_EVIDENCE_DIR, make_runtime_work_dir
from dba_assistant.deep_agent_integration.model_provider import build_model
from dba_assistant.interface.hitl import HumanApprovalHandler
from dba_assistant.interface.types import ApprovalRequest, ApprovalStatus
from dba_assistant.capabilities.redis_rdb_analysis.remote_input import (
    RemoteRedisDiscoveryError,
    discover_remote_rdb,
)
from dba_assistant.capabilities.redis_rdb_analysis.types import (
    InputSourceKind,
    RdbAnalysisRequest,
    SampleInput,
)
from dba_assistant.capabilities.redis_inspection_report.service import (
    analyze_inspection as _analyze_inspection_dataset,
    analyze_remote_inspection as _analyze_remote_inspection,
    build_log_review_payload as _build_log_review_payload,
    collect_offline_inspection_dataset as _collect_offline_inspection_dataset,
    collect_offline_log_review_payload as _collect_offline_log_review_payload,
    parse_reviewed_log_issues as _parse_reviewed_log_issues,
    summarize_inspection_dataset as _summarize_inspection_dataset,
)
from dba_assistant.capabilities.redis_inspection_report.reviewer import (
    review_redis_log_candidates as _review_redis_log_candidates,
)
from dba_assistant.tools.analyze_rdb import analyze_rdb_tool
from dba_assistant.tools.mysql_tools import (
    MySQLStagingSession,
    analyze_staged_rdb_rows as _analyze_staged,
    create_database as _create_database,
    create_staging_table as _create_staging_table,
    database_exists as _database_exists,
    insert_staging_batch as _insert_staging_batch,
    load_preparsed_dataset_from_mysql as _load_dataset,
    format_mysql_error as _format_mysql_error,
    mysql_read_query as _mysql_read,
    stage_rdb_rows_to_mysql as _stage_rows,
    table_exists as _table_exists,
)
from dba_assistant.orchestrator.config_collection_tool import make_ask_user_for_config_tool
from dba_assistant.orchestrator.redis_inspection_tools import make_redis_inspection_tools
from dba_assistant.orchestrator.report_output import (
    append_mysql_runtime_note as _append_mysql_runtime_note,
    render_analysis_output as _render_analysis_output,
)
from dba_assistant.orchestrator.tool_helpers import (
    human_readable_size as _human_readable_size,
    named_tool as _named_tool,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Runtime context and builder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolRuntimeContext:
    request: NormalizedRequest
    approval_handler: HumanApprovalHandler | None = None
    default_redis_connection: RedisConnectionConfig | None = None
    default_mysql_connection: MySQLConnectionConfig | None = None
    redis_socket_timeout: float = 5.0
    mysql_connect_timeout_seconds: float = 5.0
    mysql_read_timeout_seconds: float = 15.0
    mysql_write_timeout_seconds: float = 30.0
    model_config: Any | None = None
    event_handler: Callable[[dict[str, Any]], None] | None = None

def build_all_tools(
    request: NormalizedRequest,
    *,
    config: Any | None = None,
    connection: RedisConnectionConfig | None = None,
    mysql_connection: MySQLConnectionConfig | None = None,
    remote_rdb_state: dict[str, Any] | None = None,
    approval_handler: HumanApprovalHandler | None = None,
    event_handler: Callable[[dict[str, Any]], None] | None = None,
) -> list:
    """Build the complete tool list available to the unified agent."""
    runtime_config = getattr(config, "runtime", None)
    context = ToolRuntimeContext(
        request=request,
        approval_handler=approval_handler,
        default_redis_connection=connection,
        default_mysql_connection=mysql_connection,
        redis_socket_timeout=float(
            getattr(runtime_config, "redis_socket_timeout", 5.0)
        ),
        mysql_connect_timeout_seconds=float(
            getattr(runtime_config, "mysql_connect_timeout_seconds", 5.0)
        ),
        mysql_read_timeout_seconds=float(
            getattr(runtime_config, "mysql_read_timeout_seconds", 15.0)
        ),
        mysql_write_timeout_seconds=float(
            getattr(runtime_config, "mysql_write_timeout_seconds", 30.0)
        ),
        model_config=getattr(config, "model", None),
        event_handler=event_handler,
    )
    tools: list = []
    inspection_datasets: dict[str, Any] = {}
    inspection_log_candidate_payloads: dict[str, Any] = {}
    profile = _select_tool_capability_profile(request)

    adaptor = RedisAdaptor()
    shared_remote_rdb_state = remote_rdb_state if remote_rdb_state is not None else {}
    rdb_session_state: dict[str, Any] = {}

    if profile in {"rdb", "all"}:
        tools.append(_make_inspect_local_rdb_tool(rdb_session_state))
        tools.append(_make_analyze_local_rdb_stream_tool(context, rdb_session_state))
        tools.append(_make_analyze_staged_rdb_tool(context, rdb_session_state))
        tools.append(_make_stage_local_rdb_to_mysql_tool(context, rdb_session_state))
        tools.append(_make_analyze_preparsed_dataset_tool(context, rdb_session_state))

    if profile in {"rdb", "inspection", "all"}:
        tools.extend(
            make_redis_inspection_tools(
                context,
                adaptor,
                resolve_connection=_resolve_request_with_redis_connection,
            )
        )

    if profile in {"inspection", "all"}:
        tools.append(
            _make_collect_offline_inspection_dataset_tool(
                context,
                inspection_datasets,
            )
        )
        tools.append(
            _make_redis_inspection_log_candidates_tool(
                context,
                inspection_datasets,
                inspection_log_candidate_payloads,
            )
        )
        tools.append(
            _make_review_redis_log_candidates_tool(
                context,
                inspection_log_candidate_payloads,
            )
        )
        tools.append(
            _make_render_redis_inspection_report_tool(
                context,
                inspection_datasets,
                tool_name="render_redis_inspection_report",
            )
        )
        tools.append(
            _make_render_redis_inspection_report_tool(
                context,
                inspection_datasets,
                tool_name="redis_inspection_report",
            )
        )

    if profile in {"rdb", "all"}:
        tools.append(
            _make_discover_remote_rdb_tool(
                context,
                adaptor,
                remote_rdb_state=shared_remote_rdb_state,
            )
        )
        tools.append(
            _make_ensure_remote_rdb_snapshot_tool(
                context,
                adaptor,
                remote_rdb_state=shared_remote_rdb_state,
            )
        )
        tools.append(
            _make_fetch_remote_rdb_via_ssh_tool(
                context,
            )
        )
        tools.extend(
            _make_mysql_tools(
                context,
            )
        )

    # Generic input collection tool
    if approval_handler is not None:
        tools.append(make_ask_user_for_config_tool(approval_handler, rdb_session_state=rdb_session_state))

    return [_instrument_tool(tool, event_handler=context.event_handler) for tool in tools]


def _select_tool_capability_profile(request: NormalizedRequest) -> str:
    runtime = request.runtime_inputs
    input_kind = (runtime.input_kind or "").strip().lower()
    path_mode = (runtime.path_mode or "").strip().lower()
    prompt = f"{request.raw_prompt}\n{request.prompt}".lower()

    if input_kind in {"redis_inspection", "inspection"}:
        return "inspection"
    if path_mode in {"redis_inspection", "inspection", "redis_inspection_report"}:
        return "inspection"
    if _prompt_requests_inspection(prompt) and not _prompt_requests_rdb_analysis(prompt):
        return "inspection"
    if runtime.input_paths and _input_paths_look_like_inspection_sources(runtime.input_paths):
        if input_kind not in {"local_rdb", "precomputed", "preparsed_mysql"}:
            return "inspection"

    if input_kind in {"local_rdb", "precomputed", "preparsed_mysql", "remote_redis"}:
        return "rdb"
    if path_mode in {"auto", "database_backed_analysis", "preparsed_dataset_analysis", "direct_rdb_analysis"}:
        return "rdb"
    if runtime.remote_rdb_path or runtime.require_fresh_rdb_snapshot or runtime.ssh_host:
        return "rdb"
    if runtime.mysql_host or runtime.mysql_table or runtime.mysql_query:
        return "rdb"
    if any(_path_looks_like_rdb(path) for path in runtime.input_paths):
        return "rdb"
    return "all"


def _prompt_requests_inspection(prompt: str) -> bool:
    return any(token in prompt for token in ("inspection", "巡检", "体检"))


def _prompt_requests_rdb_analysis(prompt: str) -> bool:
    return any(token in prompt for token in ("rdb", "dump.rdb", "database_backed_analysis", "preparsed_mysql"))


def _input_paths_look_like_inspection_sources(paths: tuple[Path, ...]) -> bool:
    return any(not _path_looks_like_rdb(path) for path in paths)


def _path_looks_like_rdb(path: Path) -> bool:
    return path.suffix.lower() == ".rdb"


# ---------------------------------------------------------------------------
# Session state: large-RDB MySQL refusal and DOCX output enforcement
# ---------------------------------------------------------------------------

_MYSQL_REFUSAL_PATTERNS = [
    re.compile(r"不[要用需].*mysql", re.IGNORECASE),
    re.compile(r"no\s*mysql", re.IGNORECASE),
    re.compile(r"直接分析"),
    re.compile(r"不[要用需].*staging", re.IGNORECASE),
    re.compile(r"skip\s*mysql", re.IGNORECASE),
    re.compile(r"without\s*mysql", re.IGNORECASE),
    re.compile(r"不[要用需].*数据库"),
    re.compile(r"just\s+analyze", re.IGNORECASE),
]

_MYSQL_CONFIG_KEYWORDS = frozenset({"mysql", "数据库", "database", "staging"})

_DOCX_REQUEST_TOKENS = frozenset({"word", "docx", "doc", "文档", "报告"})

_MYSQL_REFUSAL_GUARD_MESSAGE = (
    "MySQL staging was declined for this session. "
    "Use analyze_local_rdb_stream for direct analysis of the local RDB file."
)


def _is_mysql_refusal(text: str) -> bool:
    """Detect explicit user refusal of MySQL-backed staging."""
    return any(pattern.search(text) for pattern in _MYSQL_REFUSAL_PATTERNS)


def _is_mysql_related_question(question: str) -> bool:
    lower = question.lower()
    return any(token in lower for token in _MYSQL_CONFIG_KEYWORDS)


def _prompt_requests_docx_output(prompt: str) -> bool:
    """Detect if the user prompt explicitly requests DOCX/Word output."""
    lower = prompt.lower()
    return any(token in lower for token in _DOCX_REQUEST_TOKENS)


# ---------------------------------------------------------------------------
# Local RDB inspection (Phase 3)
# ---------------------------------------------------------------------------

def _make_inspect_local_rdb_tool(rdb_session_state: dict[str, Any]):
    """Tool to provide file metadata to the LLM."""

    def inspect_local_rdb(input_paths: str) -> str:
        paths = [Path(p.strip()).expanduser() for p in input_paths.split(",") if p.strip()]
        if not paths:
            return "Error: no input paths provided."

        results = []
        any_large = False
        for path in paths:
            exists = path.exists()
            size = path.stat().st_size if exists and path.is_file() else 0
            is_large = size > LARGE_RDB_WARNING_BYTES
            if is_large:
                any_large = True
            results.append(
                {
                    "path": str(path),
                    "exists": exists,
                    "is_file": path.is_file() if exists else False,
                    "size_bytes": size,
                    "size_human": _human_readable_size(size),
                    "large_file": is_large,
                }
            )
        if any_large:
            rdb_session_state["large_rdb_detected"] = True
            rdb_session_state.setdefault("large_rdb_paths", []).extend(
                str(r["path"]) for r in results if r.get("large_file")
            )
        return json.dumps(results, indent=2)

    return _named_tool(
        inspect_local_rdb,
        "inspect_local_rdb",
        (
            "Inspect local Redis RDB dump files to see metadata before analysis. "
            "Returns JSON with existence, size, file status, and large_file flag. "
            "Use this BEFORE analysis to decide if a file is too large for direct analysis. "
            "If the user declines MySQL staging for large files, proceed directly "
            "with analyze_local_rdb_stream (set mysql_staging_refused=true). "
            "Parameter: input_paths (comma-separated file paths)."
        ),
    )


# ---------------------------------------------------------------------------
# Redis inspection report (Phase 4)
# ---------------------------------------------------------------------------

def _make_collect_offline_inspection_dataset_tool(
    context: ToolRuntimeContext,
    dataset_store: dict[str, Any],
):
    """Collect and normalize offline Redis inspection evidence."""
    request = context.request

    def collect_offline_inspection_dataset(
        input_paths: str = "",
        log_time_window_days: int | None = None,
        log_start_time: str = "",
        log_end_time: str = "",
    ) -> str:
        explicit_paths = [Path(p.strip()).expanduser() for p in input_paths.split(",") if p.strip()]
        paths = explicit_paths or list(request.runtime_inputs.input_paths)
        if not paths:
            return "Error: input_paths are required for offline inspection dataset collection."

        for path in paths:
            if not path.exists():
                return f"Error: input path does not exist on host filesystem: {path}"
        effective_log_time_window_days, effective_log_start_time, effective_log_end_time = _resolve_inspection_log_window(
            request,
            log_time_window_days=log_time_window_days,
            log_start_time=log_start_time,
            log_end_time=log_end_time,
        )
        try:
            dataset = _collect_offline_inspection_dataset(
                tuple(paths),
                log_time_window_days=effective_log_time_window_days,
                log_start_time=effective_log_start_time,
                log_end_time=effective_log_end_time,
                work_dir=request.runtime_inputs.temp_dir,
            )
        except ValueError as exc:
            return f"Error: {exc}"
        handle = f"inspection_dataset_{len(dataset_store) + 1}"
        dataset_store[handle] = dataset
        payload = _summarize_inspection_dataset(
            dataset,
            dataset_handle=handle,
            log_time_window_days=effective_log_time_window_days,
            log_start_time=effective_log_start_time,
            log_end_time=effective_log_end_time,
        )
        return json.dumps(payload, ensure_ascii=False, indent=2)

    return _named_tool(
        collect_offline_inspection_dataset,
        "collect_offline_inspection_dataset",
        (
            "Collect and normalize offline Redis inspection evidence into a dataset_handle. "
            "This tool only unpacks/parses evidence, groups systems/clusters/nodes, "
            "applies deterministic log time-window filtering, and returns a dataset summary. "
            "It does not render reports and does not perform log semantic judgement."
        ),
    )


def _make_render_redis_inspection_report_tool(
    context: ToolRuntimeContext,
    dataset_store: dict[str, Any],
    *,
    tool_name: str,
):
    """Render an inspection report from a collected dataset or live read-only snapshot."""
    request = context.request

    def render_redis_inspection_report(
        dataset_handle: str = "",
        input_paths: str = "",
        redis_host: str = "",
        redis_port: int | None = None,
        redis_db: int | None = None,
        report_language: str = "",
        output_mode: str = "",
        report_format: str = "",
        output_path: str = "",
        reviewed_log_issues_json: str = "",
        log_time_window_days: int | None = None,
        log_start_time: str = "",
        log_end_time: str = "",
    ) -> str:
        if input_paths.strip():
            return (
                "Error: offline inspection rendering requires a dataset_handle. "
                "Call collect_offline_inspection_dataset first."
            )
        language = report_language or request.runtime_inputs.report_language
        try:
            if dataset_handle.strip():
                dataset = dataset_store.get(dataset_handle.strip())
                if dataset is None:
                    return f"Error: unknown inspection dataset_handle: {dataset_handle}"
                reviewed_log_issues = _parse_reviewed_log_issues(reviewed_log_issues_json)
                if reviewed_log_issues:
                    dataset = replace(dataset, reviewed_log_issues=reviewed_log_issues)
                analysis = _analyze_inspection_dataset(
                    dataset,
                    language=language,
                    route="offline_inspection",
                )
                runtime_inputs = request.runtime_inputs
            else:
                resolved_request, connection = _resolve_request_with_redis_connection(
                    context,
                    redis_host=redis_host,
                    redis_port=redis_port,
                    redis_db=redis_db,
                )
                analysis = _analyze_remote_inspection(connection, language=language)
                runtime_inputs = resolved_request.runtime_inputs
        except ValueError as exc:
            return f"Error: {exc}"
        except PermissionError as exc:
            return str(exc)

        effective_format = report_format or runtime_inputs.report_format or "docx"
        effective_mode = output_mode or runtime_inputs.output_mode or "report"
        return _render_analysis_output(
            analysis,
            runtime_inputs=runtime_inputs,
            output_mode=effective_mode,
            report_format=effective_format,
            output_path=Path(output_path) if output_path else runtime_inputs.output_path,
            template_name="inspection",
        )

    return _named_tool(
        render_redis_inspection_report,
        tool_name,
        (
            "Render a Redis inspection summary or DOCX report from a dataset_handle "
            "created by collect_offline_inspection_dataset, or from a live read-only "
            "Redis target when no dataset_handle is supplied. "
            "Parameters: dataset_handle, "
            "redis_host, redis_port, redis_db, report_language, output_mode, report_format, "
            "output_path (optional; omit output_path to use runtime default for docx), "
            "reviewed_log_issues_json. "
            "For offline log analysis, pass reviewed_log_issues_json after LLM semantic review."
        ),
    )


def _make_redis_inspection_log_candidates_tool(
    context: ToolRuntimeContext,
    dataset_store: dict[str, Any],
    log_candidate_store: dict[str, Any],
):
    """Collect neutral Redis log candidates for LLM semantic review."""
    request = context.request

    def redis_inspection_log_candidates(
        dataset_handle: str = "",
        input_paths: str = "",
        log_time_window_days: int | None = None,
        log_start_time: str = "",
        log_end_time: str = "",
    ) -> str:
        if dataset_handle.strip():
            dataset = dataset_store.get(dataset_handle.strip())
            if dataset is None:
                return f"Error: unknown inspection dataset_handle: {dataset_handle}"
            payload = _build_log_review_payload(dataset)
            handle = _store_inspection_log_candidate_payload(log_candidate_store, payload)
            summary = _summarize_log_candidate_payload(
                payload,
                log_candidates_handle=handle,
            )
            return json.dumps(summary, ensure_ascii=False, indent=2)

        explicit_paths = [Path(p.strip()).expanduser() for p in input_paths.split(",") if p.strip()]
        paths = explicit_paths or list(request.runtime_inputs.input_paths)
        if not paths:
            return "Error: dataset_handle or input_paths are required for offline log candidate review."
        effective_log_time_window_days, effective_log_start_time, effective_log_end_time = _resolve_inspection_log_window(
            request,
            log_time_window_days=log_time_window_days,
            log_start_time=log_start_time,
            log_end_time=log_end_time,
        )
        for path in paths:
            if not path.exists():
                return f"Error: input path does not exist on host filesystem: {path}"
        try:
            payload = _collect_offline_log_review_payload(
                tuple(paths),
                log_time_window_days=effective_log_time_window_days,
                log_start_time=effective_log_start_time,
                log_end_time=effective_log_end_time,
                work_dir=request.runtime_inputs.temp_dir,
            )
        except ValueError as exc:
            return f"Error: {exc}"
        handle = _store_inspection_log_candidate_payload(log_candidate_store, payload)
        summary = _summarize_log_candidate_payload(
            payload,
            log_candidates_handle=handle,
        )
        return json.dumps(summary, ensure_ascii=False, indent=2)

    return _named_tool(
        redis_inspection_log_candidates,
        "redis_inspection_log_candidates",
        (
            "Collect neutral Redis log candidates for LLM semantic review. "
            "This tool only performs deterministic evidence reduction: time filtering, "
            "timestamp parsing, deduplication, sampling, and cluster/node bucketing. "
            "It does not decide whether a candidate is anomalous. "
            "Prefer dataset_handle from collect_offline_inspection_dataset to avoid re-parsing evidence. "
            "It stores the full candidate payload internally and returns a lightweight "
            "log_candidates_handle plus bounded preview. "
            "Next call review_redis_log_candidates with log_candidates_handle; do not pass "
            "large candidate payloads back through tool arguments."
        ),
    )


def _make_review_redis_log_candidates_tool(
    context: ToolRuntimeContext,
    log_candidate_store: dict[str, Any],
):
    """Run LLM semantic review over a log candidate payload."""
    request = context.request

    def review_redis_log_candidates(
        log_candidates_handle: str = "",
        focus_topics: str = "",
        report_language: str = "",
        log_candidates_json: str = "",
    ) -> str:
        log_candidates_payload: Any
        if log_candidates_handle.strip():
            log_candidates_payload = log_candidate_store.get(log_candidates_handle.strip())
            if log_candidates_payload is None:
                return f"Error: unknown log_candidates_handle: {log_candidates_handle}"
            effective_log_candidates_json = json.dumps(
                log_candidates_payload,
                ensure_ascii=False,
            )
        else:
            if not log_candidates_json.strip():
                return (
                    "Error: log_candidates_handle is required. "
                    "Call redis_inspection_log_candidates first and pass its handle."
                )
            effective_log_candidates_json = log_candidates_json
        if context.model_config is None:
            return "Error: model configuration is required for Redis log semantic review."
        try:
            model = build_model(context.model_config)
            return _review_redis_log_candidates(
                effective_log_candidates_json,
                model=model,
                focus_topics=focus_topics,
                report_language=report_language or request.runtime_inputs.report_language,
            )
        except ValueError as exc:
            return f"Error: {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"Error during Redis log semantic review: {exc}"

    return _named_tool(
        review_redis_log_candidates,
        "review_redis_log_candidates",
        (
            "Review Redis log candidates with an LLM and return reviewed_log_issues_json. "
            "Prefer log_candidates_handle returned by redis_inspection_log_candidates. "
            "Do not pass large candidate payload strings back through tool arguments. "
            "The legacy log_candidates_json argument is only for small compatibility cases. "
            "This tool loads the stored candidate payload by handle and does not access filesystem "
            "tools such as ls, glob, grep, or read_file. "
            "Parameters: log_candidates_handle, focus_topics, report_language."
        ),
    )


def _store_inspection_log_candidate_payload(
    store: dict[str, Any],
    payload: dict[str, Any],
) -> str:
    handle = f"inspection_log_candidates_{len(store) + 1}"
    store[handle] = payload
    return handle


def _summarize_log_candidate_payload(
    payload: dict[str, Any],
    *,
    log_candidates_handle: str,
) -> dict[str, Any]:
    clusters = payload.get("clusters")
    if not isinstance(clusters, list):
        clusters = []
    return {
        "log_candidates_handle": log_candidates_handle,
        "source_mode": payload.get("source_mode"),
        "input_sources": payload.get("input_sources") or [],
        "cluster_count": len(clusters),
        "candidate_count": _total_log_candidate_count(clusters),
        "preview": _log_candidate_preview(clusters),
        "next_step": (
            "Call review_redis_log_candidates(log_candidates_handle=...) "
            "with this handle; do not pass the full candidate payload as a tool argument."
        ),
    }


def _total_log_candidate_count(clusters: list[Any]) -> int:
    total = 0
    for cluster in clusters:
        if not isinstance(cluster, dict):
            continue
        value = cluster.get("candidate_count")
        try:
            total += int(value)
        except (TypeError, ValueError):
            candidates = cluster.get("log_candidates")
            total += len(candidates) if isinstance(candidates, list) else 0
    return total


def _log_candidate_preview(
    clusters: list[Any],
    *,
    max_clusters: int = 5,
    max_samples_per_cluster: int = 3,
) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for cluster in clusters[:max_clusters]:
        if not isinstance(cluster, dict):
            continue
        candidates = cluster.get("log_candidates")
        if not isinstance(candidates, list):
            candidates = []
        preview.append(
            {
                "cluster_id": cluster.get("cluster_id") or "",
                "cluster_name": cluster.get("cluster_name") or "",
                "candidate_count": _cluster_candidate_count(cluster, candidates),
                "samples": [
                    _candidate_preview_item(candidate)
                    for candidate in candidates[:max_samples_per_cluster]
                    if isinstance(candidate, dict)
                ],
            }
        )
    return preview


def _cluster_candidate_count(cluster: dict[str, Any], candidates: list[Any]) -> int:
    value = cluster.get("candidate_count")
    try:
        return int(value)
    except (TypeError, ValueError):
        return len(candidates)


def _candidate_preview_item(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": candidate.get("node_id") or "",
        "timestamp": candidate.get("timestamp"),
        "candidate_signal": candidate.get("candidate_signal") or "",
        "raw_message": candidate.get("raw_message") or "",
        "count": candidate.get("count", candidate.get("repeated_count", 1)),
        "repeated_count": candidate.get("repeated_count", candidate.get("count", 1)),
        "source_path": candidate.get("source_path") or "",
        "parse_confidence": candidate.get("parse_confidence") or "",
        "time_window_applied": candidate.get("time_window_applied"),
    }


def _resolve_inspection_log_window(
    request: NormalizedRequest,
    *,
    log_time_window_days: int | None,
    log_start_time: str,
    log_end_time: str,
) -> tuple[int | None, str | None, str | None]:
    effective_log_start_time = log_start_time or request.runtime_inputs.log_start_time
    effective_log_end_time = log_end_time or request.runtime_inputs.log_end_time
    effective_log_time_window_days = (
        log_time_window_days
        if log_time_window_days is not None
        else request.runtime_inputs.log_time_window_days
    )
    if (
        effective_log_time_window_days is None
        and not effective_log_start_time
        and not effective_log_end_time
    ):
        effective_log_time_window_days = DEFAULT_INSPECTION_LOG_TIME_WINDOW_DAYS
    return effective_log_time_window_days, effective_log_start_time, effective_log_end_time


# ---------------------------------------------------------------------------
# Local RDB analysis (Phase 3)
# ---------------------------------------------------------------------------

def _make_analyze_local_rdb_stream_tool(
    context: ToolRuntimeContext,
    rdb_session_state: dict[str, Any],
):
    """Combined analyze + report tool for local RDB files (streaming)."""
    request = context.request

    def analyze_local_rdb_stream(
        input_paths: str,
        profile_name: str = "generic",
        report_language: str = "",
        output_mode: str = "",
        report_format: str = "",
        output_path: str = "",
        focus_prefixes: str = "",
        mysql_staging_refused: bool = False,
    ) -> str:
        with rdb_phase_event_handler(context.event_handler):
            # Latch MySQL refusal into session state so other tools respect it.
            if mysql_staging_refused:
                rdb_session_state["mysql_staging_refused"] = True
            paths = [Path(p.strip()).expanduser() for p in input_paths.split(",") if p.strip()]
            if not paths:
                return "Error: no input paths provided."
            for path in paths:
                if not path.exists():
                    return f"Error: input path does not exist on host filesystem: {path}"
                if not path.is_file():
                    return f"Error: input path is not a regular file on host filesystem: {path}"

            overrides: dict[str, object] = {}
            if focus_prefixes:
                overrides["focus_prefixes"] = tuple(
                    p.strip() for p in focus_prefixes.split(",") if p.strip()
                )
            elif request.rdb_overrides.focus_prefixes:
                overrides["focus_prefixes"] = request.rdb_overrides.focus_prefixes
            if request.rdb_overrides.focus_only:
                overrides["focus_only"] = True
            if request.rdb_overrides.top_n:
                overrides["top_n"] = dict(request.rdb_overrides.top_n)

            try:
                analyze_kwargs = {
                    "prompt": request.prompt,
                    "input_paths": paths,
                    "input_kind": "local_rdb",
                    "profile_name": profile_name,
                    "report_language": report_language or request.runtime_inputs.report_language,
                    "path_mode": "direct_rdb_analysis",  # Locked to streaming
                    "profile_overrides": overrides,
                }
                emit_rdb_phase(
                    logger,
                    "rdb_direct_analysis_start",
                    input_count=len(paths),
                    profile_name=profile_name,
                    parser_override=os.getenv("DBA_ASSISTANT_RDB_PARSER") or "",
                )
                analysis = analyze_rdb_tool(
                    **analyze_kwargs,
                )
                emit_rdb_phase(
                    logger,
                    "rdb_direct_analysis_end",
                    input_count=len(paths),
                    route=str(getattr(analysis, "metadata", {}).get("route", "")),
                    parser_strategy=str(getattr(analysis, "metadata", {}).get("parser_strategy", "")),
                )
            except ValueError as exc:
                emit_rdb_phase(logger, "rdb_direct_analysis_error", error=str(exc))
                return f"Error: {exc}"
            except PermissionError as exc:
                emit_rdb_phase(logger, "rdb_direct_analysis_error", error=str(exc))
                return str(exc)

            from dba_assistant.core.reporter.generate_analysis_report import (
                generate_analysis_report as _generate,
            )

            diagnostic_summary_only = _env_flag("DBA_ASSISTANT_RDB_DIAGNOSTIC_SUMMARY_ONLY")
            effective_output_mode = output_mode or request.runtime_inputs.output_mode or "summary"
            effective_report_format = (
                report_format
                or request.runtime_inputs.report_format
                or ("summary" if effective_output_mode == "summary" else "docx")
            )
            if diagnostic_summary_only:
                effective_output_mode = "summary"
                effective_report_format = "summary"

            # Hard guard: force DOCX when the original prompt demands it.
            prompt_wants_docx = (
                _prompt_requests_docx_output(request.prompt)
                or _prompt_requests_docx_output(request.raw_prompt)
            )
            if prompt_wants_docx and effective_report_format != "docx" and not diagnostic_summary_only:
                effective_output_mode = "report"
                effective_report_format = "docx"

            runtime_inputs = ensure_report_output_path(
                replace(
                    request.runtime_inputs,
                    output_mode=effective_output_mode,
                    report_format=effective_report_format,
                    output_path=Path(output_path) if output_path else request.runtime_inputs.output_path,
                ),
                effective_report_format,
            )
            fmt = ReportFormat.SUMMARY if effective_report_format == "summary" else ReportFormat.DOCX
            out = runtime_inputs.output_path
            if fmt is ReportFormat.DOCX and out is None:
                return "Error: DOCX output requires an output path."

            config = ReportOutputConfig(
                mode=OutputMode.SUMMARY if effective_output_mode == "summary" else OutputMode.REPORT,
                format=fmt,
                output_path=out,
                template_name="rdb-analysis",
                language=runtime_inputs.report_language,
            )
            emit_rdb_phase(
                logger,
                "rdb_report_render_start",
                report_format=fmt.value,
                output_path=str(out) if out is not None else "",
                diagnostic_summary_only=diagnostic_summary_only,
            )
            try:
                artifact = _generate(analysis, config)
            except Exception as exc:  # noqa: BLE001
                emit_rdb_phase(
                    logger,
                    "rdb_report_render_error",
                    report_format=fmt.value,
                    output_path=str(out) if out is not None else "",
                    error=str(exc),
                )
                raise
            emit_rdb_phase(
                logger,
                "rdb_report_render_end",
                report_format=fmt.value,
                output_path=str(artifact.output_path) if artifact.output_path is not None else "",
            )

            # Postcondition: when DOCX was requested, verify the artifact path.
            if fmt is ReportFormat.DOCX:
                if artifact.output_path is not None and artifact.output_path.exists():
                    return str(artifact.output_path)
                if artifact.output_path is not None:
                    return f"Error: DOCX generation completed but artifact not found at {artifact.output_path}"
                return "Error: DOCX output was requested but no artifact path was generated by the reporter."

            if artifact.content is not None:
                return artifact.content
            if artifact.output_path is not None:
                return str(artifact.output_path)
            return "Analysis complete but no output generated."

    return _named_tool(
        analyze_local_rdb_stream,
        "analyze_local_rdb_stream",
        (
            "Analyze local Redis RDB dump files using direct streaming and generate a report. "
            "Works for all file sizes. For large files (> 1GB) when the user declines MySQL staging, "
            "set mysql_staging_refused=true. "
            "Parameters: input_paths (comma-separated file paths), "
            "profile_name ('generic' or 'rcs'), "
            "report_language (optional BCP47 code like 'zh-CN' or 'en-US'), "
            "output_mode ('summary' or 'report'), "
            "report_format ('summary' or 'docx'), "
            "output_path (optional file path; omit output_path to use runtime default for docx), "
            "focus_prefixes (optional, comma-separated key prefixes like 'cache:*,session:*'), "
            "mysql_staging_refused (set true when user declines MySQL staging for large files)."
        ),
    )


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _make_analyze_staged_rdb_tool(
    context: ToolRuntimeContext,
    rdb_session_state: dict[str, Any],
):
    """Analyze RDB data already staged in MySQL."""
    request = context.request

    def analyze_staged_rdb(
        mysql_table: str,
        mysql_host: str = "",
        mysql_port: int | None = None,
        mysql_user: str = "",
        mysql_database: str = "",
        mysql_run_id: str = "manual",
        profile_name: str = "generic",
        report_language: str = "",
        output_mode: str = "",
        report_format: str = "",
        output_path: str = "",
        focus_prefixes: str = "",
    ) -> str:
        if rdb_session_state.get("mysql_staging_refused"):
            return _MYSQL_REFUSAL_GUARD_MESSAGE
        if not mysql_table:
            return "Error: mysql_table is required for staged analysis."
        resolved_request = _resolve_request_with_mysql_context(
            context,
            mysql_host=mysql_host,
            mysql_port=mysql_port,
            mysql_user=mysql_user,
            mysql_database=mysql_database,
            mysql_table=mysql_table,
        )
        analysis_service = _build_phase3_analysis_service_for_request(
            context,
            resolved_request,
        )
        if analysis_service is None:
            return (
                "Error: MySQL connection is not configured. "
                "Provide mysql_host/mysql_user or gather them with ask_user_for_config first."
            )

        overrides: dict[str, object] = {}
        if focus_prefixes:
            overrides["focus_prefixes"] = tuple(
                p.strip() for p in focus_prefixes.split(",") if p.strip()
            )
        elif request.rdb_overrides.focus_prefixes:
            overrides["focus_prefixes"] = request.rdb_overrides.focus_prefixes

        try:
            analyze_kwargs = {
                "prompt": request.prompt,
                "input_paths": ["mysql:staged"],
                "input_kind": "local_rdb",  # Indicates origin
                "profile_name": profile_name,
                "report_language": report_language or resolved_request.runtime_inputs.report_language,
                "path_mode": "database_backed_analysis",  # Locked to MySQL backed
                "profile_overrides": overrides,
                "mysql_host": resolved_request.runtime_inputs.mysql_host,
                "mysql_port": resolved_request.runtime_inputs.mysql_port,
                "mysql_database": resolved_request.runtime_inputs.mysql_database,
                "mysql_table": mysql_table,
                "service": analysis_service,
            }
            analysis = analyze_rdb_tool(**analyze_kwargs)
        except ValueError as exc:
            return f"Error: {exc}"

        return _render_analysis_output(
            analysis,
            runtime_inputs=resolved_request.runtime_inputs,
            output_mode=output_mode or resolved_request.runtime_inputs.output_mode or "summary",
            report_format=report_format or resolved_request.runtime_inputs.report_format or "summary",
            output_path=Path(output_path) if output_path else resolved_request.runtime_inputs.output_path,
            prompt=request.prompt or request.raw_prompt,
        )

    return _named_tool(
        analyze_staged_rdb,
        "analyze_staged_rdb",
        (
            "Analyze Redis RDB data that has been previously staged in a MySQL table. "
            "Use this AFTER stage_rdb_rows_to_mysql. "
            "Parameters: mysql_table (the staging table name), mysql_host, mysql_port, "
            "mysql_user, mysql_database, mysql_run_id, report_language, "
            "profile_name, output_mode, report_format, output_path, focus_prefixes."
        ),
    )


def _make_stage_local_rdb_to_mysql_tool(
    context: ToolRuntimeContext,
    rdb_session_state: dict[str, Any],
):
    """Stage local RDB files into MySQL for heavy-duty analysis."""
    request = context.request

    def stage_local_rdb_to_mysql(
        input_paths: str,
        mysql_table: str = "",
        mysql_host: str = "",
        mysql_port: int | None = None,
        mysql_user: str = "",
        mysql_database: str = "",
        mysql_stage_batch_size: int | None = None,
    ) -> str:
        if rdb_session_state.get("mysql_staging_refused"):
            return _MYSQL_REFUSAL_GUARD_MESSAGE
        mysql_adaptor = MySQLAdaptor()
        resolved_request = _resolve_request_with_mysql_context(
            context,
            mysql_host=mysql_host,
            mysql_port=mysql_port,
            mysql_user=mysql_user,
            mysql_database=mysql_database,
            mysql_table=mysql_table or None,
            mysql_stage_batch_size=mysql_stage_batch_size,
        )
        mysql_connection = _build_mysql_connection_from_request(
            context,
            resolved_request,
        )
        if mysql_connection is None:
            return (
                "Error: MySQL connection is not configured. "
                "Provide mysql_host/mysql_user or gather them with ask_user_for_config first."
            )

        paths = [Path(p.strip()).expanduser() for p in input_paths.split(",") if p.strip()]
        if not paths:
            return "Error: no input paths provided."

        effective_table = mysql_table or build_default_mysql_table_name()
        run_id = f"rdb_stage_{int(time.time())}"
        resolved_request = replace(
            resolved_request,
            runtime_inputs=replace(
                resolved_request.runtime_inputs,
                mysql_table=effective_table,
            ),
        )

        try:
            # Runtime interrupt_on gates this tool before execution. The plan is
            # still needed to set up the approved MySQL write session.
            plan = _plan_mysql_staging_session(
                resolved_request,
                mysql_adaptor,
                mysql_connection,
                table_name=effective_table,
            )

            # Perform the actual heavy-duty staging via the capability service.
            from dba_assistant.capabilities.redis_rdb_analysis.service import analyze_rdb as _analyze_rdb
            
            # This triggers the Path A collector internally
            _analyze_rdb(
                RdbAnalysisRequest(
                    prompt=request.prompt,
                    inputs=[SampleInput(source=p, kind=InputSourceKind.LOCAL_RDB) for p in paths],
                    profile_name="generic",
                    report_language=resolved_request.runtime_inputs.report_language,
                    path_mode="database_backed_analysis",
                    mysql_host=resolved_request.runtime_inputs.mysql_host,
                    mysql_port=resolved_request.runtime_inputs.mysql_port,
                    mysql_database=resolved_request.runtime_inputs.mysql_database,
                    mysql_table=effective_table,
                    mysql_stage_batch_size=resolved_request.runtime_inputs.mysql_stage_batch_size,
                ),
                profile=None,
                remote_discovery=lambda *_args, **_kwargs: {},
                stage_rdb_rows_to_mysql=lambda table_name, rows, **kwargs: _stage_mysql_rows_direct(
                    resolved_request,
                    mysql_adaptor,
                    mysql_connection,
                    approval_handler=None,  # Already approved by runtime interrupt_on.
                    prepared_sessions={},
                    approved_write_sessions={_mysql_session_key(mysql_connection, effective_table, run_id)},
                    table_name=table_name,
                    rows=rows,
                    source_file=kwargs.get("source_file", "manual"),
                    run_id=run_id,
                ),
                analyze_staged_rdb_rows=lambda staging, **_kwargs: None, # Don't analyze yet
            )
        except MySQLOperationError as exc:
            return _format_mysql_error(exc)
        except PermissionError as exc:
            return str(exc)
        except Exception as exc: # noqa: BLE001
            return f"Error during staging: {exc}"

        return json.dumps(
            {
                "status": "staged",
                "mysql_table": effective_table,
                "mysql_run_id": run_id,
                "message": "Data successfully staged to MySQL. Now call analyze_staged_rdb.",
            }
        )

    return _named_tool(
        stage_local_rdb_to_mysql,
        "stage_local_rdb_to_mysql",
        (
            "Stage local RDB files into MySQL for database-backed analysis. "
            "Use this for LARGE files (> 1GB). "
            "REQUIRES HUMAN APPROVAL through runtime interrupt_on. "
            "After calling this, call analyze_staged_rdb to generate the report. "
            "Parameters: input_paths (comma-separated file paths), mysql_table, mysql_host, "
            "mysql_port, mysql_user, mysql_database, mysql_stage_batch_size."
        ),
    )


def _instrument_tool(
    tool,
    *,
    event_handler: Callable[[dict[str, Any]], None] | None = None,
):
    if getattr(tool, "_dba_observed_tool", False):
        return tool

    signature = inspect.signature(tool)

    @wraps(tool)
    def wrapped_tool(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        tool_name = getattr(tool, "__name__", "tool_execution")
        if event_handler is not None:
            event_handler({"type": "tool_start", "tool_name": tool_name})
        started = time.perf_counter()
        try:
            result = observe_tool_call(
                tool_name,
                dict(bound.arguments),
                lambda: tool(*args, **kwargs),
            )
        except Exception as exc:
            if event_handler is not None:
                event_handler(
                    {
                        "type": "tool_error",
                        "tool_name": tool_name,
                        "elapsed_seconds": round(time.perf_counter() - started, 6),
                        "error": str(exc),
                    }
                )
            raise
        if event_handler is not None:
            event_handler(
                {
                    "type": "tool_end",
                    "tool_name": tool_name,
                    "elapsed_seconds": round(time.perf_counter() - started, 6),
                }
            )
        return result

    wrapped_tool.__signature__ = signature
    wrapped_tool._dba_observed_tool = True
    return wrapped_tool


def _make_analyze_preparsed_dataset_tool(
    context: ToolRuntimeContext,
    rdb_session_state: dict[str, Any],
):
    """Analyze preparsed datasets from local files or MySQL-backed sources."""
    request = context.request

    def analyze_preparsed_dataset(
        input_paths: str = "",
        mysql_table: str = "",
        mysql_query: str = "",
        mysql_host: str = "",
        mysql_port: int | None = None,
        mysql_user: str = "",
        mysql_database: str = "",
        mysql_stage_batch_size: int | None = None,
        profile_name: str = "generic",
        report_language: str = "",
        output_mode: str = "",
        report_format: str = "",
        output_path: str = "",
        focus_prefixes: str = "",
    ) -> str:
        if rdb_session_state.get("mysql_staging_refused"):
            return _MYSQL_REFUSAL_GUARD_MESSAGE
        overrides: dict[str, object] = {}
        if focus_prefixes:
            overrides["focus_prefixes"] = tuple(
                p.strip() for p in focus_prefixes.split(",") if p.strip()
            )
        elif request.rdb_overrides.focus_prefixes:
            overrides["focus_prefixes"] = request.rdb_overrides.focus_prefixes
        if request.rdb_overrides.focus_only:
            overrides["focus_only"] = True
        if request.rdb_overrides.top_n:
            overrides["top_n"] = dict(request.rdb_overrides.top_n)

        resolved_request = _resolve_request_with_mysql_context(
            context,
            mysql_host=mysql_host,
            mysql_port=mysql_port,
            mysql_user=mysql_user,
            mysql_database=mysql_database,
            mysql_table=mysql_table or None,
            mysql_query=mysql_query or None,
            mysql_stage_batch_size=mysql_stage_batch_size,
        )
        effective_mysql_table = mysql_table or resolved_request.runtime_inputs.mysql_table
        effective_mysql_query = mysql_query or resolved_request.runtime_inputs.mysql_query
        analysis_service = _build_phase3_analysis_service_for_request(
            context,
            resolved_request,
        )

        if (
            effective_mysql_table
            or effective_mysql_query
            or resolved_request.runtime_inputs.input_kind == "preparsed_mysql"
        ):
            sources = [effective_mysql_table or effective_mysql_query or "mysql:dataset"]
            input_kind = "preparsed_mysql"
        else:
            sources = [Path(p.strip()) for p in input_paths.split(",") if p.strip()]
            input_kind = resolved_request.runtime_inputs.input_kind or "precomputed"
            if not sources:
                return "Error: no preparsed dataset source provided."

        try:
            analyze_kwargs = {
                "prompt": request.prompt,
                "input_paths": sources,
                "input_kind": input_kind,
                "profile_name": profile_name,
                "report_language": report_language or resolved_request.runtime_inputs.report_language,
                "path_mode": resolved_request.runtime_inputs.path_mode or request.rdb_overrides.route_name or "auto",
                "profile_overrides": overrides,
                "mysql_host": resolved_request.runtime_inputs.mysql_host,
                "mysql_table": effective_mysql_table,
                "mysql_query": effective_mysql_query,
                "mysql_stage_batch_size": resolved_request.runtime_inputs.mysql_stage_batch_size,
                "service": analysis_service,
            }
            if _callable_accepts_keyword(analyze_rdb_tool, "mysql_port"):
                analyze_kwargs["mysql_port"] = resolved_request.runtime_inputs.mysql_port
            if resolved_request.runtime_inputs.mysql_database:
                analyze_kwargs["mysql_database"] = resolved_request.runtime_inputs.mysql_database
            analysis = analyze_rdb_tool(
                **analyze_kwargs,
            )
        except ValueError as exc:
            return f"Error: {exc}"
        except PermissionError as exc:
            return str(exc)

        return _render_analysis_output(
            analysis,
            runtime_inputs=resolved_request.runtime_inputs,
            output_mode=output_mode or resolved_request.runtime_inputs.output_mode or "summary",
            report_format=report_format or resolved_request.runtime_inputs.report_format or "summary",
            output_path=Path(output_path) if output_path else resolved_request.runtime_inputs.output_path,
            prompt=request.prompt or request.raw_prompt,
        )

    return _named_tool(
        analyze_preparsed_dataset,
        "analyze_preparsed_dataset",
        (
            "Analyze a preparsed dataset and generate a report. "
            "Supports local JSON datasets or MySQL-backed preparsed datasets. "
            "Parameters: input_paths (comma-separated local dataset paths), mysql_table, mysql_query, "
            "mysql_host, mysql_port, mysql_user, mysql_database, mysql_stage_batch_size, "
            "profile_name, report_language, output_mode, report_format, output_path, focus_prefixes."
        ),
    )


# ---------------------------------------------------------------------------
# Remote RDB discovery + HITL fetch (Phase 3 extension)
# ---------------------------------------------------------------------------

def _make_discover_remote_rdb_tool(
    context: ToolRuntimeContext,
    adaptor: RedisAdaptor,
    *,
    remote_rdb_state: dict[str, Any] | None = None,
):
    """Read-only remote RDB discovery — no approval required."""

    def discover_remote_rdb_tool(
        redis_host: str = "",
        redis_port: int | None = None,
        redis_db: int | None = None,
        remote_rdb_path: str = "",
    ) -> str:
        resolved_request, connection = _resolve_request_with_redis_connection(
            context,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
        )
        try:
            discovery = _discover_remote_rdb_snapshot_compatible(
                adaptor,
                connection,
                remote_rdb_state=remote_rdb_state,
                remote_rdb_path=remote_rdb_path or resolved_request.runtime_inputs.remote_rdb_path or "",
            )
        except RemoteRedisDiscoveryError as exc:
            return json.dumps(
                {
                    "status": "failed",
                    "error_kind": exc.kind,
                    "error_stage": exc.stage,
                    "error_message": exc.message,
                    "redis_password_supplied": "yes" if exc.redis_password_supplied else "no",
                }
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps(
                {
                    "status": "failed",
                    "error_kind": "unknown_error",
                    "error_stage": "discover_remote_rdb",
                    "error_message": str(exc),
                }
            )

        return json.dumps(
            {
                "status": "succeeded",
                "redis_host": connection.host,
                "redis_port": connection.port,
                "redis_db": connection.db,
                "redis_dir": discovery.get("redis_dir"),
                "dbfilename": discovery.get("dbfilename"),
                "rdb_path": discovery.get("rdb_path"),
                "rdb_path_source": discovery.get("rdb_path_source", "discovered"),
                "redis_password_supplied": discovery.get("redis_password_supplied", "no"),
                "lastsave": discovery.get("lastsave"),
                "bgsave_in_progress": discovery.get("bgsave_in_progress"),
                "approval_required": True,
                "next_step": (
                    "Immediately call fetch_remote_rdb_via_ssh. "
                    "Do not ask for approval in plain text; runtime interrupt_on will collect it."
                ),
            },
            default=str,
        )

    return _named_tool(
        discover_remote_rdb_tool,
        "discover_remote_rdb",
        (
            "Discover the remote Redis RDB file location and persistence status. "
            "Read-only operation — does not fetch or modify anything. "
            "Returns JSON with rdb_path, lastsave, and approval_required flag. "
            "Parameters: redis_host, redis_port, redis_db, remote_rdb_path. "
            "If a latest snapshot is required, call ensure_remote_rdb_snapshot next. "
            "After successful discovery, do NOT ask the user for approval in plain text. "
            "CLI and orchestrator runtime handle approval, not the model's free-form reply."
        ),
    )


def _make_ensure_remote_rdb_snapshot_tool(
    context: ToolRuntimeContext,
    adaptor: RedisAdaptor,
    *,
    remote_rdb_state: dict[str, Any] | None = None,
) -> Any:
    def ensure_remote_rdb_snapshot_tool(
        redis_host: str = "",
        redis_port: int | None = None,
        redis_db: int | None = None,
        remote_rdb_path: str = "",
    ) -> str:
        _, connection = _resolve_request_with_redis_connection(
            context,
            redis_host=redis_host,
            redis_port=redis_port,
            redis_db=redis_db,
        )
        try:
            discovery = _discover_remote_rdb_snapshot_compatible(
                adaptor,
                connection,
                remote_rdb_state=remote_rdb_state,
                force_refresh=True,
                remote_rdb_path=remote_rdb_path,
            )
        except RemoteRedisDiscoveryError as exc:
            return f"Remote RDB discovery failed: {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"Remote RDB discovery failed: {exc}"

        try:
            refreshed = ensure_remote_rdb_snapshot_state(
                adaptor,
                connection,
                discovery=discovery,
                remote_rdb_state=remote_rdb_state,
            )
        except Exception as exc:  # noqa: BLE001
            return f"Latest remote RDB snapshot failed: {exc}"

        path_plan = resolve_remote_rdb_fetch_plan(
            refreshed,
            remote_rdb_path=remote_rdb_path,
        )
        return json.dumps(
            {
                "status": "succeeded",
                "redis_host": connection.host,
                "redis_port": connection.port,
                "redis_db": connection.db,
                "redis_dir": refreshed.get("redis_dir"),
                "dbfilename": refreshed.get("dbfilename"),
                "rdb_path": path_plan["remote_rdb_path"],
                "rdb_path_source": path_plan["remote_rdb_path_source"],
                "lastsave": refreshed.get("lastsave"),
                "bgsave_in_progress": refreshed.get("bgsave_in_progress"),
                "approval_required": True,
                "next_step": "Call fetch_remote_rdb_via_ssh with rdb_path, ssh_host, and ssh_username.",
            },
            default=str,
        )

    return _named_tool(
        ensure_remote_rdb_snapshot_tool,
        "ensure_remote_rdb_snapshot",
        (
            "Trigger a fresh Redis RDB snapshot via BGSAVE and wait until it completes. "
            "REQUIRES HUMAN APPROVAL because it modifies remote Redis persistence state. "
            "Parameters: redis_host, redis_port, redis_db, remote_rdb_path."
        ),
    )


def _make_fetch_remote_rdb_via_ssh_tool(
    context: ToolRuntimeContext,
) -> Any:
    def fetch_remote_rdb_via_ssh(
        remote_rdb_path: str,
        ssh_host: str = "",
        ssh_port: int | None = None,
        ssh_username: str = "",
        local_directory: str = "",
    ) -> str:
        if not remote_rdb_path.strip():
            return "Error: remote_rdb_path is required before SSH fetch."
        resolved_request = _resolve_request_with_ssh_context(
            context,
            ssh_host=ssh_host,
            ssh_port=ssh_port,
            ssh_username=ssh_username,
        )
        fetched_path = _fetch_remote_rdb_via_ssh(
            request=resolved_request,
            remote_rdb_path=remote_rdb_path,
            local_directory=local_directory,
            default_directory=resolved_request.runtime_inputs.evidence_dir,
        )
        return str(fetched_path)

    return _named_tool(
        fetch_remote_rdb_via_ssh,
        "fetch_remote_rdb_via_ssh",
        (
            "Fetch a remote Redis RDB over SSH and store it in a local temporary artifact. "
            "REQUIRES HUMAN APPROVAL before proceeding. "
            "Use after discover_remote_rdb and ensure_remote_rdb_snapshot when a fresh snapshot is needed. "
            "Call this directly when remote RDB retrieval is needed; do not ask for plain-text approval first. "
            "Approval is collected by runtime interrupt_on, not by conversational follow-up. "
            "Parameters: remote_rdb_path, ssh_host, ssh_port, ssh_username, local_directory. "
            "SSH credentials come from shared request context only."
        ),
    )


# ---------------------------------------------------------------------------
# MySQL tools (Phase 3.2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MySQLStagingTargetPlan:
    database_name: str
    table_name: str
    defaulted_database: bool
    defaulted_table: bool
    will_create_database: bool
    will_create_table: bool

def _make_mysql_tools(
    context: ToolRuntimeContext,
) -> list:
    """Build the MySQL capability tools."""
    prepared_sessions: dict[tuple[str, int, str, str, str], MySQLStagingSession] = {}
    approved_write_sessions: set[tuple[str, int, str, str, str]] = set()
    adaptor = MySQLAdaptor()

    def mysql_read_query(
        sql: str,
        mysql_host: str = "",
        mysql_port: int | None = None,
        mysql_user: str = "",
        mysql_database: str = "",
    ) -> str:
        resolved_request = _resolve_request_with_mysql_context(
            context,
            mysql_host=mysql_host,
            mysql_port=mysql_port,
            mysql_user=mysql_user,
            mysql_database=mysql_database,
        )
        config = _build_mysql_connection_from_request(context, resolved_request)
        if config is None:
            return (
                "Error: MySQL connection is not configured. "
                "Provide mysql_host/mysql_user or gather them with ask_user_for_config first."
            )
        try:
            return _mysql_read(adaptor, config, sql)
        except MySQLOperationError as exc:
            return _format_mysql_error(exc)

    def load_preparsed_dataset_from_mysql(
        table_name: str,
        limit: str = "100000",
        mysql_host: str = "",
        mysql_port: int | None = None,
        mysql_user: str = "",
        mysql_database: str = "",
    ) -> str:
        resolved_request = _resolve_request_with_mysql_context(
            context,
            mysql_host=mysql_host,
            mysql_port=mysql_port,
            mysql_user=mysql_user,
            mysql_database=mysql_database,
            mysql_table=table_name,
        )
        config = _build_mysql_connection_from_request(context, resolved_request)
        if config is None:
            return (
                "Error: MySQL connection is not configured. "
                "Provide mysql_host/mysql_user or gather them with ask_user_for_config first."
            )
        try:
            return _load_dataset(adaptor, config, table_name, limit=limit)
        except MySQLOperationError as exc:
            return _format_mysql_error(exc)

    def stage_rdb_rows_to_mysql(
        table_name: str,
        rows_json: str,
        source_file: str = "manual",
        run_id: str = "manual",
        batch_number: int | None = None,
        cumulative_rows: int | None = None,
        mysql_host: str = "",
        mysql_port: int | None = None,
        mysql_user: str = "",
        mysql_database: str = "",
    ) -> str:
        resolved_request = _resolve_request_with_mysql_context(
            context,
            mysql_host=mysql_host,
            mysql_port=mysql_port,
            mysql_user=mysql_user,
            mysql_database=mysql_database,
            mysql_table=table_name or None,
        )
        config = _build_mysql_connection_from_request(context, resolved_request)
        if config is None:
            return (
                "Error: MySQL connection is not configured. "
                "Provide mysql_host/mysql_user or gather them with ask_user_for_config first."
            )
        rows = json.loads(rows_json)
        effective_table = table_name or build_default_mysql_table_name()
        effective_batch_size = _effective_mysql_stage_batch_size(resolved_request)
        session_key = _mysql_session_key(config, effective_table, run_id)
        session = prepared_sessions.get(session_key)
        try:
            if session is None:
                plan = _plan_mysql_staging_session(
                    resolved_request,
                    adaptor,
                    config,
                    table_name=effective_table,
                )
                if session_key not in approved_write_sessions:
                    _request_mysql_staging_approval(
                        resolved_request,
                        approval_handler=context.approval_handler,
                        plan=plan,
                        row_count=len(rows),
                        batch_size=effective_batch_size,
                    )
                    approved_write_sessions.add(session_key)
                session = _prepare_mysql_staging_session(
                    adaptor,
                    config,
                    plan=plan,
                    run_id=run_id,
                    batch_size=effective_batch_size,
                )
                prepared_sessions[session_key] = session
            count = _call_insert_staging_batch(
                _insert_staging_batch,
                adaptor,
                session,
                source_file=source_file or "manual",
                rows=rows,
                batch_number=batch_number,
                cumulative_rows=cumulative_rows,
            )
        except MySQLOperationError as exc:
            return _format_mysql_error(exc)
        return json.dumps(
            {
                "staged": count,
                "table": session.table_name,
                "database": session.database_name,
                "mysql_host": config.host,
                "mysql_port": config.port,
                "run_id": session.run_id,
                "source_file": source_file or "manual",
                "created_database": session.created_database,
                "created_table": session.created_table,
                "defaulted_database": session.defaulted_database,
                "defaulted_table": session.defaulted_table,
                "cleanup_mode": session.cleanup_mode,
                "mysql_stage_batch_size": session.batch_size,
            }
        )

    return [
        _named_tool(
            mysql_read_query,
            "mysql_read_query",
            "Execute a bounded read-only SQL query against MySQL and return the result as JSON. "
            "Parameters: sql, mysql_host, mysql_port, mysql_user, mysql_database.",
        ),
        _named_tool(
            load_preparsed_dataset_from_mysql,
            "load_preparsed_dataset_from_mysql",
            "Load a preparsed dataset from a MySQL table and return it as JSON. "
            "Parameters: table_name, limit, mysql_host, mysql_port, mysql_user, mysql_database.",
        ),
        _named_tool(
            stage_rdb_rows_to_mysql,
            "stage_rdb_rows_to_mysql",
            "Stage parsed RDB rows into a MySQL table for database-backed aggregation. "
            "REQUIRES HUMAN APPROVAL — this is a write operation. "
            "Call this directly when staging is required; approval is collected by the shared human approval handler. "
            "Parameters: table_name, rows_json, mysql_host, mysql_port, mysql_user, mysql_database.",
        ),
    ]


def _resolve_request_with_redis_connection(
    context: ToolRuntimeContext,
    *,
    redis_host: str = "",
    redis_port: int | None = None,
    redis_db: int | None = None,
) -> tuple[NormalizedRequest, RedisConnectionConfig]:
    request = context.request
    default_connection = context.default_redis_connection
    host = (
        redis_host.strip()
        or request.runtime_inputs.redis_host
        or (default_connection.host if default_connection is not None else "")
        or DEFAULT_LOOPBACK_HOST
    )
    port = int(
        redis_port
        if redis_port is not None
        else request.runtime_inputs.redis_port
        if request.runtime_inputs.redis_port is not None
        else default_connection.port
        if default_connection is not None
        else DEFAULT_REDIS_PORT
    )
    db = int(
        redis_db
        if redis_db is not None
        else request.runtime_inputs.redis_db
        if request.runtime_inputs.redis_db is not None
        else default_connection.db
        if default_connection is not None
        else DEFAULT_REDIS_DB
    )
    resolved_request = replace(
        request,
        runtime_inputs=replace(
            request.runtime_inputs,
            redis_host=host,
            redis_port=port,
            redis_db=db,
        ),
    )
    connection = RedisConnectionConfig(
        host=host,
        port=port,
        db=db,
        password=request.secrets.redis_password
        or (default_connection.password if default_connection is not None else None),
        socket_timeout=(
            default_connection.socket_timeout
            if default_connection is not None and default_connection.socket_timeout is not None
            else context.redis_socket_timeout
        ),
    )
    return resolved_request, connection


def _resolve_request_with_mysql_context(
    context: ToolRuntimeContext,
    *,
    mysql_host: str = "",
    mysql_port: int | None = None,
    mysql_user: str = "",
    mysql_database: str = "",
    mysql_table: str | None = None,
    mysql_query: str | None = None,
    mysql_stage_batch_size: int | None = None,
) -> NormalizedRequest:
    request = context.request
    default_connection = context.default_mysql_connection
    resolved_port = int(
        mysql_port
        if mysql_port is not None
        else request.runtime_inputs.mysql_port
        if request.runtime_inputs.mysql_port is not None
        else default_connection.port
        if default_connection is not None
        else DEFAULT_MYSQL_PORT
    )
    runtime_updates: dict[str, object] = {
        "mysql_host": mysql_host.strip()
        or request.runtime_inputs.mysql_host
        or (default_connection.host if default_connection is not None else None)
        or DEFAULT_LOOPBACK_HOST,
        "mysql_port": resolved_port,
        "mysql_user": mysql_user.strip()
        or request.runtime_inputs.mysql_user
        or (default_connection.user if default_connection is not None else None)
        or DEFAULT_MYSQL_USER,
        "mysql_database": mysql_database.strip()
        or request.runtime_inputs.mysql_database
        or (default_connection.database if default_connection is not None else None)
        or DEFAULT_MYSQL_DATABASE,
    }
    if mysql_table is not None:
        runtime_updates["mysql_table"] = mysql_table or None
    if mysql_query is not None:
        runtime_updates["mysql_query"] = mysql_query or None
    if mysql_stage_batch_size is not None:
        runtime_updates["mysql_stage_batch_size"] = mysql_stage_batch_size
    return replace(
        request,
        runtime_inputs=replace(
            request.runtime_inputs,
            **runtime_updates,
        ),
    )


def _build_mysql_connection_from_request(
    context: ToolRuntimeContext,
    request: NormalizedRequest,
) -> MySQLConnectionConfig | None:
    default_connection = context.default_mysql_connection
    runtime = request.runtime_inputs
    host = runtime.mysql_host or (default_connection.host if default_connection is not None else None)
    if not host:
        return None
    return MySQLConnectionConfig(
        host=host,
        port=runtime.mysql_port or (default_connection.port if default_connection is not None else DEFAULT_MYSQL_PORT),
        user=runtime.mysql_user or (default_connection.user if default_connection is not None else DEFAULT_MYSQL_USER),
        password=request.secrets.mysql_password or (default_connection.password if default_connection is not None else ""),
        database=runtime.mysql_database or (default_connection.database if default_connection is not None else DEFAULT_MYSQL_DATABASE),
        connect_timeout_seconds=context.mysql_connect_timeout_seconds,
        read_timeout_seconds=context.mysql_read_timeout_seconds,
        write_timeout_seconds=context.mysql_write_timeout_seconds,
    )


def _resolve_request_with_ssh_context(
    context: ToolRuntimeContext,
    *,
    ssh_host: str = "",
    ssh_port: int | None = None,
    ssh_username: str = "",
    fallback_host: str = "",
) -> NormalizedRequest:
    request = context.request
    host = (
        ssh_host.strip()
        or request.runtime_inputs.ssh_host
        or fallback_host.strip()
        or request.runtime_inputs.redis_host
        or (context.default_redis_connection.host if context.default_redis_connection is not None else "")
    )
    username = ssh_username.strip() or request.runtime_inputs.ssh_username or ""
    if not host:
        raise ValueError("ssh_host is required. Ask the user for SSH host if it is missing.")
    if not username:
        raise ValueError("ssh_username is required. Ask the user for SSH username if it is missing.")
    resolved_port = int(ssh_port if ssh_port is not None else request.runtime_inputs.ssh_port or 22)
    return replace(
        request,
        runtime_inputs=replace(
            request.runtime_inputs,
            ssh_host=host,
            ssh_port=resolved_port,
            ssh_username=username,
        ),
    )


def _build_ssh_connection_from_request(request: NormalizedRequest) -> SSHConnectionConfig:
    if not request.runtime_inputs.ssh_host:
        raise ValueError("ssh_host is required before SSH fetch.")
    if not request.runtime_inputs.ssh_username:
        raise ValueError("ssh_username is required before SSH fetch.")
    if not request.secrets.ssh_password:
        raise ValueError("ssh_password is missing. Ask the user for it with secure input.")
    return SSHConnectionConfig(
        host=request.runtime_inputs.ssh_host,
        port=int(request.runtime_inputs.ssh_port or 22),
        username=request.runtime_inputs.ssh_username,
        password=request.secrets.ssh_password,
    )


def _build_phase3_analysis_service_for_request(
    context: ToolRuntimeContext,
    request: NormalizedRequest,
):
    mysql_connection = _build_mysql_connection_from_request(context, request)
    if mysql_connection is None:
        return None
    return _make_phase3_analysis_service(
        request=request,
        mysql_adaptor=MySQLAdaptor(),
        mysql_connection=mysql_connection,
        approval_handler=context.approval_handler,
    )


def _mysql_session_key(
    connection: MySQLConnectionConfig,
    table_name: str,
    run_id: str,
) -> tuple[str, int, str, str, str]:
    return (
        connection.host,
        connection.port,
        connection.database or DEFAULT_MYSQL_DATABASE,
        table_name,
        run_id,
    )


def _redis_cache_key(connection: RedisConnectionConfig) -> tuple[str, int, int]:
    return (connection.host, connection.port, connection.db)


def _make_phase3_analysis_service(
    *,
    request: NormalizedRequest,
    mysql_adaptor: MySQLAdaptor | None,
    mysql_connection: MySQLConnectionConfig | None,
    approval_handler: HumanApprovalHandler | None,
):
    if mysql_adaptor is None or mysql_connection is None:
        return None
    normalized_request = request
    prepared_sessions: dict[tuple[str, int, str, str, str], MySQLStagingSession] = {}
    approved_write_sessions: set[tuple[str, int, str, str, str]] = set()

    def run_analysis(analysis_request):
        from dba_assistant.capabilities.redis_rdb_analysis.service import analyze_rdb as _analyze_rdb

        return _analyze_rdb(
            analysis_request,
            profile=None,
            remote_discovery=lambda *_args, **_kwargs: {},
            mysql_read_query=lambda sql: mysql_adaptor.read_query(mysql_connection, sql),
            stage_rdb_rows_to_mysql=lambda table_name, rows, *, source_file="manual", run_id="manual", batch_number=None, cumulative_rows=None: _stage_mysql_rows_direct(
                normalized_request,
                mysql_adaptor,
                mysql_connection,
                approval_handler=approval_handler,
                prepared_sessions=prepared_sessions,
                approved_write_sessions=approved_write_sessions,
                table_name=table_name,
                rows=rows,
                source_file=source_file,
                run_id=run_id,
                batch_number=batch_number,
                cumulative_rows=cumulative_rows,
            ),
            analyze_staged_rdb_rows=lambda staging, *, profile, sample_rows: _analyze_staged(
                mysql_adaptor,
                prepared_sessions[_mysql_session_key(
                    mysql_connection,
                    staging.table_name,
                    staging.run_id,
                )],
                profile=profile,
                sample_rows=sample_rows,
            ),
            load_preparsed_dataset_from_mysql=lambda table_name: json.loads(
                _load_dataset(mysql_adaptor, mysql_connection, table_name)
            ),
        )

    return run_analysis


def _fetch_remote_rdb_via_ssh(
    *,
    request: NormalizedRequest,
    remote_rdb_path: str,
    local_directory: str = "",
    default_directory: Path | None = None,
) -> Path | str:
    target_path = remote_rdb_path.strip()
    if not target_path:
        return "Remote RDB path is required before SSH fetch."

    ssh_config = _build_ssh_connection_from_request(request)
    local_dir = (
        Path(local_directory).expanduser()
        if local_directory.strip()
        else make_runtime_work_dir(
            default_directory or request.runtime_inputs.evidence_dir or DEFAULT_EVIDENCE_DIR,
            prefix="remote-rdb-",
        )
    )
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / Path(target_path).name

    try:
        return SSHAdaptor().fetch_file(ssh_config, target_path, local_path)
    except Exception as exc:  # noqa: BLE001
        return f"Remote RDB fetch failed: {exc}"


def discover_remote_rdb_snapshot(
    adaptor: RedisAdaptor,
    connection: RedisConnectionConfig,
    *,
    remote_rdb_state: dict[str, Any] | None = None,
    force_refresh: bool = False,
    remote_rdb_path: str = "",
) -> dict[str, object]:
    cache_key = _redis_cache_key(connection)
    if remote_rdb_state is not None and not force_refresh:
        cached = remote_rdb_state.get(cache_key)
        if isinstance(cached, dict):
            return cached

    discovery = discover_remote_rdb(adaptor, connection)
    path_plan = resolve_remote_rdb_fetch_plan(discovery, remote_rdb_path=remote_rdb_path)
    discovery = {
        **discovery,
        "rdb_path": path_plan["remote_rdb_path"],
        "rdb_path_source": path_plan["remote_rdb_path_source"],
    }
    if remote_rdb_state is not None:
        remote_rdb_state[cache_key] = discovery
    return discovery


def _discover_remote_rdb_snapshot_compatible(
    adaptor: RedisAdaptor,
    connection: RedisConnectionConfig,
    *,
    remote_rdb_state: dict[str, Any] | None = None,
    force_refresh: bool = False,
    remote_rdb_path: str = "",
) -> dict[str, object]:
    try:
        return discover_remote_rdb_snapshot(
            adaptor,
            connection,
            remote_rdb_state=remote_rdb_state,
            force_refresh=force_refresh,
            remote_rdb_path=remote_rdb_path,
        )
    except TypeError as exc:
        if "remote_rdb_path" not in str(exc) and "force_refresh" not in str(exc):
            raise
        return discover_remote_rdb_snapshot(
            adaptor,
            connection,
            remote_rdb_state=remote_rdb_state,
        )


def resolve_remote_rdb_fetch_plan(
    discovery: dict[str, object] | None,
    *,
    remote_rdb_path: str = "",
) -> dict[str, str]:
    override_path = str(remote_rdb_path or "").strip()
    if override_path:
        return {
            "remote_rdb_path": override_path,
            "remote_rdb_path_source": "user_override",
        }

    discovered_path = str((discovery or {}).get("rdb_path") or "").strip()
    discovered_source = str((discovery or {}).get("rdb_path_source") or "discovered").strip()
    if discovered_path:
        return {
            "remote_rdb_path": discovered_path,
            "remote_rdb_path_source": discovered_source or "discovered",
        }

    return {
        "remote_rdb_path": "",
        "remote_rdb_path_source": "unresolved",
    }


def resolve_remote_rdb_acquisition_plan(
    discovery: dict[str, object] | None,
    *,
    acquisition_mode: str = "existing",
    remote_rdb_path: str = "",
) -> dict[str, str]:
    mode = (acquisition_mode or "").strip() or "existing"
    if mode not in {"existing", "fresh_snapshot"}:
        mode = "existing"
    path_plan = resolve_remote_rdb_fetch_plan(discovery, remote_rdb_path=remote_rdb_path)
    return {
        "acquisition_mode": mode,
        "bgsave_required": "yes" if mode == "fresh_snapshot" else "no",
        "redis_dir": str((discovery or {}).get("redis_dir") or "").strip(),
        "dbfilename": str((discovery or {}).get("dbfilename") or "").strip(),
        **path_plan,
    }


def ensure_remote_rdb_snapshot_state(
    adaptor: RedisAdaptor,
    connection: RedisConnectionConfig,
    *,
    discovery: dict[str, object],
    remote_rdb_state: dict[str, Any] | None,
    poll_interval_seconds: float = 0.2,
    max_attempts: int = 150,
) -> dict[str, object]:
    previous_lastsave = _coerce_int(discovery.get("lastsave"))
    already_in_progress = bool(discovery.get("bgsave_in_progress"))
    if not already_in_progress:
        bgsave = adaptor.bgsave(connection)
        _assert_adaptor_probe_success(bgsave, stage="bgsave")
    persistence = _wait_for_bgsave_completion(
        adaptor,
        connection,
        previous_lastsave=previous_lastsave,
        poll_interval_seconds=poll_interval_seconds,
        max_attempts=max_attempts,
    )
    refreshed = {
        **discovery,
        "lastsave": persistence.get("lastsave"),
        "bgsave_in_progress": persistence.get("bgsave_in_progress"),
    }
    if remote_rdb_state is not None:
        remote_rdb_state[_redis_cache_key(connection)] = refreshed
    return refreshed


def _wait_for_bgsave_completion(
    adaptor: RedisAdaptor,
    connection: RedisConnectionConfig,
    *,
    previous_lastsave: int | None,
    poll_interval_seconds: float,
    max_attempts: int,
) -> dict[str, object]:
    saw_in_progress = False
    for _ in range(max_attempts):
        persistence = adaptor.info(connection, section="persistence")
        _assert_adaptor_probe_success(persistence, stage="info(persistence)")
        in_progress = bool(persistence.get("rdb_bgsave_in_progress"))
        lastsave = _coerce_int(persistence.get("rdb_last_save_time"))
        saw_in_progress = saw_in_progress or in_progress
        if not in_progress and (
            previous_lastsave is None
            or lastsave is None
            or lastsave > previous_lastsave
            or saw_in_progress
        ):
            return {
                "lastsave": lastsave,
                "bgsave_in_progress": persistence.get("rdb_bgsave_in_progress"),
            }
        time.sleep(poll_interval_seconds)
    raise TimeoutError("Timed out waiting for Redis BGSAVE to complete.")


def _coerce_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _assert_adaptor_probe_success(response: object, *, stage: str) -> None:
    if not isinstance(response, dict):
        raise RuntimeError(f"Redis {stage} returned a non-dictionary payload.")
    if response.get("available") is False:
        error = response.get("error")
        if isinstance(error, dict):
            kind = str(error.get("kind") or "unknown_error")
            message = str(error.get("message") or "No error message returned by Redis.")
            raise RuntimeError(f"{kind}: {message}")
        raise RuntimeError(f"Redis {stage} reported failure without error details.")


def _render_remote_rdb_analysis(
    *,
    request: NormalizedRequest,
    local_path: Path,
    connection: RedisConnectionConfig,
    profile_name: str,
    output_mode: str,
    report_format: str,
    output_path: str,
    analysis_service,
) -> str:
    overrides: dict[str, object] = {}
    if request.rdb_overrides.focus_prefixes:
        overrides["focus_prefixes"] = request.rdb_overrides.focus_prefixes
    if request.rdb_overrides.focus_only:
        overrides["focus_only"] = True
    if request.rdb_overrides.top_n:
        overrides["top_n"] = dict(request.rdb_overrides.top_n)

    try:
        analyze_kwargs = {
            "prompt": request.prompt,
            "input_paths": [local_path],
            "input_kind": "local_rdb",
            "profile_name": profile_name,
            "report_language": request.runtime_inputs.report_language,
            "path_mode": request.runtime_inputs.path_mode or request.rdb_overrides.route_name or "auto",
            "profile_overrides": overrides,
            "mysql_host": request.runtime_inputs.mysql_host,
            "mysql_database": request.runtime_inputs.mysql_database,
            "mysql_stage_batch_size": request.runtime_inputs.mysql_stage_batch_size,
            "service": analysis_service,
        }
        if _callable_accepts_keyword(analyze_rdb_tool, "mysql_port"):
            analyze_kwargs["mysql_port"] = request.runtime_inputs.mysql_port
        analysis = analyze_rdb_tool(**analyze_kwargs)
    except ValueError as exc:
        return f"Error: {exc}"
    except PermissionError as exc:
        return str(exc)

    from dba_assistant.core.reporter.generate_analysis_report import (
        generate_analysis_report as _generate,
    )

    runtime_inputs = ensure_report_output_path(
        replace(
            request.runtime_inputs,
            output_mode=output_mode,
            report_format=report_format,
            output_path=Path(output_path) if output_path else request.runtime_inputs.output_path,
        ),
        report_format,
    )
    fmt = ReportFormat.SUMMARY if report_format == "summary" else ReportFormat.DOCX
    out = runtime_inputs.output_path
    if fmt is ReportFormat.DOCX and out is None:
        return "Error: DOCX output requires an output path."

    config = ReportOutputConfig(
        mode=OutputMode.SUMMARY if output_mode == "summary" else OutputMode.REPORT,
        format=fmt,
        output_path=out,
        template_name="rdb-analysis",
        language=runtime_inputs.report_language,
    )
    artifact = _generate(analysis, config)
    if artifact.content is not None:
        return _append_mysql_runtime_note(artifact.content, analysis=analysis)
    if artifact.output_path is not None:
        return str(artifact.output_path)
    return "Analysis complete but no output generated."


def _request_mysql_staging_approval(
    request: NormalizedRequest,
    *,
    approval_handler: HumanApprovalHandler | None,
    plan: MySQLStagingTargetPlan,
    row_count: int,
    batch_size: int,
) -> None:
    if approval_handler is None:
        raise PermissionError("MySQL staging requires an approval handler.")

    host = request.runtime_inputs.mysql_host or "127.0.0.1"
    port = request.runtime_inputs.mysql_port
    lines = [
        "MySQL-backed staging requires human approval.",
        f"Target: {host}:{port}/{plan.database_name}.{plan.table_name}",
        f"Batch size: {batch_size}",
        "会写入 staging rows。",
    ]
    if plan.will_create_database:
        lines.append("如果数据库不存在，会创建数据库。")
    if plan.will_create_table:
        lines.append("如果表不存在，会创建表。")

    approval_request = ApprovalRequest(
        action="stage_rdb_rows_to_mysql",
        message="\n".join(lines),
        details={
            "mysql_host": host,
            "mysql_port": port,
            "mysql_database": plan.database_name,
            "mysql_table": plan.table_name,
            "row_count": row_count,
            "mysql_stage_batch_size": batch_size,
            "session_scope": "mysql_staging_session",
            "will_create_database": "yes" if plan.will_create_database else "no",
            "will_create_table": "yes" if plan.will_create_table else "no",
            "defaulted_database": "yes" if plan.defaulted_database else "no",
            "defaulted_table": "yes" if plan.defaulted_table else "no",
        },
    )
    response = approval_handler.request_approval(approval_request)
    if response.status is not ApprovalStatus.APPROVED:
        raise PermissionError(
            "Operation denied by user: refused MySQL staging write session for "
            f"{plan.database_name}.{plan.table_name}."
        )


def _plan_mysql_staging_session(
    request: NormalizedRequest,
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    *,
    table_name: str,
) -> MySQLStagingTargetPlan:
    database_name = request.runtime_inputs.mysql_database or config.database or DEFAULT_MYSQL_DATABASE
    defaulted_database = not bool(request.runtime_inputs.mysql_database)
    defaulted_table = not bool(request.runtime_inputs.mysql_table)
    admin_config = replace(config, database=None)
    database_exists = _database_exists(adaptor, admin_config, database_name)
    database_config = replace(config, database=database_name)
    table_exists = database_exists and _table_exists(adaptor, database_config, table_name)

    return MySQLStagingTargetPlan(
        database_name=database_name,
        table_name=table_name,
        defaulted_database=defaulted_database,
        defaulted_table=defaulted_table,
        will_create_database=not database_exists,
        will_create_table=not table_exists,
    )


def _prepare_mysql_staging_session(
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    *,
    plan: MySQLStagingTargetPlan,
    run_id: str,
    batch_size: int,
) -> MySQLStagingSession:
    admin_config = replace(config, database=None)
    database_created = False
    table_created = False
    session_started = time.perf_counter()

    _log_mysql_staging_phase(
        config=config,
        database_name=plan.database_name,
        table_name=plan.table_name,
        mysql_stage_batch_size=batch_size,
        stage="session_start",
        elapsed_seconds=0.0,
        run_id=run_id,
    )

    if plan.will_create_database:
        create_database_started = time.perf_counter()
        _log_mysql_staging_phase(
            config=config,
            database_name=plan.database_name,
            table_name=plan.table_name,
            mysql_stage_batch_size=batch_size,
            stage="create_database_start",
            elapsed_seconds=round(create_database_started - session_started, 6),
            run_id=run_id,
        )
        try:
            _create_database(adaptor, admin_config, plan.database_name)
            database_created = True
        except Exception as exc:  # noqa: BLE001
            _log_mysql_staging_phase(
                config=config,
                database_name=plan.database_name,
                table_name=plan.table_name,
                mysql_stage_batch_size=batch_size,
                stage="create_database_error",
                elapsed_seconds=round(time.perf_counter() - session_started, 6),
                run_id=run_id,
                error=str(exc),
            )
            raise
        _log_mysql_staging_phase(
            config=config,
            database_name=plan.database_name,
            table_name=plan.table_name,
            mysql_stage_batch_size=batch_size,
            stage="create_database_end",
            elapsed_seconds=round(time.perf_counter() - create_database_started, 6),
            run_id=run_id,
        )

    database_config = replace(config, database=plan.database_name)
    if plan.will_create_table:
        create_table_started = time.perf_counter()
        _log_mysql_staging_phase(
            config=config,
            database_name=plan.database_name,
            table_name=plan.table_name,
            mysql_stage_batch_size=batch_size,
            stage="create_table_start",
            elapsed_seconds=round(create_table_started - session_started, 6),
            run_id=run_id,
        )
        try:
            _create_staging_table(adaptor, database_config, plan.table_name)
            table_created = True
        except Exception as exc:  # noqa: BLE001
            _log_mysql_staging_phase(
                config=config,
                database_name=plan.database_name,
                table_name=plan.table_name,
                mysql_stage_batch_size=batch_size,
                stage="create_table_error",
                elapsed_seconds=round(time.perf_counter() - session_started, 6),
                run_id=run_id,
                error=str(exc),
            )
            raise
        _log_mysql_staging_phase(
            config=config,
            database_name=plan.database_name,
            table_name=plan.table_name,
            mysql_stage_batch_size=batch_size,
            stage="create_table_end",
            elapsed_seconds=round(time.perf_counter() - create_table_started, 6),
            run_id=run_id,
        )

    _log_mysql_staging_phase(
        config=config,
        database_name=plan.database_name,
        table_name=plan.table_name,
        mysql_stage_batch_size=batch_size,
        stage="session_ready",
        elapsed_seconds=round(time.perf_counter() - session_started, 6),
        run_id=run_id,
    )

    return MySQLStagingSession(
        connection=database_config,
        database_name=plan.database_name,
        table_name=plan.table_name,
        run_id=run_id,
        batch_size=batch_size,
        created_database=database_created,
        created_table=table_created,
        defaulted_database=plan.defaulted_database,
        defaulted_table=plan.defaulted_table,
        cleanup_mode="retain",
    )


def _stage_mysql_rows_direct(
    request: NormalizedRequest,
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    *,
    approval_handler: HumanApprovalHandler | None,
    prepared_sessions: dict[tuple[str, int, str, str, str], MySQLStagingSession],
    approved_write_sessions: set[tuple[str, int, str, str, str]],
    table_name: str,
    rows: list[dict[str, object]],
    source_file: str,
    run_id: str,
    batch_number: int | None = None,
    cumulative_rows: int | None = None,
) -> dict[str, object]:
    effective_table = table_name or request.runtime_inputs.mysql_table or build_default_mysql_table_name()
    effective_batch_size = _effective_mysql_stage_batch_size(request)
    session_key = _mysql_session_key(config, effective_table, run_id)
    session = prepared_sessions.get(session_key)
    if session is None:
        plan = _plan_mysql_staging_session(
            request,
            adaptor,
            config,
            table_name=effective_table,
        )
        if session_key not in approved_write_sessions:
            _request_mysql_staging_approval(
                request,
                approval_handler=approval_handler,
                plan=plan,
                row_count=len(rows),
                batch_size=effective_batch_size,
            )
            approved_write_sessions.add(session_key)
        session = _prepare_mysql_staging_session(
            adaptor,
            config,
            plan=plan,
            run_id=run_id,
            batch_size=effective_batch_size,
        )
        prepared_sessions[session_key] = session
    staged = _call_insert_staging_batch(
        _insert_staging_batch,
        adaptor,
        session,
        source_file=source_file,
        rows=rows,
        batch_number=batch_number,
        cumulative_rows=cumulative_rows,
    )
    return {
        "staged": staged,
        "table": session.table_name,
        "database": session.database_name,
        "mysql_host": request.runtime_inputs.effective_mysql_host(),
        "mysql_port": request.runtime_inputs.mysql_port,
        "run_id": session.run_id,
        "created_database": session.created_database,
        "created_table": session.created_table,
        "defaulted_database": session.defaulted_database,
        "defaulted_table": session.defaulted_table,
        "cleanup_mode": session.cleanup_mode,
        "mysql_stage_batch_size": session.batch_size,
    }


def _log_mysql_staging_phase(
    *,
    config: MySQLConnectionConfig,
    database_name: str,
    table_name: str,
    mysql_stage_batch_size: int,
    stage: str,
    elapsed_seconds: float,
    run_id: str,
    error: str | None = None,
) -> None:
    logger.info(
        "mysql staging phase",
        extra={
            "event_name": "mysql_staging_phase",
            "stage": stage,
            "mysql_host": config.host,
            "mysql_port": config.port,
            "mysql_database": database_name,
            "mysql_table": table_name,
            "mysql_stage_batch_size": mysql_stage_batch_size,
            "batch_number": None,
            "batch_rows": None,
            "cumulative_rows": None,
            "elapsed_seconds": elapsed_seconds,
            "run_id": run_id,
            "error": error,
        },
    )
    return None


def _call_insert_staging_batch(
    insert_staging_batch_fn,
    adaptor: MySQLAdaptor,
    session: MySQLStagingSession,
    *,
    source_file: str,
    rows: list[dict[str, object]],
    batch_number: int | None,
    cumulative_rows: int | None,
) -> int:
    kwargs: dict[str, object] = {
        "source_file": source_file,
        "rows": rows,
    }
    if _callable_accepts_keyword(insert_staging_batch_fn, "batch_number"):
        kwargs["batch_number"] = batch_number
    if _callable_accepts_keyword(insert_staging_batch_fn, "cumulative_rows"):
        kwargs["cumulative_rows"] = cumulative_rows
    return insert_staging_batch_fn(adaptor, session, **kwargs)


def _callable_accepts_keyword(func: Any, keyword: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            return True
    return keyword in signature.parameters


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _effective_mysql_stage_batch_size(request: NormalizedRequest) -> int:
    return request.runtime_inputs.effective_mysql_stage_batch_size()
