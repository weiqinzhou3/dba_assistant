from __future__ import annotations

from pathlib import Path
from typing import Any

from dba_assistant.adaptors.redis_adaptor import RedisConnectionConfig
from dba_assistant.capabilities.redis_inspection_report.analyzer import analyze_inspection_dataset
from dba_assistant.capabilities.redis_inspection_report.collectors.offline_evidence_collector import (
    RedisInspectionOfflineCollector,
    RedisInspectionOfflineInput,
)
from dba_assistant.capabilities.redis_inspection_report.collectors.remote_redis_collector import (
    RedisInspectionRemoteCollector,
    RedisInspectionRemoteInput,
)
from dba_assistant.capabilities.redis_inspection_report.types import (
    InspectionCluster,
    InspectionDataset,
    InspectionNode,
    InspectionSystem,
)
from dba_assistant.core.observability import get_current_execution_session
from dba_assistant.core.reporter.report_model import AnalysisReport


def analyze_offline_inspection(
    sources: tuple[Path, ...],
    *,
    language: str = "zh-CN",
    log_time_window_days: int | None = None,
    log_start_time: str | None = None,
    log_end_time: str | None = None,
    collector: RedisInspectionOfflineCollector | None = None,
) -> AnalysisReport:
    dataset = (collector or RedisInspectionOfflineCollector()).collect(
        RedisInspectionOfflineInput(
            sources=sources,
            log_time_window_days=log_time_window_days,
            log_start_time=log_start_time,
            log_end_time=log_end_time,
        )
    )
    return analyze_inspection(dataset, language=language, route="offline_inspection")


def analyze_remote_inspection(
    connection: RedisConnectionConfig,
    *,
    language: str = "zh-CN",
    collector: RedisInspectionRemoteCollector | None = None,
) -> AnalysisReport:
    snapshot = (collector or RedisInspectionRemoteCollector()).collect(
        RedisInspectionRemoteInput(connection=connection)
    )
    dataset = remote_snapshot_to_dataset(snapshot, connection=connection)
    _record_dataset_phase(dataset, phase="online_collection")
    return analyze_inspection(dataset, language=language, route="online_inspection")


def analyze_inspection(
    dataset: InspectionDataset,
    *,
    language: str = "zh-CN",
    route: str,
) -> AnalysisReport:
    _record_dataset_phase(dataset, phase="inspection_analysis_start")
    report = analyze_inspection_dataset(dataset, language=language)
    metadata = {**report.metadata, "route": route, "source_mode": dataset.source_mode}
    _record_phase(
        "inspection_analysis_end",
        route=route,
        finding_count=metadata.get("finding_count"),
        system_count=metadata.get("system_count"),
        cluster_count=metadata.get("cluster_count"),
        node_count=metadata.get("node_count"),
    )
    return AnalysisReport(
        title=report.title,
        summary=report.summary,
        sections=report.sections,
        metadata=metadata,
        language=report.language,
    )


def remote_snapshot_to_dataset(
    snapshot: dict[str, Any],
    *,
    connection: RedisConnectionConfig,
) -> InspectionDataset:
    redis_facts: dict[str, Any] = {}
    info = snapshot.get("info")
    if isinstance(info, dict):
        redis_facts.update({key: value for key, value in info.items() if key != "available"})

    config = snapshot.get("config")
    if isinstance(config, dict) and isinstance(config.get("data"), dict):
        redis_facts.update(config["data"])

    slowlog = snapshot.get("slowlog")
    if isinstance(slowlog, dict):
        redis_facts["slowlog"] = slowlog

    cluster_info = snapshot.get("cluster_info")
    if isinstance(cluster_info, dict) and isinstance(cluster_info.get("data"), dict):
        redis_facts.update(cluster_info["data"])
        if cluster_info["data"]:
            redis_facts.setdefault("cluster_enabled", "1")

    host = connection.host
    port = connection.port
    role = _normalize_role(str(redis_facts.get("role") or ""))
    node = InspectionNode(
        node_id=f"{host}:{port}",
        hostname=host,
        ip=host,
        port=port,
        role=role,
        version=str(redis_facts.get("redis_version") or "") or None,
        source_path=f"redis://{host}:{port}/{connection.db}",
        redis_facts=redis_facts,
    )
    cluster_type = "redis-cluster" if str(redis_facts.get("cluster_enabled") or "0") == "1" else "standalone"
    return InspectionDataset(
        systems=(
            InspectionSystem(
                system_id=f"redis-{host}-{port}",
                name=f"Redis {host}:{port}",
                clusters=(
                    InspectionCluster(
                        cluster_id="redis-cluster" if cluster_type == "redis-cluster" else f"standalone-{host}:{port}",
                        name="redis-cluster" if cluster_type == "redis-cluster" else f"{host}:{port}",
                        cluster_type=cluster_type,
                        nodes=(node,),
                        metadata={
                            "cluster_nodes_available": str(
                                isinstance(snapshot.get("cluster_nodes"), dict)
                                and bool(snapshot.get("cluster_nodes", {}).get("available"))
                            ).lower()
                        },
                    ),
                ),
            ),
        ),
        source_mode="online",
        input_sources=(f"redis://{host}:{port}/{connection.db}",),
        metadata={"route": "online_inspection"},
    )


def _record_dataset_phase(dataset: InspectionDataset, *, phase: str) -> None:
    system_count = len(dataset.systems)
    cluster_count = sum(len(system.clusters) for system in dataset.systems)
    node_count = sum(len(cluster.nodes) for system in dataset.systems for cluster in system.clusters)
    _record_phase(
        phase,
        stage="end",
        input_mode=dataset.source_mode,
        system_count=system_count,
        cluster_count=cluster_count,
        node_count=node_count,
    )


def _record_phase(phase: str, **payload: Any) -> None:
    session = get_current_execution_session()
    if session is None:
        return
    session.record_event("redis_inspection_phase", phase=phase, **payload)


def _normalize_role(role: str) -> str | None:
    role = role.strip().lower()
    if role == "slave":
        return "replica"
    return role or None


__all__ = [
    "analyze_inspection",
    "analyze_offline_inspection",
    "analyze_remote_inspection",
    "remote_snapshot_to_dataset",
]
