"""Shared types for the interface adapter layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class InterfaceSurface(str, Enum):
    CLI = "cli"
    API = "api"
    WEBUI = "webui"


class ApprovalStatus(str, Enum):
    APPROVED = "approved"
    DENIED = "denied"


@dataclass(frozen=True)
class InterfaceRequest:
    """Raw request from any interface (CLI, Web, API)."""

    prompt: str
    surface: InterfaceSurface = InterfaceSurface.CLI
    input_paths: list[Path] = field(default_factory=list)
    output_path: Path | None = None
    config_path: str | None = None
    profile: str | None = None
    report_format: str | None = None
    input_kind: str | None = None
    path_mode: str | None = None
    redis_password: str | None = None
    ssh_host: str | None = None
    ssh_port: int | None = None
    ssh_username: str | None = None
    ssh_password: str | None = None
    remote_rdb_path: str | None = None
    remote_rdb_path_source: str | None = None
    require_fresh_rdb_snapshot: bool | None = None
    mysql_host: str | None = None
    mysql_port: int | None = None
    mysql_user: str | None = None
    mysql_database: str | None = None
    mysql_password: str | None = None
    mysql_table: str | None = None
    mysql_query: str | None = None


@dataclass(frozen=True)
class ApprovalRequest:
    """Structured request for human approval of a sensitive operation."""

    action: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApprovalResponse:
    """Human response to an approval request."""

    status: ApprovalStatus
    action: str
    reason: str | None = None
