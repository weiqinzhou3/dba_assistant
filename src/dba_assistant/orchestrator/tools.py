"""Unified tool registry for the orchestrator.

All tools the Deep Agent can invoke are built here.  Tools are closures
so that connection credentials and request context
are captured at construction time — the LLM never sees raw secrets.
"""
from __future__ import annotations

from pathlib import Path

from dba_assistant.adaptors.redis_adaptor import (
    DEFAULT_CONFIG_PATTERN,
    DEFAULT_SLOWLOG_LENGTH,
    RedisAdaptor,
    RedisConnectionConfig,
)
from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides
from dba_assistant.core.reporter.types import OutputMode, ReportFormat, ReportOutputConfig
from dba_assistant.skills.redis_rdb_analysis.remote_input import discover_remote_rdb
from dba_assistant.tools.analyze_rdb import analyze_rdb_tool


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

def build_all_tools(
    request: NormalizedRequest,
    *,
    connection: RedisConnectionConfig | None = None,
) -> list:
    """Build the complete tool list available to the unified agent."""
    tools: list = []

    # Local RDB analysis (always available)
    tools.append(_make_analyze_local_rdb_tool(request))

    # Redis inspection & remote-RDB tools (only when connection info is present)
    if connection is not None:
        adaptor = RedisAdaptor()
        tools.extend(_make_redis_inspection_tools(adaptor, connection))
        tools.append(_make_discover_remote_rdb_tool(adaptor, connection))
        tools.append(_make_fetch_and_analyze_remote_rdb_tool(adaptor, connection))

    return tools


# ---------------------------------------------------------------------------
# Local RDB analysis (Phase 3)
# ---------------------------------------------------------------------------

def _make_analyze_local_rdb_tool(request: NormalizedRequest):
    """Combined analyze + report tool for local RDB files."""

    def analyze_local_rdb(
        input_paths: str,
        profile_name: str = "generic",
        output_mode: str = "summary",
        report_format: str = "summary",
        output_path: str = "",
        focus_prefixes: str = "",
    ) -> str:
        paths = [Path(p.strip()) for p in input_paths.split(",") if p.strip()]
        if not paths:
            return "Error: no input paths provided."

        overrides: dict[str, object] = {}
        if focus_prefixes:
            overrides["focus_prefixes"] = tuple(
                p.strip() for p in focus_prefixes.split(",") if p.strip()
            )
        if request.rdb_overrides.top_n:
            overrides["top_n"] = dict(request.rdb_overrides.top_n)

        analysis = analyze_rdb_tool(
            prompt=request.prompt,
            input_paths=paths,
            profile_name=profile_name,
            path_mode=request.rdb_overrides.route_name or "auto",
            profile_overrides=overrides,
        )

        from dba_assistant.core.reporter.generate_analysis_report import (
            generate_analysis_report as _generate,
        )

        fmt = ReportFormat.SUMMARY if report_format == "summary" else ReportFormat.DOCX
        out = Path(output_path) if output_path else request.runtime_inputs.output_path
        if fmt is ReportFormat.DOCX and out is None:
            return "Error: DOCX output requires an output path."

        config = ReportOutputConfig(
            mode=OutputMode.SUMMARY if output_mode == "summary" else OutputMode.REPORT,
            format=fmt,
            output_path=out,
            template_name="rdb-analysis",
        )
        artifact = _generate(analysis, config)
        if artifact.content is not None:
            return artifact.content
        if artifact.output_path is not None:
            return str(artifact.output_path)
        return "Analysis complete but no output generated."

    return _named_tool(
        analyze_local_rdb,
        "analyze_local_rdb",
        (
            "Analyze local Redis RDB dump files and generate a report. "
            "Parameters: input_paths (comma-separated file paths), "
            "profile_name ('generic' or 'rcs'), "
            "output_mode ('summary' or 'report'), "
            "report_format ('summary' or 'docx'), "
            "output_path (file path, required for docx), "
            "focus_prefixes (optional, comma-separated key prefixes like 'cache:*,session:*')."
        ),
    )


# ---------------------------------------------------------------------------
# Remote RDB discovery + HITL fetch (Phase 3 extension)
# ---------------------------------------------------------------------------

def _make_discover_remote_rdb_tool(
    adaptor: RedisAdaptor,
    connection: RedisConnectionConfig,
):
    """Read-only remote RDB discovery — no approval required."""

    def discover_remote_rdb_tool() -> str:
        try:
            discovery = discover_remote_rdb(adaptor, connection)
        except Exception as exc:  # noqa: BLE001
            return f"Discovery failed: {exc}"

        import json
        return json.dumps(
            {
                "rdb_path": discovery.get("rdb_path"),
                "lastsave": discovery.get("lastsave"),
                "bgsave_in_progress": discovery.get("bgsave_in_progress"),
                "approval_required": True,
                "next_step": "Call fetch_and_analyze_remote_rdb to fetch the RDB after human approval.",
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
            "After discovery, call fetch_and_analyze_remote_rdb to proceed."
        ),
    )


def _make_fetch_and_analyze_remote_rdb_tool(
    adaptor: RedisAdaptor,
    connection: RedisConnectionConfig,
):
    """Remote RDB fetch + analysis tool protected by Deep Agent interrupt_on."""

    def fetch_and_analyze_remote_rdb(
        profile_name: str = "generic",
        output_mode: str = "summary",
        report_format: str = "summary",
        output_path: str = "",
    ) -> str:
        try:
            discovery = discover_remote_rdb(adaptor, connection)
        except Exception as exc:  # noqa: BLE001
            return f"Remote RDB discovery failed: {exc}"

        rdb_path = discovery.get("rdb_path", "unknown")
        return (
            f"Remote RDB is at {rdb_path} on {connection.host}. "
            "SSH-based fetch is not yet implemented. "
            "Please manually retrieve the file and re-run with --input <local_path>."
        )

    return _named_tool(
        fetch_and_analyze_remote_rdb,
        "fetch_and_analyze_remote_rdb",
        (
            "Fetch and analyze an RDB file from a remote Redis server. "
            "REQUIRES HUMAN APPROVAL before proceeding. "
            "Use after discover_remote_rdb to fetch the actual RDB file. "
            "Parameters: profile_name, output_mode, report_format, output_path."
        ),
    )


# ---------------------------------------------------------------------------
# Redis inspection tools (Phase 2)
# ---------------------------------------------------------------------------

def _make_redis_inspection_tools(
    adaptor: RedisAdaptor,
    connection: RedisConnectionConfig,
) -> list:
    """Build the five read-only Redis inspection tools."""

    def redis_ping() -> dict[str, object]:
        return adaptor.ping(connection)

    def redis_info(section: str | None = None) -> dict[str, object]:
        return adaptor.info(connection, section=section)

    def redis_config_get() -> dict[str, object]:
        return adaptor.config_get(connection, pattern=DEFAULT_CONFIG_PATTERN)

    def redis_slowlog_get() -> dict[str, object]:
        return adaptor.slowlog_get(connection, length=DEFAULT_SLOWLOG_LENGTH)

    def redis_client_list() -> dict[str, object]:
        return adaptor.client_list(connection)

    return [
        _named_tool(redis_ping, "redis_ping", "Ping Redis and return availability status."),
        _named_tool(redis_info, "redis_info", "Return read-only Redis INFO data. Optional parameter: section (e.g. 'memory', 'persistence', 'server')."),
        _named_tool(redis_config_get, "redis_config_get", "Return bounded Redis CONFIG GET probe (maxmemory, dir, dbfilename)."),
        _named_tool(redis_slowlog_get, "redis_slowlog_get", "Return bounded Redis SLOWLOG GET entries."),
        _named_tool(redis_client_list, "redis_client_list", "Return Redis client-list count."),
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _named_tool(func: Any, name: str, description: str) -> Any:
    func.__name__ = name
    func.__doc__ = description
    return func
