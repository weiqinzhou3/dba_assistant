from dba_assistant.capabilities.redis_inspection_report.analyzer import analyze_inspection_dataset
from dba_assistant.capabilities.redis_inspection_report.types import (
    InspectionCluster,
    InspectionDataset,
    InspectionNode,
    InspectionSystem,
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
                                    "rdb_bgsave_in_progress": "0",
                                    "aof_enabled": "0",
                                    "cluster_enabled": "1",
                                    "cluster_state": "fail",
                                },
                                host_facts={"transparent_hugepage": "always [madvise] never"},
                                log_facts={"error_events": [{"level": "error", "message": "OOM command not allowed"}]},
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
    )

    report = analyze_inspection_dataset(dataset, language="zh-CN")

    assert report.title == "Redis 巡检报告"
    assert report.metadata["system_count"] == "1"
    assert report.metadata["cluster_count"] == "1"
    assert report.metadata["node_count"] == "2"
    assert report.metadata["finding_count"] == "5"
    section_titles = [section.title for section in report.sections]
    assert section_titles == [
        "巡检范围与输入说明",
        "集群识别与架构总览",
        "巡检结果总结",
        "巡检目标及方法",
        "系统配置检查",
        "操作系统检查",
        "Redis 数据库检查",
        "错误日志与异常事件分析",
        "风险与整改建议",
        "附录",
    ]
    summary_section = next(section for section in report.sections if section.id == "inspection_summary")
    assert any("高风险" in block.text for block in summary_section.blocks if hasattr(block, "text"))
    risk_section = next(section for section in report.sections if section.id == "risk_remediation")
    risk_table = risk_section.blocks[0]
    rows = risk_table.rows
    assert any(row[0] == "Redis Cluster 状态异常" and row[1] == "high" for row in rows)
    assert any(row[0] == "Redis 版本不一致" and row[1] == "medium" for row in rows)
    assert any("OOM" in row[4] for row in rows)
