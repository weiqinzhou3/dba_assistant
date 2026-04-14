from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import tarfile
import tempfile
from typing import Any

from dba_assistant.capabilities.redis_inspection_report.types import (
    InspectionCluster,
    InspectionDataset,
    InspectionNode,
    InspectionSystem,
)


@dataclass(frozen=True)
class RedisInspectionOfflineInput:
    sources: tuple[Path, ...]
    system_name: str | None = None


@dataclass(frozen=True)
class _EvidenceFile:
    path: Path
    relative_path: Path
    text: str


_IP_PORT_PATTERN = re.compile(
    r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3})(?:[_:-](?P<port>\d{2,5}))?"
)
_FACT_LINE_PATTERN = re.compile(r"^\s*([^#\s:=][^:=\s]*)\s*(?::|\s)\s*(.*?)\s*$")
_LOG_EVENT_PATTERN = re.compile(
    r"(?i)\b(error|warning|warn|restart|fail|oom|fork|aof|rdb|replication)\b"
)


class RedisInspectionOfflineCollector:
    def collect(self, collector_input: RedisInspectionOfflineInput) -> InspectionDataset:
        if not collector_input.sources:
            raise ValueError("At least one offline inspection source is required.")

        nodes: list[InspectionNode] = []
        with tempfile.TemporaryDirectory(prefix="dba-inspection-") as tmp_name:
            tmp_root = Path(tmp_name)
            for source in collector_input.sources:
                source = Path(source).expanduser()
                if not source.exists():
                    raise FileNotFoundError(f"Offline inspection source does not exist: {source}")
                nodes.extend(self._collect_source(source, tmp_root))

        clusters = _group_nodes(nodes)
        system_name = collector_input.system_name or _default_system_name(collector_input.sources)
        return InspectionDataset(
            systems=(
                InspectionSystem(
                    system_id=_slug(system_name),
                    name=system_name,
                    clusters=clusters,
                ),
            ),
            source_mode="offline",
            input_sources=tuple(str(Path(source).expanduser()) for source in collector_input.sources),
            metadata={"route": "offline_inspection"},
        )

    def _collect_source(self, source: Path, tmp_root: Path) -> list[InspectionNode]:
        if source.is_file() and tarfile.is_tarfile(source):
            extract_root = tmp_root / _slug(source.stem)
            extract_root.mkdir(parents=True, exist_ok=True)
            self._safe_extract_tar(source, extract_root)
            return self._collect_directory(extract_root)
        if source.is_dir():
            return self._collect_directory(source)
        return [_build_node_from_group(source.parent, [_read_text_file(source, source.parent)])]

    def _collect_directory(self, root: Path) -> list[InspectionNode]:
        files = [_read_text_file(path, root) for path in sorted(root.rglob("*")) if path.is_file()]
        grouped = _group_files_by_node(root, files)
        return [_build_node_from_group(group_path, group_files) for group_path, group_files in grouped.items()]

    def _safe_extract_tar(self, archive: Path, destination: Path) -> None:
        destination_resolved = destination.resolve()
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                target = (destination / member.name).resolve()
                if os.path.commonpath((str(destination_resolved), str(target))) != str(destination_resolved):
                    raise ValueError(f"Unsafe path in inspection archive: {member.name}")
            tar.extractall(destination)


def _read_text_file(path: Path, root: Path) -> _EvidenceFile:
    text = path.read_bytes().decode("utf-8", errors="replace")
    return _EvidenceFile(path=path, relative_path=path.relative_to(root), text=text)


def _group_files_by_node(root: Path, files: list[_EvidenceFile]) -> dict[Path, list[_EvidenceFile]]:
    groups: dict[Path, list[_EvidenceFile]] = {}
    for item in files:
        group_path = _node_group_path(root, item.path)
        groups.setdefault(group_path, []).append(item)
    return groups


def _node_group_path(root: Path, path: Path) -> Path:
    parent = path.parent
    return root if parent == root else parent


def _build_node_from_group(group_path: Path, files: list[_EvidenceFile]) -> InspectionNode:
    redis_facts: dict[str, Any] = {}
    host_facts: dict[str, Any] = {}
    log_events: list[dict[str, str]] = []
    source_paths = [item.path for item in files]

    for item in files:
        name = item.relative_path.name.lower()
        if _is_redis_fact_file(name):
            redis_facts.update(_parse_fact_lines(item.text))
            continue
        if "slowlog" in name:
            redis_facts["slowlog"] = {"count": _count_nonempty_lines(item.text), "entries": []}
            continue
        if "log" in name:
            log_events.extend(_parse_log_events(item.text))
            continue
        if _is_thp_file(name):
            host_facts["transparent_hugepage"] = _first_nonempty_line(item.text)
            continue
        if name in {"hostname", "hostname.txt"}:
            host_facts["hostname"] = _first_nonempty_line(item.text)
            continue
        if name in {"uname", "uname.txt", "kernel.txt"}:
            host_facts["kernel"] = _first_nonempty_line(item.text)
            continue
        if "os" in name or "release" in name:
            host_facts["os"] = _first_nonempty_line(item.text)

    inferred_ip, inferred_port = _infer_ip_port(group_path, source_paths)
    port = _coerce_int(redis_facts.get("tcp_port")) or inferred_port or 6379
    hostname = str(host_facts.get("hostname") or inferred_ip or group_path.name)
    role = _normalize_role(str(redis_facts.get("role") or ""))
    version = str(redis_facts.get("redis_version") or "") or None
    node_id = f"{inferred_ip or hostname}:{port}"

    return InspectionNode(
        node_id=node_id,
        hostname=hostname,
        ip=inferred_ip,
        port=port,
        role=role,
        version=version,
        source_path=str(group_path),
        collect_time=str(redis_facts.get("collect_time") or "") or None,
        host_facts=host_facts,
        redis_facts=redis_facts,
        log_facts={"error_events": log_events} if log_events else {},
    )


def _group_nodes(nodes: list[InspectionNode]) -> tuple[InspectionCluster, ...]:
    buckets: dict[str, list[InspectionNode]] = {}
    for node in nodes:
        cluster_key = _cluster_key(node)
        buckets.setdefault(cluster_key, []).append(node)

    clusters: list[InspectionCluster] = []
    for key, grouped_nodes in sorted(buckets.items()):
        sorted_nodes = tuple(sorted(grouped_nodes, key=lambda item: item.node_id))
        cluster_type = _cluster_type(sorted_nodes)
        clusters.append(
            InspectionCluster(
                cluster_id=key,
                name=key,
                cluster_type=cluster_type,
                nodes=sorted_nodes,
            )
        )
    return tuple(clusters)


def _cluster_key(node: InspectionNode) -> str:
    facts = node.redis_facts
    if str(facts.get("cluster_enabled") or "0") == "1":
        return str(facts.get("cluster_id") or "redis-cluster")
    master_host = str(facts.get("master_host") or "").strip()
    master_port = str(facts.get("master_port") or "").strip()
    if master_host:
        return f"replication-{master_host}:{master_port or 6379}"
    if (node.role or "").lower() == "master":
        return f"replication-{node.ip or node.hostname}:{node.port or 6379}"
    return f"standalone-{node.node_id}"


def _cluster_type(nodes: tuple[InspectionNode, ...]) -> str:
    if any(str(node.redis_facts.get("cluster_enabled") or "0") == "1" for node in nodes):
        return "redis-cluster"
    if len(nodes) > 1 or any(node.role for node in nodes):
        return "replication"
    return "standalone"


def _parse_fact_lines(text: str) -> dict[str, str]:
    facts: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _FACT_LINE_PATTERN.match(stripped)
        if match is None:
            continue
        key, value = match.groups()
        facts[key.strip()] = value.strip()
    return facts


def _parse_log_events(text: str) -> list[dict[str, str]]:
    events = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _LOG_EVENT_PATTERN.search(stripped)
        if match is None:
            continue
        events.append({"level": match.group(1).lower(), "message": stripped})
    return events


def _is_redis_fact_file(name: str) -> bool:
    return name in {"info", "info.txt", "redis_info.txt", "redis-info.txt"} or "redis_info" in name


def _is_thp_file(name: str) -> bool:
    return "transparent_hugepage" in name or name in {"thp", "thp.txt"}


def _infer_ip_port(group_path: Path, source_paths: list[Path]) -> tuple[str | None, int | None]:
    search_text = " ".join([group_path.name, *(path.name for path in source_paths), str(group_path)])
    match = _IP_PORT_PATTERN.search(search_text)
    if match is None:
        return None, None
    port = match.group("port")
    return match.group("ip"), int(port) if port else None


def _normalize_role(role: str) -> str | None:
    role = role.strip().lower()
    if role == "slave":
        return "replica"
    return role or None


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _count_nonempty_lines(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


def _coerce_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _default_system_name(sources: tuple[Path, ...]) -> str:
    if len(sources) == 1:
        return Path(sources[0]).expanduser().stem or "Redis System"
    return "Redis System"


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return slug or "redis-system"


__all__ = ["RedisInspectionOfflineCollector", "RedisInspectionOfflineInput"]
