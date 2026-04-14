from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InspectionFinding:
    risk_name: str
    severity: str
    target: str
    evidence: str
    impact: str
    recommendation: str
    category: str


@dataclass(frozen=True)
class InspectionNode:
    node_id: str
    hostname: str
    ip: str | None = None
    port: int | None = None
    role: str | None = None
    version: str | None = None
    source_path: str | None = None
    collect_time: str | None = None
    host_facts: dict[str, Any] = field(default_factory=dict)
    redis_facts: dict[str, Any] = field(default_factory=dict)
    log_facts: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InspectionCluster:
    cluster_id: str
    name: str
    cluster_type: str
    nodes: tuple[InspectionNode, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InspectionSystem:
    system_id: str
    name: str
    clusters: tuple[InspectionCluster, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InspectionDataset:
    systems: tuple[InspectionSystem, ...]
    source_mode: str
    input_sources: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "InspectionCluster",
    "InspectionDataset",
    "InspectionFinding",
    "InspectionNode",
    "InspectionSystem",
]
