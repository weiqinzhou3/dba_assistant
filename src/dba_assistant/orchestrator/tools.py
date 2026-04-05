"""Unified tool registry for the orchestrator.

All tools the Deep Agent can invoke are built here.  Tools are closures
so that connection credentials and request context
are captured at construction time — the LLM never sees raw secrets.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from dba_assistant.adaptors.mysql_adaptor import MySQLAdaptor, MySQLConnectionConfig
from dba_assistant.adaptors.redis_adaptor import (
    DEFAULT_CONFIG_PATTERN,
    DEFAULT_SLOWLOG_LENGTH,
    RedisAdaptor,
    RedisConnectionConfig,
)
from dba_assistant.adaptors.ssh_adaptor import SSHAdaptor, SSHConnectionConfig
from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides
from dba_assistant.core.reporter.types import OutputMode, ReportFormat, ReportOutputConfig
from dba_assistant.capabilities.redis_rdb_analysis.remote_input import discover_remote_rdb
from dba_assistant.tools.analyze_rdb import analyze_rdb_tool
from dba_assistant.tools.mysql_tools import (
    load_preparsed_dataset_from_mysql as _load_dataset,
    mysql_read_query as _mysql_read,
    stage_rdb_rows_to_mysql as _stage_rows,
)


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------

def build_all_tools(
    request: NormalizedRequest,
    *,
    connection: RedisConnectionConfig | None = None,
    mysql_connection: MySQLConnectionConfig | None = None,
    remote_rdb_state: dict[str, Any] | None = None,
) -> list:
    """Build the complete tool list available to the unified agent."""
    tools: list = []
    mysql_adaptor = MySQLAdaptor() if mysql_connection is not None else None

    # Local RDB analysis (always available)
    tools.append(
        _make_analyze_local_rdb_tool(
            request,
            mysql_adaptor=mysql_adaptor,
            mysql_connection=mysql_connection,
        )
    )
    tools.append(
        _make_analyze_preparsed_dataset_tool(
            request,
            mysql_adaptor=mysql_adaptor,
            mysql_connection=mysql_connection,
        )
    )

    # Redis inspection & remote-RDB tools (only when connection info is present)
    if connection is not None:
        adaptor = RedisAdaptor()
        shared_remote_rdb_state = remote_rdb_state if remote_rdb_state is not None else {}
        tools.extend(_make_redis_inspection_tools(adaptor, connection))
        tools.append(
            _make_discover_remote_rdb_tool(
                adaptor,
                connection,
                remote_rdb_state=shared_remote_rdb_state,
            )
        )
        tools.extend(
            _make_remote_rdb_fetch_tools(
                request,
                adaptor,
                connection,
                remote_rdb_state=shared_remote_rdb_state,
                mysql_adaptor=mysql_adaptor,
                mysql_connection=mysql_connection,
            )
        )

    # MySQL tools (only when MySQL connection info is present)
    if mysql_connection is not None:
        assert mysql_adaptor is not None
        tools.extend(_make_mysql_tools(mysql_adaptor, mysql_connection))

    return tools


# ---------------------------------------------------------------------------
# Local RDB analysis (Phase 3)
# ---------------------------------------------------------------------------

def _make_analyze_local_rdb_tool(
    request: NormalizedRequest,
    *,
    mysql_adaptor: MySQLAdaptor | None = None,
    mysql_connection: MySQLConnectionConfig | None = None,
):
    """Combined analyze + report tool for local RDB files."""

    analysis_service = _make_phase3_analysis_service(
        mysql_adaptor=mysql_adaptor,
        mysql_connection=mysql_connection,
    )

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

        try:
            analysis = analyze_rdb_tool(
                prompt=request.prompt,
                input_paths=paths,
                input_kind=request.runtime_inputs.input_kind or "local_rdb",
                profile_name=profile_name,
                path_mode=request.runtime_inputs.path_mode or request.rdb_overrides.route_name or "auto",
                profile_overrides=overrides,
                service=analysis_service,
            )
        except ValueError as exc:
            return f"Error: {exc}"

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


def _make_analyze_preparsed_dataset_tool(
    request: NormalizedRequest,
    *,
    mysql_adaptor: MySQLAdaptor | None = None,
    mysql_connection: MySQLConnectionConfig | None = None,
):
    """Analyze preparsed datasets from local files or MySQL-backed sources."""

    analysis_service = _make_phase3_analysis_service(
        mysql_adaptor=mysql_adaptor,
        mysql_connection=mysql_connection,
    )

    def analyze_preparsed_dataset(
        input_paths: str = "",
        mysql_table: str = "",
        mysql_query: str = "",
        profile_name: str = "generic",
        output_mode: str = "summary",
        report_format: str = "summary",
        output_path: str = "",
        focus_prefixes: str = "",
    ) -> str:
        overrides: dict[str, object] = {}
        if focus_prefixes:
            overrides["focus_prefixes"] = tuple(
                p.strip() for p in focus_prefixes.split(",") if p.strip()
            )
        if request.rdb_overrides.top_n:
            overrides["top_n"] = dict(request.rdb_overrides.top_n)

        effective_mysql_table = mysql_table or request.runtime_inputs.mysql_table
        effective_mysql_query = mysql_query or request.runtime_inputs.mysql_query

        if effective_mysql_table or effective_mysql_query or request.runtime_inputs.input_kind == "preparsed_mysql":
            sources = [effective_mysql_table or effective_mysql_query or "mysql:dataset"]
            input_kind = "preparsed_mysql"
        else:
            sources = [Path(p.strip()) for p in input_paths.split(",") if p.strip()]
            input_kind = request.runtime_inputs.input_kind or "precomputed"
            if not sources:
                return "Error: no preparsed dataset source provided."

        try:
            analysis = analyze_rdb_tool(
                prompt=request.prompt,
                input_paths=sources,
                input_kind=input_kind,
                profile_name=profile_name,
                path_mode=request.runtime_inputs.path_mode or request.rdb_overrides.route_name or "auto",
                profile_overrides=overrides,
                mysql_table=effective_mysql_table,
                mysql_query=effective_mysql_query,
                service=analysis_service,
            )
        except ValueError as exc:
            return f"Error: {exc}"

        return _render_analysis_output(
            analysis,
            output_mode=output_mode,
            report_format=report_format,
            output_path=Path(output_path) if output_path else request.runtime_inputs.output_path,
        )

    return _named_tool(
        analyze_preparsed_dataset,
        "analyze_preparsed_dataset",
        (
            "Analyze a preparsed dataset and generate a report. "
            "Supports local JSON datasets or MySQL-backed preparsed datasets. "
            "Parameters: input_paths (comma-separated local dataset paths), mysql_table, mysql_query, "
            "profile_name, output_mode, report_format, output_path, focus_prefixes."
        ),
    )


# ---------------------------------------------------------------------------
# Remote RDB discovery + HITL fetch (Phase 3 extension)
# ---------------------------------------------------------------------------

def _make_discover_remote_rdb_tool(
    adaptor: RedisAdaptor,
    connection: RedisConnectionConfig,
    *,
    remote_rdb_state: dict[str, Any] | None = None,
):
    """Read-only remote RDB discovery — no approval required."""

    def discover_remote_rdb_tool() -> str:
        try:
            discovery = discover_remote_rdb_snapshot(
                adaptor,
                connection,
                remote_rdb_state=remote_rdb_state,
            )
        except Exception as exc:  # noqa: BLE001
            return f"Discovery failed: {exc}"

        import json
        return json.dumps(
            {
                "redis_dir": discovery.get("redis_dir"),
                "dbfilename": discovery.get("dbfilename"),
                "rdb_path": discovery.get("rdb_path"),
                "rdb_path_source": discovery.get("rdb_path_source", "discovered"),
                "lastsave": discovery.get("lastsave"),
                "bgsave_in_progress": discovery.get("bgsave_in_progress"),
                "approval_required": True,
                "next_step": "Call fetch_remote_rdb_via_ssh to fetch the RDB after human approval.",
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
            "After discovery, call fetch_remote_rdb_via_ssh to proceed."
        ),
    )


def _make_remote_rdb_fetch_tools(
    request: NormalizedRequest,
    adaptor: RedisAdaptor,
    connection: RedisConnectionConfig,
    *,
    remote_rdb_state: dict[str, Any] | None = None,
    mysql_adaptor: MySQLAdaptor | None = None,
    mysql_connection: MySQLConnectionConfig | None = None,
):
    """Remote RDB fetch + analysis tools protected by Deep Agent interrupt_on."""

    analysis_service = _make_phase3_analysis_service(
        mysql_adaptor=mysql_adaptor,
        mysql_connection=mysql_connection,
    )

    def _fetch_remote_and_continue(
        profile_name: str = "generic",
        output_mode: str = "summary",
        report_format: str = "summary",
        output_path: str = "",
        acquisition_mode: str = "",
    ) -> str:
        try:
            discovery = discover_remote_rdb_snapshot(
                adaptor,
                connection,
                remote_rdb_state=remote_rdb_state,
            )
        except Exception as exc:  # noqa: BLE001
            return f"Remote RDB discovery failed: {exc}"

        acquisition_plan = resolve_remote_rdb_acquisition_plan(
            request,
            discovery,
            acquisition_mode=acquisition_mode,
        )
        if acquisition_plan["acquisition_mode"] == "fresh_snapshot":
            try:
                discovery = ensure_remote_rdb_snapshot(
                    adaptor,
                    connection,
                    discovery=discovery,
                    remote_rdb_state=remote_rdb_state,
                )
            except Exception as exc:  # noqa: BLE001
                return f"Latest remote RDB snapshot failed: {exc}"

        fetched_path = _fetch_remote_rdb_via_ssh(
            request=request,
            connection=connection,
            discovery=discovery,
        )
        if isinstance(fetched_path, str):
            return fetched_path

        return _render_remote_rdb_analysis(
            request=request,
            local_path=fetched_path,
            connection=connection,
            profile_name=profile_name,
            output_mode=output_mode,
            report_format=report_format,
            output_path=output_path,
            analysis_service=analysis_service,
        )

    def fetch_remote_rdb_via_ssh(
        profile_name: str = "generic",
        output_mode: str = "summary",
        report_format: str = "summary",
        output_path: str = "",
        acquisition_mode: str = "",
    ) -> str:
        return _fetch_remote_and_continue(
            profile_name=profile_name,
            output_mode=output_mode,
            report_format=report_format,
            output_path=output_path,
            acquisition_mode=acquisition_mode,
        )

    canonical_tool = _named_tool(
        fetch_remote_rdb_via_ssh,
        "fetch_remote_rdb_via_ssh",
        (
            "Fetch a remote Redis RDB over SSH, store it in a local temporary artifact, "
            "then continue into the unified Phase 3 analysis chain. "
            "REQUIRES HUMAN APPROVAL before proceeding. "
            "Use after discover_remote_rdb. "
            "If remote_rdb_path is not already overridden by the user, this tool must auto-discover "
            "Redis dir and dbfilename by querying Redis directly instead of asking the user for dir. "
            "Parameters: profile_name, output_mode, report_format, output_path, "
            "acquisition_mode ('existing' or 'fresh_snapshot'). "
            "SSH credentials come from shared request context only."
        ),
    )
    return [canonical_tool]


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
# MySQL tools (Phase 3.2)
# ---------------------------------------------------------------------------

def _make_mysql_tools(
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
) -> list:
    """Build the MySQL capability tools."""

    def mysql_read_query(sql: str) -> str:
        return _mysql_read(adaptor, config, sql)

    def load_preparsed_dataset_from_mysql(table_name: str, limit: str = "100000") -> str:
        return _load_dataset(adaptor, config, table_name, limit=int(limit))

    def stage_rdb_rows_to_mysql(table_name: str, rows_json: str) -> str:
        rows = json.loads(rows_json)
        return _stage_rows(adaptor, config, table_name, rows)

    return [
        _named_tool(
            mysql_read_query,
            "mysql_read_query",
            "Execute a bounded read-only SQL query against MySQL and return the result as JSON. "
            "Parameter: sql (the SQL query string).",
        ),
        _named_tool(
            load_preparsed_dataset_from_mysql,
            "load_preparsed_dataset_from_mysql",
            "Load a preparsed dataset from a MySQL table and return it as JSON. "
            "Parameters: table_name (the table to read), limit (max rows, default 100000).",
        ),
        _named_tool(
            stage_rdb_rows_to_mysql,
            "stage_rdb_rows_to_mysql",
            "Stage parsed RDB rows into a MySQL table for database-backed aggregation. "
            "REQUIRES HUMAN APPROVAL — this is a write operation. "
            "Parameters: table_name (staging table name), rows_json (JSON array of row objects).",
        ),
    ]


def _make_phase3_analysis_service(
    *,
    mysql_adaptor: MySQLAdaptor | None,
    mysql_connection: MySQLConnectionConfig | None,
):
    if mysql_adaptor is None or mysql_connection is None:
        return None

    def run_analysis(request):
        from dba_assistant.capabilities.redis_rdb_analysis.service import analyze_rdb as _analyze_rdb

        return _analyze_rdb(
            request,
            profile=None,
            remote_discovery=lambda *_args, **_kwargs: {},
            mysql_read_query=lambda sql: json.loads(
                _mysql_read(mysql_adaptor, mysql_connection, sql)
            ),
            stage_rdb_rows_to_mysql=lambda table_name, rows: json.loads(
                _stage_rows(mysql_adaptor, mysql_connection, table_name, rows)
            ),
            load_preparsed_dataset_from_mysql=lambda table_name: json.loads(
                _load_dataset(mysql_adaptor, mysql_connection, table_name)
            ),
        )

    return run_analysis


def _fetch_remote_rdb_via_ssh(
    *,
    request: NormalizedRequest,
    connection: RedisConnectionConfig,
    discovery: dict[str, object],
) -> Path | str:
    resolution = resolve_remote_rdb_fetch_plan(request, discovery)
    target_path = resolution["remote_rdb_path"]
    if not target_path:
        return "Remote RDB discovery did not return a usable rdb_path."

    ssh_config = SSHConnectionConfig(
        host=request.runtime_inputs.ssh_host or connection.host,
        port=int(request.runtime_inputs.ssh_port or 22),
        username=request.runtime_inputs.ssh_username or None,
        password=request.secrets.ssh_password or None,
    )
    local_dir = Path(tempfile.mkdtemp(prefix="dba-assistant-remote-rdb-"))
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
) -> dict[str, object]:
    if remote_rdb_state is not None and not force_refresh:
        cached = remote_rdb_state.get("discovery")
        if isinstance(cached, dict):
            return cached

    discovery = discover_remote_rdb(adaptor, connection)
    if remote_rdb_state is not None:
        remote_rdb_state["discovery"] = discovery
    return discovery


def resolve_remote_rdb_fetch_plan(
    request: NormalizedRequest,
    discovery: dict[str, object] | None,
    *,
    remote_rdb_path: str = "",
) -> dict[str, str]:
    user_override_path = ""
    if request.runtime_inputs.remote_rdb_path_source == "user_override":
        user_override_path = str(request.runtime_inputs.remote_rdb_path or "").strip()
    if user_override_path:
        return {
            "remote_rdb_path": user_override_path,
            "remote_rdb_path_source": "user_override",
        }

    discovered_path = str((discovery or {}).get("rdb_path") or "").strip()
    discovered_source = str((discovery or {}).get("rdb_path_source") or "discovered").strip()
    if discovered_path:
        return {
            "remote_rdb_path": discovered_path,
            "remote_rdb_path_source": discovered_source or "discovered",
        }

    fallback_path = ""
    fallback_source = ""
    if request.runtime_inputs.remote_rdb_path:
        fallback_path = str(request.runtime_inputs.remote_rdb_path).strip()
        fallback_source = str(
            request.runtime_inputs.remote_rdb_path_source or "fallback_default"
        ).strip()
    elif remote_rdb_path:
        fallback_path = str(remote_rdb_path).strip()
        fallback_source = "fallback_default"

    return {
        "remote_rdb_path": fallback_path,
        "remote_rdb_path_source": fallback_source or "fallback_default",
    }


def resolve_remote_rdb_acquisition_plan(
    request: NormalizedRequest,
    discovery: dict[str, object] | None,
    *,
    acquisition_mode: str = "",
) -> dict[str, str]:
    mode = (acquisition_mode or "").strip() or (
        "fresh_snapshot" if request.runtime_inputs.require_fresh_rdb_snapshot else "existing"
    )
    if mode not in {"existing", "fresh_snapshot"}:
        mode = "existing"
    path_plan = resolve_remote_rdb_fetch_plan(request, discovery)
    return {
        "acquisition_mode": mode,
        "bgsave_required": "yes" if mode == "fresh_snapshot" else "no",
        "redis_dir": str((discovery or {}).get("redis_dir") or "").strip(),
        "dbfilename": str((discovery or {}).get("dbfilename") or "").strip(),
        **path_plan,
    }


def ensure_remote_rdb_snapshot(
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
        adaptor.bgsave(connection)
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
        remote_rdb_state["discovery"] = refreshed
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
    if request.rdb_overrides.top_n:
        overrides["top_n"] = dict(request.rdb_overrides.top_n)

    try:
        analysis = analyze_rdb_tool(
            prompt=request.prompt,
            input_paths=[local_path],
            input_kind="local_rdb",
            profile_name=profile_name,
            path_mode=request.runtime_inputs.path_mode or request.rdb_overrides.route_name or "auto",
            profile_overrides=overrides,
            service=analysis_service,
        )
    except ValueError as exc:
        return f"Error: {exc}"

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


def _render_analysis_output(
    analysis,
    *,
    output_mode: str,
    report_format: str,
    output_path: Path | None,
) -> str:
    from dba_assistant.core.reporter.generate_analysis_report import (
        generate_analysis_report as _generate,
    )

    fmt = ReportFormat.SUMMARY if report_format == "summary" else ReportFormat.DOCX
    if fmt is ReportFormat.DOCX and output_path is None:
        return "Error: DOCX output requires an output path."

    config = ReportOutputConfig(
        mode=OutputMode.SUMMARY if output_mode == "summary" else OutputMode.REPORT,
        format=fmt,
        output_path=output_path,
        template_name="rdb-analysis",
    )
    artifact = _generate(analysis, config)
    if artifact.content is not None:
        return artifact.content
    if artifact.output_path is not None:
        return str(artifact.output_path)
    return "Analysis complete but no output generated."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _named_tool(func: Any, name: str, description: str) -> Any:
    func.__name__ = name
    func.__doc__ = description
    return func
