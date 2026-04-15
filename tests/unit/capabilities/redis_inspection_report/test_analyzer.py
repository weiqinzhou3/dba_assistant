from dba_assistant.capabilities.redis_inspection_report.analyzer import (
    analyze_inspection_dataset,
    _keyspace_summary,
    _cluster_status_display,
)
from dba_assistant.capabilities.redis_inspection_report.types import (
    InspectionCluster,
    InspectionDataset,
    InspectionNode,
    InspectionSystem,
    ReviewedLogIssue,
)


def test_analyzer_builds_report_sections_and_findings_from_cluster_dataset() -> None:
    dataset = InspectionDataset(
        systems=(
            InspectionSystem(
                system_id="system-1",
                name="Payment Redis",
                clusters=(
                    InspectionCluster(
                        cluster_id="cluster-a",
                        name="cluster-a",
                        cluster_type="redis-cluster",
                        nodes=(
                            InspectionNode(
                                node_id="10.0.0.1:6379",
                                hostname="redis-a",
                                ip="10.0.0.1",
                                port=6379,
                                role="master",
                                version="6.2.12",
                                source_path="/evidence/redis-a",
                                redis_facts={
                                    "used_memory": "920",
                                    "maxmemory": "1000",
                                    "mem_fragmentation_ratio": "1.82",
                                    "db0": "keys=100,expires=40,avg_ttl=1000",
                                    "rdb_bgsave_in_progress": "0",
                                    "rdb_last_bgsave_status": "err",
                                    "aof_enabled": "0",
                                    "cluster_enabled": "1",
                                    "cluster_state": "fail",
                                    "master_link_status": "down",
                                },
                                host_facts={"transparent_hugepage": "[always] madvise never", "swap": "SwapTotal: 1G / SwapFree: 0"},
                                log_facts={
                                    "log_candidates": [
                                        {"candidate_signal": "oom_signal", "raw_message": "OOM command not allowed"},
                                        {"candidate_signal": "replication_signal", "raw_message": "replication backlog warning"},
                                    ],
                                    "log_candidate_count": "2",
                                },
                            ),
                            InspectionNode(
                                node_id="10.0.0.2:6379",
                                hostname="redis-b",
                                ip="10.0.0.2",
                                port=6379,
                                role="replica",
                                version="7.0.15",
                                source_path="/evidence/redis-b",
                                redis_facts={"used_memory": "100", "maxmemory": "1000"},
                            ),
                        ),
                    ),
                ),
            ),
        ),
        source_mode="offline",
        input_sources=("/evidence",),
        reviewed_log_issues=(
            ReviewedLogIssue(
                cluster_id="cluster-a",
                cluster_name="cluster-a",
                issue_name="Redis 日志显示 OOM 与复制异常",
                is_anomalous=True,
                severity="high",
                why="OOM and replication warning were reviewed as related runtime anomalies.",
                affected_nodes=("10.0.0.1:6379",),
                supporting_samples=("OOM command not allowed", "replication backlog warning"),
                recommendation="检查内存水位、复制链路和业务写入峰值。",
                merge_key="cluster-a:oom-replication",
                category="log",
                confidence="high",
            ),
        ),
    )

    report = analyze_inspection_dataset(dataset, language="zh-CN")

    assert report.title == "Redis 巡检报告"
    assert report.metadata["system_count"] == "1"
    assert report.metadata["cluster_count"] == "1"
    assert report.metadata["node_count"] == "2"
    assert report.summary is None
    assert int(report.metadata["finding_count"]) >= 8
    top_level_titles = [section.title for section in report.sections if section.level == 1]
    assert top_level_titles == [
        "巡检概述",
        "巡检范围与输入说明",
        "问题概览与整改优先级",
        "集群识别与架构总览",
        "巡检目标及方法",
        "系统配置检查",
        "操作系统检查",
        "Redis 数据库检查",
        "风险与整改建议",
        "附录",
    ]
    assert top_level_titles.count("巡检概述") == 1
    cluster_subsections = [section for section in report.sections if section.level == 2]
    assert [section.title for section in cluster_subsections].count("cluster-a") >= 4
    main_tables = [
        block
        for section in report.sections
        if section.id != "appendix"
        for block in section.blocks
        if hasattr(block, "columns")
    ]
    assert all("系统" not in table.columns for table in main_tables)
    assert all("归并置信度" not in table.columns for table in main_tables)
    assert all("归并依据" not in table.columns for table in main_tables)
    problem_section = next(section for section in report.sections if section.id == "problem_overview")
    assert any("高风险" in block.text for block in problem_section.blocks if hasattr(block, "text"))
    problem_tables = [block for block in problem_section.blocks if hasattr(block, "columns")]
    assert len(problem_tables) <= 1
    assert any(
        "cluster-a" in block.text and "Redis 日志显示 OOM 与复制异常" in block.text
        for block in problem_section.blocks
        if hasattr(block, "text")
    )
    architecture_section = next(section for section in report.sections if section.id == "architecture_overview")
    architecture_table = next(block for block in architecture_section.blocks if hasattr(block, "columns"))
    assert architecture_table.columns == ["集群", "类型", "节点数", "Master 数", "Replica 数", "主要结论", "风险等级"]
    assert architecture_table.rows[0][0] == "cluster-a"
    redis_cluster_section = next(section for section in report.sections if section.id == "redis_database__cluster-a")
    redis_table_titles = [block.title for block in redis_cluster_section.blocks if hasattr(block, "title")]
    assert redis_table_titles == [
        "架构与角色摘要",
        "版本与一致性检查",
        "内存与 maxmemory",
        "持久化状态",
        "复制状态",
        "Key 空间摘要",
        "Slowlog 摘要",
        "Redis 日志候选摘要",
    ]
    assert all(len(block.columns) <= 4 for block in redis_cluster_section.blocks if hasattr(block, "columns"))
    risk_cluster_section = next(section for section in report.sections if section.id == "risk_remediation__cluster-a")
    assert all(not hasattr(block, "columns") for block in risk_cluster_section.blocks)
    risk_text = "\n".join(
        block.text
        for section in report.sections
        if section.id.startswith("risk_remediation__cluster-a")
        for block in section.blocks
        if hasattr(block, "text")
    )
    assert "风险等级：high" in risk_text
    assert "Redis Cluster 状态异常" in risk_text
    assert "Redis 版本不一致" in risk_text
    assert "Redis 持久化最近一次保存失败" in risk_text
    assert "Redis 复制链路异常" in risk_text
    assert "主机 Swap 已使用" in risk_text
    assert risk_text.count("Redis 日志显示 OOM 与复制异常") == 1
    assert "Review：" in risk_text
    assert "Samples：" in risk_text
    assert "Confidence：high" in risk_text
    assert "review=" not in risk_text
    assert "samples=" not in risk_text


# ---------------------------------------------------------------------------
# Round 1.2 tests
# ---------------------------------------------------------------------------

def _make_simple_dataset(**overrides) -> InspectionDataset:
    """Minimal dataset helper for focused tests."""
    reviewed_log_issues = overrides.pop("reviewed_log_issues", ())
    node_facts = overrides.pop("redis_facts", {"redis_version": "7.0.15", "used_memory": "100", "maxmemory": "1000"})
    node_kwargs = {
        "node_id": "10.0.0.1:6379",
        "hostname": "redis-a",
        "ip": "10.0.0.1",
        "port": 6379,
        "role": "master",
        "version": "7.0.15",
        "source_path": "/evidence/redis-a",
        "redis_facts": node_facts,
    }
    node_kwargs.update({k: v for k, v in overrides.items() if k in InspectionNode.__dataclass_fields__})
    cluster_kwargs = {
        "cluster_id": "cluster-a",
        "name": "test-cluster",
        "cluster_type": overrides.get("cluster_type", "redis-cluster"),
        "nodes": (InspectionNode(**node_kwargs),),
    }
    return InspectionDataset(
        systems=(
            InspectionSystem(
                system_id="sys-1",
                name="Test System",
                clusters=(InspectionCluster(**cluster_kwargs),),
            ),
        ),
        source_mode="offline",
        input_sources=("/evidence",),
        reviewed_log_issues=reviewed_log_issues,
    )


def test_overview_table_does_not_contain_system_count() -> None:
    """#4: 巡检概览 should not include 系统数."""
    dataset = _make_simple_dataset()
    report = analyze_inspection_dataset(dataset)
    overview = next(s for s in report.sections if s.id == "inspection_overview")
    overview_table = next(b for b in overview.blocks if hasattr(b, "rows"))
    row_labels = [row[0] for row in overview_table.rows]
    assert "系统数" not in row_labels
    assert "输入模式" in row_labels
    assert "集群/子集群数" in row_labels
    assert "节点数" in row_labels


def test_keyspace_summary_rejects_dbus_and_systemd_content() -> None:
    """#2: keyspace extraction must only match db\\d+ with valid Redis keyspace values."""
    node = InspectionNode(
        node_id="10.0.0.1:6379", hostname="h", ip="10.0.0.1", port=6379,
        role="master", version="7.0", source_path="/e",
        redis_facts={
            "db0": "keys=11442500,expires=1857443,avg_ttl=450945900",
            "db1": "keys=5,expires=0,avg_ttl=0",
            "dbus": "10555",
            "dbus-daemon": "/usr/bin/dbus-daemon",
        },
    )
    result = _keyspace_summary(node)
    assert "db0=" in result
    assert "db1=" in result
    assert "dbus" not in result
    assert "systemd" not in result
    assert "/usr/bin" not in result


def test_keyspace_summary_rejects_malformed_values() -> None:
    """Keyspace entries without valid keys=...,expires=...,avg_ttl=... are dropped."""
    node = InspectionNode(
        node_id="10.0.0.1:6379", hostname="h", ip="10.0.0.1", port=6379,
        role="master", version="7.0", source_path="/e",
        redis_facts={
            "db0": "keys=100,expires=40,avg_ttl=1000",
            "db99": "random garbage text",
        },
    )
    result = _keyspace_summary(node)
    assert "db0=" in result
    assert "db99" not in result


def test_cluster_status_display_shows_normal_for_ok_state() -> None:
    """#3: redis-cluster with cluster_state=ok should show 正常."""
    cluster = InspectionCluster(
        cluster_id="c", name="c", cluster_type="redis-cluster",
        nodes=(
            InspectionNode(
                node_id="n", hostname="h", ip="1.1.1.1", port=6379,
                role="master", version="7.0", source_path="/e",
                redis_facts={"cluster_state": "ok", "cluster_enabled": "1"},
            ),
        ),
    )
    assert _cluster_status_display(cluster, cluster.nodes[0]) == "正常"


def test_cluster_status_display_shows_abnormal_for_non_ok_state() -> None:
    """#3: redis-cluster with cluster_state=fail should show 异常."""
    cluster = InspectionCluster(
        cluster_id="c", name="c", cluster_type="redis-cluster",
        nodes=(
            InspectionNode(
                node_id="n", hostname="h", ip="1.1.1.1", port=6379,
                role="master", version="7.0", source_path="/e",
                redis_facts={"cluster_state": "fail", "cluster_enabled": "1"},
            ),
        ),
    )
    result = _cluster_status_display(cluster, cluster.nodes[0])
    assert "异常" in result


def test_cluster_status_display_shows_insufficient_evidence_when_missing() -> None:
    """#3: redis-cluster without cluster_state should show 证据不足."""
    cluster = InspectionCluster(
        cluster_id="c", name="c", cluster_type="redis-cluster",
        nodes=(
            InspectionNode(
                node_id="n", hostname="h", ip="1.1.1.1", port=6379,
                role="master", version="7.0", source_path="/e",
                redis_facts={"cluster_enabled": "1"},
            ),
        ),
    )
    assert _cluster_status_display(cluster, cluster.nodes[0]) == "证据不足"


def test_cluster_status_display_dash_for_non_cluster() -> None:
    """#3: Non-cluster types should still show '-'."""
    cluster = InspectionCluster(
        cluster_id="c", name="c", cluster_type="standalone",
        nodes=(
            InspectionNode(
                node_id="n", hostname="h", ip="1.1.1.1", port=6379,
                role="master", version="7.0", source_path="/e",
                redis_facts={},
            ),
        ),
    )
    assert _cluster_status_display(cluster, cluster.nodes[0]) == "-"


def test_problem_overview_is_executive_summary_not_wide_table() -> None:
    """Chapter 3 should be executive summary text, with at most a small priority table."""
    dataset = _make_simple_dataset(
        redis_facts={
            "used_memory": "920",
            "maxmemory": "1000",
            "redis_version": "7.0.15",
            "cluster_enabled": "1",
        },
    )
    report = analyze_inspection_dataset(dataset)
    top_level_titles = [section.title for section in report.sections if section.level == 1]
    assert top_level_titles[2] == "问题概览与整改优先级"
    problem_section = next(s for s in report.sections if s.id == "problem_overview")
    text_blocks = [b.text for b in problem_section.blocks if hasattr(b, "text")]
    tables = [b for b in problem_section.blocks if hasattr(b, "columns")]
    assert any("test-cluster" in text and "Redis 内存水位过高" in text for text in text_blocks)
    assert all("..." not in text for text in text_blocks)
    assert len(tables) <= 1
    if tables:
        assert tables[0].columns == ["优先级", "集群", "风险等级", "关键问题", "优先动作"]


def test_redis_table_titles_have_no_hardcoded_number_prefix() -> None:
    """#1: Table titles in redis cluster sections should not have hardcoded 8.x prefixes."""
    dataset = _make_simple_dataset()
    report = analyze_inspection_dataset(dataset)
    redis_sections = [s for s in report.sections if s.id.startswith("redis_database__")]
    for section in redis_sections:
        for block in section.blocks:
            if hasattr(block, "title") and block.title:
                assert not block.title[0].isdigit(), f"Table title should not start with number: {block.title}"


def test_normal_log_candidates_do_not_create_findings_without_reviewed_anomaly() -> None:
    dataset = _make_simple_dataset(
        log_facts={
            "log_candidates": [
                {
                    "candidate_signal": "persistence_signal",
                    "raw_message": "Background append only file rewriting terminated with success",
                },
                {
                    "candidate_signal": "persistence_signal",
                    "raw_message": "RDB: 8 MB of memory used by copy-on-write",
                },
            ],
            "log_candidate_count": "2",
        },
        reviewed_log_issues=(
            ReviewedLogIssue(
                cluster_id="cluster-a",
                cluster_name="test-cluster",
                issue_name="正常持久化后台任务",
                is_anomalous=False,
                severity="info",
                why="AOF rewrite success and RDB copy-on-write metrics are normal persistence lifecycle events.",
                affected_nodes=("10.0.0.1:6379",),
                supporting_samples=(
                    "Background append only file rewriting terminated with success",
                    "RDB: 8 MB of memory used by copy-on-write",
                ),
                recommendation="无需整改，保留为背景证据。",
                merge_key="normal-persistence",
                category="log",
                confidence="high",
            ),
        ),
    )

    report = analyze_inspection_dataset(dataset)

    risk_text = _risk_text(report)
    assert "正常持久化后台任务" not in risk_text
    assert "Redis 错误日志存在异常事件" not in risk_text


def test_reviewed_log_issue_drives_findings() -> None:
    dataset = _make_simple_dataset(
        log_facts={
            "log_candidates": [
                {"candidate_signal": "oom_signal", "raw_message": "OOM command not allowed"},
                {"candidate_signal": "fork_signal", "raw_message": "Can't save in background: fork failed"},
            ],
            "log_candidate_count": "2",
        },
        reviewed_log_issues=(
            ReviewedLogIssue(
                cluster_id="cluster-a",
                cluster_name="test-cluster",
                issue_name="Redis 日志显示 OOM 与 fork 失败",
                is_anomalous=True,
                severity="high",
                why="LLM review linked OOM and fork failure to memory pressure.",
                affected_nodes=("10.0.0.1:6379",),
                supporting_samples=("OOM command not allowed", "Can't save in background: fork failed"),
                recommendation="优先检查内存水位、fork 内存和业务写入峰值。",
                merge_key="memory-pressure-log",
                category="log",
                confidence="high",
            ),
        ),
    )

    report = analyze_inspection_dataset(dataset)

    risk_text = _risk_text(report)
    assert "Redis 日志显示 OOM 与 fork 失败" in risk_text
    assert "风险等级：high" in risk_text
    assert "LLM review" in risk_text
    assert "OOM command not allowed" in risk_text


def test_problem_overview_merges_reviewed_log_issues_by_cluster_merge_key() -> None:
    dataset = _make_simple_dataset(
        reviewed_log_issues=(
            ReviewedLogIssue(
                cluster_id="cluster-a",
                cluster_name="test-cluster",
                issue_name="复制链路反复中断",
                is_anomalous=True,
                severity="high",
                why="replication break samples were reviewed as the same incident pattern.",
                affected_nodes=("10.0.0.1:6379",),
                supporting_samples=("MASTER <-> REPLICA sync failed",),
                recommendation="检查主从网络、认证和 backlog。",
                merge_key="replication-break",
                category="log",
                confidence="high",
            ),
            ReviewedLogIssue(
                cluster_id="cluster-a",
                cluster_name="test-cluster",
                issue_name="复制链路反复中断",
                is_anomalous=True,
                severity="high",
                why="same issue on another node.",
                affected_nodes=("10.0.0.2:6379",),
                supporting_samples=("MASTER timeout during replication",),
                recommendation="检查主从网络、认证和 backlog。",
                merge_key="replication-break",
                category="log",
                confidence="medium",
            ),
        ),
    )

    report = analyze_inspection_dataset(dataset)
    problem_section = next(s for s in report.sections if s.id == "problem_overview")
    problem_text = "\n".join(b.text for b in problem_section.blocks if hasattr(b, "text"))

    assert problem_text.count("复制链路反复中断") == 1
    assert "10.0.0.1:6379" in problem_text
    assert "10.0.0.2:6379" in problem_text


def test_reviewed_log_issue_cluster_scope_does_not_leak_foreign_nodes() -> None:
    cluster_a = InspectionCluster(
        cluster_id="cluster-a",
        name="glp-redis",
        cluster_type="redis-cluster",
        nodes=(
            InspectionNode(
                node_id="10.0.0.1:6379",
                hostname="a",
                ip="10.0.0.1",
                port=6379,
                role="master",
                version="7.0",
                source_path="/e/a",
                redis_facts={"used_memory": "100", "maxmemory": "1000"},
            ),
        ),
    )
    cluster_b = InspectionCluster(
        cluster_id="cluster-b",
        name="other-redis",
        cluster_type="redis-cluster",
        nodes=(
            InspectionNode(
                node_id="10.0.0.9:6379",
                hostname="b",
                ip="10.0.0.9",
                port=6379,
                role="master",
                version="7.0",
                source_path="/e/b",
                redis_facts={"used_memory": "100", "maxmemory": "1000"},
            ),
        ),
    )
    dataset = InspectionDataset(
        systems=(
            InspectionSystem(
                system_id="sys-1",
                name="System",
                clusters=(cluster_a, cluster_b),
            ),
        ),
        source_mode="offline",
        input_sources=("/evidence",),
        reviewed_log_issues=(
            ReviewedLogIssue(
                cluster_id="cluster-a",
                cluster_name="glp-redis",
                issue_name="日志显示复制链路异常",
                is_anomalous=True,
                severity="high",
                why="reviewed as a cluster-a replication issue.",
                affected_nodes=("10.0.0.1:6379", "10.0.0.9:6379"),
                supporting_samples=("MASTER timeout",),
                recommendation="检查 cluster-a 主从网络。",
                merge_key="replication-break",
                category="log",
                confidence="high",
            ),
        ),
    )

    report = analyze_inspection_dataset(dataset)

    glp_section = next(section for section in report.sections if section.id == "risk_remediation__glp-redis")
    other_section = next(section for section in report.sections if section.id == "risk_remediation__other-redis")
    assert all(not hasattr(block, "columns") for block in glp_section.blocks)
    assert all(not hasattr(block, "columns") for block in other_section.blocks)
    glp_text = "\n".join(
        block.text
        for section in report.sections
        if section.id.startswith("risk_remediation__glp-redis")
        for block in section.blocks
        if hasattr(block, "text")
    )
    other_text = "\n".join(
        block.text
        for section in report.sections
        if section.id.startswith("risk_remediation__other-redis")
        for block in section.blocks
        if hasattr(block, "text")
    )
    assert "日志显示复制链路异常" in glp_text
    assert "10.0.0.1:6379" in glp_text
    assert "10.0.0.9:6379" not in glp_text
    assert "日志显示复制链路异常" not in other_text


def _risk_text(report):
    risk_sections = [
        section
        for section in report.sections
        if section.id.startswith("risk_remediation__")
    ]
    return "\n".join(
        block.text
        for section in risk_sections
        for block in section.blocks
        if hasattr(block, "text")
    )
