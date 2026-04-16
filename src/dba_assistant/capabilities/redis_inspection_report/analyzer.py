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
from dba_assistant.skills_runtime.assets import (
    load_numbered_outline_titles,
    load_skill_yaml_asset,
)
from dba_assistant.core.reporter.report_model import (
    AnalysisReport,
    InfoTableBlock,
    InfoTableRow,
    ReportSectionModel,
    TableBlock,
    TextBlock,
)


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_SKILL_NAME = "redis-inspection-report"


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
    ]
    sections.extend(_problem_overview_sections(dataset, findings, severity_counts))
    sections.extend(
        [
            _architecture_section(dataset, findings),
            _method_section(dataset),
            _system_config_overview_section(findings),
        ]
    )
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
    cluster_lookup = _build_cluster_lookup(dataset)
    grouped: dict[tuple[str, str], list[ReviewedLogIssue]] = {}
    for issue in dataset.reviewed_log_issues:
        if not issue.is_anomalous:
            continue
        cluster = _resolve_reviewed_issue_cluster(issue, cluster_lookup)
        cluster_key = (
            cluster.cluster_id
            if cluster is not None
            else issue.cluster_id
            or issue.cluster_name
            or "unknown-cluster"
        )
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
        cluster = _resolve_reviewed_issue_cluster(primary, cluster_lookup)
        valid_nodes = {node.node_id for node in cluster.nodes} if cluster is not None else set()
        known_nodes = {
            key.removeprefix("node:")
            for key in cluster_lookup
            if key.startswith("node:")
        }
        affected_nodes = tuple(
            sorted(
                {
                    node
                    for issue in issues
                    for node in issue.affected_nodes
                    if str(node).strip()
                    and (not known_nodes or node not in known_nodes or node in valid_nodes)
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
                target=", ".join(affected_nodes)
                or (cluster.name if cluster is not None else primary.cluster_name or primary.cluster_id),
                evidence="; ".join(evidence_parts) or "-",
                impact=primary.why or "日志候选经 LLM semantic review 判定为需要关注的异常。",
                recommendation=" / ".join(recommendations) or primary.recommendation or "结合原始日志时间线和运行状态复核。",
                category=primary.category or "log",
                merge_key=merge_key,
                affected_nodes=affected_nodes,
                source="llm_log_review",
                cluster_id=cluster.cluster_id if cluster is not None else primary.cluster_id or None,
                cluster_name=cluster.name if cluster is not None else primary.cluster_name or None,
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
        title=_outline_title(0, "巡检概述"),
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
        title=_outline_title(1, "巡检范围与输入说明"),
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
        title=_outline_title(3, "集群识别与架构总览"),
        blocks=blocks,
    )


def _problem_overview_sections(
    dataset: InspectionDataset,
    findings: list[InspectionFinding],
    severity_counts: Counter,
) -> list[ReportSectionModel]:
    high_total = severity_counts["critical"] + severity_counts["high"]
    summaries = _problem_overview_summaries(dataset, findings)
    table_title, table_columns = _problem_overview_table_contract()
    if summaries:
        table_rows = [
            [
                str(index),
                item["cluster"],
                item["severity"],
                item["problems"],
            ]
            for index, item in enumerate(summaries, start=1)
        ]
    else:
        table_rows = [["1", "-", "info", "未发现需要优先整改的明确高/中风险集群，建议保持例行巡检和容量监控。"]]

    return [
        ReportSectionModel(
            id="problem_overview",
            title=_outline_title(2, "问题概览与整改优先级"),
            blocks=[
                TextBlock(
                    text=(
                        f"本章面向管理视角，仅汇总需要优先决策的集群级问题和处置方向，不展开证据明细。"
                        f"本次巡检共发现 {len(findings)} 个风险项，其中高风险 {high_total} 项，"
                        f"中风险 {severity_counts['medium']} 项。"
                    )
                )
            ],
        ),
        ReportSectionModel(
            id="problem_overview__priority",
            title=table_title,
            level=2,
            blocks=[
                TableBlock(
                    title=table_title,
                    columns=table_columns,
                    rows=table_rows,
                    show_title=False,
                    table_kind="summary_priority_table",
                )
            ],
        ),
        ReportSectionModel(
            id="problem_overview__node_direction",
            title=_chapter3_direction_title(),
            level=2,
        ),
        *_problem_direction_sections(dataset, findings),
    ]


def _problem_overview_summaries(
    dataset: InspectionDataset,
    findings: list[InspectionFinding],
) -> list[dict[str, str]]:
    summaries: list[dict[str, str]] = []
    for cluster in _iter_clusters(dataset):
        cluster_findings = _findings_for_cluster(cluster, findings)
        significant = [f for f in cluster_findings if f.severity in {"critical", "high", "medium"}]
        if not significant:
            continue
        merged = _merge_cluster_findings(significant)
        highest = _highest_severity(merged)
        summaries.append(
            {
                "cluster": cluster.name,
                "severity": highest,
                "problems": "；".join(finding.risk_name for finding in merged),
            }
        )
    return sorted(
        summaries,
        key=lambda item: (
            SEVERITY_ORDER.get(item["severity"], 99),
            item["cluster"],
        ),
    )


def _problem_direction_sections(
    dataset: InspectionDataset,
    findings: list[InspectionFinding],
) -> list[ReportSectionModel]:
    grouped: dict[str, dict[str, set[str] | list[str]]] = {}
    for cluster in _iter_clusters(dataset):
        significant = [
            finding
            for finding in _findings_for_cluster(cluster, findings)
            if finding.severity in {"critical", "high", "medium"}
        ]
        for finding in _merge_cluster_findings(significant):
            item = grouped.setdefault(
                finding.risk_name,
                {"clusters": set(), "nodes": set(), "actions": []},
            )
            clusters = item["clusters"] if isinstance(item["clusters"], set) else set()
            nodes = item["nodes"] if isinstance(item["nodes"], set) else set()
            actions = item["actions"] if isinstance(item["actions"], list) else []
            clusters.add(cluster.name)
            nodes.update(_target_items(finding))
            actions.extend(_split_actions(finding.recommendation))

    if not grouped:
        return [
            ReportSectionModel(
                id="problem_overview__node_direction__no-explicit-priority",
                title="未发现明确优先问题",
                level=3,
                blocks=[
                    InfoTableBlock(
                        table_kind="issue_scope_table",
                        rows=[
                            InfoTableRow(label="问题类型", text="未发现明确优先问题"),
                            InfoTableRow(label="涉及集群", text="-"),
                            InfoTableRow(label="涉及节点", text="-"),
                            InfoTableRow(label="优先处置方向", text="保持例行巡检和容量监控。", bullet=True),
                        ]
                    )
                ],
            )
        ]

    ordered_names = _ordered_problem_names(grouped)
    sections: list[ReportSectionModel] = []
    contract_actions = _chapter3_problem_type_actions()
    for risk_name in ordered_names:
        item = grouped[risk_name]
        clusters = sorted(str(value) for value in item["clusters"])
        nodes = sorted(str(value) for value in item["nodes"])
        actions = _unique_strings(contract_actions.get(risk_name) or item["actions"])
        sections.append(
            ReportSectionModel(
                id=f"problem_overview__node_direction__{_slug(risk_name)}",
                title=risk_name,
                level=3,
                blocks=[
                    InfoTableBlock(
                        table_kind="issue_scope_table",
                        rows=[
                            InfoTableRow(label="问题类型", text=risk_name),
                            InfoTableRow(label="涉及集群", text=", ".join(clusters) or "-"),
                            InfoTableRow(label="涉及节点", text=", ".join(nodes) or "-"),
                            InfoTableRow(label="优先处置方向", text="\n".join(actions), bullet=True),
                        ]
                    )
                ],
            )
        )
    return sections


def _ordered_problem_names(grouped: dict[str, object]) -> list[str]:
    configured = _chapter3_problem_type_order()
    configured_set = set(configured)
    return [
        *[name for name in configured if name in grouped],
        *sorted(name for name in grouped if name not in configured_set),
    ]


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
                cluster_id=primary.cluster_id,
                cluster_name=primary.cluster_name,
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
        title=_outline_title(4, "巡检目标及方法"),
        blocks=[
            TextBlock(text="巡检目标是识别 Redis 架构、配置、运行状态、主机环境和日志异常风险，并形成可审计的整改建议。"),
            TextBlock(text=f"本次采用方法：{method}。在线路径仅使用只读命令，不执行写入或自动修复。"),
        ],
    )


def _system_config_overview_section(findings: list[InspectionFinding]) -> ReportSectionModel:
    return ReportSectionModel(
        id="system_config",
        title=_outline_title(5, "系统配置检查"),
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
        title=_outline_title(6, "操作系统检查"),
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
        title=_outline_title(7, "Redis 数据库检查"),
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
                        table_kind="log_candidate_summary_table",
                    ),
                ],
            )
        )
    return sections


def _risk_overview_section(findings: list[InspectionFinding]) -> ReportSectionModel:
    severity_counts = Counter(finding.severity for finding in findings)
    return ReportSectionModel(
        id="risk_remediation",
        title=_outline_title(8, "风险与整改建议"),
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
        risk_entries = _merge_cluster_risk_entries(cluster_findings)
        sections.append(
            ReportSectionModel(
                id=_cluster_section_id("risk_remediation", cluster),
                title=cluster.name,
                level=2,
                blocks=[
                    TextBlock(text=f"{cluster.name} 风险项按等级排序，以下条目分别列出对象、影响、证据和整改动作。"),
                ],
            )
        )
        if not risk_entries:
            sections.append(
                ReportSectionModel(
                    id=f"{_cluster_section_id('risk_remediation', cluster)}__no-explicit-risk",
                    title="未发现明确风险",
                    level=3,
                    blocks=[
                        InfoTableBlock(
                            table_kind="risk_detail_table",
                            rows=[
                                InfoTableRow(label="风险等级", text="info"),
                                InfoTableRow(label="风险描述", text="当前证据未显示明确风险。"),
                                InfoTableRow(label="证据", text="-"),
                                InfoTableRow(label="整改建议", text="保持例行巡检和容量监控。", bullet=True),
                            ]
                        )
                    ],
                )
            )
            continue
        for entry in risk_entries:
            sections.append(
                ReportSectionModel(
                    id=f"{_cluster_section_id('risk_remediation', cluster)}__{_slug(str(entry['risk_name']))}",
                    title=str(entry["risk_name"]),
                    level=3,
                    blocks=[_risk_detail_block(entry)],
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
        title=_outline_title(9, "附录"),
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
    cluster_ids = {cluster.cluster_id, cluster.name}
    scoped: list[InspectionFinding] = []
    for finding in findings:
        if finding.cluster_id or finding.cluster_name:
            if finding.cluster_id in cluster_ids or finding.cluster_name in cluster_ids:
                scoped.append(finding)
            continue
        if finding.target in targets or any(node in targets for node in finding.affected_nodes):
            scoped.append(finding)
    return scoped


def _build_cluster_lookup(dataset: InspectionDataset) -> dict[str, InspectionCluster]:
    lookup: dict[str, InspectionCluster] = {}
    for cluster in _iter_clusters(dataset):
        if cluster.cluster_id:
            lookup[cluster.cluster_id] = cluster
        if cluster.name:
            lookup[cluster.name] = cluster
        for node in cluster.nodes:
            if node.node_id:
                lookup[f"node:{node.node_id}"] = cluster
    return lookup


def _resolve_reviewed_issue_cluster(
    issue: ReviewedLogIssue,
    cluster_lookup: dict[str, InspectionCluster],
) -> InspectionCluster | None:
    if issue.cluster_id and issue.cluster_id in cluster_lookup:
        return cluster_lookup[issue.cluster_id]
    if issue.cluster_name and issue.cluster_name in cluster_lookup:
        return cluster_lookup[issue.cluster_name]
    for node in issue.affected_nodes:
        cluster = cluster_lookup.get(f"node:{node}")
        if cluster is not None:
            return cluster
    return None


def _target_items(finding: InspectionFinding) -> list[str]:
    return _unique_strings(finding.affected_nodes or (finding.target,))


def _merge_cluster_risk_entries(findings: list[InspectionFinding]) -> list[dict[str, object]]:
    grouped: dict[str, list[InspectionFinding]] = {}
    for finding in findings:
        grouped.setdefault(finding.risk_name, []).append(finding)

    entries: list[dict[str, object]] = []
    for risk_name, items in grouped.items():
        primary = min(items, key=lambda item: SEVERITY_ORDER.get(item.severity, 99))
        is_log_review = any(_is_log_review_finding(item) for item in items)
        targets = _unique_strings(
            target
            for item in items
            for target in _target_items(item)
        )
        impacts = _unique_strings(item.impact for item in items if item.impact)
        recommendations = _unique_strings(
            action
            for item in items
            for action in _split_actions(item.recommendation)
        )
        impact_text = " / ".join(impacts) or primary.impact
        evidence_lines = _risk_evidence_lines(items, is_log_review=is_log_review)
        review_text = ""
        if is_log_review:
            review_text = " / ".join(
                _unique_strings(
                    fields.get("review", "")
                    for item in items
                    for fields in (_split_review_evidence(item.evidence),)
                    if fields.get("review")
                )
            )
        display_review = is_log_review and _review_has_distinct_analysis(review_text, impact_text)
        entries.append(
            {
                "risk_name": risk_name,
                "severity": primary.severity,
                "targets": targets,
                "impact": impact_text,
                "recommendations": recommendations or [primary.recommendation],
                "evidence_lines": evidence_lines,
                "is_log_review": is_log_review,
                "display_review": display_review,
                "review": review_text,
            }
        )

    return sorted(
        entries,
        key=lambda item: (
            SEVERITY_ORDER.get(str(item["severity"]), 99),
            str(item["risk_name"]),
        ),
    )


def _risk_detail_block(entry: dict[str, object]) -> InfoTableBlock:
    rows: list[InfoTableRow] = []
    for field in _chapter9_field_order():
        if field == "Review" and not entry.get("display_review"):
            continue
        if field == "风险等级":
            rows.append(InfoTableRow(label=field, text=str(entry["severity"])))
        elif field == "风险描述":
            rows.append(InfoTableRow(label=field, text=f"{entry['risk_name']}。"))
        elif field == "涉及对象":
            rows.append(InfoTableRow(label=field, text=", ".join(str(item) for item in entry["targets"]) or "-"))
        elif field == "影响说明":
            rows.append(InfoTableRow(label=field, text=str(entry["impact"]) or "-"))
        elif field == "Review":
            rows.append(InfoTableRow(label=field, text=str(entry.get("review") or "-")))
        elif field == "证据":
            rows.append(InfoTableRow(label=field, text="\n".join(str(line) for line in entry["evidence_lines"] or ["-"])))
        elif field == "整改建议":
            rows.append(
                InfoTableRow(
                    label=field,
                    text="\n".join(str(action) for action in entry["recommendations"] or ["保持例行巡检和容量监控。"]),
                    bullet=True,
                )
            )
    return InfoTableBlock(rows=rows, table_kind="risk_detail_table")


def _risk_evidence_lines(items: list[InspectionFinding], *, is_log_review: bool) -> list[str]:
    if is_log_review:
        samples: list[str] = []
        confidences: list[str] = []
        raw_evidence: list[str] = []
        for item in items:
            fields = _split_review_evidence(item.evidence)
            if fields:
                if fields.get("samples"):
                    samples.append(fields["samples"])
                if fields.get("confidence"):
                    confidences.append(fields["confidence"])
            elif item.evidence and item.evidence != "-":
                raw_evidence.append(item.evidence)
        lines = []
        unique_samples = _unique_strings(samples)
        unique_confidences = _unique_strings(confidences)
        if unique_samples:
            lines.append(f"Samples：{' | '.join(unique_samples)}")
        if unique_confidences:
            lines.append(f"Confidence：{', '.join(unique_confidences)}")
        lines.extend(raw_evidence)
        return lines or ["-"]

    lines: list[str] = []
    for item in items:
        evidence = item.evidence if item.evidence else "-"
        for target in _target_items(item):
            lines.append(f"{target}：{evidence}")
    return _unique_strings(lines) or ["-"]


def _is_log_review_finding(finding: InspectionFinding) -> bool:
    return finding.source == "llm_log_review" or bool(_split_review_evidence(finding.evidence))


def _review_has_distinct_analysis(review_text: str, impact_text: str) -> bool:
    normalized_review = _normalize_review_for_comparison(review_text)
    if not normalized_review:
        return False
    return normalized_review != _normalize_review_for_comparison(impact_text)


def _normalize_review_for_comparison(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value).replace("\u3000", " ").strip())
    return text.rstrip(".。;；!！?？").strip()


def _split_review_evidence(evidence: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in re.split(r"\s*;\s*", evidence):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip().lower()
        if key in {"review", "samples", "confidence"}:
            fields[key] = value.strip()
    return fields


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


def _split_actions(value: str) -> list[str]:
    text = _string_value(value)
    if not text:
        return []
    normalized = text
    for separator in ("；", ";", " / ", "｜", "|"):
        normalized = normalized.replace(separator, "\n")
    normalized = normalized.replace("，必要时", "\n必要时")
    normalized = normalized.replace("，并", "\n并")
    normalized = normalized.replace("，先", "\n先")
    return _unique_strings(
        part.strip().strip("。")
        for part in normalized.splitlines()
        if part.strip().strip("。")
    )


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


def _table_schema(name: str, *, fallback_title: str, fallback_columns: list[str]) -> tuple[str, list[str]]:
    schema = load_skill_yaml_asset(_SKILL_NAME, "assets/table_schemas.yaml").get(name)
    if not isinstance(schema, dict):
        return fallback_title, fallback_columns
    title = str(schema.get("title") or fallback_title)
    columns = schema.get("columns")
    if not isinstance(columns, list) or not all(isinstance(column, str) for column in columns):
        columns = fallback_columns
    return title, list(columns)


def _section_contracts() -> dict[str, Any]:
    contracts = load_skill_yaml_asset(_SKILL_NAME, "assets/section_contracts.yaml")
    return contracts if isinstance(contracts, dict) else {}


def _chapter3_contract() -> dict[str, Any]:
    contract = _section_contracts().get("chapter_3")
    return contract if isinstance(contract, dict) else {}


def _chapter9_contract() -> dict[str, Any]:
    contract = _section_contracts().get("chapter_9")
    return contract if isinstance(contract, dict) else {}


def _problem_overview_table_contract() -> tuple[str, list[str]]:
    fallback_title, fallback_columns = _table_schema(
        "problem_overview",
        fallback_title="优先级速览",
        fallback_columns=["序号", "集群", "风险等级", "关键问题"],
    )
    for subsection in _chapter3_contract().get("subsections", []):
        if not isinstance(subsection, dict) or subsection.get("id") != "priority_overview":
            continue
        title = str(subsection.get("title") or fallback_title)
        columns = subsection.get("columns")
        if isinstance(columns, list) and all(isinstance(column, str) for column in columns):
            return title, list(columns)
    return fallback_title, fallback_columns


def _chapter3_direction_title() -> str:
    for subsection in _chapter3_contract().get("subsections", []):
        if isinstance(subsection, dict) and subsection.get("id") == "node_direction":
            return str(subsection.get("title") or "涉及节点与优先处置方向")
    return "涉及节点与优先处置方向"


def _chapter3_problem_type_order() -> list[str]:
    value = _chapter3_contract().get("problem_type_order")
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return [
        "AOF重写频繁触发",
        "RDB持久化期间Copy-on-Write内存使用量高",
        "fork失败导致无法后台保存",
        "Redis集群节点故障与恢复事件",
        "主机 Swap 已使用",
        "主机透明大页处于 always",
        "Redis 内存碎片率偏高",
        "Redis 未配置 maxmemory",
    ]


def _chapter3_problem_type_actions() -> dict[str, list[str]]:
    raw = _chapter3_contract().get("problem_type_actions")
    if not isinstance(raw, dict):
        return {}
    actions: dict[str, list[str]] = {}
    for risk_name, value in raw.items():
        if isinstance(value, list):
            actions[str(risk_name)] = _unique_strings(value)
    return actions


def _chapter9_field_order() -> list[str]:
    fields = _chapter9_contract().get("fields")
    if isinstance(fields, list) and all(isinstance(field, str) for field in fields):
        return list(fields)
    return ["风险等级", "风险描述", "涉及对象", "影响说明", "Review", "证据", "整改建议"]


def _outline_title(index: int, fallback: str) -> str:
    titles = load_numbered_outline_titles(_SKILL_NAME, "assets/report_outline.md")
    if 0 <= index < len(titles):
        return titles[index]
    return fallback


__all__ = ["analyze_inspection_dataset"]
