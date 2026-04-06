"""Unified interface adapter.

Shared boundary for CLI, Web, and API interfaces.
Handles request normalization, HITL delegation, and artifact formatting.
"""
from __future__ import annotations

from dataclasses import replace

from dba_assistant.application.prompt_parser import normalize_raw_request
from dba_assistant.application.request_models import NormalizedRequest
from dba_assistant.core.reporter.output_path_policy import ensure_report_output_path
from dba_assistant.deep_agent_integration.config import load_app_config
from dba_assistant.interface.hitl import HumanApprovalHandler
from dba_assistant.interface.types import InterfaceRequest
from dba_assistant.orchestrator.agent import run_orchestrated


def handle_request(
    request: InterfaceRequest,
    *,
    approval_handler: HumanApprovalHandler,
) -> str:
    """Unified entry point for all interfaces.

    1. Load config
    2. Normalize raw prompt into structured request
    3. Apply interface-level overrides (--profile, --output, etc.)
    4. Delegate to the orchestrator (unified Deep Agent)
    5. Return formatted output
    """
    config = load_app_config(request.config_path)

    normalized = normalize_raw_request(
        request.prompt,
        default_output_mode=config.runtime.default_output_mode,
        input_paths=request.input_paths,
    )
    normalized = _apply_overrides(normalized, request)
    normalized = replace(
        normalized,
        runtime_inputs=ensure_report_output_path(
            normalized.runtime_inputs,
            normalized.runtime_inputs.report_format,
        ),
    )

    return run_orchestrated(normalized, config=config, approval_handler=approval_handler)


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
        runtime_inputs = replace(runtime_inputs, input_kind=request.input_kind)

    if request.path_mode is not None:
        runtime_inputs = replace(runtime_inputs, path_mode=request.path_mode)

    if request.redis_password is not None:
        secrets = replace(normalized.secrets, redis_password=request.redis_password)
        normalized = replace(normalized, secrets=secrets)

    if request.ssh_host is not None:
        runtime_inputs = replace(runtime_inputs, ssh_host=request.ssh_host)

    if request.ssh_port is not None:
        runtime_inputs = replace(runtime_inputs, ssh_port=request.ssh_port)

    if request.ssh_username is not None:
        runtime_inputs = replace(runtime_inputs, ssh_username=request.ssh_username)

    if request.remote_rdb_path is not None:
        runtime_inputs = replace(
            runtime_inputs,
            remote_rdb_path=request.remote_rdb_path,
            remote_rdb_path_source=request.remote_rdb_path_source or "user_override",
        )

    if request.require_fresh_rdb_snapshot is not None:
        runtime_inputs = replace(
            runtime_inputs,
            require_fresh_rdb_snapshot=request.require_fresh_rdb_snapshot,
        )

    if request.mysql_host is not None:
        runtime_inputs = replace(runtime_inputs, mysql_host=request.mysql_host)

    if request.mysql_port is not None:
        runtime_inputs = replace(runtime_inputs, mysql_port=request.mysql_port)

    if request.mysql_user is not None:
        runtime_inputs = replace(runtime_inputs, mysql_user=request.mysql_user)

    if request.mysql_database is not None:
        runtime_inputs = replace(runtime_inputs, mysql_database=request.mysql_database)

    if request.mysql_table is not None:
        runtime_inputs = replace(runtime_inputs, mysql_table=request.mysql_table)

    if request.mysql_query is not None:
        runtime_inputs = replace(runtime_inputs, mysql_query=request.mysql_query)

    if request.mysql_password is not None:
        secrets = replace(normalized.secrets, mysql_password=request.mysql_password)
        normalized = replace(normalized, secrets=secrets)

    if request.ssh_password is not None:
        secrets = replace(normalized.secrets, ssh_password=request.ssh_password)
        normalized = replace(normalized, secrets=secrets)

    return replace(normalized, runtime_inputs=runtime_inputs, rdb_overrides=rdb_overrides)
