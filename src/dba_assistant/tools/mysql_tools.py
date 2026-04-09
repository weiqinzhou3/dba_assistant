"""MySQL capability tools for the unified Deep Agent."""
from __future__ import annotations

from dataclasses import dataclass
import inspect
import json
import logging
from time import perf_counter
from typing import Any

from dba_assistant.adaptors.mysql_adaptor import (
    MySQLAdaptor,
    MySQLConnectionConfig,
    MySQLOperationError,
)
from dba_assistant.capabilities.redis_rdb_analysis.profile_resolver import normalize_profile_top_n
from dba_assistant.capabilities.redis_rdb_analysis.types import EffectiveProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MySQLStagingSession:
    connection: MySQLConnectionConfig
    database_name: str
    table_name: str
    run_id: str
    batch_size: int
    created_database: bool = False
    created_table: bool = False
    defaulted_database: bool = False
    defaulted_table: bool = False
    cleanup_mode: str = "retain"


def mysql_read_query(
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    sql: str,
) -> str:
    rows = adaptor.read_query(config, sql)
    return json.dumps(rows, default=str)


def load_preparsed_dataset_from_mysql(
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    table_name: str,
    *,
    limit: int | str | None = 100_000,
) -> str:
    safe_table = _sanitize_identifier(table_name)
    sql = f"SELECT key_name, key_type, size_bytes, has_expiration, ttl_seconds FROM {safe_table} LIMIT {_normalize_limit(limit)}"
    rows = adaptor.read_query(config, sql)
    return json.dumps({"source": f"mysql:{table_name}", "rows": rows}, default=str)


def database_exists(
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    database_name: str,
) -> bool:
    sql = (
        "SELECT SCHEMA_NAME AS schema_name "
        "FROM INFORMATION_SCHEMA.SCHEMATA "
        f"WHERE SCHEMA_NAME = {_quote_string_literal(database_name)} "
        "LIMIT 1"
    )
    return bool(adaptor.read_query(_without_database(config), sql))


def table_exists(
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    table_name: str,
) -> bool:
    if not config.database:
        raise ValueError("MySQL table existence checks require a selected database.")
    sql = (
        "SELECT TABLE_NAME AS table_name "
        "FROM INFORMATION_SCHEMA.TABLES "
        f"WHERE TABLE_SCHEMA = {_quote_string_literal(config.database)} "
        f"AND TABLE_NAME = {_quote_string_literal(_sanitize_identifier_text(table_name))} "
        "LIMIT 1"
    )
    return bool(adaptor.read_query(config, sql))


def create_database(
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    database_name: str,
) -> int:
    admin_config = _without_database(config)
    sql = f"CREATE DATABASE IF NOT EXISTS {_sanitize_identifier(database_name)}"
    started = perf_counter()
    _log_mysql_staging_phase(
        config=admin_config,
        database_name=database_name,
        stage="create_database_start",
    )
    try:
        result = adaptor.execute_write(admin_config, sql)
    except MySQLOperationError as exc:
        wrapped = _relabel_mysql_operation_error(
            exc,
            config=admin_config,
            operation="create_database",
            summary="MySQL create database failed",
        )
        _log_mysql_staging_phase(
            config=admin_config,
            database_name=database_name,
            stage="create_database_error",
            elapsed_seconds=round(perf_counter() - started, 6),
            error=str(wrapped),
        )
        raise wrapped from exc
    _log_mysql_staging_phase(
        config=admin_config,
        database_name=database_name,
        stage="create_database_end",
        elapsed_seconds=round(perf_counter() - started, 6),
    )
    return result


def create_staging_table(
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    table_name: str,
) -> int:
    safe_table = _sanitize_identifier(table_name)
    # Stage once, analyze many times: keep only indexes that materially help MySQL-side analysis.
    sql = f"""
CREATE TABLE IF NOT EXISTS {safe_table} (
    stage_run_id VARCHAR(64) NOT NULL,
    source_file VARCHAR(1024) NOT NULL,
    key_name TEXT NOT NULL,
    key_type VARCHAR(64) NOT NULL,
    size_bytes BIGINT NOT NULL,
    has_expiration TINYINT(1) NOT NULL,
    ttl_seconds BIGINT NULL,
    INDEX idx_stage_run_id (stage_run_id),
    INDEX idx_stage_run_key_type (stage_run_id, key_type),
    INDEX idx_stage_run_size (stage_run_id, size_bytes),
    INDEX idx_stage_run_key_name_prefix (stage_run_id, key_name(191))
)
""".strip()
    started = perf_counter()
    _log_mysql_staging_phase(
        config=config,
        table_name=table_name,
        stage="create_table_start",
    )
    try:
        result = adaptor.execute_write(config, sql)
    except MySQLOperationError as exc:
        wrapped = _relabel_mysql_operation_error(
            exc,
            config=config,
            operation="create_table",
            table_name=table_name,
            summary="MySQL create table failed",
        )
        _log_mysql_staging_phase(
            config=config,
            table_name=table_name,
            stage="create_table_error",
            elapsed_seconds=round(perf_counter() - started, 6),
            error=str(wrapped),
        )
        raise wrapped from exc
    _log_mysql_staging_phase(
        config=config,
        table_name=table_name,
        stage="create_table_end",
        elapsed_seconds=round(perf_counter() - started, 6),
    )
    return result


def insert_staging_batch(
    adaptor: MySQLAdaptor,
    session: MySQLStagingSession,
    *,
    source_file: str,
    rows: list[dict[str, Any]],
    batch_number: int | None = None,
    cumulative_rows: int | None = None,
) -> int:
    if not rows:
        return 0

    safe_table = _sanitize_identifier(session.table_name)
    sql = (
        f"INSERT INTO {safe_table} "
        "(stage_run_id, source_file, key_name, key_type, size_bytes, has_expiration, ttl_seconds) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)"
    )
    params = [
        (
            session.run_id,
            source_file,
            str(row.get("key_name") or ""),
            str(row.get("key_type") or ""),
            _coerce_int(row.get("size_bytes")),
            1 if bool(row.get("has_expiration")) else 0,
            _coerce_optional_int(row.get("ttl_seconds")),
        )
        for row in rows
    ]
    started = perf_counter()

    def log_write_phase(event: str, payload: dict[str, Any]) -> None:
        _log_mysql_staging_phase(
            config=session.connection,
            database_name=session.database_name,
            table_name=session.table_name,
            mysql_stage_batch_size=session.batch_size,
            batch_number=batch_number,
            batch_rows=len(rows),
            cumulative_rows=cumulative_rows,
            stage=event,
            elapsed_seconds=payload.get("elapsed_seconds"),
            rowcount=payload.get("rowcount"),
            param_count=payload.get("param_count"),
            source_file=source_file,
            run_id=session.run_id,
        )

    try:
        result = _execute_write_with_optional_log_hook(
            adaptor,
            session.connection,
            sql,
            params=params,
            log_hook=log_write_phase,
        )
    except MySQLOperationError as exc:
        wrapped = _relabel_mysql_operation_error(
            exc,
            config=session.connection,
            operation="insert_batch",
            table_name=session.table_name,
            summary="MySQL insert batch failed",
        )
        _log_mysql_staging_phase(
            config=session.connection,
            database_name=session.database_name,
            table_name=session.table_name,
            mysql_stage_batch_size=session.batch_size,
            batch_number=batch_number,
            batch_rows=len(rows),
            cumulative_rows=cumulative_rows,
            stage="insert_batch_error",
            elapsed_seconds=round(perf_counter() - started, 6),
            error=str(wrapped),
            source_file=source_file,
            run_id=session.run_id,
        )
        raise wrapped from exc
    _log_mysql_staging_phase(
        config=session.connection,
        database_name=session.database_name,
        table_name=session.table_name,
        mysql_stage_batch_size=session.batch_size,
        batch_number=batch_number,
        batch_rows=len(rows),
        cumulative_rows=cumulative_rows,
        stage="insert_batch_end",
        elapsed_seconds=round(perf_counter() - started, 6),
        source_file=source_file,
        run_id=session.run_id,
    )
    return result


def stage_rdb_rows_to_mysql(
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    table_name: str,
    rows: list[dict[str, Any]],
    *,
    run_id: str = "manual",
    source_file: str = "manual",
) -> str:
    if not rows:
        return json.dumps({"staged": 0, "table": table_name, "run_id": run_id})

    create_staging_table(adaptor, config, table_name)
    session = MySQLStagingSession(
        connection=config,
        database_name=config.database or "",
        table_name=table_name,
        run_id=run_id,
        batch_size=len(rows),
    )
    count = insert_staging_batch(adaptor, session, source_file=source_file, rows=rows)
    return json.dumps(
        {
            "staged": count,
            "table": table_name,
            "database": config.database or "",
            "run_id": run_id,
            "source_file": source_file,
        }
    )


def analyze_staged_rdb_rows(
    adaptor: MySQLAdaptor,
    session: MySQLStagingSession,
    *,
    profile: EffectiveProfile,
    sample_rows: list[list[str]],
) -> dict[str, dict[str, object]]:
    safe_table = _sanitize_identifier(session.table_name)
    run_filter = f"stage_run_id = {_quote_string_literal(session.run_id)}"
    prefix_expr = (
        "CASE "
        "WHEN LOCATE(':', key_name) > 0 THEN CONCAT(SUBSTRING_INDEX(key_name, ':', 1), ':*') "
        "ELSE CONCAT(key_name, ':*') "
        "END"
    )
    allowed_ids = set(profile.sections)
    top_n_map = normalize_profile_top_n(profile.top_n)
    default_big_key_limit = top_n_map["top_big_keys"]
    focused_prefix_limit = top_n_map["focused_prefix_top_keys"]

    overall_row = _run_logged_analysis_query(
        adaptor,
        session,
        query_name="overall_summary",
        sql=(
            f"SELECT COUNT(*) AS total_keys, COALESCE(SUM(size_bytes), 0) AS total_bytes "
            f"FROM {safe_table} WHERE {run_filter}"
        ),
    )[0]
    total_keys = int(overall_row.get("total_keys") or 0)
    total_bytes = int(overall_row.get("total_bytes") or 0)
    total_samples = len(sample_rows)
    overall_summary = {
        "total_samples": total_samples,
        "total_keys": total_keys,
        "total_bytes": total_bytes,
    }

    type_rows = _run_logged_analysis_query(
        adaptor,
        session,
        query_name="key_type_summary",
        sql=(
            "SELECT key_type, COUNT(*) AS key_count, COALESCE(SUM(size_bytes), 0) AS memory_bytes "
            f"FROM {safe_table} WHERE {run_filter} "
            "GROUP BY key_type "
            "ORDER BY key_count DESC, memory_bytes DESC, key_type ASC"
        ),
    )
    counts = {str(row["key_type"]): int(row["key_count"]) for row in type_rows}
    memory_bytes = {str(row["key_type"]): int(row["memory_bytes"]) for row in type_rows}

    expiration_row = _run_logged_analysis_query(
        adaptor,
        session,
        query_name="expiration_summary",
        sql=(
            "SELECT "
            "COALESCE(SUM(CASE WHEN has_expiration = 1 THEN 1 ELSE 0 END), 0) AS expired_count, "
            "COALESCE(SUM(CASE WHEN has_expiration = 0 THEN 1 ELSE 0 END), 0) AS persistent_count "
            f"FROM {safe_table} WHERE {run_filter}"
        ),
    )[0]
    expired_count = int(expiration_row.get("expired_count") or 0)
    persistent_count = int(expiration_row.get("persistent_count") or 0)

    prefix_rows: list[dict[str, Any]] = []
    if "prefix_top_summary" in allowed_ids:
        prefix_rows = _run_logged_analysis_query(
            adaptor,
            session,
            query_name="prefix_top_summary",
            sql=(
                f"SELECT {prefix_expr} AS prefix_label, COUNT(*) AS key_count, "
                "COALESCE(SUM(size_bytes), 0) AS memory_bytes "
                f"FROM {safe_table} WHERE {run_filter} "
                "GROUP BY prefix_label "
                f"ORDER BY key_count DESC, memory_bytes DESC, prefix_label ASC LIMIT {top_n_map['prefix_top']}"
            ),
        )

    focus_breakdown_rows: list[list[str]] = []
    focused_sections: list[dict[str, object]] = []
    needs_focused_prefix_queries = bool(profile.focus_prefixes) and (
        "focused_prefix_analysis" in allowed_ids
        or "prefix_expiration_breakdown" in allowed_ids
        or profile.focus_only
    )
    for focus_prefix in profile.focus_prefixes if needs_focused_prefix_queries else ():
        prefix_like = _build_prefix_like_pattern(focus_prefix)
        focus_filter = f"{run_filter} AND key_name LIKE {_quote_string_literal(prefix_like)}"
        summary_row = _run_logged_analysis_query(
            adaptor,
            session,
            query_name="focused_prefix_summary",
            sql=(
                "SELECT COUNT(*) AS matched_key_count, "
                "COALESCE(SUM(size_bytes), 0) AS total_size_bytes, "
                "COALESCE(SUM(CASE WHEN has_expiration = 1 THEN 1 ELSE 0 END), 0) AS with_expiration, "
                "COALESCE(SUM(CASE WHEN has_expiration = 0 THEN 1 ELSE 0 END), 0) AS without_expiration "
                f"FROM {safe_table} WHERE {focus_filter}"
            ),
            focus_prefix=focus_prefix,
        )[0]
        matched_key_count = int(summary_row.get("matched_key_count") or 0)
        total_size = int(summary_row.get("total_size_bytes") or 0)
        with_expiration = int(summary_row.get("with_expiration") or 0)
        without_expiration = int(summary_row.get("without_expiration") or 0)
        focus_breakdown_rows.append(
            [
                focus_prefix,
                str(with_expiration),
                str(without_expiration),
                str(matched_key_count),
            ]
        )

        type_breakdown_rows = _run_logged_analysis_query(
            adaptor,
            session,
            query_name="focused_prefix_type_breakdown",
            sql=(
                "SELECT key_type, COUNT(*) AS key_count "
                f"FROM {safe_table} WHERE {focus_filter} "
                "GROUP BY key_type ORDER BY key_count DESC, key_type ASC"
            ),
            focus_prefix=focus_prefix,
        )
        top_key_rows = _run_logged_analysis_query(
            adaptor,
            session,
            query_name="focused_prefix_top_keys",
            sql=(
                "SELECT key_name, key_type, size_bytes "
                f"FROM {safe_table} WHERE {focus_filter} "
                f"ORDER BY size_bytes DESC, key_name ASC LIMIT {focused_prefix_limit}"
            ),
            focus_prefix=focus_prefix,
        )
        summary_text = (
            f"前缀 {focus_prefix} 共匹配 {matched_key_count} 个键，累计内存占用 {total_size} 字节。"
            if matched_key_count
            else f"前缀 {focus_prefix} 未匹配到符合条件的键。"
        )
        focused_sections.append(
            {
                "prefix": focus_prefix,
                "matched_key_count": matched_key_count,
                "total_size_bytes": total_size,
                "key_type_breakdown": {
                    str(row["key_type"]): int(row["key_count"]) for row in type_breakdown_rows
                },
                "top_keys": [
                    [str(row["key_name"]), str(row["key_type"]), str(int(row["size_bytes"]))]
                    for row in top_key_rows
                ],
                "expiration_stats": {
                    "with_expiration": with_expiration,
                    "without_expiration": without_expiration,
                },
                "summary_text": summary_text,
                "limit": focused_prefix_limit,
            }
        )

    def read_top_keys(limit_key: str, *, key_type: str | None = None, include_type: bool) -> dict[str, object]:
        conditions = [run_filter]
        if key_type is not None:
            conditions.append(f"key_type = {_quote_string_literal(key_type)}")
        elif limit_key == "other_big_keys":
            known = ", ".join(
                _quote_string_literal(value)
                for value in ("string", "hash", "list", "set", "zset", "stream")
            )
            conditions.append(f"key_type NOT IN ({known})")
        where_clause = " AND ".join(conditions)
        columns = "key_name, key_type, size_bytes" if include_type else "key_name, size_bytes"
        query_name = "top_big_keys" if limit_key == "top_big_keys" else "typed_big_keys"
        rows = _run_logged_analysis_query(
            adaptor,
            session,
            query_name=query_name,
            sql=(
                f"SELECT {columns} FROM {safe_table} WHERE {where_clause} "
                f"ORDER BY size_bytes DESC, key_name ASC LIMIT {top_n_map[limit_key]}"
            ),
            key_type=key_type or ("other" if limit_key == "other_big_keys" else None),
            limit_key=limit_key,
        )
        if include_type:
            rendered_rows = [
                [str(row["key_name"]), str(row["key_type"]), str(int(row["size_bytes"]))]
                for row in rows
            ]
        else:
            rendered_rows = [
                [str(row["key_name"]), str(int(row["size_bytes"]))]
                for row in rows
            ]
        return {"limit": top_n_map[limit_key], "rows": rendered_rows}

    return {
        "executive_summary": overall_summary,
        "background": {
            "profile_name": profile.name,
            "focus_prefix_count": len(profile.focus_prefixes),
        },
        "analysis_results": overall_summary,
        "sample_overview": {
            "sample_rows": sample_rows,
        },
        "overall_summary": overall_summary,
        "key_type_summary": {
            "counts": counts,
            "memory_bytes": memory_bytes,
            "rows": [
                [key_type, str(counts[key_type]), str(memory_bytes[key_type])]
                for key_type in sorted(counts, key=lambda key: (-counts[key], -memory_bytes[key], key))
            ],
        },
        "key_type_memory_breakdown": {
            "rows": [
                [key_type, str(memory_bytes[key_type])]
                for key_type in sorted(memory_bytes, key=lambda key: (-memory_bytes[key], key))
            ],
        },
        "expiration_summary": {
            "expired_count": expired_count,
            "persistent_count": persistent_count,
        },
        "non_expiration_summary": {
            "persistent_count": persistent_count,
        },
        "prefix_top_summary": {
            "rows": [
                [str(row["prefix_label"]), str(int(row["key_count"])), str(int(row["memory_bytes"]))]
                for row in prefix_rows
            ],
        },
        "prefix_expiration_breakdown": {
            "rows": focus_breakdown_rows,
        },
        "top_big_keys": read_top_keys("top_big_keys", include_type=True) if "top_big_keys" in allowed_ids else {"limit": default_big_key_limit, "rows": []},
        "top_string_keys": read_top_keys("string_big_keys", key_type="string", include_type=False) if "top_string_keys" in allowed_ids else {"limit": top_n_map["string_big_keys"], "rows": []},
        "top_hash_keys": read_top_keys("hash_big_keys", key_type="hash", include_type=False) if "top_hash_keys" in allowed_ids else {"limit": top_n_map["hash_big_keys"], "rows": []},
        "top_list_keys": read_top_keys("list_big_keys", key_type="list", include_type=False) if "top_list_keys" in allowed_ids else {"limit": top_n_map["list_big_keys"], "rows": []},
        "top_set_keys": read_top_keys("set_big_keys", key_type="set", include_type=False) if "top_set_keys" in allowed_ids else {"limit": top_n_map["set_big_keys"], "rows": []},
        "top_zset_keys": read_top_keys("zset_big_keys", key_type="zset", include_type=False) if "top_zset_keys" in allowed_ids else {"limit": top_n_map["zset_big_keys"], "rows": []},
        "top_stream_keys": read_top_keys("stream_big_keys", key_type="stream", include_type=False) if "top_stream_keys" in allowed_ids else {"limit": top_n_map["stream_big_keys"], "rows": []},
        "top_other_keys": read_top_keys("other_big_keys", include_type=False) if "top_other_keys" in allowed_ids else {"limit": top_n_map["other_big_keys"], "rows": []},
        "focused_prefix_analysis": {
            "sections": focused_sections,
        },
        "loan_prefix_detail": _build_loan_prefix_detail(
            adaptor,
            session,
            safe_table=safe_table,
            run_filter=run_filter,
            enabled="loan_prefix_detail" in allowed_ids,
            limit=focused_prefix_limit,
        ),
        "conclusions": {},
    }


def _sanitize_identifier(name: str) -> str:
    return f"`{_sanitize_identifier_text(name)}`"


def _sanitize_identifier_text(name: str) -> str:
    clean = "".join(c for c in name if c.isalnum() or c == "_")
    if not clean:
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return clean


def _quote_string_literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected integer-compatible value, got {value!r}") from exc


def _coerce_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return _coerce_int(value)


def _normalize_limit(limit: int | str | None) -> int:
    if limit is None:
        return 100_000
    if isinstance(limit, str):
        normalized = limit.strip()
        if normalized.lower() in {"", "none", "null"}:
            return 100_000
        limit = normalized
    try:
        return int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid MySQL dataset row limit: {limit!r}") from exc


def format_mysql_error(exc: MySQLOperationError) -> str:
    return f"Error: {exc}"


def _without_database(config: MySQLConnectionConfig) -> MySQLConnectionConfig:
    return MySQLConnectionConfig(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=None,
        connect_timeout_seconds=config.connect_timeout_seconds,
        read_timeout_seconds=config.read_timeout_seconds,
        write_timeout_seconds=config.write_timeout_seconds,
    )


def _relabel_mysql_operation_error(
    exc: MySQLOperationError,
    *,
    config: MySQLConnectionConfig,
    operation: str,
    summary: str,
    table_name: str | None = None,
    query_name: str | None = None,
) -> MySQLOperationError:
    effective_summary = exc.summary if exc.summary != "MySQL operation failed" else summary
    return exc.__class__(
        summary=effective_summary,
        stage=exc.stage,
        config=config,
        root_cause=exc.root_cause,
        operation=operation,
        table=table_name,
        query_name=query_name,
    )


def _execute_write_with_optional_log_hook(
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    sql: str,
    *,
    params: list[tuple[Any, ...]] | None = None,
    log_hook=None,
) -> int:
    if _callable_accepts_keyword(adaptor.execute_write, "log_hook"):
        return adaptor.execute_write(config, sql, params=params, log_hook=log_hook)
    return adaptor.execute_write(config, sql, params=params)


def _log_mysql_staging_phase(
    *,
    config: MySQLConnectionConfig,
    stage: str,
    database_name: str | None = None,
    table_name: str | None = None,
    mysql_stage_batch_size: int | None = None,
    batch_number: int | None = None,
    batch_rows: int | None = None,
    cumulative_rows: int | None = None,
    elapsed_seconds: float | None = None,
    source_file: str | None = None,
    run_id: str | None = None,
    error: str | None = None,
    rowcount: int | None = None,
    param_count: int | None = None,
) -> None:
    logger.info(
        "mysql staging phase",
        extra={
            "event_name": "mysql_staging_phase",
            "stage": stage,
            "mysql_host": config.host,
            "mysql_port": config.port,
            "mysql_database": database_name or config.database or "",
            "mysql_table": table_name,
            "mysql_stage_batch_size": mysql_stage_batch_size,
            "batch_number": batch_number,
            "batch_rows": batch_rows,
            "cumulative_rows": cumulative_rows,
            "elapsed_seconds": elapsed_seconds,
            "source_file": source_file,
            "run_id": run_id,
            "error": error,
            "rowcount": rowcount,
            "param_count": param_count,
        },
    )
    return None


def _run_logged_analysis_query(
    adaptor: MySQLAdaptor,
    session: MySQLStagingSession,
    *,
    query_name: str,
    sql: str,
    **details: object,
) -> list[dict[str, Any]]:
    started = perf_counter()
    _log_mysql_analysis_phase(
        config=session.connection,
        query_name=query_name,
        stage="start",
        table_name=session.table_name,
        run_id=session.run_id,
        **details,
    )
    try:
        rows = adaptor.read_query(
            session.connection,
            _apply_max_execution_time_hint(sql, session.connection.read_timeout_seconds),
        )
    except MySQLOperationError as exc:
        wrapped = _relabel_mysql_operation_error(
            exc,
            config=session.connection,
            operation="analysis_query",
            summary="MySQL analysis query failed",
            table_name=session.table_name,
            query_name=query_name,
        )
        _log_mysql_analysis_phase(
            config=session.connection,
            query_name=query_name,
            stage="error",
            table_name=session.table_name,
            run_id=session.run_id,
            elapsed_seconds=round(perf_counter() - started, 6),
            error=str(wrapped),
            **details,
        )
        raise wrapped from exc
    _log_mysql_analysis_phase(
        config=session.connection,
        query_name=query_name,
        stage="end",
        table_name=session.table_name,
        run_id=session.run_id,
        elapsed_seconds=round(perf_counter() - started, 6),
        rows_returned=len(rows),
        **details,
    )
    return rows


def _build_loan_prefix_detail(
    adaptor: MySQLAdaptor,
    session: MySQLStagingSession,
    *,
    safe_table: str,
    run_filter: str,
    enabled: bool,
    limit: int,
) -> dict[str, object]:
    if not enabled:
        return {"limit": limit, "rows": []}
    rows = _run_logged_analysis_query(
        adaptor,
        session,
        query_name="loan_prefix_detail",
        sql=(
            "SELECT key_name, key_type, size_bytes "
            f"FROM {safe_table} WHERE {run_filter} "
            "AND key_name LIKE 'loan:%' "
            f"ORDER BY size_bytes DESC, key_name ASC LIMIT {limit}"
        ),
        limit=limit,
        focus_prefix="loan:*",
    )
    return {
        "limit": limit,
        "rows": [
            [str(row["key_name"]), str(row["key_type"]), str(int(row["size_bytes"]))]
            for row in rows
        ],
    }


def _apply_max_execution_time_hint(sql: str, timeout_seconds: float) -> str:
    normalized = sql.lstrip()
    if not normalized.upper().startswith("SELECT"):
        return sql
    timeout_ms = max(1, int(timeout_seconds * 1000))
    return normalized.replace("SELECT", f"SELECT /*+ MAX_EXECUTION_TIME({timeout_ms}) */", 1)


def _log_mysql_analysis_phase(
    *,
    config: MySQLConnectionConfig,
    query_name: str,
    stage: str,
    table_name: str,
    run_id: str,
    elapsed_seconds: float | None = None,
    rows_returned: int | None = None,
    error: str | None = None,
    **details: object,
) -> None:
    logger.info(
        "mysql analysis phase",
        extra={
            "event_name": "mysql_analysis_phase",
            "query_name": query_name,
            "stage": stage,
            "mysql_host": config.host,
            "mysql_port": config.port,
            "mysql_database": config.database or "",
            "mysql_table": table_name,
            "run_id": run_id,
            "elapsed_seconds": elapsed_seconds,
            "rows_returned": rows_returned,
            "error": error,
            **details,
        },
    )
    return None


def _callable_accepts_keyword(func, keyword: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            return True
    return keyword in signature.parameters


def _build_prefix_like_pattern(prefix: str) -> str:
    if prefix.endswith("*"):
        return prefix[:-1] + "%"
    return prefix
