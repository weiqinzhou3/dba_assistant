from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_LOOPBACK_HOST = "127.0.0.1"
DEFAULT_REDIS_PORT = 6379
DEFAULT_REDIS_DB = 0
DEFAULT_MYSQL_PORT = 3306
DEFAULT_MYSQL_USER = "root"
DEFAULT_MYSQL_DATABASE = "dba_assistant_staging"
DEFAULT_MYSQL_TABLE_PREFIX = "rdb_stage_auto"
DEFAULT_MYSQL_STAGE_BATCH_SIZE = 2000
LARGE_RDB_WARNING_BYTES = 1_000_000_000


@dataclass(frozen=True)
class RuntimeInputs:
    redis_host: str | None = None
    redis_port: int = DEFAULT_REDIS_PORT
    redis_db: int = DEFAULT_REDIS_DB
    output_mode: str = "summary"
    report_language: str = "zh-CN"
    report_format: str | None = None
    output_path: Path | None = None
    input_paths: tuple[Path, ...] = field(default_factory=tuple)
    input_kind: str | None = None
    path_mode: str | None = None
    ssh_host: str | None = None
    ssh_port: int | None = None
    ssh_username: str | None = None
    remote_rdb_path: str | None = None
    remote_rdb_path_source: str | None = None
    require_fresh_rdb_snapshot: bool = False
    mysql_host: str | None = None
    mysql_port: int = DEFAULT_MYSQL_PORT
    mysql_user: str | None = None
    mysql_database: str | None = None
    mysql_table: str | None = None
    mysql_query: str | None = None
    mysql_stage_batch_size: int | None = None
    log_time_window_days: int | None = None
    log_start_time: str | None = None
    log_end_time: str | None = None

    def effective_redis_host(self) -> str:
        return self.redis_host or DEFAULT_LOOPBACK_HOST

    def effective_mysql_host(self) -> str:
        return self.mysql_host or DEFAULT_LOOPBACK_HOST

    def effective_mysql_user(self) -> str:
        return self.mysql_user or DEFAULT_MYSQL_USER

    def effective_mysql_database(self) -> str:
        return self.mysql_database or DEFAULT_MYSQL_DATABASE

    def applied_mysql_defaults(self) -> tuple[str, ...]:
        defaults: list[str] = []
        if not self.mysql_host:
            defaults.append("mysql_host")
        if not self.mysql_user:
            defaults.append("mysql_user")
        if not self.mysql_database:
            defaults.append("mysql_database")
        if not self.mysql_table:
            defaults.append("mysql_table")
        return tuple(defaults)

    def effective_mysql_stage_batch_size(self) -> int:
        return self.mysql_stage_batch_size or DEFAULT_MYSQL_STAGE_BATCH_SIZE


@dataclass(frozen=True)
class Secrets:
    redis_password: str | None = None
    ssh_password: str | None = None
    mysql_password: str | None = None


@dataclass(frozen=True)
class RdbOverrides:
    profile_name: str | None = None
    route_name: str | None = None
    focus_prefixes: tuple[str, ...] = ()
    focus_only: bool = False
    top_n: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedRequest:
    raw_prompt: str
    prompt: str
    runtime_inputs: RuntimeInputs
    secrets: Secrets
    rdb_overrides: RdbOverrides = field(default_factory=RdbOverrides)


def build_default_mysql_table_name(*, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
    return f"{DEFAULT_MYSQL_TABLE_PREFIX}_{timestamp}"
