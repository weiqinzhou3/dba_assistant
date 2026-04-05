"""Unified Deep Agent — capability selection through tools.

The orchestrator builds a single agent that has access to ALL DBA Assistant
tools and lets the LLM decide which capabilities to invoke.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from deepagents import create_deep_agent
from langgraph.types import Command

from dba_assistant.adaptors.mysql_adaptor import MySQLConnectionConfig
from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.application.request_models import NormalizedRequest
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
from dba_assistant.orchestrator.tools import build_all_tools

SYSTEM_PROMPT = """\
You are DBA Assistant, a specialized database administration assistant focused on Redis diagnostics and analysis.

Available capabilities (use the corresponding tool):
1. **analyze_local_rdb** — Analyze local Redis RDB dump files. Use when local .rdb file paths are provided.
2. **analyze_preparsed_dataset** — Analyze a preparsed dataset from local JSON or MySQL-backed source.
3. **discover_remote_rdb** — Read-only discovery of remote Redis RDB location and persistence info.
4. **fetch_remote_rdb_via_ssh** — Fetch a remote RDB via SSH (requires human approval) then continue analysis.
5. **redis_ping / redis_info / redis_config_get / redis_slowlog_get / redis_client_list** — \
Live read-only Redis inspection.
6. **mysql_read_query** — Execute a bounded read-only SQL query against MySQL.
7. **load_preparsed_dataset_from_mysql** — Load a preparsed dataset from a MySQL table.
8. **stage_rdb_rows_to_mysql** — Stage parsed RDB rows into MySQL for database-backed analysis \
(requires human approval).

Rules:
- All Redis operations are strictly read-only.
- For remote RDB: call discover_remote_rdb first, then fetch_remote_rdb_via_ssh.
- MySQL read operations (mysql_read_query, load_preparsed_dataset_from_mysql) are lower-risk.
- MySQL write operations (stage_rdb_rows_to_mysql) require human approval before execution.
- Use the profile the user requests (generic, rcs). Default to generic.
- Generate reports in the requested format (summary / docx). Default to summary.
- Be concise. Return tool output directly when it already answers the user's question.
"""


def build_unified_agent(
    request: NormalizedRequest,
    config: AppConfig,
    approval_handler: HumanApprovalHandler,
) -> object:
    """Build the unified Deep Agent with all available tools."""
    connection = _build_connection(request, config)
    mysql_connection = _build_mysql_connection(request)

    tools = build_all_tools(
        request, connection=connection, mysql_connection=mysql_connection,
    )

    model = build_model(config.model)
    backend = build_runtime_backend()
    checkpointer = build_runtime_checkpointer()

    interrupt_on: dict[str, Any] = {
        "fetch_remote_rdb_via_ssh": {
            "allowed_decisions": ["approve", "reject"],
            "description": _build_remote_rdb_interrupt_description(request),
        },
        "fetch_and_analyze_remote_rdb": {
            "allowed_decisions": ["approve", "reject"],
            "description": _build_remote_rdb_interrupt_description(request),
        },
    }
    if mysql_connection is not None:
        interrupt_on["stage_rdb_rows_to_mysql"] = {
            "allowed_decisions": ["approve", "reject"],
            "description": _build_mysql_staging_interrupt_description(request),
        }

    return create_deep_agent(
        name="dba-assistant",
        model=model,
        tools=tools,
        backend=backend,
        checkpointer=checkpointer,
        skills=get_skill_sources(),
        memory=get_memory_sources(),
        interrupt_on=interrupt_on,
        system_prompt=SYSTEM_PROMPT,
    )


def run_orchestrated(
    request: NormalizedRequest,
    *,
    config: AppConfig,
    approval_handler: HumanApprovalHandler,
) -> str:
    """Run the unified Deep Agent and return the final output."""
    agent = build_unified_agent(request, config, approval_handler)
    user_message = _build_user_message(request)
    run_config = {"configurable": {"thread_id": f"dba-assistant-{uuid4()}"}}
    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_message}]},
        config=run_config,
    )

    while interrupts := _extract_interrupts(result):
        resume_payload = _handle_interrupts(interrupts, approval_handler)
        if resume_payload is None:
            return "Operation denied by user."
        result = agent.invoke(Command(resume=resume_payload), config=run_config)

    return extract_agent_output(result)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_connection(
    request: NormalizedRequest,
    config: AppConfig,
) -> RedisConnectionConfig | None:
    """Build a Redis connection config from the normalized request, or None."""
    if not request.runtime_inputs.redis_host:
        return None
    return RedisConnectionConfig(
        host=request.runtime_inputs.redis_host,
        port=request.runtime_inputs.redis_port,
        db=request.runtime_inputs.redis_db,
        password=request.secrets.redis_password,
        socket_timeout=config.runtime.redis_socket_timeout,
    )


def _build_mysql_connection(
    request: NormalizedRequest,
) -> MySQLConnectionConfig | None:
    """Build a MySQL connection config from the normalized request, or None."""
    if not request.runtime_inputs.mysql_host:
        return None
    return MySQLConnectionConfig(
        host=request.runtime_inputs.mysql_host,
        port=request.runtime_inputs.mysql_port,
        user=request.runtime_inputs.mysql_user or "root",
        password=request.secrets.mysql_password or "",
        database=request.runtime_inputs.mysql_database or "",
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
    if request.runtime_inputs.ssh_host:
        ssh_port = request.runtime_inputs.ssh_port or 22
        ssh_user = request.runtime_inputs.ssh_username or "unspecified"
        context_lines.append(
            f"SSH connection: {request.runtime_inputs.ssh_host}:{ssh_port} as {ssh_user}"
        )
    if request.runtime_inputs.remote_rdb_path:
        context_lines.append(f"Remote RDB path override: {request.runtime_inputs.remote_rdb_path}")

    if request.runtime_inputs.mysql_host:
        context_lines.append(
            f"MySQL connection: {request.runtime_inputs.mysql_host}:"
            f"{request.runtime_inputs.mysql_port}"
        )
    if request.runtime_inputs.mysql_table:
        context_lines.append(f"MySQL table: {request.runtime_inputs.mysql_table}")
    if request.runtime_inputs.mysql_query:
        context_lines.append(f"MySQL query: {request.runtime_inputs.mysql_query}")

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
                },
            )
            response = approval_handler.request_approval(request)
            if response.status is ApprovalStatus.APPROVED:
                decisions.append({"type": "approve"})
            else:
                return None
    return {"decisions": decisions}


def _build_remote_rdb_interrupt_description(request: NormalizedRequest):
    target = (
        f"{request.runtime_inputs.redis_host}:{request.runtime_inputs.redis_port}"
        if request.runtime_inputs.redis_host
        else "unknown target"
    )
    ssh_target = (
        f"{request.runtime_inputs.ssh_host}:{request.runtime_inputs.ssh_port or 22}"
        if request.runtime_inputs.ssh_host
        else "same as Redis host"
    )

    def describe_remote_rdb_fetch_interrupt(
        tool_call: dict[str, Any],
        state: Any,
        runtime: Any,
    ) -> str:
        args = tool_call.get("args", {})
        profile_name = args.get("profile_name", request.rdb_overrides.profile_name or "generic")
        output_mode = args.get("output_mode", request.runtime_inputs.output_mode or "summary")
        report_format = args.get("report_format", request.runtime_inputs.report_format or output_mode)
        output_path = args.get("output_path") or request.runtime_inputs.output_path or "stdout"
        return (
            "Remote RDB acquisition requires human approval.\n\n"
            f"Target Redis: {target}\n"
            f"SSH target: {ssh_target}\n"
            "The agent wants to fetch and analyze a remote Redis RDB.\n"
            f"Profile: {profile_name}\n"
            f"Output mode: {output_mode}\n"
            f"Report format: {report_format}\n"
            f"Output path: {output_path}\n"
            "Approve only if remote RDB retrieval is allowed for this target."
        )

    return describe_remote_rdb_fetch_interrupt


def _build_mysql_staging_interrupt_description(request: NormalizedRequest):
    mysql_target = (
        f"{request.runtime_inputs.mysql_host}:{request.runtime_inputs.mysql_port}"
        if request.runtime_inputs.mysql_host
        else "unknown MySQL target"
    )

    def describe_mysql_staging_interrupt(
        tool_call: dict[str, Any],
        state: Any,
        runtime: Any,
    ) -> str:
        args = tool_call.get("args", {})
        table_name = args.get("table_name", "unknown")
        return (
            "MySQL staging write requires human approval.\n\n"
            f"Target MySQL: {mysql_target}\n"
            f"Staging table: {table_name}\n"
            "The agent wants to write parsed RDB rows into MySQL.\n"
            "Approve only if MySQL write access is allowed for this target."
        )

    return describe_mysql_staging_interrupt
