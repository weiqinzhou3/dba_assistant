"""Unified interface adapter.

Shared boundary for CLI, Web, and API interfaces.
Handles request normalization, HITL delegation, and artifact formatting.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from dba_assistant.application.prompt_parser import normalize_raw_request
from dba_assistant.application.request_models import (
    DEFAULT_MYSQL_STAGE_BATCH_SIZE,
    NormalizedRequest,
)
from dba_assistant.core.observability import bootstrap_observability, start_execution_session
from dba_assistant.core.observability.sanitizer import summarize_prompt
from dba_assistant.deep_agent_integration.config import AppConfig, ObservabilityConfig, load_app_config
from dba_assistant.interface.hitl import AuditedApprovalHandler, HumanApprovalHandler
from dba_assistant.interface.types import InterfaceRequest
from dba_assistant.orchestrator.agent import run_orchestrated


def handle_request(
    request: InterfaceRequest,
    *,
    approval_handler: HumanApprovalHandler,
    thread_id: str | None = None,
    event_handler: Callable[[dict[str, Any]], None] | None = None,
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
    raw_request_summary = _summarize_interface_request(request)
    audited_handler = AuditedApprovalHandler(approval_handler)

    with start_execution_session(
        interface_surface=request.surface,
        normalized_request=normalized,
        raw_request_summary=raw_request_summary,
    ):
        if event_handler is None:
            result = run_orchestrated(
                normalized,
                config=config,
                approval_handler=audited_handler,
                thread_id=thread_id,
            )
        else:
            result = run_orchestrated(
                normalized,
                config=config,
                approval_handler=audited_handler,
                thread_id=thread_id,
                event_handler=event_handler,
            )
        return result, normalized


def _apply_overrides(
    normalized: NormalizedRequest,
    request: InterfaceRequest,
) -> NormalizedRequest:
    """Apply interface-level overrides onto the normalized request."""
    runtime_inputs = normalized.runtime_inputs
    rdb_overrides = normalized.rdb_overrides
    secrets = normalized.secrets

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
        runtime_inputs = replace(runtime_inputs, input_kind=request.input_kind)

    if request.path_mode is not None:
        runtime_inputs = replace(runtime_inputs, path_mode=request.path_mode)

    runtime_updates: dict[str, Any] = {}
    if request.ssh_host is not None:
        runtime_updates["ssh_host"] = request.ssh_host
    if request.ssh_port is not None:
        runtime_updates["ssh_port"] = request.ssh_port
    if request.ssh_username is not None:
        runtime_updates["ssh_username"] = request.ssh_username
    if request.remote_rdb_path is not None:
        runtime_updates["remote_rdb_path"] = request.remote_rdb_path
        runtime_updates["remote_rdb_path_source"] = request.remote_rdb_path_source or "user_override"
    elif request.remote_rdb_path_source is not None:
        runtime_updates["remote_rdb_path_source"] = request.remote_rdb_path_source
    if request.require_fresh_rdb_snapshot is not None:
        runtime_updates["require_fresh_rdb_snapshot"] = request.require_fresh_rdb_snapshot
    if request.mysql_host is not None:
        runtime_updates["mysql_host"] = request.mysql_host
    if request.mysql_port is not None:
        runtime_updates["mysql_port"] = request.mysql_port
    if request.mysql_user is not None:
        runtime_updates["mysql_user"] = request.mysql_user
    if request.mysql_database is not None:
        runtime_updates["mysql_database"] = request.mysql_database
    if request.mysql_table is not None:
        runtime_updates["mysql_table"] = request.mysql_table
    if request.mysql_query is not None:
        runtime_updates["mysql_query"] = request.mysql_query
    if request.mysql_stage_batch_size is not None:
        runtime_updates["mysql_stage_batch_size"] = request.mysql_stage_batch_size
    if request.log_time_window_days is not None:
        runtime_updates["log_time_window_days"] = request.log_time_window_days
    if request.log_start_time is not None:
        runtime_updates["log_start_time"] = request.log_start_time
    if request.log_end_time is not None:
        runtime_updates["log_end_time"] = request.log_end_time
    if runtime_updates:
        runtime_inputs = replace(runtime_inputs, **runtime_updates)

    secret_updates: dict[str, Any] = {}
    if request.redis_password is not None:
        secret_updates["redis_password"] = request.redis_password
    if request.ssh_password is not None:
        secret_updates["ssh_password"] = request.ssh_password
    if request.mysql_password is not None:
        secret_updates["mysql_password"] = request.mysql_password
    if secret_updates:
        secrets = replace(secrets, **secret_updates)

    return replace(
        normalized,
        runtime_inputs=runtime_inputs,
        rdb_overrides=rdb_overrides,
        secrets=secrets,
    )


def _apply_runtime_defaults(
    normalized: NormalizedRequest,
    config: AppConfig,
) -> NormalizedRequest:
    """Inject configuration defaults into the request."""
    runtime = normalized.runtime_inputs
    if runtime.mysql_stage_batch_size is None:
        configured_batch_size = getattr(
            getattr(config, "runtime", object()),
            "mysql_stage_batch_size",
            DEFAULT_MYSQL_STAGE_BATCH_SIZE,
        )
        runtime = replace(runtime, mysql_stage_batch_size=configured_batch_size)

    paths = getattr(config, "paths", None)
    agent = getattr(config, "agent", None)
    filesystem_backend = getattr(agent, "filesystem_backend", None)
    path_defaults: dict[str, Any] = {}
    if runtime.filesystem_root_dir is None and getattr(filesystem_backend, "root_dir", None) is not None:
        path_defaults["filesystem_root_dir"] = filesystem_backend.root_dir
    if runtime.artifact_dir is None and getattr(paths, "artifact_dir", None) is not None:
        path_defaults["artifact_dir"] = paths.artifact_dir
    if runtime.evidence_dir is None and getattr(paths, "evidence_dir", None) is not None:
        path_defaults["evidence_dir"] = paths.evidence_dir
    if runtime.temp_dir is None and getattr(paths, "temp_dir", None) is not None:
        path_defaults["temp_dir"] = paths.temp_dir
    if path_defaults:
        runtime = replace(runtime, **path_defaults)

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
