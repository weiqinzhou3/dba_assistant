"""Unified interface adapter.

Shared boundary for CLI, Web, and API interfaces.
Handles request normalization, HITL delegation, and artifact formatting.
"""
from __future__ import annotations

from dataclasses import replace

from dba_assistant.application.prompt_parser import normalize_raw_request
from dba_assistant.application.request_models import NormalizedRequest
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

    return replace(normalized, runtime_inputs=runtime_inputs, rdb_overrides=rdb_overrides)
