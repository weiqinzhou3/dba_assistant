from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable


@dataclass(frozen=True)
class MySQLConnectionConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


class MySQLAdaptor:
    def __init__(self, connect: Callable[..., Any] | None = None) -> None:
        self._connect = connect or _default_connect

    @staticmethod
    def dict_cursor_class() -> object:
        pymysql = _load_pymysql()
        if pymysql is None:
            return dict
        return pymysql.cursors.DictCursor

    def execute_query(self, config: MySQLConnectionConfig, sql: str) -> list[dict[str, Any]]:
        connection = self._connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password,
            database=config.database,
            cursorclass=self.dict_cursor_class(),
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                return list(cursor.fetchall())
        finally:
            connection.close()


def _default_connect(**kwargs: Any) -> Any:
    pymysql = _load_pymysql(required=True)
    return pymysql.connect(**kwargs)


def _load_pymysql(*, required: bool = False) -> Any | None:
    try:
        return import_module("pymysql")
    except ModuleNotFoundError:
        if required:
            raise RuntimeError("PyMySQL is required for MySQLAdaptor default connections.") from None
        return None
