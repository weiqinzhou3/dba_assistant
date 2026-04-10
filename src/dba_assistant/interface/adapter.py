"""Unified interface adapter.

Shared boundary for CLI, Web, and API interfaces.
Handles request normalization, HITL delegation, and artifact formatting.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from dba_assistant.application.prompt_parser import normalize_raw_request
from dba_assistant.application.request_models import (
    DEFAULT_LOOPBACK_HOST,
    DEFAULT_MYSQL_DATABASE,
    DEFAULT_MYSQL_USER,
    NormalizedRequest,
)
from dba_assistant.core.observability import bootstrap_observability, start_execution_session
from dba_assistant.core.observability.sanitizer import sanitize_mapping, summarize_prompt
from dba_assistant.core.reporter.output_path_policy import ensure_report_output_path
from dba_assistant.deep_agent_integration.config import ObservabilityConfig, load_app_config
from dba_assistant.interface.hitl import AuditedApprovalHandler, HumanApprovalHandler
from dba_assistant.interface.types import InterfaceRequest
from dba_assistant.orchestrator.agent import run_orchestrated


def handle_request(
    request: InterfaceRequest,
    *,
    approval_handler: HumanApprovalHandler,
    thread_id: str | None = None,
) -> tuple[str, NormalizedRequest]:
    """Unified entry point for all interfaces."""
    config = load_app_config(request.config_path)
    bootstrap_observability(getattr(config, "observability", ObservabilityConfig()))

    normalized = normalize_raw_request(
        request.prompt,
        default_output_mode=config.runtime.default_output_mode,
        input_paths=request.input_paths,
    )
    normalized = _apply_overrides(normalized, request)
    normalized = _apply_runtime_defaults(normalized, config)
    normalized = _apply_conventional_defaults(normalized)
    normalized = replace(
        normalized,
        runtime_inputs=ensure_report_output_path(
            normalized.runtime_inputs,
            normalized.runtime_inputs.report_format,
        ),
    )
    raw_request_summary = _summarize_interface_request(request)
    audited_handler = AuditedApprovalHandler(approval_handler)

    # Fast-Track: Inject pre-inspected file metadata
    if normalized.runtime_inputs.input_paths:
        metadata_lines = []
        for path in normalized.runtime_inputs.input_paths:
            p = Path(path).expanduser()
            if p.exists() and p.is_file():
                size = p.stat().st_size
                metadata_lines.append(f"- {path}: {size / (1024*1024*1024):.2f} GB (exists)")
            else:
                metadata_lines.append(f"- {path}: missing or invalid")
        
        if metadata_lines:
            pre_inspection_context = "\n[Automated File Inspection]\n" + "\n".join(metadata_lines)
            pre_inspection_context += "\n**CRITICAL**: Stick to these files. Do NOT search for or analyze other files unless explicitly asked."
            normalized = replace(normalized, prompt=normalized.prompt + pre_inspection_context)

    with start_execution_session(
        interface_surface=request.surface,
        normalized_request=normalized,
        raw_request_summary=raw_request_summary,
    ):
        result = run_orchestrated(
            normalized,
            config=config,
            approval_handler=audited_handler,
            thread_id=thread_id,
        )
        return result, normalized


def _apply_overrides(
    normalized: NormalizedRequest,
    request: InterfaceRequest,
) -> NormalizedRequest:
    """Apply interface-level overrides onto the normalized request."""
    runtime_inputs = normalized.runtime_inputs
    rdb_overrides = normalized.rdb_overrides

    if request.report_format is not None:
        runtime_inputs = replace(
            runtime_inputs,
            output_mode="summary" if request.report_format == "summary" else "report",
            report_format=None if request.report_format == "summary" else request.report_format,
        )

    if request.output_path is not None:
        runtime_inputs = replace(runtime_inputs, output_path=request.output_path)

    if request.input_paths:
        runtime_inputs = replace(runtime_inputs, input_paths=tuple(request.input_paths))

    if request.profile is not None:
        rdb_overrides = replace(rdb_overrides, profile_name=request.profile)

    if request.input_kind is not None:
        rdb_overrides = replace(rdb_overrides, input_kind=request.input_kind)

    if request.path_mode is not None:
        rdb_overrides = replace(rdb_overrides, route_name=request.path_mode)

    return replace(
        normalized,
        runtime_inputs=runtime_inputs,
        rdb_overrides=rdb_overrides,
    )


def _apply_runtime_defaults(
    normalized: NormalizedRequest,
    config: AppConfig,
) -> NormalizedRequest:
    """Inject configuration defaults into the request."""
    runtime = normalized.runtime_inputs
    if runtime.mysql_stage_batch_size is None:
        runtime = replace(runtime, mysql_stage_batch_size=config.runtime.mysql_stage_batch_size)
    
    return replace(normalized, runtime_inputs=runtime)


def _apply_conventional_defaults(normalized: NormalizedRequest) -> NormalizedRequest:
    """Apply business-level conventional defaults."""
    runtime = normalized.runtime_inputs
    if not runtime.mysql_host:
        runtime = replace(runtime, mysql_host=DEFAULT_LOOPBACK_HOST)
    if not runtime.mysql_database:
        runtime = replace(runtime, mysql_database=DEFAULT_MYSQL_DATABASE)
    if not runtime.mysql_user:
        runtime = replace(runtime, mysql_user=DEFAULT_MYSQL_USER)
    return replace(normalized, runtime_inputs=runtime)


def _summarize_interface_request(request: InterfaceRequest) -> dict[str, Any]:
    """Provide a summarized version of the raw interface request for auditing."""
    return {
        "surface": request.surface,
        "prompt_summary": summarize_prompt(request.prompt),
        "input_paths": [str(p) for p in request.input_paths],
        "output_path": str(request.output_path) if request.output_path else None,
        "config_path": str(request.config_path) if request.config_path else None,
        "profile": request.profile,
        "report_format": request.report_format,
        "input_kind": request.input_kind,
        "path_mode": request.path_mode,
        "ssh_host": request.ssh_host,
        "ssh_port": request.ssh_port,
        "ssh_username": request.ssh_username,
        "remote_rdb_path": request.remote_rdb_path,
        "mysql_host": request.mysql_host,
        "mysql_port": request.mysql_port,
        "mysql_user": request.mysql_user,
        "mysql_database": request.mysql_database,
        "mysql_table": request.mysql_table,
        "mysql_query": request.mysql_query,
        "mysql_stage_batch_size": request.mysql_stage_batch_size,
        "secret_presence": {
            "redis_password": bool(request.redis_password),
            "ssh_password": bool(request.ssh_password),
            "mysql_password": bool(request.mysql_password),
        },
    }
