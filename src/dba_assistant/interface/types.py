"""Shared types for the interface adapter layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ApprovalStatus(str, Enum):
    APPROVED = "approved"
    DENIED = "denied"


@dataclass(frozen=True)
class InterfaceRequest:
    """Raw request from any interface (CLI, Web, API)."""

    prompt: str
    input_paths: list[Path] = field(default_factory=list)
    output_path: Path | None = None
    config_path: str | None = None
    profile: str | None = None
    report_format: str | None = None


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
