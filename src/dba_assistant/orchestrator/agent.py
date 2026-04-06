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
from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig
from dba_assistant.application.request_models import (
    DEFAULT_LOOPBACK_HOST,
    DEFAULT_MYSQL_DATABASE,
    DEFAULT_MYSQL_USER,
    NormalizedRequest,
)
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
from dba_assistant.capabilities.redis_rdb_analysis.remote_input import RemoteRedisDiscoveryError
from dba_assistant.orchestrator.tools import (
    build_all_tools,
    resolve_remote_rdb_acquisition_plan,
    discover_remote_rdb_snapshot,
    resolve_remote_rdb_fetch_plan,
)

APPROVAL_REQUEST_PHRASES = (
    "do you approve",
    "please confirm",
    "now i need your approval",
    "need your approval",
)

SYSTEM_PROMPT = """\
You are DBA Assistant, a specialized database administration assistant focused on Redis diagnostics and analysis.

Available capabilities (use the corresponding tool):
1. **analyze_local_rdb** — Analyze local Redis RDB dump files. Use when local .rdb file paths are provided.
2. **analyze_preparsed_dataset** — Analyze a preparsed dataset from local JSON or MySQL-backed source.
3. **discover_remote_rdb** — Read-only discovery of remote Redis RDB location and persistence info.
4. **fetch_remote_rdb_via_ssh** — Fetch a remote RDB via SSH (requires human approval) and, when needed, trigger BGSAVE for a fresh snapshot before analysis.
5. **redis_ping / redis_info / redis_config_get / redis_slowlog_get / redis_client_list** — \
Live read-only Redis inspection.
6. **mysql_read_query** — Execute a bounded read-only SQL query against MySQL.
7. **load_preparsed_dataset_from_mysql** — Load a preparsed dataset from a MySQL table.
8. **stage_rdb_rows_to_mysql** — Stage parsed RDB rows into MySQL for database-backed analysis \
(requires human approval).

Rules:
- If explicit local input paths are already present in context, treat them as authoritative host filesystem paths.
- For explicit local `.rdb` paths, do not use filesystem browsing tools to verify, replace, or search for alternatives before analysis.
- Do not claim that an explicit local path is missing unless analyze_local_rdb itself returns that host-side validation error.
- When explicit local `.rdb` paths are provided, call analyze_local_rdb directly rather than exploring the repository for sample files.
- Redis inspection tools are read-only. Remote fetch remains approval-gated, and fresh_snapshot may trigger approved BGSAVE before fetch.
- For remote RDB: call discover_remote_rdb first, then fetch_remote_rdb_via_ssh.
- When the user asks for the latest/fresh RDB snapshot, use fetch_remote_rdb_via_ssh with acquisition_mode='fresh_snapshot'.
- For approval-gated tools such as fetch_remote_rdb_via_ssh and stage_rdb_rows_to_mysql, never ask the user for approval in plain text.
- fetch_remote_rdb_via_ssh collects approval through runtime interrupt_on.
- stage_rdb_rows_to_mysql collects approval through the shared human approval handler before writing.
- In single-run CLI flows, do not end with text like "Do you approve?" or "Please confirm" when the next step should be an approval-gated tool.
- If Redis connection details are available and the user did not provide remote_rdb_path, do not ask the user for dir/dbfilename first; discover them by executing Redis discovery.
- If Redis discovery fails, surface the exact failure reason and stage. Do not paraphrase it as missing dir/dbfilename unless discovery explicitly returned missing_dir/missing_dbfilename.
- Only ask the user for dir/dbfilename/remote_rdb_path when Redis discovery explicitly returned missing_dir/missing_dbfilename and you need the user to override it.
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
    remote_rdb_state: dict[str, Any] = {}

    tools = _build_all_tools_compatible(
        request,
        connection=connection,
        mysql_connection=mysql_connection,
        remote_rdb_state=remote_rdb_state,
        approval_handler=approval_handler,
    )

    model = build_model(config.model)
    backend = build_runtime_backend()
    checkpointer = build_runtime_checkpointer()

    interrupt_on: dict[str, Any] = {
        "fetch_remote_rdb_via_ssh": {
            "allowed_decisions": ["approve", "reject"],
            "description": _build_remote_rdb_interrupt_description(
                request,
                path_resolution_resolver=_make_remote_rdb_path_resolution_resolver(
                    request,
                    connection=connection,
                    remote_rdb_state=remote_rdb_state,
                ),
            ),
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
        system_prompt=SYSTEM_PROMPT,
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
) -> str:
    """Run the unified Deep Agent and return the final output."""
    shortcut = _run_explicit_local_rdb_analysis(request, approval_handler=approval_handler)
    if shortcut is not None:
        return shortcut

    agent = build_unified_agent(request, config, approval_handler)
    user_message = _build_user_message(request)
    run_config = {"configurable": {"thread_id": f"dba-assistant-{uuid4()}"}}
    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_message}]},
        config=run_config,
    )
    approval_retry_count = 0

    while True:
        while interrupts := _extract_interrupts(result):
            resume_payload = _handle_interrupts(interrupts, approval_handler)
            if resume_payload is None:
                return "Operation denied by user."
            result = agent.invoke(Command(resume=resume_payload), config=run_config)

        if not _should_force_runtime_approval(agent, request, result):
            break
        if approval_retry_count >= 1:
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

    return extract_agent_output(result)


def _run_explicit_local_rdb_analysis(
    request: NormalizedRequest,
    *,
    approval_handler: HumanApprovalHandler,
) -> str | None:
    if not _has_explicit_local_rdb_inputs(request):
        return None

    mysql_connection = _build_mysql_connection(request)
    tools = _build_all_tools_compatible(
        request,
        mysql_connection=mysql_connection,
        approval_handler=approval_handler,
    )
    analyze_tool = next(
        (tool for tool in tools if getattr(tool, "__name__", "") == "analyze_local_rdb"),
        None,
    )
    if analyze_tool is None:
        raise RuntimeError("analyze_local_rdb tool is unavailable for explicit local RDB inputs.")

    profile_name = request.rdb_overrides.profile_name or "generic"
    output_mode = request.runtime_inputs.output_mode or "summary"
    report_format = request.runtime_inputs.report_format or "summary"
    output_path = str(request.runtime_inputs.output_path) if request.runtime_inputs.output_path else ""
    focus_prefixes = ",".join(request.rdb_overrides.focus_prefixes)
    input_paths = ",".join(str(path) for path in request.runtime_inputs.input_paths)
    return analyze_tool(
        input_paths=input_paths,
        profile_name=profile_name,
        output_mode=output_mode,
        report_format=report_format,
        output_path=output_path,
        focus_prefixes=focus_prefixes,
    )


def _has_explicit_local_rdb_inputs(request: NormalizedRequest) -> bool:
    paths = request.runtime_inputs.input_paths
    if not paths:
        return False
    if request.runtime_inputs.input_kind == "local_rdb":
        return all(str(path).lower().endswith(".rdb") for path in paths)
    if request.runtime_inputs.redis_host is not None:
        return False
    return all(str(path).lower().endswith(".rdb") for path in paths)


def _build_all_tools_compatible(
    request: NormalizedRequest,
    **kwargs: Any,
) -> list:
    try:
        return build_all_tools(request, **kwargs)
    except TypeError as exc:
        if "approval_handler" not in str(exc):
            raise
        compatible_kwargs = dict(kwargs)
        compatible_kwargs.pop("approval_handler", None)
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


def _make_remote_rdb_path_resolution_resolver(
    request: NormalizedRequest,
    *,
    connection: RedisConnectionConfig | None,
    remote_rdb_state: dict[str, Any],
):
    if connection is None:
        return lambda tool_args: resolve_remote_rdb_acquisition_plan(
            request,
            None,
            acquisition_mode=str(tool_args.get("acquisition_mode", "")),
        )

    adaptor = RedisAdaptor()

    def resolve_from_discovery(tool_args: dict[str, Any]) -> dict[str, str]:
        try:
            discovery = discover_remote_rdb_snapshot(
                adaptor,
                connection,
                remote_rdb_state=remote_rdb_state,
            )
        except RemoteRedisDiscoveryError as exc:
            resolution = resolve_remote_rdb_acquisition_plan(
                request,
                None,
                acquisition_mode=str(tool_args.get("acquisition_mode", "")),
            )
            resolution["discovery_status"] = "failed"
            resolution["discovery_error_stage"] = exc.stage
            resolution["discovery_error_kind"] = exc.kind
            resolution["discovery_error_message"] = exc.message
            resolution["redis_password_supplied"] = "yes" if exc.redis_password_supplied else "no"
            resolution["bgsave_required"] = "blocked"
            if not resolution.get("remote_rdb_path"):
                resolution["remote_rdb_path_source"] = "unresolved"
            return resolution
        except Exception as exc:  # noqa: BLE001
            resolution = resolve_remote_rdb_acquisition_plan(
                request,
                None,
                acquisition_mode=str(tool_args.get("acquisition_mode", "")),
            )
            resolution["discovery_status"] = "failed"
            resolution["discovery_error_stage"] = "discover_remote_rdb"
            resolution["discovery_error_kind"] = "unknown_error"
            resolution["discovery_error_message"] = str(exc)
            resolution["redis_password_supplied"] = "yes" if request.secrets.redis_password else "no"
            resolution["bgsave_required"] = "blocked"
            if not resolution.get("remote_rdb_path"):
                resolution["remote_rdb_path_source"] = "unresolved"
            return resolution
        return {
            **resolve_remote_rdb_acquisition_plan(
                request,
                discovery,
                acquisition_mode=str(tool_args.get("acquisition_mode", "")),
            ),
            "discovery_status": "succeeded",
        }

    return resolve_from_discovery


def _build_remote_rdb_interrupt_description(
    request: NormalizedRequest,
    *,
    path_resolution_resolver=None,
):
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
        resolution = (
            path_resolution_resolver(args)
            if path_resolution_resolver is not None
            else resolve_remote_rdb_acquisition_plan(
                request,
                None,
                acquisition_mode=str(args.get("acquisition_mode", "")),
            )
        )
        profile_name = args.get("profile_name", request.rdb_overrides.profile_name or "generic")
        output_mode = args.get("output_mode", request.runtime_inputs.output_mode or "summary")
        report_format = args.get("report_format", request.runtime_inputs.report_format or output_mode)
        output_path = args.get("output_path") or request.runtime_inputs.output_path or "stdout"
        redis_dir = resolution.get("redis_dir") or "unresolved"
        dbfilename = resolution.get("dbfilename") or "unresolved"
        remote_rdb_path = resolution.get("remote_rdb_path") or "unresolved"
        remote_rdb_path_source = resolution.get("remote_rdb_path_source") or "fallback_default"
        acquisition_mode = resolution.get("acquisition_mode") or "existing"
        bgsave_required = resolution.get("bgsave_required") or "no"
        discovery_status = resolution.get("discovery_status") or (
            "succeeded" if remote_rdb_path_source == "discovered" else "not_run"
        )
        discovery_error_stage = resolution.get("discovery_error_stage") or ""
        discovery_error_kind = resolution.get("discovery_error_kind") or ""
        discovery_error_message = resolution.get("discovery_error_message") or ""
        redis_password_supplied = resolution.get("redis_password_supplied") or (
            "yes" if request.secrets.redis_password else "no"
        )
        ssh_username = request.runtime_inputs.ssh_username or "unspecified"
        lines = [
            "Remote RDB acquisition requires human approval.",
            "",
            f"Target Redis: {target}",
            f"SSH target: {ssh_target}",
            f"SSH username: {ssh_username}",
            f"Discovery status: {discovery_status}",
        ]
        if discovery_status == "failed":
            lines.extend(
                [
                    f"Discovery failure stage: {discovery_error_stage or 'unknown'}",
                    f"Discovery failure kind: {discovery_error_kind or 'unknown_error'}",
                    f"Discovery failure message: {discovery_error_message or 'No error details available.'}",
                    f"Redis password supplied: {redis_password_supplied}",
                    f"Remote RDB path: {remote_rdb_path}",
                    f"remote_rdb_path_source: {remote_rdb_path_source}",
                    f"Acquisition mode: {acquisition_mode}",
                    f"BGSAVE required: {bgsave_required}",
                ]
            )
        else:
            lines.extend(
                [
                    f"Redis dir: {redis_dir}",
                    f"Redis dbfilename: {dbfilename}",
                    f"Remote RDB path: {remote_rdb_path}",
                    f"remote_rdb_path_source: {remote_rdb_path_source}",
                    f"Acquisition mode: {acquisition_mode}",
                    f"BGSAVE required: {bgsave_required}",
                ]
            )
        lines.extend(
            [
                "The agent wants to fetch and analyze a remote Redis RDB.",
                f"Profile: {profile_name}",
                f"Output mode: {output_mode}",
                f"Report format: {report_format}",
                f"Output path: {output_path}",
                "Approve only if remote RDB retrieval is allowed for this target.",
            ]
        )
        return "\n".join(lines)

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


def _mysql_context_requested(request: NormalizedRequest) -> bool:
    runtime = request.runtime_inputs
    return any(
        (
            runtime.mysql_host,
            runtime.mysql_user,
            runtime.mysql_database,
            runtime.mysql_table,
            runtime.mysql_query,
            request.secrets.mysql_password,
            runtime.input_kind == "preparsed_mysql",
            runtime.path_mode == "database_backed_analysis",
        )
    )


def _redis_context_requested(request: NormalizedRequest) -> bool:
    runtime = request.runtime_inputs
    if runtime.redis_host or request.secrets.redis_password:
        return True
    if runtime.input_kind == "remote_redis":
        return True
    if runtime.remote_rdb_path or runtime.require_fresh_rdb_snapshot or runtime.ssh_host:
        return True
    if runtime.input_paths:
        return False
    return "redis" in request.prompt.lower()
