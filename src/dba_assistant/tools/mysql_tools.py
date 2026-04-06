"""MySQL capability tools for the unified Deep Agent."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from dba_assistant.adaptors.mysql_adaptor import MySQLAdaptor, MySQLConnectionConfig
from dba_assistant.capabilities.redis_rdb_analysis.analyzers.big_keys import _normalize_top_n
from dba_assistant.capabilities.redis_rdb_analysis.types import EffectiveProfile


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
    sql = f"CREATE DATABASE IF NOT EXISTS {_sanitize_identifier(database_name)}"
    return adaptor.execute_write(_without_database(config), sql)


def create_staging_table(
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    table_name: str,
) -> int:
    safe_table = _sanitize_identifier(table_name)
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
    INDEX idx_stage_run_type (stage_run_id, key_type),
    INDEX idx_stage_run_size (stage_run_id, size_bytes),
    INDEX idx_stage_run_expiration (stage_run_id, has_expiration)
)
""".strip()
    return adaptor.execute_write(config, sql)


def insert_staging_batch(
    adaptor: MySQLAdaptor,
    session: MySQLStagingSession,
    *,
    source_file: str,
    rows: list[dict[str, Any]],
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
    return adaptor.execute_write(session.connection, sql, params=params)


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
    top_n_map = _normalize_top_n(profile.top_n)

    overall_row = adaptor.read_query(
        session.connection,
        (
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

    type_rows = adaptor.read_query(
        session.connection,
        (
            "SELECT key_type, COUNT(*) AS key_count, COALESCE(SUM(size_bytes), 0) AS memory_bytes "
            f"FROM {safe_table} WHERE {run_filter} "
            "GROUP BY key_type "
            "ORDER BY key_count DESC, memory_bytes DESC, key_type ASC"
        ),
    )
    counts = {str(row["key_type"]): int(row["key_count"]) for row in type_rows}
    memory_bytes = {str(row["key_type"]): int(row["memory_bytes"]) for row in type_rows}

    expiration_row = adaptor.read_query(
        session.connection,
        (
            "SELECT "
            "COALESCE(SUM(CASE WHEN has_expiration = 1 THEN 1 ELSE 0 END), 0) AS expired_count, "
            "COALESCE(SUM(CASE WHEN has_expiration = 0 THEN 1 ELSE 0 END), 0) AS persistent_count "
            f"FROM {safe_table} WHERE {run_filter}"
        ),
    )[0]
    expired_count = int(expiration_row.get("expired_count") or 0)
    persistent_count = int(expiration_row.get("persistent_count") or 0)

    prefix_rows = adaptor.read_query(
        session.connection,
        (
            f"SELECT {prefix_expr} AS prefix_label, COUNT(*) AS key_count, "
            "COALESCE(SUM(size_bytes), 0) AS memory_bytes "
            f"FROM {safe_table} WHERE {run_filter} "
            "GROUP BY prefix_label "
            f"ORDER BY key_count DESC, memory_bytes DESC, prefix_label ASC LIMIT {top_n_map['prefix_top']}"
        ),
    )

    focus_breakdown_rows: list[list[str]] = []
    focused_sections: list[dict[str, object]] = []
    for focus_prefix in profile.focus_prefixes:
        prefix_like = _build_prefix_like_pattern(focus_prefix)
        focus_filter = f"{run_filter} AND key_name LIKE {_quote_string_literal(prefix_like)}"
        summary_row = adaptor.read_query(
            session.connection,
            (
                "SELECT COUNT(*) AS matched_key_count, "
                "COALESCE(SUM(size_bytes), 0) AS total_size_bytes, "
                "COALESCE(SUM(CASE WHEN has_expiration = 1 THEN 1 ELSE 0 END), 0) AS with_expiration, "
                "COALESCE(SUM(CASE WHEN has_expiration = 0 THEN 1 ELSE 0 END), 0) AS without_expiration "
                f"FROM {safe_table} WHERE {focus_filter}"
            ),
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

        type_breakdown_rows = adaptor.read_query(
            session.connection,
            (
                "SELECT key_type, COUNT(*) AS key_count "
                f"FROM {safe_table} WHERE {focus_filter} "
                "GROUP BY key_type ORDER BY key_count DESC, key_type ASC"
            ),
        )
        top_key_rows = adaptor.read_query(
            session.connection,
            (
                "SELECT key_name, key_type, size_bytes "
                f"FROM {safe_table} WHERE {focus_filter} "
                f"ORDER BY size_bytes DESC, key_name ASC LIMIT {top_n_map['focused_prefix_top_keys']}"
            ),
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
                "limit": top_n_map["focused_prefix_top_keys"],
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
        rows = adaptor.read_query(
            session.connection,
            (
                f"SELECT {columns} FROM {safe_table} WHERE {where_clause} "
                f"ORDER BY size_bytes DESC, key_name ASC LIMIT {top_n_map[limit_key]}"
            ),
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
        "top_big_keys": read_top_keys("top_big_keys", include_type=True),
        "top_string_keys": read_top_keys("string_big_keys", key_type="string", include_type=False),
        "top_hash_keys": read_top_keys("hash_big_keys", key_type="hash", include_type=False),
        "top_list_keys": read_top_keys("list_big_keys", key_type="list", include_type=False),
        "top_set_keys": read_top_keys("set_big_keys", key_type="set", include_type=False),
        "top_zset_keys": read_top_keys("zset_big_keys", key_type="zset", include_type=False),
        "top_stream_keys": read_top_keys("stream_big_keys", key_type="stream", include_type=False),
        "top_other_keys": read_top_keys("other_big_keys", include_type=False),
        "focused_prefix_analysis": {
            "sections": focused_sections,
        },
        "loan_prefix_detail": (
            {
                "rows": [
                    [str(row["key_name"]), str(row["key_type"]), str(int(row["size_bytes"]))]
                    for row in adaptor.read_query(
                        session.connection,
                        (
                            "SELECT key_name, key_type, size_bytes "
                            f"FROM {safe_table} WHERE {run_filter} "
                            "AND key_name LIKE 'loan:%' "
                            "ORDER BY size_bytes DESC, key_name ASC"
                        ),
                    )
                ],
            }
            if profile.name.lower() == "rcs"
            else {"rows": []}
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


def _without_database(config: MySQLConnectionConfig) -> MySQLConnectionConfig:
    return MySQLConnectionConfig(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=None,
    )


def _build_prefix_like_pattern(prefix: str) -> str:
    if prefix.endswith("*"):
        return prefix[:-1] + "%"
    return prefix
