from pathlib import Path

from dba_assistant.adaptors.mysql_adaptor import MySQLConnectionConfig
from dba_assistant.capabilities.redis_rdb_analysis.collectors.path_a_mysql_backed_collector import (
    PathAMySQLBackedCollector,
)
from dba_assistant.tools.mysql_tools import (
    load_preparsed_dataset_from_mysql,
    stage_rdb_rows_to_mysql,
)


class InMemoryTextMySQLAdaptor:
    def __init__(self) -> None:
        self._rows_by_table: dict[str, list[dict[str, object]]] = {}

    def execute_write(self, _config, sql: str, params=None) -> int:
        if sql.startswith("CREATE TABLE IF NOT EXISTS "):
            table_name = sql.removeprefix("CREATE TABLE IF NOT EXISTS ").split(" ", 1)[0].strip("`")
            self._rows_by_table.setdefault(table_name, [])
            return 0

        if sql.startswith("INSERT INTO "):
            table_name = sql.removeprefix("INSERT INTO ").split(" ", 1)[0].strip("`")
            column_names = [
                column.strip().strip("`")
                for column in sql.split("(", 1)[1].split(")", 1)[0].split(",")
            ]
            stored_rows = self._rows_by_table.setdefault(table_name, [])
            for row_values in params or []:
                stored_rows.append(
                    {
                        column: None if value is None else str(value)
                        for column, value in zip(column_names, row_values, strict=True)
                    }
                )
            return len(params or [])

        raise AssertionError(f"Unexpected write SQL: {sql}")

    def read_query(self, _config, sql: str) -> list[dict[str, object]]:
        if not sql.startswith("SELECT * FROM "):
            raise AssertionError(f"Unexpected read SQL: {sql}")

        tail = sql.removeprefix("SELECT * FROM ")
        table_name, _, raw_limit = tail.partition(" LIMIT ")
        rows = self._rows_by_table.get(table_name.strip("`"), [])
        return [dict(row) for row in rows[: int(raw_limit)]]


def test_path_a_mysql_backed_collector_round_trips_none_and_false_through_mysql_text_storage() -> None:
    adaptor = InMemoryTextMySQLAdaptor()
    config = MySQLConnectionConfig(
        host="localhost",
        port=3306,
        user="test",
        password="test",
        database="testdb",
    )
    collector = PathAMySQLBackedCollector(
        parser=lambda _path: [
            {
                "key_name": "cache:1",
                "key_type": "string",
                "size_bytes": 123,
                "has_expiration": False,
                "ttl_seconds": None,
            }
        ],
        stage_rows_to_mysql=lambda table_name, rows: stage_rdb_rows_to_mysql(
            adaptor,
            config,
            table_name,
            rows,
        ),
        load_preparsed_dataset_from_mysql=lambda table_name: load_preparsed_dataset_from_mysql(
            adaptor,
            config,
            table_name,
        ),
    )

    dataset = collector.collect([Path("/tmp/dump.rdb")])

    assert dataset.records[0].size_bytes == 123
    assert dataset.records[0].has_expiration is False
    assert dataset.records[0].ttl_seconds is None
