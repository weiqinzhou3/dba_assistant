from __future__ import annotations

from contextlib import AbstractContextManager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
import traceback
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, TypeVar
from uuid import uuid4

from dba_assistant.application.request_models import NormalizedRequest
from dba_assistant.core.observability.bootstrap import get_audit_recorder
from dba_assistant.core.observability.sanitizer import sanitize_mapping, sanitize_value, summarize_prompt
from dba_assistant.interface.types import InterfaceSurface


T = TypeVar("T")

_CURRENT_SESSION: ContextVar["ExecutionSession | None"] = ContextVar(
    "dba_assistant_execution_session",
    default=None,
)


@dataclass(frozen=True)
class ArtifactRecord:
    output_mode: str
    output_path: str | None
    artifact_id: str | None
    report_metadata: dict[str, Any]


class ExecutionSession(AbstractContextManager["ExecutionSession"]):
    def __init__(
        self,
        *,
        interface_surface: InterfaceSurface,
        normalized_request: NormalizedRequest,
        raw_request_summary: dict[str, Any] | None = None,
    ) -> None:
        self.execution_id = f"exec-{uuid4()}"
        self.interface_surface = interface_surface
        self.normalized_request = normalized_request
        self.raw_request_summary = sanitize_mapping(raw_request_summary or {})
        self.normalized_request_summary = _summarize_normalized_request(normalized_request)
        self.started_at = _utc_now()
        self.ended_at: str | None = None
        self.final_status = "success"
        self.status_detail: str | None = None
        self.tool_invocation_sequence: list[dict[str, Any]] = []
        self.artifacts: list[ArtifactRecord] = []
        self._token: Token[ExecutionSession | None] | None = None
        self._recorder = get_audit_recorder()

    def __enter__(self) -> "ExecutionSession":
        self._token = _CURRENT_SESSION.set(self)
        self.record_event(
            "execution_started",
            normalized_request_summary=self.normalized_request_summary,
            raw_request_summary=self.raw_request_summary,
            output_mode=self.normalized_request.runtime_inputs.output_mode,
            output_path=_stringify_path(self.normalized_request.runtime_inputs.output_path),
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> bool | None:
        if exc is not None:
            if isinstance(exc, KeyboardInterrupt):
                self.mark_status("interrupted", detail=str(exc))
            else:
                self.mark_status(
                    "failure",
                    detail="".join(traceback.format_exception_only(type(exc), exc)).strip(),
                )
        self.ended_at = _utc_now()
        self.record_event(
            "execution_completed",
            end_timestamp=self.ended_at,
            final_status=self.final_status,
            status_detail=self.status_detail,
            selected_capability=self.selected_capability,
            dominant_skill=self.dominant_skill,
            selected_route=self.selected_route,
            output_mode=self.output_mode,
            output_path=self.output_path,
            artifact_id=self.artifact_id,
            report_metadata=self.report_metadata,
            tool_invocation_sequence=self.tool_invocation_sequence,
            normalized_request_summary=self.normalized_request_summary,
        )
        if self._token is not None:
            _CURRENT_SESSION.reset(self._token)
        return None

    @property
    def selected_capability(self) -> str | None:
        if not self.tool_invocation_sequence:
            return None
        return str(self.tool_invocation_sequence[0]["tool_name"])

    @property
    def dominant_skill(self) -> str | None:
        if self.selected_route:
            return "redis_rdb_analysis"
        name = self.selected_capability or ""
        if name.startswith("analyze_") or "rdb" in name or name.startswith("mysql_"):
            return "redis_rdb_analysis"
        if name.startswith("redis_"):
            return "redis_inspection_report"
        return None

    @property
    def selected_route(self) -> str | None:
        metadata = self.report_metadata
        if not metadata:
            return None
        route = metadata.get("route")
        return None if route is None else str(route)

    @property
    def output_mode(self) -> str:
        if self.artifacts:
            return self.artifacts[-1].output_mode
        return self.normalized_request.runtime_inputs.output_mode

    @property
    def output_path(self) -> str | None:
        if self.artifacts:
            return self.artifacts[-1].output_path
        return _stringify_path(self.normalized_request.runtime_inputs.output_path)

    @property
    def artifact_id(self) -> str | None:
        if self.artifacts:
            return self.artifacts[-1].artifact_id
        return None

    @property
    def report_metadata(self) -> dict[str, Any]:
        if self.artifacts:
            return self.artifacts[-1].report_metadata
        return {}

    def mark_status(self, status: str, *, detail: str | None = None) -> None:
        self.final_status = status
        self.status_detail = sanitize_value(detail)

    def record_event(self, event_type: str, **payload: Any) -> None:
        if self._recorder is None:
            return
        self._recorder.record(
            event_type,
            execution_id=self.execution_id,
            interface_surface=self.interface_surface.value,
            start_timestamp=self.started_at,
            **payload,
        )

    def record_tool_result(
        self,
        *,
        tool_name: str,
        tool_args_summary: dict[str, Any],
        status: str,
        started_at: str,
        ended_at: str,
        duration_ms: int,
    ) -> None:
        entry = {
            "tool_name": tool_name,
            "tool_args_summary": sanitize_mapping(tool_args_summary),
            "status": status,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_ms": duration_ms,
        }
        self.tool_invocation_sequence.append(entry)
        self.record_event("tool_completed", **entry)

    def record_artifact(
        self,
        *,
        output_mode: str,
        output_path: Path | str | None,
        artifact_id: str | None = None,
        report_metadata: dict[str, Any] | None = None,
    ) -> None:
        artifact = ArtifactRecord(
            output_mode=str(output_mode),
            output_path=_stringify_path(output_path),
            artifact_id=artifact_id,
            report_metadata=sanitize_mapping(report_metadata or {}),
        )
        self.artifacts.append(artifact)
        self.record_event(
            "artifact_generated",
            output_mode=artifact.output_mode,
            output_path=artifact.output_path,
            artifact_id=artifact.artifact_id,
            report_metadata=artifact.report_metadata,
        )


def start_execution_session(
    *,
    interface_surface: InterfaceSurface,
    normalized_request: NormalizedRequest,
    raw_request_summary: dict[str, Any] | None = None,
) -> ExecutionSession:
    return ExecutionSession(
        interface_surface=interface_surface,
        normalized_request=normalized_request,
        raw_request_summary=raw_request_summary,
    )


def get_current_execution_session() -> ExecutionSession | None:
    return _CURRENT_SESSION.get()


def observe_tool_call(tool_name: str, tool_args: dict[str, Any], fn: Callable[[], T]) -> T:
    session = get_current_execution_session()
    started_at = _utc_now()
    started_perf = perf_counter()
    try:
        result = fn()
    except Exception:
        if session is not None:
            session.record_tool_result(
                tool_name=tool_name,
                tool_args_summary=tool_args,
                status="failure",
                started_at=started_at,
                ended_at=_utc_now(),
                duration_ms=int((perf_counter() - started_perf) * 1000),
            )
        raise

    status = "success"
    if isinstance(result, str) and result.startswith("Operation denied by user"):
        status = "denied"
        if session is not None:
            session.mark_status("denied", detail=result)

    if session is not None:
        session.record_tool_result(
            tool_name=tool_name,
            tool_args_summary=tool_args,
            status=status,
            started_at=started_at,
            ended_at=_utc_now(),
            duration_ms=int((perf_counter() - started_perf) * 1000),
        )
    return result


def _summarize_normalized_request(request: NormalizedRequest) -> dict[str, Any]:
    runtime_inputs = request.runtime_inputs
    return sanitize_mapping(
        {
            "prompt_summary": summarize_prompt(request.prompt),
            "input_kind": runtime_inputs.input_kind,
            "path_mode": runtime_inputs.path_mode,
            "input_paths": [str(path) for path in runtime_inputs.input_paths],
            "redis_target": (
                f"{runtime_inputs.redis_host}:{runtime_inputs.redis_port}"
                if runtime_inputs.redis_host
                else None
            ),
            "ssh_target": (
                f"{runtime_inputs.ssh_host}:{runtime_inputs.ssh_port or 22}"
                if runtime_inputs.ssh_host
                else None
            ),
            "remote_rdb_path": runtime_inputs.remote_rdb_path,
            "mysql_target": (
                f"{runtime_inputs.mysql_host}:{runtime_inputs.mysql_port}"
                if runtime_inputs.mysql_host
                else None
            ),
            "mysql_database": runtime_inputs.mysql_database,
            "mysql_table": runtime_inputs.mysql_table,
            "mysql_query": runtime_inputs.mysql_query,
            "profile_name": request.rdb_overrides.profile_name,
            "output_mode": runtime_inputs.output_mode,
            "report_format": runtime_inputs.report_format,
            "output_path": _stringify_path(runtime_inputs.output_path),
            "focus_prefixes": list(request.rdb_overrides.focus_prefixes),
            "secret_presence": {
                "redis_password": bool(request.secrets.redis_password),
                "ssh_password": bool(request.secrets.ssh_password),
                "mysql_password": bool(request.secrets.mysql_password),
            },
        }
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stringify_path(value: Path | str | None) -> str | None:
    if value is None:
        return None
    return str(value)
