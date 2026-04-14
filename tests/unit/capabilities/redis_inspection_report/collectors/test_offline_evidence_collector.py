from pathlib import Path
import tarfile

from dba_assistant.capabilities.redis_inspection_report.collectors.offline_evidence_collector import (
    RedisInspectionOfflineCollector,
    RedisInspectionOfflineInput,
)


def _write_output(
    node_root: Path,
    *,
    hostname: str,
    ip: str,
    port: int,
    display_title: str | None = None,
    role: str = "master",
    master_host: str | None = None,
    cluster_enabled: str = "1",
    cluster_lines: tuple[str, ...] = (),
) -> None:
    date_dir = node_root / str(port) / "20260324"
    date_dir.mkdir(parents=True)
    replication_lines = [f"role:{role}"]
    if master_host:
        replication_lines.extend(
            [
                f"master_host:{master_host}",
                f"master_port:{port}",
                "master_link_status:up",
            ]
        )
    (date_dir / f"{hostname}-20260324-090000.output").write_text(
        "\n".join(
            [
                f"############ {display_title or hostname} #############",
                "############ uptime #############",
                " 09:21:25 up 10 days,  1 user,  load average: 0.01, 0.02, 0.03",
                "############ release #############",
                "Red Hat Enterprise Linux release 8.8 (Ootpa)",
                "############ kernel version#############",
                f"Linux {hostname} 4.18.0-test x86_64 GNU/Linux",
                "############ IP ADDR #############",
                f"    inet {ip}/24 brd 10.0.0.255 scope global eth0",
                "############ kernel variables #############",
                f"kernel.hostname = {hostname}",
                "############ memory #############",
                "MemTotal:       131975056 kB",
                "MemFree:        80000000 kB",
                "SwapTotal:       8388604 kB",
                "SwapFree:        8380000 kB",
                "############ transparent_hugepage #############",
                "[always] madvise never",
                "############ redis info #############",
                "redis_version:7.0.15",
                "redis_mode:cluster",
                f"tcp_port:{port}",
                "used_memory:100",
                "maxmemory:1000",
                "mem_fragmentation_ratio:1.01",
                "rdb_last_bgsave_status:ok",
                "aof_enabled:1",
                *replication_lines,
                f"cluster_enabled:{cluster_enabled}",
                "cluster_state:ok",
                "db0:keys=10,expires=5,avg_ttl=1000",
                "############ redis cluster #############",
                *cluster_lines,
            ]
        ),
        encoding="utf-8",
    )
    (date_dir / "redis.log").write_text("Ready to accept connections\n", encoding="utf-8")


def test_offline_collector_normalizes_node_directories_into_cluster_dataset(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    node_a = root / "10.0.0.1_6379"
    node_b = root / "10.0.0.2_6379"
    node_a.mkdir(parents=True)
    node_b.mkdir(parents=True)
    (node_a / "redis_info.txt").write_text(
        "\n".join(
            [
                "redis_version:6.2.12",
                "tcp_port:6379",
                "role:master",
                "cluster_enabled:1",
                "cluster_state:ok",
                "used_memory:100",
                "maxmemory:1000",
            ]
        ),
        encoding="utf-8",
    )
    (node_a / "redis.log").write_text("2026-04-14 # Error loading DB\n", encoding="utf-8")
    (node_b / "INFO").write_text(
        "\n".join(
            [
                "redis_version:6.2.12",
                "tcp_port:6379",
                "role:slave",
                "master_host:10.0.0.1",
                "master_port:6379",
                "cluster_enabled:1",
                "cluster_state:ok",
            ]
        ),
        encoding="utf-8",
    )
    (node_b / "thp.txt").write_text("always [madvise] never\n", encoding="utf-8")

    dataset = RedisInspectionOfflineCollector().collect(RedisInspectionOfflineInput(sources=(root,)))

    assert dataset.source_mode == "offline"
    assert dataset.input_sources == (str(root),)
    assert len(dataset.systems) == 1
    assert len(dataset.systems[0].clusters) == 1
    cluster = dataset.systems[0].clusters[0]
    assert cluster.cluster_type == "redis-cluster"
    assert [node.node_id for node in cluster.nodes] == ["10.0.0.1:6379", "10.0.0.2:6379"]
    first = cluster.nodes[0]
    assert first.hostname == "10.0.0.1"
    assert first.role == "master"
    assert first.redis_facts["redis_version"] == "6.2.12"
    assert first.log_facts["error_events"][0]["message"] == "2026-04-14 # Error loading DB"
    assert cluster.nodes[1].host_facts["transparent_hugepage"] == "always [madvise] never"


def test_offline_collector_accepts_mixed_tar_and_directory_inputs(tmp_path: Path) -> None:
    archive_root = tmp_path / "archive-root"
    _write_output(
        archive_root / "sccust_redis01",
        hostname="sccust_redis01",
        ip="10.0.0.1",
        port=6380,
        cluster_lines=(
            "node-a 10.0.0.1:6380@16380 master - 0 0 1 connected 0-5460",
            "node-b 10.0.0.2:6380@16380 slave node-a 0 0 2 connected",
        ),
    )
    archive = tmp_path / "sccust-node.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(archive_root, arcname="archive-root")

    directory_root = tmp_path / "directory-root"
    _write_output(
        directory_root / "sccust_redis02",
        hostname="sccust_redis02",
        ip="10.0.0.2",
        port=6380,
        role="slave",
        master_host="10.0.0.1",
        cluster_lines=(
            "node-a 10.0.0.1:6380@16380 master - 0 0 1 connected 0-5460",
            "node-b 10.0.0.2:6380@16380 slave node-a 0 0 2 connected",
        ),
    )

    dataset = RedisInspectionOfflineCollector().collect(
        RedisInspectionOfflineInput(sources=(archive, directory_root))
    )

    system = dataset.systems[0]
    assert system.name == "sccust"
    assert len(system.clusters) == 1
    cluster = system.clusters[0]
    assert cluster.name == "sccust_redis"
    assert cluster.metadata["grouping_confidence"] == "high"
    assert cluster.metadata["grouping_evidence"]
    assert [node.hostname for node in cluster.nodes] == ["sccust_redis01", "sccust_redis02"]


def test_offline_collector_groups_multiple_subclusters_under_one_system(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write_output(
        root / "pr-plms-redis-v01",
        hostname="pr-plms-redis-v01",
        ip="10.0.1.1",
        port=6379,
        display_title="= pr-plms-redis-v01 =",
    )
    _write_output(root / "pr-plms-redis-v02", hostname="pr-plms-redis-v02", ip="10.0.1.2", port=6379)
    _write_output(root / "pr-plms-rcsredis-v01", hostname="pr-plms-rcsredis-v01", ip="10.0.2.1", port=6379)

    dataset = RedisInspectionOfflineCollector().collect(RedisInspectionOfflineInput(sources=(root,)))

    assert [system.name for system in dataset.systems] == ["pr-plms"]
    clusters = dataset.systems[0].clusters
    assert [cluster.name for cluster in clusters] == ["pr-plms-rcsredis", "pr-plms-redis"]
    assert [len(cluster.nodes) for cluster in clusters] == [1, 2]


def test_offline_collector_keeps_uncertain_grouping_explainable(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    node_dir = root / "unknown-node"
    node_dir.mkdir(parents=True)
    (node_dir / "notes.txt").write_text("plain evidence without redis topology\n", encoding="utf-8")

    dataset = RedisInspectionOfflineCollector().collect(RedisInspectionOfflineInput(sources=(root,)))

    cluster = dataset.systems[0].clusters[0]
    assert cluster.cluster_type == "unknown"
    assert cluster.metadata["grouping_confidence"] == "low"
    assert cluster.metadata["unresolved_grouping"] == "true"
    assert "insufficient" in " ".join(cluster.metadata["grouping_evidence"])
    assert dataset.metadata["unresolved_grouping_count"] == "1"


def test_offline_collector_rejects_unsupported_file_inputs(tmp_path: Path) -> None:
    unsupported = tmp_path / "screenshot.png"
    unsupported.write_bytes(b"\x89PNG\r\n")

    try:
        RedisInspectionOfflineCollector().collect(RedisInspectionOfflineInput(sources=(unsupported,)))
    except ValueError as exc:
        assert "Unsupported offline inspection evidence file" in str(exc)
    else:
        raise AssertionError("unsupported file should be rejected")


def test_offline_collector_keeps_log_events_bounded_with_overflow_metadata(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    node_dir = root / "redis-node"
    node_dir.mkdir(parents=True)
    (node_dir / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")
    (node_dir / "redis.log").write_text(
        "\n".join(f"2026-04-14 09:00:{index:02d} # ERROR sample event {index}" for index in range(25)),
        encoding="utf-8",
    )

    dataset = RedisInspectionOfflineCollector().collect(RedisInspectionOfflineInput(sources=(root,)))

    node = dataset.systems[0].clusters[0].nodes[0]
    assert len(node.log_facts["error_events"]) == 20
    assert node.log_facts["error_event_count"] == "25"
    assert node.log_facts["error_event_overflow_count"] == "5"


def test_offline_collector_accepts_tar_gz_evidence_bundle(tmp_path: Path) -> None:
    bundle_root = tmp_path / "bundle"
    node_dir = bundle_root / "redis-node"
    node_dir.mkdir(parents=True)
    (node_dir / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6380\n", encoding="utf-8")
    archive = tmp_path / "inspection.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(bundle_root, arcname="bundle")

    dataset = RedisInspectionOfflineCollector().collect(RedisInspectionOfflineInput(sources=(archive,)))

    node = dataset.systems[0].clusters[0].nodes[0]
    assert node.port == 6380
    assert node.version == "7.0.15"
    assert node.source_path.endswith("bundle/redis-node")


# ---------------------------------------------------------------------------
# Round 1.2: Log time window filtering tests
# ---------------------------------------------------------------------------


def test_log_time_window_filters_old_events_by_default(tmp_path: Path) -> None:
    """Default 30-day window should exclude events older than 30 days."""
    root = tmp_path / "evidence"
    node_dir = root / "redis-node"
    node_dir.mkdir(parents=True)
    (node_dir / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")

    from datetime import datetime, timedelta
    recent = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    old = "2023-01-15 10:00:00"
    ancient = "2024-03-01 08:00:00"
    (node_dir / "redis.log").write_text(
        "\n".join([
            f"{recent} # ERROR recent event within window",
            f"{old} # ERROR old event outside window 2023",
            f"{ancient} # ERROR old event outside window 2024",
            f"{recent} # WARNING another recent warning",
        ]),
        encoding="utf-8",
    )

    dataset = RedisInspectionOfflineCollector().collect(
        RedisInspectionOfflineInput(sources=(root,))
    )

    node = dataset.systems[0].clusters[0].nodes[0]
    assert int(node.log_facts["error_event_count"]) == 2, (
        "Only events within the default 30-day window should be counted"
    )


def test_log_time_window_explicit_days(tmp_path: Path) -> None:
    """Explicit log_time_window_days=7 should only keep events from last 7 days."""
    root = tmp_path / "evidence"
    node_dir = root / "redis-node"
    node_dir.mkdir(parents=True)
    (node_dir / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")

    from datetime import datetime, timedelta
    within_7 = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    outside_7 = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d %H:%M:%S")
    (node_dir / "redis.log").write_text(
        "\n".join([
            f"{within_7} # ERROR event within 7 days",
            f"{outside_7} # ERROR event outside 7 days",
        ]),
        encoding="utf-8",
    )

    dataset = RedisInspectionOfflineCollector().collect(
        RedisInspectionOfflineInput(sources=(root,), log_time_window_days=7)
    )

    node = dataset.systems[0].clusters[0].nodes[0]
    assert int(node.log_facts["error_event_count"]) == 1


def test_log_without_timestamp_not_filtered_out(tmp_path: Path) -> None:
    """Log lines without parseable timestamps should pass through the filter."""
    root = tmp_path / "evidence"
    node_dir = root / "redis-node"
    node_dir.mkdir(parents=True)
    (node_dir / "info.txt").write_text("redis_version:7.0.15\nrole:master\ntcp_port:6379\n", encoding="utf-8")
    (node_dir / "redis.log").write_text(
        "Some ERROR without timestamp\n",
        encoding="utf-8",
    )

    dataset = RedisInspectionOfflineCollector().collect(
        RedisInspectionOfflineInput(sources=(root,))
    )

    node = dataset.systems[0].clusters[0].nodes[0]
    assert int(node.log_facts["error_event_count"]) == 1
