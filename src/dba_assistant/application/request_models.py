from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RuntimeInputs:
    redis_host: str | None = None
    redis_port: int = 6379
    redis_db: int = 0
    output_mode: str = "summary"
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
    mysql_port: int = 3306
    mysql_user: str | None = None
    mysql_database: str | None = None
    mysql_table: str | None = None
    mysql_query: str | None = None


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
    top_n: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedRequest:
    raw_prompt: str
    prompt: str
    runtime_inputs: RuntimeInputs
    secrets: Secrets
    rdb_overrides: RdbOverrides = field(default_factory=RdbOverrides)
