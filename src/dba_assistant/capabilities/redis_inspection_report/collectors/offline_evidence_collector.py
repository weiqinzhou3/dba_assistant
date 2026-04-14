from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha1
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
from dba_assistant.application.request_models import DEFAULT_INSPECTION_LOG_TIME_WINDOW_DAYS
from dba_assistant.core.observability import get_current_execution_session


@dataclass(frozen=True)
class RedisInspectionOfflineInput:
    sources: tuple[Path, ...]
    system_name: str | None = None
    log_time_window_days: int | None = None
    log_start_time: str | None = None
    log_end_time: str | None = None


@dataclass(frozen=True)
class _EvidenceFile:
    path: Path
    relative_path: Path
    text: str


_IP_PORT_PATTERN = re.compile(
    r"(?P<ip>(?:\d{1,3}\.){3}\d{1,3})(?:[_:-](?P<port>\d{2,5}))?"
)
_FACT_LINE_PATTERN = re.compile(r"^\s*([^#\s:=][^:=\s]*)\s*(?::|\s)\s*(.*?)\s*$")
_LOG_CANDIDATE_PATTERN = re.compile(
    r"(?i)\b(error|warning|warn|restart|fail|failed|oom|fork|aof|rdb|replication|"
    r"append only|copy-on-write|bgsave|rewrite|cluster)\b"
)
_SECTION_PATTERN = re.compile(r"^#+\s*(?P<title>[^#].*?)\s*#+\s*$")
_ALLOWED_EVIDENCE_SUFFIXES = frozenset(
    {"", ".txt", ".log", ".output", ".conf", ".cfg", ".ini", ".json", ".out"}
)
_MAX_LOG_EVENTS_PER_NODE = 20
_LOG_TIMESTAMP_PATTERN = re.compile(
    r"(?P<ts>\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    r"(?:[\sT]\d{1,2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?)?)"
)
_LOG_DMY_YEAR_TIMESTAMP_PATTERN = re.compile(
    r"(?P<ts>\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}\s+\d{1,2}:\d{2}:\d{2}(?:\.\d{1,6})?)"
)
_LOG_DMY_NO_YEAR_TIMESTAMP_PATTERN = re.compile(
    r"(?P<ts>\d{1,2}\s+[A-Za-z]{3,9}\s+\d{1,2}:\d{2}:\d{2}(?:\.\d{1,6})?)"
)
_LOG_TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S.%f",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d",
)
_LOG_DMY_YEAR_TIMESTAMP_FORMATS = (
    "%d %b %Y %H:%M:%S.%f",
    "%d %b %Y %H:%M:%S",
    "%d %B %Y %H:%M:%S.%f",
    "%d %B %Y %H:%M:%S",
)
_LOG_DMY_NO_YEAR_TIMESTAMP_FORMATS = (
    "%d %b %H:%M:%S.%f",
    "%d %b %H:%M:%S",
    "%d %B %H:%M:%S.%f",
    "%d %B %H:%M:%S",
)


class RedisInspectionOfflineCollector:
    def collect(self, collector_input: RedisInspectionOfflineInput) -> InspectionDataset:
        if not collector_input.sources:
            raise ValueError("At least one offline inspection source is required.")

        log_time_bounds = _resolve_log_time_bounds(collector_input)

        nodes: list[InspectionNode] = []
        with tempfile.TemporaryDirectory(prefix="dba-inspection-") as tmp_name:
            tmp_root = Path(tmp_name)
            _record_phase(
                "offline_input_detected",
                source_count=len(collector_input.sources),
                input_sources=[str(Path(source).expanduser()) for source in collector_input.sources],
                log_time_window_days=collector_input.log_time_window_days,
                log_start_time=collector_input.log_start_time,
                log_end_time=collector_input.log_end_time,
                effective_log_start=log_time_bounds[0].isoformat() if log_time_bounds else None,
                effective_log_end=log_time_bounds[1].isoformat() if log_time_bounds else None,
            )
            _record_phase("archive_extract_start")
            for source in collector_input.sources:
                source = Path(source).expanduser()
                if not source.exists():
                    raise FileNotFoundError(f"Offline inspection source does not exist: {source}")
                nodes.extend(self._collect_source(source, tmp_root, log_time_bounds=log_time_bounds))
            _record_phase("archive_extract_end")

        _record_phase("evidence_grouping_start", node_candidate_count=len(nodes))
        systems = _group_nodes(nodes, fallback_system_name=collector_input.system_name)
        _attach_log_candidate_scope(systems)
        cluster_count = sum(len(system.clusters) for system in systems)
        unresolved_count = sum(
            1
            for system in systems
            for cluster in system.clusters
            if cluster.metadata.get("unresolved_grouping") == "true"
        )
        _record_phase(
            "evidence_grouping_end",
            system_count=len(systems),
            cluster_count=cluster_count,
            node_count=len(nodes),
            unresolved_grouping_count=unresolved_count,
        )
        _record_phase(
            "system_cluster_node_grouping_ready",
            system_count=len(systems),
            cluster_count=cluster_count,
            node_count=len(nodes),
            unresolved_grouping_count=unresolved_count,
        )
        return InspectionDataset(
            systems=systems,
            source_mode="offline",
            input_sources=tuple(str(Path(source).expanduser()) for source in collector_input.sources),
            metadata=_metadata_without_empty_values(
                {
                "route": "offline_inspection",
                "unresolved_grouping_count": str(unresolved_count),
                "log_time_window_days": collector_input.log_time_window_days,
                "log_start_time": collector_input.log_start_time,
                "log_end_time": collector_input.log_end_time,
                }
            ),
        )

    def _collect_source(
        self,
        source: Path,
        tmp_root: Path,
        *,
        log_time_bounds: tuple[datetime, datetime] | None = None,
    ) -> list[InspectionNode]:
        if source.is_file() and tarfile.is_tarfile(source):
            extract_root = tmp_root / _slug(source.stem)
            extract_root.mkdir(parents=True, exist_ok=True)
            self._safe_extract_tar(source, extract_root)
            return self._collect_directory(extract_root, log_time_bounds=log_time_bounds)
        if source.is_dir():
            return self._collect_directory(source, log_time_bounds=log_time_bounds)
        if not _is_supported_evidence_file(source):
            raise ValueError(f"Unsupported offline inspection evidence file: {source}")
        return [_build_node_from_group(source.parent, [_read_text_file(source, source.parent)], log_time_bounds=log_time_bounds)]

    def _collect_directory(
        self,
        root: Path,
        *,
        log_time_bounds: tuple[datetime, datetime] | None = None,
    ) -> list[InspectionNode]:
        nodes: list[InspectionNode] = []
        files: list[_EvidenceFile] = []
        nested_extract_root = root / ".dba-extracted"
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.is_relative_to(nested_extract_root):
                continue
            if tarfile.is_tarfile(path):
                nested_root = nested_extract_root / _slug(path.stem)
                nested_root.mkdir(parents=True, exist_ok=True)
                self._safe_extract_tar(path, nested_root)
                nodes.extend(self._collect_directory(nested_root, log_time_bounds=log_time_bounds))
                continue
            if not _is_supported_evidence_file(path):
                continue
            files.append(_read_text_file(path, root))
        grouped = _group_files_by_node(root, files)
        nodes.extend(
            _build_node_from_group(group_path, group_files, log_time_bounds=log_time_bounds)
            for group_path, group_files in grouped.items()
        )
        return nodes

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


def _build_node_from_group(
    group_path: Path,
    files: list[_EvidenceFile],
    *,
    log_time_bounds: tuple[datetime, datetime] | None = None,
) -> InspectionNode:
    redis_facts: dict[str, Any] = {}
    host_facts: dict[str, Any] = {}
    log_candidates: list[dict[str, Any]] = []
    log_candidate_count = 0
    source_paths = [item.path for item in files]

    for item in files:
        name = item.relative_path.name.lower()
        if _is_combined_output_file(name):
            parsed_redis_facts, parsed_host_facts = _parse_combined_output(item.text)
            redis_facts.update(parsed_redis_facts)
            host_facts.update({key: value for key, value in parsed_host_facts.items() if value})
            continue
        if _is_redis_fact_file(name):
            redis_facts.update(_parse_fact_lines(item.text))
            continue
        if "slowlog" in name:
            redis_facts["slowlog"] = {"count": _count_nonempty_lines(item.text), "entries": []}
            continue
        if "log" in name:
            available = max(0, _MAX_LOG_EVENTS_PER_NODE - len(log_candidates))
            parsed_candidates, parsed_count = _parse_log_candidates(
                item.text,
                limit=available,
                time_bounds=log_time_bounds,
                source_path=item.path,
            )
            log_candidates.extend(parsed_candidates)
            log_candidate_count += parsed_count
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
    inferred_ip = str(redis_facts.get("bind_ip") or host_facts.get("ip") or inferred_ip or "") or None
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
        log_facts={
            "log_candidates": [
                {
                    **candidate,
                    "node_id": node_id,
                    "source_path": candidate.get("source_path") or str(group_path),
                }
                for candidate in log_candidates
            ],
            "log_candidate_count": str(log_candidate_count),
            "log_candidate_overflow_count": str(max(0, log_candidate_count - len(log_candidates))),
        }
        if log_candidate_count
        else {},
    )


def _group_nodes(
    nodes: list[InspectionNode],
    *,
    fallback_system_name: str | None = None,
) -> tuple[InspectionSystem, ...]:
    system_buckets: dict[str, list[InspectionNode]] = {}
    for node in nodes:
        system_key = _system_key(node, fallback_system_name=fallback_system_name)
        system_buckets.setdefault(system_key, []).append(node)

    systems: list[InspectionSystem] = []
    for system_key, system_nodes in sorted(system_buckets.items()):
        cluster_buckets: dict[str, list[InspectionNode]] = {}
        for node in system_nodes:
            cluster_buckets.setdefault(_cluster_key(node), []).append(node)
        clusters: list[InspectionCluster] = []
        for key, grouped_nodes in sorted(cluster_buckets.items()):
            sorted_nodes = tuple(sorted(grouped_nodes, key=lambda item: item.node_id))
            cluster_type = _cluster_type(sorted_nodes)
            metadata = _cluster_metadata(key, sorted_nodes, cluster_type)
            clusters.append(
                InspectionCluster(
                    cluster_id=_slug(key),
                    name=metadata["candidate_cluster"],
                    cluster_type=cluster_type,
                    nodes=sorted_nodes,
                    metadata=metadata,
                )
            )
        systems.append(
            InspectionSystem(
                system_id=_slug(system_key),
                name=system_key,
                clusters=tuple(clusters),
                metadata={"node_count": str(len(system_nodes))},
            )
        )
    return tuple(systems)


def _attach_log_candidate_scope(systems: tuple[InspectionSystem, ...]) -> None:
    for system in systems:
        for cluster in system.clusters:
            for node in cluster.nodes:
                candidates = node.log_facts.get("log_candidates")
                if not isinstance(candidates, list):
                    continue
                for candidate in candidates:
                    if not isinstance(candidate, dict):
                        continue
                    candidate.setdefault("cluster_id", cluster.cluster_id)
                    candidate.setdefault("cluster_name", cluster.name)
                    candidate.setdefault("node_id", node.node_id)


def _cluster_key(node: InspectionNode) -> str:
    facts = node.redis_facts
    family = _cluster_family(node)
    if str(facts.get("cluster_enabled") or "0") == "1":
        return f"{family}|cluster_family"
    master_host = str(facts.get("master_host") or "").strip()
    master_port = str(facts.get("master_port") or "").strip()
    if master_host:
        return f"{family}|replication:{master_host}:{master_port or node.port or 6379}"
    if (node.role or "").lower() == "master":
        return f"{family}|replication:{node.ip or node.hostname}:{node.port or 6379}"
    if _has_redis_evidence(node):
        return f"{family}|standalone:{node.node_id}"
    return f"unknown|{node.node_id}"


def _cluster_type(nodes: tuple[InspectionNode, ...]) -> str:
    if not any(_has_redis_evidence(node) for node in nodes):
        return "unknown"
    if any(str(node.redis_facts.get("cluster_enabled") or "0") == "1" for node in nodes):
        return "redis-cluster"
    if len(nodes) > 1 or any(node.role for node in nodes):
        return "replication"
    return "standalone"


def _cluster_metadata(
    key: str,
    nodes: tuple[InspectionNode, ...],
    cluster_type: str,
) -> dict[str, Any]:
    candidate_cluster = key.split("|", 1)[0]
    evidence: list[str] = []
    confidence = "medium"
    if cluster_type == "redis-cluster" and any(node.redis_facts.get("cluster_topology_signature") for node in nodes):
        confidence = "high"
        evidence.append("cluster_nodes_topology_signature")
    if any(node.redis_facts.get("master_host") for node in nodes):
        evidence.append("replication_master_host")
    if any(node.hostname for node in nodes):
        evidence.append("hostname_family")
    if cluster_type == "unknown":
        confidence = "low"
        evidence.append("insufficient redis topology evidence")
    return {
        "candidate_cluster": candidate_cluster,
        "grouping_confidence": confidence,
        "grouping_evidence": evidence,
        "unresolved_grouping": "true" if confidence == "low" else "false",
    }


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
        facts[key.strip()] = value.strip().lstrip("=").strip()
    return facts


def _parse_combined_output(text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    facts = _parse_fact_lines(text)
    sections = _parse_sections(text)
    redis_facts: dict[str, Any] = dict(facts)
    host_facts: dict[str, Any] = {}

    hostname = str(facts.get("kernel.hostname") or "").strip() or _first_header_hostname(text)
    if hostname:
        host_facts["hostname"] = hostname
    release = _first_section_line(sections, "release")
    if release:
        host_facts["os"] = release
    kernel = _first_section_line(sections, "kernel version")
    if kernel:
        host_facts["kernel"] = kernel
    uptime = _first_section_line(sections, "uptime")
    if uptime:
        host_facts["uptime"] = uptime
    thp = _first_section_line(sections, "transparent_hugepage")
    if thp:
        host_facts["transparent_hugepage"] = thp

    ip = _first_ip_from_text(text)
    if ip:
        host_facts["ip"] = ip
        redis_facts.setdefault("bind_ip", ip)
    memory_summary = _memory_summary(text)
    if memory_summary:
        host_facts["memory"] = memory_summary
    swap_summary = _swap_summary(text)
    if swap_summary:
        host_facts["swap"] = swap_summary
    ulimit = _section_excerpt(sections, "ulimit", limit=4)
    if ulimit:
        host_facts["ulimit"] = ulimit
    iptables = _section_excerpt(sections, "iptables", limit=3)
    if iptables:
        host_facts["iptables_selinux"] = iptables

    cluster_lines = _section_lines(sections, "redis cluster")
    cluster_nodes = [_parse_cluster_node_line(line) for line in cluster_lines]
    cluster_nodes = [node for node in cluster_nodes if node]
    if cluster_nodes:
        redis_facts["cluster_nodes"] = cluster_nodes
        redis_facts["cluster_node_count"] = str(len(cluster_nodes))
        endpoint_signature = sorted(
            str(node.get("endpoint"))
            for node in cluster_nodes
            if node.get("endpoint")
        )
        if endpoint_signature:
            redis_facts["cluster_topology_signature"] = sha1(
                "|".join(endpoint_signature).encode("utf-8")
            ).hexdigest()[:12]
    return redis_facts, host_facts


def _parse_log_candidates(
    text: str,
    *,
    limit: int,
    time_bounds: tuple[datetime, datetime] | None = None,
    source_path: Path | None = None,
) -> tuple[list[dict[str, Any]], int]:
    candidates_by_key: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    candidate_count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _LOG_CANDIDATE_PATTERN.search(stripped)
        if match is None:
            continue
        timestamp = _extract_timestamp(stripped, time_bounds=time_bounds)
        if time_bounds is not None:
            # Active time filtering is strict: lines with unparseable timestamps
            # cannot bypass the requested/default window.
            if timestamp is None or timestamp < time_bounds[0] or timestamp > time_bounds[1]:
                continue
        candidate_count += 1
        key = _normalize_log_candidate_key(stripped)
        existing = candidates_by_key.get(key)
        if existing is not None:
            existing["count"] = int(existing["count"]) + 1
            existing["repeated_count"] = int(existing["repeated_count"]) + 1
            continue
        if len(ordered_keys) >= limit:
            continue
        ordered_keys.append(key)
        candidates_by_key[key] = {
            "timestamp": timestamp.isoformat() if timestamp is not None else None,
            "raw_message": stripped,
            "candidate_signal": _candidate_signal(stripped),
            "count": 1,
            "repeated_count": 0,
            "source_path": str(source_path) if source_path is not None else "",
            "parse_confidence": "high" if timestamp is not None else "unbounded",
            "time_window_applied": time_bounds is not None,
        }
    return [candidates_by_key[key] for key in ordered_keys], candidate_count


def _normalize_log_candidate_key(message: str) -> str:
    return re.sub(r"\s+", " ", message.strip())


def _candidate_signal(message: str) -> str:
    lowered = message.lower()
    if "oom" in lowered:
        return "oom_signal"
    if "fork" in lowered:
        return "fork_signal"
    if "cluster" in lowered and ("fail" in lowered or "failed" in lowered):
        return "cluster_fail_signal"
    if "replication" in lowered or "replica" in lowered or "slave" in lowered or "master" in lowered:
        return "replication_signal"
    if any(token in lowered for token in ("aof", "rdb", "bgsave", "append only", "copy-on-write", "rewrite")):
        return "persistence_signal"
    if "warning" in lowered or "warn" in lowered:
        return "warning_signal"
    return "generic_attention_signal"


def _is_redis_fact_file(name: str) -> bool:
    return name in {"info", "info.txt", "redis_info.txt", "redis-info.txt"} or "redis_info" in name


def _is_combined_output_file(name: str) -> bool:
    return name.endswith(".output") or name.endswith(".out")


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


def _system_key(node: InspectionNode, *, fallback_system_name: str | None) -> str:
    if fallback_system_name:
        return fallback_system_name
    hostname = _normalized_hostname(node.hostname)
    family = _hostname_family_parts(hostname)
    if not family:
        return "Redis System"
    parts = family.split("-")
    if parts[0] == "pr" and len(parts) >= 2:
        return "-".join(parts[:2])
    if parts[-1].startswith("redis") and len(parts) > 1:
        return "-".join(parts[:-1]) or parts[0]
    if len(parts) >= 2 and parts[1].startswith("redis"):
        return parts[0]
    return parts[0]


def _cluster_family(node: InspectionNode) -> str:
    hostname = _normalized_hostname(node.hostname)
    family = _hostname_family_parts(hostname)
    if family:
        return family.replace("sccust-redis", "sccust_redis")
    return f"standalone-{node.node_id}"


def _hostname_family_parts(hostname: str) -> str:
    if not hostname:
        return ""
    value = re.sub(r"[-_]?v?\d+$", "", hostname)
    value = re.sub(r"redis\d+$", "redis", value)
    value = re.sub(r"[-_]+$", "", value)
    return value


def _normalized_hostname(hostname: str) -> str:
    return hostname.strip().lower().replace("_", "-")


def _has_redis_evidence(node: InspectionNode) -> bool:
    facts = node.redis_facts
    return any(
        key in facts
        for key in (
            "redis_version",
            "redis_mode",
            "role",
            "cluster_enabled",
            "used_memory",
            "maxmemory",
        )
    )


def _parse_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = _SECTION_PATTERN.match(line.strip())
        if match:
            current = _clean_section_title(match.group("title")).lower()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line.rstrip())
    return sections


def _first_header_hostname(text: str) -> str:
    for line in text.splitlines():
        match = _SECTION_PATTERN.match(line.strip())
        if not match:
            continue
        title = _clean_section_title(match.group("title"))
        if title.lower() not in {
            "uptime",
            "release",
            "kernel version",
            "ip addr",
            "kernel variables",
        }:
            return title
    return ""


def _section_lines(sections: dict[str, list[str]], key_fragment: str) -> list[str]:
    for key, lines in sections.items():
        if key_fragment in key:
            return [line.strip() for line in lines if line.strip()]
    return []


def _first_section_line(sections: dict[str, list[str]], key_fragment: str) -> str:
    lines = _section_lines(sections, key_fragment)
    return lines[0] if lines else ""


def _section_excerpt(sections: dict[str, list[str]], key_fragment: str, *, limit: int) -> str:
    lines = _section_lines(sections, key_fragment)
    return " / ".join(lines[:limit])


def _first_ip_from_text(text: str) -> str:
    match = re.search(r"\binet\s+((?:\d{1,3}\.){3}\d{1,3})(?:/|\s)", text)
    return match.group(1) if match else ""


def _memory_summary(text: str) -> str:
    total = _first_regex(text, r"MemTotal:\s+([^\n]+)")
    free = _first_regex(text, r"MemFree:\s+([^\n]+)")
    if total or free:
        return f"MemTotal: {total or '-'} / MemFree: {free or '-'}"
    return ""


def _swap_summary(text: str) -> str:
    total = _first_regex(text, r"SwapTotal:\s+([^\n]+)")
    free = _first_regex(text, r"SwapFree:\s+([^\n]+)")
    if total or free:
        return f"SwapTotal: {total or '-'} / SwapFree: {free or '-'}"
    return ""


def _first_regex(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _parse_cluster_node_line(line: str) -> dict[str, Any]:
    parts = line.split()
    if len(parts) < 3 or ":" not in parts[1]:
        return {}
    endpoint = parts[1].split("@", 1)[0]
    ip, port = endpoint.rsplit(":", 1)
    flags = parts[2].split(",")
    role = "master" if "master" in flags else "replica" if "slave" in flags else "unknown"
    return {
        "node_id": parts[0],
        "endpoint": endpoint,
        "ip": ip,
        "port": port,
        "role": role,
        "master_id": parts[3] if len(parts) > 3 and parts[3] != "-" else "",
    }


def _clean_section_title(title: str) -> str:
    cleaned = re.sub(r"[=#]+", " ", title).strip()
    return re.sub(r"\s+", " ", cleaned)


def _is_supported_evidence_file(path: Path) -> bool:
    if tarfile.is_tarfile(path):
        return True
    name = path.name.lower()
    return name in {"info", "redis_info", "hostname", "uname"} or path.suffix.lower() in _ALLOWED_EVIDENCE_SUFFIXES


def _record_phase(phase: str, **payload: Any) -> None:
    session = get_current_execution_session()
    if session is None:
        return
    session.record_event("redis_inspection_phase", phase=phase, **payload)


def _metadata_without_empty_values(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in {None, ""}}


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return slug or "redis-system"


def _resolve_log_time_bounds(
    collector_input: RedisInspectionOfflineInput,
) -> tuple[datetime, datetime] | None:
    """Compute effective (start, end) for log filtering.

    Priority:
    1. Explicit log_start_time / log_end_time from user
    2. log_time_window_days from user
    3. Default: last 30 days
    """
    now = datetime.now()
    if collector_input.log_start_time or collector_input.log_end_time:
        start = (
            _parse_user_timestamp(collector_input.log_start_time)
            if collector_input.log_start_time
            else (now - timedelta(days=DEFAULT_INSPECTION_LOG_TIME_WINDOW_DAYS))
        )
        end = (
            _parse_user_timestamp(collector_input.log_end_time)
            if collector_input.log_end_time
            else now
        )
        return (start, end)
    window_days = (
        collector_input.log_time_window_days
        if collector_input.log_time_window_days is not None
        else DEFAULT_INSPECTION_LOG_TIME_WINDOW_DAYS
    )
    return (now - timedelta(days=window_days), now)


def _parse_user_timestamp(value: str) -> datetime:
    parsed = _parse_iso_timestamp(value.strip())
    if parsed is not None:
        return parsed
    for fmt in _LOG_TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        pass
    raise ValueError(f"Unsupported log timestamp: {value}")


def _extract_timestamp(
    line: str,
    *,
    time_bounds: tuple[datetime, datetime] | None = None,
) -> datetime | None:
    match = _LOG_TIMESTAMP_PATTERN.search(line)
    if match is not None:
        raw = match.group("ts")
        parsed = _parse_iso_timestamp(raw)
        if parsed is not None:
            return parsed
        parsed = _parse_with_formats(raw, _LOG_TIMESTAMP_FORMATS)
        if parsed is not None:
            return parsed

    match = _LOG_DMY_YEAR_TIMESTAMP_PATTERN.search(line)
    if match is not None:
        parsed = _parse_with_formats(match.group("ts"), _LOG_DMY_YEAR_TIMESTAMP_FORMATS)
        if parsed is not None:
            return parsed

    match = _LOG_DMY_NO_YEAR_TIMESTAMP_PATTERN.search(line)
    if match is not None:
        return _parse_day_month_without_year(match.group("ts"), time_bounds=time_bounds)

    return None


def _parse_with_formats(value: str, formats: tuple[str, ...]) -> datetime | None:
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _parse_iso_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _parse_day_month_without_year(
    value: str,
    *,
    time_bounds: tuple[datetime, datetime] | None,
) -> datetime | None:
    parsed_without_year = _parse_with_formats(value, _LOG_DMY_NO_YEAR_TIMESTAMP_FORMATS)
    if parsed_without_year is None:
        return None

    if time_bounds is None:
        return parsed_without_year.replace(year=datetime.now().year)

    start, end = time_bounds
    for year in range(start.year, end.year + 1):
        candidate = parsed_without_year.replace(year=year)
        if start <= candidate <= end:
            return candidate
    return parsed_without_year.replace(year=start.year)


__all__ = ["RedisInspectionOfflineCollector", "RedisInspectionOfflineInput"]
