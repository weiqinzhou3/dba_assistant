"""MySQL capability tools for the unified Deep Agent.

Provides three bounded tool surfaces:
- mysql_read_query: execute read-only SQL
- load_preparsed_dataset_from_mysql: load a preparsed dataset
- stage_rdb_rows_to_mysql: write parsed RDB rows into a staging table
"""
from __future__ import annotations

import json
from typing import Any

from dba_assistant.adaptors.mysql_adaptor import MySQLAdaptor, MySQLConnectionConfig


def mysql_read_query(
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    sql: str,
) -> str:
    """Execute a bounded read-only SQL query and return the result as JSON."""
    rows = adaptor.read_query(config, sql)
    return json.dumps(rows, default=str)


def load_preparsed_dataset_from_mysql(
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    table_name: str,
    *,
    limit: int = 100_000,
) -> str:
    """Load a preparsed dataset from MySQL and return it as JSON.

    The dataset shape matches what preparsed_dataset_analysis expects.
    """
    safe_table = _sanitize_identifier(table_name)
    sql = f"SELECT * FROM {safe_table} LIMIT {int(limit)}"
    rows = adaptor.read_query(config, sql)
    return json.dumps({"source": f"mysql:{table_name}", "rows": rows}, default=str)


def stage_rdb_rows_to_mysql(
    adaptor: MySQLAdaptor,
    config: MySQLConnectionConfig,
    table_name: str,
    rows: list[dict[str, Any]],
) -> str:
    """Stage parsed RDB rows into a MySQL table for database-backed aggregation.

    Creates the staging table if it does not exist, then inserts all rows.
    This is a write operation — callers should gate it behind HITL approval.
    """
    if not rows:
        return json.dumps({"staged": 0, "table": table_name})

    safe_table = _sanitize_identifier(table_name)
    columns = list(rows[0].keys())
    safe_columns = [_sanitize_identifier(c) for c in columns]

    create_sql = (
        f"CREATE TABLE IF NOT EXISTS {safe_table} ("
        + ", ".join(f"{col} TEXT" for col in safe_columns)
        + ")"
    )
    adaptor.execute_write(config, create_sql)

    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f"INSERT INTO {safe_table} ({', '.join(safe_columns)}) VALUES ({placeholders})"
    params = [tuple(str(row.get(c, "")) for c in columns) for row in rows]
    count = adaptor.execute_write(config, insert_sql, params=params)

    return json.dumps({"staged": count, "table": table_name})


def _sanitize_identifier(name: str) -> str:
    """Basic SQL identifier sanitization — backtick-quote after stripping unsafe chars."""
    clean = "".join(c for c in name if c.isalnum() or c == "_")
    if not clean:
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return f"`{clean}`"
