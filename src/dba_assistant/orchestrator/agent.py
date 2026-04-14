"""Unified Deep Agent — capability selection through tools.

The orchestrator builds a single agent that has access to ALL DBA Assistant
tools and lets the LLM decide which capabilities to invoke.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from deepagents import create_deep_agent
from langgraph.types import Command

from dba_assistant.adaptors.mysql_adaptor import MySQLConnectionConfig
from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.application.request_models import (
    DEFAULT_LOOPBACK_HOST,
    DEFAULT_MYSQL_DATABASE,
    DEFAULT_MYSQL_USER,
    NormalizedRequest,
)
from dba_assistant.core.observability import get_current_execution_session
from dba_assistant.deep_agent_integration.config import AppConfig
from dba_assistant.deep_agent_integration.model_provider import build_model
from dba_assistant.deep_agent_integration.runtime_support import (
    build_runtime_backend,
    build_runtime_checkpointer,
    extract_agent_output,
    get_memory_sources,
    get_skill_sources,
)
from dba_assistant.interface.hitl import HumanApprovalHandler
from dba_assistant.interface.types import ApprovalRequest, ApprovalStatus
from dba_assistant.orchestrator.tools import (
    build_all_tools,
)

APPROVAL_REQUEST_PHRASES = (
    "do you approve",
    "please confirm",
    "now i need your approval",
    "need your approval",
)
FALLBACK_ON_REJECT_ACTIONS = frozenset({"stage_local_rdb_to_mysql"})
SYSTEM_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "unified_system_prompt.md"


def build_unified_agent(
    request: NormalizedRequest,
    config: AppConfig,
    approval_handler: HumanApprovalHandler,
) -> object:
    """Build the unified Deep Agent with all available tools."""
    connection = _build_connection(request, config)
    mysql_connection = _build_mysql_connection(request, config)
    remote_rdb_state: dict[str, Any] = {}

    tools = _build_all_tools_compatible(
        request,
        config=config,
        connection=connection,
        mysql_connection=mysql_connection,
        remote_rdb_state=remote_rdb_state,
        approval_handler=approval_handler,
    )

    model = build_model(config.model)
    backend = build_runtime_backend()
    checkpointer = build_runtime_checkpointer()

    interrupt_on: dict[str, Any] = {
        "ensure_remote_rdb_snapshot": {
            "allowed_decisions": ["approve", "reject"],
            "description": _build_remote_snapshot_interrupt_description(request),
        },
        "fetch_remote_rdb_via_ssh": {
            "allowed_decisions": ["approve", "reject"],
            "description": _build_remote_rdb_interrupt_description(request),
        },
        "stage_local_rdb_to_mysql": {
            "allowed_decisions": ["approve", "reject"],
            "description": _build_mysql_staging_interrupt_description(request),
        },
    }
    agent = create_deep_agent(
        name="dba-assistant",
        model=model,
        tools=tools,
        backend=backend,
        checkpointer=checkpointer,
        skills=get_skill_sources(),
        memory=get_memory_sources(),
        interrupt_on=interrupt_on,
        system_prompt=_load_system_prompt(),
    )
    try:
        setattr(agent, "_dba_remote_rdb_state", remote_rdb_state)
    except Exception:  # noqa: BLE001
        pass
    return agent


def run_orchestrated(
    request: NormalizedRequest,
    *,
    config: AppConfig,
    approval_handler: HumanApprovalHandler,
    thread_id: str | None = None,
) -> str:
    """Run the unified Deep Agent and return the final output."""
    agent = build_unified_agent(request, config, approval_handler)
    user_message = _build_user_message(request)
    run_config = {"configurable": {"thread_id": thread_id or f"dba-assistant-{uuid4()}"}}
    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_message}]},
        config=run_config,
    )
    approval_retry_count = 0

    while True:
        while interrupts := _extract_interrupts(result):
            resume_payload = _handle_interrupts(interrupts, approval_handler)
            if resume_payload is None:
                session = get_current_execution_session()
                if session is not None:
                    session.mark_status("denied", detail="user rejected approval request")
                return "Operation denied by user."
            result = agent.invoke(Command(resume=resume_payload), config=run_config)

        if not _should_force_runtime_approval(agent, request, result):
            break
        if approval_retry_count >= 1:
            session = get_current_execution_session()
            if session is not None:
                session.mark_status(
                    "failure",
                    detail="model asked for approval in plain text instead of using interrupt_on",
                )
            return (
                "Internal policy violation: the model asked for approval in plain text "
                "instead of invoking the approval-gated tool fetch_remote_rdb_via_ssh."
            )
        approval_retry_count += 1
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Policy reminder: do not ask for approval in plain text. "
                            "If remote RDB retrieval is needed, call fetch_remote_rdb_via_ssh "
                            "now so runtime can collect approval."
                        ),
                    }
                ]
            },
            config=run_config,
        )

    final_output = extract_agent_output(result)
    return _finalize_runtime_output(request, final_output)


def _build_all_tools_compatible(
    request: NormalizedRequest,
    **kwargs: Any,
) -> list:
    try:
        return build_all_tools(request, **kwargs)
    except TypeError as exc:
        message = str(exc)
        if "approval_handler" not in message and "config" not in message:
            raise
        compatible_kwargs = dict(kwargs)
        compatible_kwargs.pop("approval_handler", None)
        compatible_kwargs.pop("config", None)
        return build_all_tools(request, **compatible_kwargs)


def _should_force_runtime_approval(
    agent: object,
    request: NormalizedRequest,
    result: object,
) -> bool:
    text = extract_agent_output(result).strip()
    if not text:
        return False
    lowered = text.lower()
    if not any(phrase in lowered for phrase in APPROVAL_REQUEST_PHRASES):
        return False
    if request.runtime_inputs.redis_host is None:
        return False
    remote_rdb_state = getattr(agent, "_dba_remote_rdb_state", None)
    if not isinstance(remote_rdb_state, dict):
        return False
    discovery = remote_rdb_state.get("discovery")
    if not isinstance(discovery, dict):
        return False
    if not str(discovery.get("rdb_path") or "").strip():
        return False
    return bool(discovery.get("requires_confirmation"))


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


def _finalize_runtime_output(request: NormalizedRequest, agent_output: str) -> str:
    session = get_current_execution_session()
    if session is None:
        return agent_output
    if not _docx_contract_required(request, session):
        return agent_output

    artifact_path = _resolve_docx_artifact_path(session)
    if artifact_path is not None:
        return artifact_path

    session.mark_status(
        "failure",
        detail="DOCX artifact contract violated: no generated .docx artifact was recorded.",
    )
    return (
        "DOCX artifact contract violated: the agent selected DOCX output, "
        "but no generated .docx artifact was produced."
    )


def _docx_contract_required(request: NormalizedRequest, session: Any) -> bool:
    runtime = request.runtime_inputs
    if (runtime.report_format or "").lower() == "docx":
        return True
    if runtime.output_path is not None and runtime.output_path.suffix.lower() == ".docx":
        return True
    return any(_tool_call_requested_docx(entry) for entry in session.tool_invocation_sequence)


def _tool_call_requested_docx(entry: dict[str, Any]) -> bool:
    args = entry.get("tool_args_summary")
    if not isinstance(args, dict):
        return False
    report_format = str(args.get("report_format", "")).strip().lower()
    if report_format == "docx":
        return True
    output_path = str(args.get("output_path", "")).strip().lower()
    if output_path.endswith(".docx"):
        return True
    return False


def _resolve_docx_artifact_path(session: Any) -> str | None:
    for artifact in reversed(session.artifacts):
        output_path = artifact.output_path
        if not isinstance(output_path, str) or not output_path.lower().endswith(".docx"):
            continue
        path = Path(output_path)
        if path.exists() and path.is_file():
            return str(path)
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_connection(
    request: NormalizedRequest,
    config: AppConfig,
) -> RedisConnectionConfig | None:
    """Build a Redis connection config from the normalized request, or None."""
    if not _redis_context_requested(request):
        return None
    return RedisConnectionConfig(
        host=request.runtime_inputs.redis_host or DEFAULT_LOOPBACK_HOST,
        port=request.runtime_inputs.redis_port,
        db=request.runtime_inputs.redis_db,
        password=request.secrets.redis_password,
        socket_timeout=config.runtime.redis_socket_timeout,
    )


def _build_mysql_connection(
    request: NormalizedRequest,
    config: AppConfig,
) -> MySQLConnectionConfig | None:
    """Build a MySQL connection config from the normalized request, or None."""
    if not _mysql_context_requested(request):
        return None
    return MySQLConnectionConfig(
        host=request.runtime_inputs.mysql_host or DEFAULT_LOOPBACK_HOST,
        port=request.runtime_inputs.mysql_port,
        user=request.runtime_inputs.mysql_user or DEFAULT_MYSQL_USER,
        password=request.secrets.mysql_password or "",
        database=request.runtime_inputs.mysql_database or DEFAULT_MYSQL_DATABASE,
        connect_timeout_seconds=config.runtime.mysql_connect_timeout_seconds,
        read_timeout_seconds=config.runtime.mysql_read_timeout_seconds,
        write_timeout_seconds=config.runtime.mysql_write_timeout_seconds,
    )


def _build_user_message(request: NormalizedRequest) -> str:
    """Build the user message including structured context."""
    parts: list[str] = [request.prompt]
    context_lines: list[str] = []

    if request.runtime_inputs.input_paths:
        paths = ", ".join(str(p) for p in request.runtime_inputs.input_paths)
        context_lines.append(f"Local RDB files: {paths}")

    if request.runtime_inputs.input_kind:
        context_lines.append(f"Input kind: {request.runtime_inputs.input_kind}")

    if request.runtime_inputs.path_mode:
        context_lines.append(f"Path mode: {request.runtime_inputs.path_mode}")

    if request.runtime_inputs.redis_host:
        context_lines.append(
            f"Redis connection: {request.runtime_inputs.redis_host}:"
            f"{request.runtime_inputs.redis_port}"
        )
    if request.secrets.redis_password:
        context_lines.append("Redis password: present via secure context")
    if request.runtime_inputs.ssh_host:
        ssh_port = request.runtime_inputs.ssh_port or 22
        ssh_user = request.runtime_inputs.ssh_username or "unspecified"
        context_lines.append(
            f"SSH connection: {request.runtime_inputs.ssh_host}:{ssh_port} as {ssh_user}"
        )
    if request.secrets.ssh_password:
        context_lines.append("SSH password: present via secure context")
    if request.runtime_inputs.remote_rdb_path:
        source = request.runtime_inputs.remote_rdb_path_source or "user_override"
        context_lines.append(
            f"Remote RDB path override: {request.runtime_inputs.remote_rdb_path} ({source})"
        )
    if request.runtime_inputs.require_fresh_rdb_snapshot:
        context_lines.append("Remote RDB acquisition mode: fresh_snapshot")

    if _mysql_context_requested(request):
        context_lines.append(
            f"MySQL connection: {(request.runtime_inputs.mysql_host or DEFAULT_LOOPBACK_HOST)}:"
            f"{request.runtime_inputs.mysql_port}"
        )
        context_lines.append(
            f"MySQL database: {request.runtime_inputs.mysql_database or DEFAULT_MYSQL_DATABASE}"
        )
    if request.runtime_inputs.mysql_table:
        context_lines.append(f"MySQL table: {request.runtime_inputs.mysql_table}")
    if request.runtime_inputs.mysql_query:
        context_lines.append(f"MySQL query: {request.runtime_inputs.mysql_query}")
    if request.runtime_inputs.log_time_window_days is not None:
        context_lines.append(f"Log time window: last {request.runtime_inputs.log_time_window_days} days")
    if request.runtime_inputs.log_start_time or request.runtime_inputs.log_end_time:
        context_lines.append(
            "Log time range: "
            f"{request.runtime_inputs.log_start_time or '-'} to {request.runtime_inputs.log_end_time or '-'}"
        )

    if request.rdb_overrides.profile_name:
        context_lines.append(f"Profile: {request.rdb_overrides.profile_name}")

    output_mode = request.runtime_inputs.output_mode or "summary"
    report_format = request.runtime_inputs.report_format or output_mode
    context_lines.append(f"Output: {output_mode} / {report_format}")

    if request.runtime_inputs.output_path:
        context_lines.append(f"Output path: {request.runtime_inputs.output_path}")

    if request.rdb_overrides.focus_prefixes:
        context_lines.append(
            f"Focus prefixes: {', '.join(request.rdb_overrides.focus_prefixes)}"
        )

    if context_lines:
        parts.append("\n[Context]\n" + "\n".join(f"- {line}" for line in context_lines))

    return "\n".join(parts)


def _extract_interrupts(result: object) -> list[object]:
    if not isinstance(result, dict):
        return []
    interrupts = result.get("__interrupt__")
    if isinstance(interrupts, list):
        return list(interrupts)
    if isinstance(interrupts, tuple):
        return list(interrupts)
    return []


def _handle_interrupts(
    interrupts: list[object],
    approval_handler: HumanApprovalHandler,
) -> dict[str, object] | None:
    decisions: list[dict[str, object]] = []
    for interrupt in interrupts:
        value = getattr(interrupt, "value", None)
        if not isinstance(value, dict):
            continue
        for action in value.get("action_requests", []):
            if not isinstance(action, dict):
                continue
            request = ApprovalRequest(
                action=str(action.get("name", "tool_execution")),
                message=str(action.get("description", "Tool execution requires approval.")),
                details={
                    "args": action.get("args", {}),
                    "denial_semantics": (
                        "fallback"
                        if str(action.get("name", "tool_execution")) in FALLBACK_ON_REJECT_ACTIONS
                        else "abort"
                    ),
                },
            )
            response = approval_handler.request_approval(request)
            if response.status is ApprovalStatus.APPROVED:
                decisions.append({"type": "approve"})
            elif request.action in FALLBACK_ON_REJECT_ACTIONS:
                decisions.append({"type": "reject"})
            else:
                return None
    return {"decisions": decisions}


def _build_remote_snapshot_interrupt_description(request: NormalizedRequest):
    def describe_remote_snapshot_interrupt(
        tool_call: dict[str, Any],
        state: Any,
        runtime: Any,
    ) -> str:
        args = tool_call.get("args", {})
        redis_host = str(args.get("redis_host") or request.runtime_inputs.redis_host or "unknown")
        redis_port = str(args.get("redis_port") or request.runtime_inputs.redis_port or 6379)
        redis_db = str(args.get("redis_db") or request.runtime_inputs.redis_db or 0)
        remote_rdb_path = str(args.get("remote_rdb_path") or request.runtime_inputs.remote_rdb_path or "auto-discover")
        return "\n".join(
            [
                "Remote Redis snapshot generation requires human approval.",
                "",
                f"Target Redis: {redis_host}:{redis_port}",
                f"Redis DB: {redis_db}",
                f"Remote RDB path hint: {remote_rdb_path}",
                "The agent wants to trigger BGSAVE and wait for the new RDB snapshot.",
                "Approve only if remote snapshot generation is allowed for this target.",
            ]
        )

    return describe_remote_snapshot_interrupt


def _build_remote_rdb_interrupt_description(request: NormalizedRequest):

    def describe_remote_rdb_fetch_interrupt(
        tool_call: dict[str, Any],
        state: Any,
        runtime: Any,
    ) -> str:
        args = tool_call.get("args", {})
        ssh_host = str(args.get("ssh_host") or request.runtime_inputs.ssh_host or "unknown")
        ssh_port = str(args.get("ssh_port") or request.runtime_inputs.ssh_port or 22)
        ssh_username = str(args.get("ssh_username") or request.runtime_inputs.ssh_username or "unspecified")
        remote_rdb_path = str(args.get("remote_rdb_path") or request.runtime_inputs.remote_rdb_path or "unresolved")
        local_directory = str(args.get("local_directory") or "temporary workspace")
        return "\n".join(
            [
                "Remote RDB acquisition requires human approval.",
                "",
                f"SSH target: {ssh_host}:{ssh_port}",
                f"SSH username: {ssh_username}",
                f"Remote RDB path: {remote_rdb_path}",
                f"Local destination: {local_directory}",
                "The agent wants to fetch and analyze a remote Redis RDB.",
                "Approve only if remote RDB retrieval is allowed for this target.",
            ]
        )

    return describe_remote_rdb_fetch_interrupt


def _build_mysql_staging_interrupt_description(request: NormalizedRequest):
    def describe_mysql_staging_interrupt(
        tool_call: dict[str, Any],
        state: Any,
        runtime: Any,
    ) -> str:
        args = tool_call.get("args", {})
        mysql_host = str(args.get("mysql_host") or request.runtime_inputs.mysql_host or "unknown")
        mysql_port = str(args.get("mysql_port") or request.runtime_inputs.mysql_port or 3306)
        mysql_database = str(
            args.get("mysql_database") or request.runtime_inputs.mysql_database or DEFAULT_MYSQL_DATABASE
        )
        table_name = str(args.get("mysql_table") or request.runtime_inputs.mysql_table or "auto-generated")
        input_paths = str(args.get("input_paths") or "unspecified")
        return (
            "MySQL staging write requires human approval.\n\n"
            f"Input RDB paths: {input_paths}\n"
            f"Target MySQL: {mysql_host}:{mysql_port}/{mysql_database}\n"
            f"Staging table: {table_name}\n"
            "The agent wants to write parsed RDB rows into MySQL.\n"
            "Approve only if MySQL write access is allowed for this target.\n"
            "Reject means: do not write to MySQL; continue with direct streaming analysis instead."
        )

    return describe_mysql_staging_interrupt


def _mysql_context_requested(request: NormalizedRequest) -> bool:
    runtime = request.runtime_inputs
    return any(
        (
            runtime.mysql_host,
            runtime.mysql_user,
            runtime.mysql_database,
            runtime.mysql_table,
            runtime.mysql_query,
            runtime.input_kind == "preparsed_mysql",
            runtime.path_mode == "database_backed_analysis",
        )
    )


def _redis_context_requested(request: NormalizedRequest) -> bool:
    runtime = request.runtime_inputs
    if runtime.redis_host:
        return True
    if runtime.input_kind == "remote_redis":
        return True
    if runtime.remote_rdb_path or runtime.require_fresh_rdb_snapshot or runtime.ssh_host:
        return True
    if runtime.input_paths:
        return False
    return False
