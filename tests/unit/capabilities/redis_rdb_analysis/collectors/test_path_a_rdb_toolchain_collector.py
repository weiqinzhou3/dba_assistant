from pathlib import Path

from dba_assistant.adaptors.mysql_adaptor import MySQLAdaptor, MySQLConnectionConfig
from dba_assistant.capabilities.redis_rdb_analysis.collectors.path_a_rdb_toolchain_collector import (
    PathARdbToolchainCollector,
)


def test_path_a_collector_runs_parser_import_and_query() -> None:
    fixture_path = Path("tests/fixtures/rdb/sql/sample_top_keys.csv")
    source = Path("/tmp/dump.rdb")
    calls: list[str] = []

    collector = PathARdbToolchainCollector(
        run_rdb_tools=lambda path: calls.append(f"parse:{path.name}") or fixture_path,
        mysql_import=lambda csv_path: calls.append(f"import:{csv_path.name}"),
        fetch_rows=lambda: [
            {
                "key_name": "loan:1",
                "key_type": "hash",
                "size_bytes": 128,
                "has_expiration": False,
                "ttl_seconds": None,
            }
        ],
    )

    dataset = collector.collect([source])

    assert calls == ["parse:dump.rdb", "import:sample_top_keys.csv"]
    assert dataset.samples[0].source == source
    assert dataset.records[0].key_name == "loan:1"
    assert dataset.records[0].sample_id == "sample-1"
    assert dataset.records[0].prefix_segments == ("loan",)


def test_mysql_adaptor_executes_query_and_returns_dict_rows() -> None:
    calls: dict[str, object] = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def execute(self, sql: str) -> None:
            calls["sql"] = sql

        def fetchall(self) -> list[dict[str, object]]:
            return [{"key_name": "loan:1", "size_bytes": 128}]

    class FakeConnection:
        def cursor(self) -> FakeCursor:
            return FakeCursor()

        def close(self) -> None:
            calls["closed"] = True

    def fake_connect(**kwargs):
        calls["connect_kwargs"] = kwargs
        return FakeConnection()

    adaptor = MySQLAdaptor(connect=fake_connect)
    config = MySQLConnectionConfig(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="secret",
        database="rdb_analysis",
    )

    rows = adaptor.execute_query(config, "SELECT key_name, size_bytes FROM top_keys")

    assert rows == [{"key_name": "loan:1", "size_bytes": 128}]
    assert calls["sql"] == "SELECT key_name, size_bytes FROM top_keys"
    assert calls["closed"] is True
    assert calls["connect_kwargs"] == {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "secret",
        "database": "rdb_analysis",
        "cursorclass": MySQLAdaptor.dict_cursor_class(),
        "connect_timeout": 5.0,
        "read_timeout": 15.0,
        "write_timeout": 30.0,
    }
