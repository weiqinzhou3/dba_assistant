from __future__ import annotations

from collections import Counter
import re
from typing import Any

from dba_assistant.capabilities.redis_inspection_report.types import (
    InspectionCluster,
    InspectionDataset,
    InspectionFinding,
    InspectionNode,
    ReviewedLogIssue,
)
from dba_assistant.core.reporter.report_model import (
    AnalysisReport,
    ReportSectionModel,
    TableBlock,
    TextBlock,
)


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def analyze_inspection_dataset(dataset: InspectionDataset, *, language: str = "zh-CN") -> AnalysisReport:
    findings = _collect_findings(dataset)
    system_count, cluster_count, node_count = _count_scope(dataset)
    severity_counts = Counter(finding.severity for finding in findings)
    metadata = {
        "source_mode": dataset.source_mode,
        "system_count": str(system_count),
        "cluster_count": str(cluster_count),
        "node_count": str(node_count),
        "finding_count": str(len(findings)),
        "high_findings": str(severity_counts["critical"] + severity_counts["high"]),
        "medium_findings": str(severity_counts["medium"]),
        "unresolved_grouping_count": str(_unresolved_grouping_count(dataset)),
        **{key: str(value) for key, value in dataset.metadata.items()},
    }
    sections = _build_report_sections(
        dataset,
        findings=findings,
        system_count=system_count,
        cluster_count=cluster_count,
        node_count=node_count,
        severity_counts=severity_counts,
    )
    return AnalysisReport(
        title="Redis 巡检报告" if language != "en-US" else "Redis Inspection Report",
        summary=None,
        sections=sections,
        metadata=metadata,
        language=language,
    )


def _build_report_sections(
    dataset: InspectionDataset,
    *,
    findings: list[InspectionFinding],
    system_count: int,
    cluster_count: int,
    node_count: int,
    severity_counts: Counter,
) -> list[ReportSectionModel]:
    sections: list[ReportSectionModel] = [
        _overview_section(dataset, system_count, cluster_count, node_count, findings, severity_counts),
        _scope_section(dataset, system_count, cluster_count, node_count),
        _problem_overview_section(dataset, findings, severity_counts),
        _architecture_section(dataset, findings),
        _method_section(dataset),
        _system_config_overview_section(findings),
    ]
    sections.extend(_system_config_cluster_sections(dataset))
    sections.append(_os_overview_section(findings))
    sections.extend(_os_cluster_sections(dataset))
    sections.append(_redis_overview_section(findings))
    sections.extend(_redis_cluster_sections(dataset))
    sections.append(_risk_overview_section(findings))
    sections.extend(_risk_cluster_sections(dataset, findings))
    sections.append(_appendix_section(dataset))
    return sections


def _collect_findings(dataset: InspectionDataset) -> list[InspectionFinding]:
    findings: list[InspectionFinding] = []
    findings.extend(_reviewed_log_issue_findings(dataset))
    for cluster in _iter_clusters(dataset):
        if cluster.metadata.get("unresolved_grouping") == "true":
            findings.append(
                InspectionFinding(
                    risk_name="集群归并证据不足",
                    severity="low",
                    target=cluster.name,
                    evidence="; ".join(str(item) for item in cluster.metadata.get("grouping_evidence", [])),
                    impact="证据不足时系统不会静默合并节点，报告中的集群边界需要人工复核。",
                    recommendation="补充 Redis INFO、CLUSTER NODES、节点命名或复制关系证据后重新归并。",
                    category="architecture",
                )
            )
        versions = sorted({node.version for node in cluster.nodes if node.version})
        if len(versions) > 1:
            findings.append(
                InspectionFinding(
                    risk_name="Redis 版本不一致",
                    severity="medium",
                    target=cluster.name,
                    evidence=f"发现版本: {', '.join(versions)}",
                    impact="同一集群内版本不一致会增加故障定位、兼容性与变更风险。",
                    recommendation="规划版本统一窗口，先在从节点验证后按集群维护流程滚动升级。",
                    category="redis",
                )
            )
        for node in cluster.nodes:
            findings.extend(_node_findings(cluster, node))
    return sorted(
        findings,
        key=lambda item: (
            SEVERITY_ORDER.get(item.severity, 99),
            item.category,
            item.risk_name,
            item.target,
        ),
    )


def _node_findings(cluster: InspectionCluster, node: InspectionNode) -> list[InspectionFinding]:
    findings: list[InspectionFinding] = []
    target = node.node_id
    facts = node.redis_facts

    used_memory = _to_float(facts.get("used_memory"))
    maxmemory = _to_float(facts.get("maxmemory"))
    if used_memory is not None and maxmemory and maxmemory > 0:
        ratio = used_memory / maxmemory
        if ratio >= 0.85:
            findings.append(
                InspectionFinding(
                    risk_name="Redis 内存水位过高",
                    severity="high",
                    target=target,
                    evidence=f"used_memory={_fmt_number(used_memory)}, maxmemory={_fmt_number(maxmemory)}, ratio={ratio:.2%}",
                    impact="内存水位过高时容易触发淘汰、写入失败或进程 OOM。",
                    recommendation="结合业务容量增长评估扩容、拆分热点 key 或调整 maxmemory 策略。",
                    category="redis",
                )
            )
    elif maxmemory == 0:
        findings.append(
            InspectionFinding(
                risk_name="Redis 未配置 maxmemory",
                severity="medium",
                target=target,
                evidence="maxmemory=0",
                impact="未设置内存上限时 Redis 可能持续占用主机内存并影响系统稳定性。",
                recommendation="根据实例容量规划配置 maxmemory，并明确淘汰策略。",
                category="redis",
            )
        )

    fragmentation = _to_float(facts.get("mem_fragmentation_ratio"))
    if fragmentation is not None and fragmentation >= 1.5:
        findings.append(
            InspectionFinding(
                risk_name="Redis 内存碎片率偏高",
                severity="medium",
                target=target,
                evidence=f"mem_fragmentation_ratio={fragmentation:.2f}",
                impact="碎片率偏高会放大实际内存占用，并可能造成容量误判。",
                recommendation="结合 active defrag、业务写入模式和实例重启窗口评估治理方案。",
                category="redis",
            )
        )

    cluster_state = _string_value(facts.get("cluster_state"))
    if cluster.cluster_type == "redis-cluster" and cluster_state and cluster_state.lower() != "ok":
        findings.append(
            InspectionFinding(
                risk_name="Redis Cluster 状态异常",
                severity="high",
                target=target,
                evidence=f"cluster_state={cluster_state}",
                impact="Cluster 非 ok 状态可能导致槽位不可用、请求失败或故障转移异常。",
                recommendation="检查 CLUSTER INFO/NODES、槽位覆盖、节点连通性和故障转移状态。",
                category="redis",
            )
        )

    slowlog_count = _slowlog_count(node)
    if slowlog_count > 0:
        findings.append(
            InspectionFinding(
                risk_name="Redis 慢日志存在记录",
                severity="medium",
                target=target,
                evidence=f"slowlog_count={slowlog_count}",
                impact="慢命令会增加 Redis 单线程阻塞风险并拉高业务延迟。",
                recommendation="定位慢命令来源，优化命令复杂度、数据结构和访问模式。",
                category="redis",
            )
        )

    if _string_value(facts.get("rdb_last_bgsave_status")).lower() in {"err", "error", "fail", "failed"}:
        findings.append(
            InspectionFinding(
                risk_name="Redis 持久化最近一次保存失败",
                severity="high",
                target=target,
                evidence=f"rdb_last_bgsave_status={facts.get('rdb_last_bgsave_status')}",
                impact="RDB 最近一次保存失败会降低实例异常退出后的数据恢复能力。",
                recommendation="检查磁盘空间、权限、fork 内存和 Redis 日志，确认下一次 BGSAVE 是否恢复正常。",
                category="redis",
            )
        )

    if _string_value(facts.get("aof_last_write_status")).lower() in {"err", "error", "fail", "failed"}:
        findings.append(
            InspectionFinding(
                risk_name="Redis AOF 最近一次写入失败",
                severity="high",
                target=target,
                evidence=f"aof_last_write_status={facts.get('aof_last_write_status')}",
                impact="AOF 写入失败会影响持久化完整性，并可能导致故障恢复点落后。",
                recommendation="检查 AOF 目录、磁盘空间、fsync 延迟和 Redis 错误日志。",
                category="redis",
            )
        )

    master_link_status = _string_value(facts.get("master_link_status")).lower()
    if master_link_status not in {"", "up"}:
        findings.append(
            InspectionFinding(
                risk_name="Redis 复制链路异常",
                severity="high",
                target=target,
                evidence=f"master_link_status={facts.get('master_link_status')}",
                impact="复制链路异常会造成主从数据延迟或读写切换风险。",
                recommendation="检查主从网络连通性、复制 backlog、认证配置和主节点负载。",
                category="redis",
            )
        )

    thp = _string_value(node.host_facts.get("transparent_hugepage"))
    if thp and thp.strip().startswith("[always]"):
        findings.append(
            InspectionFinding(
                risk_name="主机透明大页处于 always",
                severity="medium",
                target=target,
                evidence=f"transparent_hugepage={thp}",
                impact="透明大页可能导致 Redis 延迟抖动。",
                recommendation="按 Redis 官方建议关闭 THP，并在系统启动配置中持久化。",
                category="os",
            )
        )

    swap = _string_value(node.host_facts.get("swap"))
    if _swap_used(swap):
        findings.append(
            InspectionFinding(
                risk_name="主机 Swap 已使用",
                severity="medium",
                target=target,
                evidence=swap,
                impact="Redis 对延迟敏感，Swap 使用可能导致请求抖动或超时。",
                recommendation="确认内存余量和 vm.swappiness 设置，必要时扩容或调整实例内存上限。",
                category="os",
            )
        )

    return findings


def _reviewed_log_issue_findings(dataset: InspectionDataset) -> list[InspectionFinding]:
    grouped: dict[tuple[str, str], list[ReviewedLogIssue]] = {}
    for issue in dataset.reviewed_log_issues:
        if not issue.is_anomalous:
            continue
        cluster_key = issue.cluster_id or issue.cluster_name or "unknown-cluster"
        merge_key = issue.merge_key or "|".join(
            [
                issue.cluster_name,
                issue.issue_name,
                issue.severity,
                issue.why,
                issue.recommendation,
            ]
        )
        grouped.setdefault((cluster_key, merge_key), []).append(issue)

    findings: list[InspectionFinding] = []
    for (_cluster_key, merge_key), issues in grouped.items():
        primary = min(issues, key=lambda item: SEVERITY_ORDER.get(item.severity, 99))
        affected_nodes = tuple(
            sorted(
                {
                    node
                    for issue in issues
                    for node in issue.affected_nodes
                    if str(node).strip()
                }
            )
        )
        samples = _unique_strings(
            sample
            for issue in issues
            for sample in issue.supporting_samples
        )
        reasons = _unique_strings(issue.why for issue in issues if issue.why)
        recommendations = _unique_strings(issue.recommendation for issue in issues if issue.recommendation)
        confidences = _unique_strings(issue.confidence for issue in issues if issue.confidence)
        evidence_parts = []
        if reasons:
            evidence_parts.append("review=" + " / ".join(reasons))
        if samples:
            evidence_parts.append("samples=" + " | ".join(samples[:5]))
        if confidences:
            evidence_parts.append("confidence=" + ", ".join(confidences))
        findings.append(
            InspectionFinding(
                risk_name=primary.issue_name,
                severity=primary.severity,
                target=", ".join(affected_nodes) or primary.cluster_name or primary.cluster_id,
                evidence="; ".join(evidence_parts) or "-",
                impact=primary.why or "日志候选经 LLM semantic review 判定为需要关注的异常。",
                recommendation=" / ".join(recommendations) or primary.recommendation or "结合原始日志时间线和运行状态复核。",
                category=primary.category or "log",
                merge_key=merge_key,
                affected_nodes=affected_nodes,
                source="llm_log_review",
            )
        )
    return findings


def _overview_section(
    dataset: InspectionDataset,
    system_count: int,
    cluster_count: int,
    node_count: int,
    findings: list[InspectionFinding],
    severity_counts: Counter,
) -> ReportSectionModel:
    return ReportSectionModel(
        id="inspection_overview",
        title="巡检概述",
        blocks=[
            TextBlock(
                text=(
                    f"本次 Redis 离线巡检覆盖 {system_count} 个系统、{cluster_count} 个集群/子集群、"
                    f"{node_count} 个节点。报告先给出巡检结论，再按系统、集群和节点展开配置、"
                    "操作系统、Redis 数据库与风险整改证据。"
                )
            ),
            TableBlock(
                title="巡检概览",
                columns=["项目", "结果"],
                rows=[
                    ["输入模式", dataset.source_mode],
                    ["集群/子集群数", str(cluster_count)],
                    ["节点数", str(node_count)],
                    ["风险项总数", str(len(findings))],
                    ["高风险项", str(severity_counts["critical"] + severity_counts["high"])],
                    ["中风险项", str(severity_counts["medium"])],
                ],
            ),
        ],
    )


def _scope_section(
    dataset: InspectionDataset,
    system_count: int,
    cluster_count: int,
    node_count: int,
) -> ReportSectionModel:
    rows = [[str(index), source] for index, source in enumerate(dataset.input_sources, start=1)]
    if not rows:
        rows = [["1", dataset.source_mode]]
    return ReportSectionModel(
        id="scope_input",
        title="巡检范围与输入说明",
        blocks=[
            TextBlock(text=f"本次巡检输入模式为 {dataset.source_mode}，识别到 {system_count} 个系统、{cluster_count} 个集群、{node_count} 个节点。"),
            TableBlock(title="输入来源", columns=["序号", "来源"], rows=rows),
        ],
    )


def _architecture_section(dataset: InspectionDataset, findings: list[InspectionFinding]) -> ReportSectionModel:
    rows: list[list[str]] = []
    for system in dataset.systems:
        for cluster in system.clusters:
            masters = sum(1 for node in cluster.nodes if (node.role or "").lower() == "master")
            replicas = sum(1 for node in cluster.nodes if (node.role or "").lower() in {"slave", "replica"})
            cluster_findings = _findings_for_cluster(cluster, findings)
            rows.append(
                [
                    cluster.name,
                    cluster.cluster_type,
                    str(len(cluster.nodes)),
                    str(masters),
                    str(replicas),
                    _cluster_main_conclusion(cluster_findings),
                    _highest_severity(cluster_findings),
                ]
            )
    unresolved_count = _unresolved_grouping_count(dataset)
    blocks: list[TextBlock | TableBlock] = [
        TextBlock(text="本章按集群维度汇总架构类型、节点规模、角色分布和主要巡检结论，详细节点证据在后续章节展开。")
    ]
    if unresolved_count:
        blocks.append(TextBlock(text=f"存在 {unresolved_count} 个集群归并证据不足，正文仅保留提示，详细依据见附录和审计元数据。"))
    blocks.append(
        TableBlock(
            title="集群架构与风险概览",
            columns=["集群", "类型", "节点数", "Master 数", "Replica 数", "主要结论", "风险等级"],
            rows=rows or [["-", "-", "0", "0", "0", "未识别到 Redis 集群证据", "info"]],
        )
    )
    return ReportSectionModel(
        id="architecture_overview",
        title="集群识别与架构总览",
        blocks=blocks,
    )


def _problem_overview_section(
    dataset: InspectionDataset,
    findings: list[InspectionFinding],
    severity_counts: Counter,
) -> ReportSectionModel:
    rows = _problem_overview_rows(dataset, findings)
    high_total = severity_counts["critical"] + severity_counts["high"]
    if not rows:
        rows = [["-", "未发现需要优先整改的明确问题", "-", "info", "当前证据未显示高/中风险", "保持例行巡检和容量监控。"]]
    return ReportSectionModel(
        id="problem_overview",
        title="问题概览与整改优先级",
        blocks=[
            TextBlock(
                text=(
                    f"本章按集群维度归并问题。本次巡检共发现 {len(findings)} 个风险项，"
                    f"其中高风险 {high_total} 项，中风险 {severity_counts['medium']} 项。"
                )
            ),
            TableBlock(
                title="集群级问题概览与整改优先级",
                columns=["集群", "关键问题", "涉及节点", "风险等级", "影响", "优先整改建议"],
                rows=rows,
            ),
        ],
    )


def _problem_overview_rows(
    dataset: InspectionDataset,
    findings: list[InspectionFinding],
) -> list[list[str]]:
    rows: list[list[str]] = []
    for cluster in _iter_clusters(dataset):
        cluster_findings = _findings_for_cluster(cluster, findings)
        significant = [f for f in cluster_findings if f.severity in {"critical", "high", "medium"}]
        if not significant:
            continue
        for finding in _merge_cluster_findings(significant):
            rows.append([
                cluster.name,
                finding.risk_name,
                ", ".join(finding.affected_nodes) if finding.affected_nodes else finding.target,
                finding.severity,
                _shorten(finding.impact, limit=60),
                _shorten(finding.recommendation, limit=60),
            ])
    return rows


def _merge_cluster_findings(findings: list[InspectionFinding]) -> list[InspectionFinding]:
    grouped: dict[str, list[InspectionFinding]] = {}
    for finding in findings:
        key = finding.merge_key or "|".join(
            [
                finding.risk_name,
                finding.severity,
                finding.impact,
                finding.recommendation,
            ]
        )
        grouped.setdefault(key, []).append(finding)

    merged: list[InspectionFinding] = []
    for _key, items in grouped.items():
        primary = min(items, key=lambda item: SEVERITY_ORDER.get(item.severity, 99))
        affected_nodes = tuple(
            sorted(
                {
                    node
                    for item in items
                    for node in (item.affected_nodes or (item.target,))
                    if str(node).strip()
                }
            )
        )
        merged.append(
            InspectionFinding(
                risk_name=primary.risk_name,
                severity=primary.severity,
                target=", ".join(affected_nodes) or primary.target,
                evidence=primary.evidence,
                impact=primary.impact,
                recommendation=primary.recommendation,
                category=primary.category,
                merge_key=primary.merge_key,
                affected_nodes=affected_nodes,
                source=primary.source,
            )
        )
    return sorted(
        merged,
        key=lambda item: (
            SEVERITY_ORDER.get(item.severity, 99),
            item.risk_name,
            item.target,
        ),
    )


def _method_section(dataset: InspectionDataset) -> ReportSectionModel:
    method = "离线证据包解析、节点归并、确定性证据归约、LLM 日志语义审阅、共享报告渲染" if dataset.source_mode == "offline" else "在线只读 Redis 探测、统一数据建模、确定性规则分析、共享报告渲染"
    return ReportSectionModel(
        id="inspection_method",
        title="巡检目标及方法",
        blocks=[
            TextBlock(text="巡检目标是识别 Redis 架构、配置、运行状态、主机环境和日志异常风险，并形成可审计的整改建议。"),
            TextBlock(text=f"本次采用方法：{method}。在线路径仅使用只读命令，不执行写入或自动修复。"),
        ],
    )


def _system_config_overview_section(findings: list[InspectionFinding]) -> ReportSectionModel:
    return ReportSectionModel(
        id="system_config",
        title="系统配置检查",
        blocks=[
            TextBlock(text=f"配置检查重点覆盖 maxmemory、淘汰策略、持久化配置等项目；相关风险项 {sum(1 for item in findings if item.category == 'redis')} 个。"),
        ],
    )


def _system_config_cluster_sections(dataset: InspectionDataset) -> list[ReportSectionModel]:
    sections: list[ReportSectionModel] = []
    for cluster in _iter_clusters(dataset):
        memory_rows = [
            [
                node.node_id,
                _string_value(node.redis_facts.get("maxmemory")) or "-",
                _string_value(node.redis_facts.get("maxmemory_policy") or node.redis_facts.get("maxmemory-policy")) or "-",
            ]
            for node in cluster.nodes
        ]
        persistence_rows = [
            [
                node.node_id,
                _string_value(node.redis_facts.get("appendonly") or node.redis_facts.get("aof_enabled")) or "-",
                _persistence_status(node),
            ]
            for node in cluster.nodes
        ]
        sections.append(
            ReportSectionModel(
                id=_cluster_section_id("system_config", cluster),
                title=cluster.name,
                level=2,
                blocks=[
                    TextBlock(text=f"{cluster.name} 的配置明细按节点列示，重点关注容量上限、淘汰策略和持久化开关。"),
                    TableBlock(
                        title="容量与淘汰策略",
                        columns=["节点", "maxmemory", "淘汰策略"],
                        rows=memory_rows or [["-", "-", "-"]],
                    ),
                    TableBlock(
                        title="持久化配置",
                        columns=["节点", "AOF/appendonly", "持久化状态"],
                        rows=persistence_rows or [["-", "-", "-"]],
                    ),
                ],
            )
        )
    return sections


def _os_overview_section(findings: list[InspectionFinding]) -> ReportSectionModel:
    return ReportSectionModel(
        id="os_inspection",
        title="操作系统检查",
        blocks=[
            TextBlock(text=f"操作系统检查覆盖平台、内核、透明大页、swap 等主机侧证据；相关风险项 {sum(1 for item in findings if item.category == 'os')} 个。"),
        ],
    )


def _os_cluster_sections(dataset: InspectionDataset) -> list[ReportSectionModel]:
    sections: list[ReportSectionModel] = []
    for cluster in _iter_clusters(dataset):
        platform_rows = [
            [
                node.node_id,
                _string_value(node.host_facts.get("os")) or "-",
                _shorten(_string_value(node.host_facts.get("kernel")) or "-", limit=90),
            ]
            for node in cluster.nodes
        ]
        host_param_rows = [
            [
                node.node_id,
                _string_value(node.host_facts.get("transparent_hugepage")) or "-",
                _string_value(node.host_facts.get("swap")) or "-",
            ]
            for node in cluster.nodes
        ]
        sections.append(
            ReportSectionModel(
                id=_cluster_section_id("os_inspection", cluster),
                title=cluster.name,
                level=2,
                blocks=[
                    TextBlock(text=f"{cluster.name} 的主机侧检查以节点为单位列示，长文本内核信息在表内做摘要展示。"),
                    TableBlock(
                        title="平台与内核",
                        columns=["节点", "OS", "内核摘要"],
                        rows=platform_rows or [["-", "-", "-"]],
                    ),
                    TableBlock(
                        title="主机参数",
                        columns=["节点", "THP", "Swap"],
                        rows=host_param_rows or [["-", "-", "-"]],
                    ),
                ],
            )
        )
    return sections


def _redis_overview_section(findings: list[InspectionFinding]) -> ReportSectionModel:
    return ReportSectionModel(
        id="redis_database",
        title="Redis 数据库检查",
        blocks=[
            TextBlock(text=f"Redis 数据库检查覆盖架构、角色、版本、内存、持久化、key 空间、复制、Cluster 状态、慢日志和经审阅的日志问题；相关风险项 {sum(1 for item in findings if item.category in {'redis', 'log'})} 个。"),
        ],
    )


def _redis_cluster_sections(dataset: InspectionDataset) -> list[ReportSectionModel]:
    sections: list[ReportSectionModel] = []
    for cluster in _iter_clusters(dataset):
        sections.append(
            ReportSectionModel(
                id=_cluster_section_id("redis_database", cluster),
                title=cluster.name,
                level=2,
                blocks=[
                    TextBlock(text=f"{cluster.name} 的 Redis 检查拆分为 8 个小节，避免使用一张不可阅读的宽表。"),
                    TableBlock(
                        title="架构与角色摘要",
                        columns=["节点", "角色", "端口", "Cluster 状态"],
                        rows=_architecture_role_rows(cluster),
                    ),
                    TableBlock(
                        title="版本与一致性检查",
                        columns=["版本", "节点数"],
                        rows=_version_rows(cluster),
                    ),
                    TableBlock(
                        title="内存与 maxmemory",
                        columns=["节点", "used_memory", "maxmemory", "水位"],
                        rows=_memory_rows(cluster),
                    ),
                    TableBlock(
                        title="持久化状态",
                        columns=["节点", "RDB", "AOF"],
                        rows=_persistence_rows(cluster),
                    ),
                    TableBlock(
                        title="复制状态",
                        columns=["节点", "角色", "复制状态"],
                        rows=_replication_rows(cluster),
                    ),
                    TableBlock(
                        title="Key 空间摘要",
                        columns=["节点", "Key 空间"],
                        rows=_keyspace_rows(cluster),
                    ),
                    TableBlock(
                        title="Slowlog 摘要",
                        columns=["节点", "慢日志数"],
                        rows=_slowlog_rows(cluster),
                    ),
                    TableBlock(
                        title="Redis 日志候选摘要",
                        columns=["节点", "候选数", "样本"],
                        rows=_log_rows(cluster),
                    ),
                ],
            )
        )
    return sections


def _risk_overview_section(findings: list[InspectionFinding]) -> ReportSectionModel:
    severity_counts = Counter(finding.severity for finding in findings)
    return ReportSectionModel(
        id="risk_remediation",
        title="风险与整改建议",
        blocks=[
            TableBlock(
                title="风险等级汇总",
                columns=["风险等级", "数量"],
                rows=[
                    ["critical", str(severity_counts["critical"])],
                    ["high", str(severity_counts["high"])],
                    ["medium", str(severity_counts["medium"])],
                    ["low", str(severity_counts["low"])],
                    ["info", str(severity_counts["info"])],
                ],
            )
        ],
    )


def _risk_cluster_sections(dataset: InspectionDataset, findings: list[InspectionFinding]) -> list[ReportSectionModel]:
    sections: list[ReportSectionModel] = []
    for cluster in _iter_clusters(dataset):
        cluster_findings = _findings_for_cluster(cluster, findings)
        rows = [
            [
                finding.risk_name,
                finding.severity,
                finding.target,
                finding.impact,
                finding.evidence,
                finding.recommendation,
            ]
            for finding in cluster_findings
        ]
        sections.append(
            ReportSectionModel(
                id=_cluster_section_id("risk_remediation", cluster),
                title=cluster.name,
                level=2,
                blocks=[
                    TextBlock(text=f"{cluster.name} 风险项按等级排序，整改建议需要结合原始证据复核后执行。"),
                    TableBlock(
                        title="风险与整改建议清单",
                        columns=["风险名称", "风险等级", "发现对象", "影响说明", "证据", "建议整改措施"],
                        rows=rows or [["未发现明确风险", "info", "-", "-", "-", "保持例行巡检和容量监控。"]],
                    ),
                ],
            )
        )
    return sections


def _appendix_section(dataset: InspectionDataset) -> ReportSectionModel:
    rows = [
        [
            cluster.name,
            node.node_id,
            node.hostname,
            node.ip or "-",
            "" if node.port is None else str(node.port),
            node.source_path or "-",
        ]
        for _, cluster, node in _iter_scoped_nodes(dataset)
    ]
    grouping_rows = [
        [
            cluster.name,
            str(cluster.metadata.get("grouping_confidence") or "-"),
            "; ".join(str(item) for item in cluster.metadata.get("grouping_evidence", [])) or "-",
        ]
        for cluster in _iter_clusters(dataset)
    ]
    return ReportSectionModel(
        id="appendix",
        title="附录",
        blocks=[
            TextBlock(text="附录保留节点来源与关键标识，便于后续回溯证据。"),
            TableBlock(title="节点清单", columns=["集群", "节点", "主机名", "IP", "端口", "来源"], rows=rows or [["-", "-", "-", "-", "-", "-"]]),
            TableBlock(title="归并依据附录", columns=["集群", "归并状态", "归并依据"], rows=grouping_rows or [["-", "-", "-"]]),
        ],
    )


def _architecture_role_rows(cluster: InspectionCluster) -> list[list[str]]:
    return [
        [
            node.node_id,
            node.role or "-",
            "" if node.port is None else str(node.port),
            _cluster_status_display(cluster, node),
        ]
        for node in cluster.nodes
    ] or [["-", "-", "-", "-"]]


def _cluster_status_display(cluster: InspectionCluster, node: InspectionNode) -> str:
    if cluster.cluster_type != "redis-cluster":
        return "-"
    raw = _string_value(node.redis_facts.get("cluster_state")).strip().lower()
    if raw == "ok":
        return "正常"
    if raw and raw != "":
        return f"异常 ({raw})"
    return "证据不足"


def _version_rows(cluster: InspectionCluster) -> list[list[str]]:
    counts = Counter(node.version or "未知" for node in cluster.nodes)
    return [[version, str(count)] for version, count in sorted(counts.items())] or [["未知", "0"]]


def _memory_rows(cluster: InspectionCluster) -> list[list[str]]:
    rows = []
    for node in cluster.nodes:
        used_memory = _to_float(node.redis_facts.get("used_memory"))
        maxmemory = _to_float(node.redis_facts.get("maxmemory"))
        if used_memory is not None and maxmemory and maxmemory > 0:
            waterline = f"{used_memory / maxmemory:.2%}"
        elif maxmemory == 0:
            waterline = "未设置上限"
        else:
            waterline = "-"
        rows.append(
            [
                node.node_id,
                _string_value(node.redis_facts.get("used_memory")) or "-",
                _string_value(node.redis_facts.get("maxmemory")) or "-",
                waterline,
            ]
        )
    return rows or [["-", "-", "-", "-"]]


def _persistence_rows(cluster: InspectionCluster) -> list[list[str]]:
    return [
        [
            node.node_id,
            _string_value(node.redis_facts.get("rdb_last_bgsave_status") or node.redis_facts.get("rdb_bgsave_in_progress") or "-"),
            _string_value(node.redis_facts.get("aof_last_write_status") or node.redis_facts.get("aof_enabled") or "-"),
        ]
        for node in cluster.nodes
    ] or [["-", "-", "-"]]


def _replication_rows(cluster: InspectionCluster) -> list[list[str]]:
    return [
        [node.node_id, node.role or "-", _replication_status(node)]
        for node in cluster.nodes
    ] or [["-", "-", "-"]]


def _keyspace_rows(cluster: InspectionCluster) -> list[list[str]]:
    return [
        [node.node_id, _keyspace_summary(node)]
        for node in cluster.nodes
    ] or [["-", "-"]]


def _slowlog_rows(cluster: InspectionCluster) -> list[list[str]]:
    return [
        [node.node_id, str(_slowlog_count(node))]
        for node in cluster.nodes
    ] or [["-", "0"]]


def _log_rows(cluster: InspectionCluster) -> list[list[str]]:
    rows = []
    for node in cluster.nodes:
        candidates = _log_candidates(node)
        if not candidates and not _log_candidate_count(node):
            continue
        sample = " | ".join(
            _shorten(_string_value(candidate.get("raw_message")), limit=80)
            for candidate in candidates[:2]
            if _string_value(candidate.get("raw_message"))
        ) or "-"
        overflow_count = _log_candidate_overflow_count(node)
        if overflow_count:
            sample = f"{sample}；另有 {overflow_count} 条未展开"
        rows.append([node.node_id, str(_log_candidate_count(node)), sample])
    return rows or [["-", "0", "未提取到日志候选"]]


def _findings_for_cluster(
    cluster: InspectionCluster,
    findings: list[InspectionFinding],
) -> list[InspectionFinding]:
    targets = {cluster.name, *(node.node_id for node in cluster.nodes)}
    return [
        finding
        for finding in findings
        if finding.target in targets
        or any(node in targets for node in finding.affected_nodes)
    ]


def _highest_severity(findings: list[InspectionFinding]) -> str:
    if not findings:
        return "info"
    return min(findings, key=lambda item: SEVERITY_ORDER.get(item.severity, 99)).severity


def _cluster_main_conclusion(findings: list[InspectionFinding]) -> str:
    if not findings:
        return "未发现明确风险"
    high_count = sum(1 for finding in findings if finding.severity in {"critical", "high"})
    medium_count = sum(1 for finding in findings if finding.severity == "medium")
    if high_count:
        return f"存在 {high_count} 项高风险，需优先处理"
    if medium_count:
        return f"存在 {medium_count} 项中风险，建议纳入整改计划"
    return f"存在 {len(findings)} 项低风险/提示项，建议复核"


def _cluster_section_id(prefix: str, cluster: InspectionCluster) -> str:
    return f"{prefix}__{_slug(cluster.name)}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return slug or "cluster"


def _shorten(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _count_scope(dataset: InspectionDataset) -> tuple[int, int, int]:
    system_count = len(dataset.systems)
    clusters = list(_iter_clusters(dataset))
    nodes = list(_iter_nodes(dataset))
    return system_count, len(clusters), len(nodes)


def _iter_clusters(dataset: InspectionDataset):
    for system in dataset.systems:
        yield from system.clusters


def _iter_nodes(dataset: InspectionDataset):
    for cluster in _iter_clusters(dataset):
        yield from cluster.nodes


def _iter_scoped_nodes(dataset: InspectionDataset):
    for system in dataset.systems:
        for cluster in system.clusters:
            for node in cluster.nodes:
                yield system, cluster, node


def _unresolved_grouping_count(dataset: InspectionDataset) -> int:
    return sum(
        1
        for cluster in _iter_clusters(dataset)
        if cluster.metadata.get("unresolved_grouping") == "true"
    )


def _slowlog_count(node: InspectionNode) -> int:
    slowlog = node.redis_facts.get("slowlog")
    if isinstance(slowlog, dict):
        value = slowlog.get("count")
        if isinstance(value, int):
            return value
    value = node.redis_facts.get("slowlog_count")
    parsed = _to_float(value)
    return int(parsed or 0)


def _log_candidates(node: InspectionNode) -> list[dict[str, Any]]:
    candidates = node.log_facts.get("log_candidates")
    if isinstance(candidates, list):
        return [candidate for candidate in candidates if isinstance(candidate, dict)]
    return []


def _log_candidate_count(node: InspectionNode) -> int:
    parsed = _to_float(node.log_facts.get("log_candidate_count"))
    return int(parsed) if parsed is not None else len(_log_candidates(node))


def _log_candidate_overflow_count(node: InspectionNode) -> int:
    parsed = _to_float(node.log_facts.get("log_candidate_overflow_count"))
    return int(parsed) if parsed is not None else 0


def _unique_strings(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _string_value(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _persistence_status(node: InspectionNode) -> str:
    facts = node.redis_facts
    rdb_status = _string_value(facts.get("rdb_last_bgsave_status") or facts.get("rdb_bgsave_in_progress") or "-")
    aof_status = _string_value(facts.get("aof_last_write_status") or facts.get("aof_enabled") or "-")
    return f"RDB={rdb_status}; AOF={aof_status}"


def _replication_status(node: InspectionNode) -> str:
    facts = node.redis_facts
    if node.role in {"replica", "slave"}:
        return f"master={facts.get('master_host', '-')}; link={facts.get('master_link_status', '-')}"
    return f"connected_slaves={facts.get('connected_slaves', '-')}"


_KEYSPACE_DB_PATTERN = re.compile(r"^db\d+$")
_KEYSPACE_VALUE_PATTERN = re.compile(
    r"keys=\d+,expires=\d+,avg_ttl=\d+"
)


def _keyspace_summary(node: InspectionNode) -> str:
    parts = []
    for key, value in sorted(node.redis_facts.items()):
        if not _KEYSPACE_DB_PATTERN.match(str(key)):
            continue
        val_str = str(value)
        if _KEYSPACE_VALUE_PATTERN.search(val_str):
            parts.append(f"{key}={val_str}")
    return "; ".join(parts) or "-"


def _swap_used(summary: str) -> bool:
    total = _extract_kb(summary, "SwapTotal")
    free = _extract_kb(summary, "SwapFree")
    if total is None or free is None:
        return False
    return total > 0 and free < total


def _extract_kb(summary: str, key: str) -> int | None:
    import re

    match = re.search(rf"{key}:\s*([0-9]+)", summary)
    return int(match.group(1)) if match else None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _fmt_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.2f}"


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


__all__ = ["analyze_inspection_dataset"]
