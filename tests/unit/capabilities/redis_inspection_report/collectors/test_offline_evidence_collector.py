from pathlib import Path
import tarfile

from dba_assistant.capabilities.redis_inspection_report.collectors.offline_evidence_collector import (
    RedisInspectionOfflineCollector,
    RedisInspectionOfflineInput,
)


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
