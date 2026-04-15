from __future__ import annotations

from dataclasses import replace
import json
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
    ReviewedLogIssue,
)
from dba_assistant.core.observability import get_current_execution_session
from dba_assistant.core.reporter.report_model import AnalysisReport
from dba_assistant.skills_runtime.assets import load_skill_json_asset


_SKILL_NAME = "redis-inspection-report"


def analyze_offline_inspection(
    sources: tuple[Path, ...],
    *,
    language: str = "zh-CN",
    log_time_window_days: int | None = None,
    log_start_time: str | None = None,
    log_end_time: str | None = None,
    reviewed_log_issues: tuple[ReviewedLogIssue, ...] = (),
    collector: RedisInspectionOfflineCollector | None = None,
    work_dir: Path | None = None,
) -> AnalysisReport:
    dataset = (collector or RedisInspectionOfflineCollector()).collect(
        RedisInspectionOfflineInput(
            sources=sources,
            log_time_window_days=log_time_window_days,
            log_start_time=log_start_time,
            log_end_time=log_end_time,
            work_dir=work_dir,
        )
    )
    if reviewed_log_issues:
        dataset = replace(dataset, reviewed_log_issues=reviewed_log_issues)
    return analyze_inspection(dataset, language=language, route="offline_inspection")


def collect_offline_inspection_dataset(
    sources: tuple[Path, ...],
    *,
    log_time_window_days: int | None = None,
    log_start_time: str | None = None,
    log_end_time: str | None = None,
    collector: RedisInspectionOfflineCollector | None = None,
    work_dir: Path | None = None,
) -> InspectionDataset:
    return (collector or RedisInspectionOfflineCollector()).collect(
        RedisInspectionOfflineInput(
            sources=sources,
            log_time_window_days=log_time_window_days,
            log_start_time=log_start_time,
            log_end_time=log_end_time,
            work_dir=work_dir,
        )
    )


def summarize_inspection_dataset(
    dataset: InspectionDataset,
    *,
    dataset_handle: str,
    log_time_window_days: int | None = None,
    log_start_time: str | None = None,
    log_end_time: str | None = None,
) -> dict[str, Any]:
    clusters: list[dict[str, Any]] = []
    total_log_candidate_count = 0
    for system in dataset.systems:
        for cluster in system.clusters:
            cluster_log_candidate_count = 0
            for node in cluster.nodes:
                cluster_log_candidate_count += _log_candidate_count(node)
            total_log_candidate_count += cluster_log_candidate_count
            clusters.append(
                {
                    "system_id": system.system_id,
                    "system_name": system.name,
                    "cluster_id": cluster.cluster_id,
                    "cluster_name": cluster.name,
                    "cluster_type": cluster.cluster_type,
                    "node_count": len(cluster.nodes),
                    "log_candidate_count": cluster_log_candidate_count,
                    "nodes": [
                        {
                            "node_id": node.node_id,
                            "hostname": node.hostname,
                            "ip": node.ip,
                            "port": node.port,
                            "role": node.role,
                            "version": node.version,
                            "source_path": node.source_path,
                            "log_candidate_count": str(node.log_facts.get("log_candidate_count") or "0"),
                        }
                        for node in cluster.nodes
                    ],
                }
            )
    return {
        "dataset_handle": dataset_handle,
        "source_mode": dataset.source_mode,
        "input_sources": list(dataset.input_sources),
        "system_count": len(dataset.systems),
        "cluster_count": len(clusters),
        "node_count": sum(len(cluster.nodes) for system in dataset.systems for cluster in system.clusters),
        "has_log_candidates": total_log_candidate_count > 0,
        "total_log_candidate_count": total_log_candidate_count,
        "log_time_window": {
            "log_time_window_days": log_time_window_days,
            "log_start_time": log_start_time,
            "log_end_time": log_end_time,
        },
        "clusters": clusters,
    }


def build_log_review_payload(dataset: InspectionDataset) -> dict[str, Any]:
    clusters: list[dict[str, Any]] = []
    for system in dataset.systems:
        for cluster in system.clusters:
            candidates: list[dict[str, Any]] = []
            for node in cluster.nodes:
                raw_candidates = node.log_facts.get("log_candidates")
                if not isinstance(raw_candidates, list):
                    continue
                candidates.extend(candidate for candidate in raw_candidates if isinstance(candidate, dict))
            clusters.append(
                {
                    "system_id": system.system_id,
                    "system_name": system.name,
                    "cluster_id": cluster.cluster_id,
                    "cluster_name": cluster.name,
                    "candidate_count": sum(_log_candidate_count(node) for node in cluster.nodes),
                    "log_candidates": candidates,
                }
            )
    return {
        "source_mode": dataset.source_mode,
        "input_sources": list(dataset.input_sources),
        "clusters": clusters,
        "review_output_schema": load_skill_json_asset(_SKILL_NAME, "assets/log_issue_schema.json"),
    }


def collect_offline_log_review_payload(
    sources: tuple[Path, ...],
    *,
    log_time_window_days: int | None = None,
    log_start_time: str | None = None,
    log_end_time: str | None = None,
    collector: RedisInspectionOfflineCollector | None = None,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    dataset = collect_offline_inspection_dataset(
        sources,
        log_time_window_days=log_time_window_days,
        log_start_time=log_start_time,
        log_end_time=log_end_time,
        collector=collector,
        work_dir=work_dir,
    )
    return build_log_review_payload(dataset)


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


def parse_reviewed_log_issues(
    payload: str | list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> tuple[ReviewedLogIssue, ...]:
    if payload is None or payload == "":
        return ()
    raw: Any
    if isinstance(payload, str):
        raw = json.loads(payload)
    else:
        raw = payload
    if isinstance(raw, dict):
        raw_items = raw.get("issues") or raw.get("reviewed_log_issues") or []
    else:
        raw_items = raw
    if not isinstance(raw_items, (list, tuple)):
        raise ValueError("reviewed_log_issues_json must be a JSON list or object with an issues list.")

    issues: list[ReviewedLogIssue] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        issue_name = str(item.get("issue_name") or "").strip()
        if not issue_name:
            continue
        issues.append(
            ReviewedLogIssue(
                cluster_id=str(item.get("cluster_id") or "").strip(),
                cluster_name=str(item.get("cluster_name") or "").strip(),
                issue_name=issue_name,
                is_anomalous=_bool_value(item.get("is_anomalous")),
                severity=str(item.get("severity") or "medium").strip().lower(),
                why=str(item.get("why") or "").strip(),
                affected_nodes=_string_tuple(item.get("affected_nodes")),
                supporting_samples=_string_tuple(item.get("supporting_samples")),
                recommendation=str(item.get("recommendation") or "").strip(),
                merge_key=str(item.get("merge_key") or "").strip(),
                category=str(item.get("category") or "log").strip() or "log",
                confidence=str(item.get("confidence") or "medium").strip().lower(),
            )
        )
    return tuple(issues)


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


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "y"}
    return bool(value)


def _log_candidate_count(node: InspectionNode) -> int:
    value = node.log_facts.get("log_candidate_count")
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


__all__ = [
    "analyze_inspection",
    "analyze_offline_inspection",
    "analyze_remote_inspection",
    "build_log_review_payload",
    "collect_offline_inspection_dataset",
    "collect_offline_log_review_payload",
    "parse_reviewed_log_issues",
    "remote_snapshot_to_dataset",
    "summarize_inspection_dataset",
]
