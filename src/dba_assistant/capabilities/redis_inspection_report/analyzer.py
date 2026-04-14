from __future__ import annotations

from collections import Counter
from typing import Any

from dba_assistant.capabilities.redis_inspection_report.types import (
    InspectionCluster,
    InspectionDataset,
    InspectionFinding,
    InspectionNode,
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
    summary = _build_summary(system_count, cluster_count, node_count, severity_counts)
    metadata = {
        "source_mode": dataset.source_mode,
        "system_count": str(system_count),
        "cluster_count": str(cluster_count),
        "node_count": str(node_count),
        "finding_count": str(len(findings)),
        "high_findings": str(severity_counts["critical"] + severity_counts["high"]),
        "medium_findings": str(severity_counts["medium"]),
        **{key: str(value) for key, value in dataset.metadata.items()},
    }
    sections = [
        _scope_section(dataset, system_count, cluster_count, node_count),
        _architecture_section(dataset),
        _summary_section(findings, severity_counts),
        _method_section(dataset),
        _system_config_section(dataset, findings),
        _os_section(dataset, findings),
        _redis_section(dataset, findings),
        _log_section(dataset, findings),
        _risk_section(findings),
        _appendix_section(dataset),
    ]
    return AnalysisReport(
        title="Redis 巡检报告" if language != "en-US" else "Redis Inspection Report",
        summary=summary,
        sections=sections,
        metadata=metadata,
        language=language,
    )


def _collect_findings(dataset: InspectionDataset) -> list[InspectionFinding]:
    findings: list[InspectionFinding] = []
    for cluster in _iter_clusters(dataset):
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

    for event in _log_events(node):
        message = _string_value(event.get("message"))
        findings.append(
            InspectionFinding(
                risk_name="Redis 错误日志存在异常事件",
                severity="high" if _is_high_log_event(message) else "medium",
                target=target,
                evidence=message,
                impact="错误日志中的异常事件可能对应服务重启、持久化失败、复制中断或内存风险。",
                recommendation="按事件时间线关联业务告警、Redis 状态与主机资源，优先处理重复出现的 error/OOM/fail 事件。",
                category="log",
            )
        )
    return findings


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


def _architecture_section(dataset: InspectionDataset) -> ReportSectionModel:
    rows: list[list[str]] = []
    for system in dataset.systems:
        for cluster in system.clusters:
            masters = sum(1 for node in cluster.nodes if (node.role or "").lower() == "master")
            replicas = sum(1 for node in cluster.nodes if (node.role or "").lower() in {"slave", "replica"})
            rows.append(
                [
                    system.name,
                    cluster.name,
                    cluster.cluster_type,
                    str(len(cluster.nodes)),
                    str(masters),
                    str(replicas),
                ]
            )
    return ReportSectionModel(
        id="architecture_overview",
        title="集群识别与架构总览",
        blocks=[
            TextBlock(text="系统按统一 inspection dataset 归并为系统、集群、节点三层，便于离线和在线路径复用同一分析器。"),
            TableBlock(
                title="集群归并结果",
                columns=["系统", "集群", "类型", "节点数", "Master 数", "Replica 数"],
                rows=rows or [["-", "-", "-", "0", "0", "0"]],
            ),
        ],
    )


def _summary_section(findings: list[InspectionFinding], severity_counts: Counter) -> ReportSectionModel:
    rows = [
        ["critical", str(severity_counts["critical"])],
        ["high", str(severity_counts["high"])],
        ["medium", str(severity_counts["medium"])],
        ["low", str(severity_counts["low"])],
        ["info", str(severity_counts["info"])],
    ]
    high_total = severity_counts["critical"] + severity_counts["high"]
    return ReportSectionModel(
        id="inspection_summary",
        title="巡检结果总结",
        blocks=[
            TextBlock(text=f"本次巡检共发现 {len(findings)} 个风险项，其中高风险 {high_total} 项，中风险 {severity_counts['medium']} 项。"),
            TableBlock(title="风险等级统计", columns=["风险等级", "数量"], rows=rows),
        ],
    )


def _method_section(dataset: InspectionDataset) -> ReportSectionModel:
    method = "离线证据包解析、节点归并、规则分析、共享报告渲染" if dataset.source_mode == "offline" else "在线只读 Redis 探测、统一数据建模、规则分析、共享报告渲染"
    return ReportSectionModel(
        id="inspection_method",
        title="巡检目标及方法",
        blocks=[
            TextBlock(text="巡检目标是识别 Redis 架构、配置、运行状态、主机环境和日志异常风险，并形成可审计的整改建议。"),
            TextBlock(text=f"本次采用方法：{method}。在线路径仅使用只读命令，不执行写入或自动修复。"),
        ],
    )


def _system_config_section(dataset: InspectionDataset, findings: list[InspectionFinding]) -> ReportSectionModel:
    rows = []
    for node in _iter_nodes(dataset):
        rows.append(
            [
                node.node_id,
                _string_value(node.redis_facts.get("maxmemory")) or "-",
                _string_value(node.redis_facts.get("maxmemory_policy") or node.redis_facts.get("maxmemory-policy")) or "-",
                _string_value(node.redis_facts.get("appendonly") or node.redis_facts.get("aof_enabled")) or "-",
            ]
        )
    return ReportSectionModel(
        id="system_config",
        title="系统配置检查",
        blocks=[
            TextBlock(text=f"配置检查重点覆盖 maxmemory、淘汰策略、持久化配置等项目；相关风险项 {sum(1 for item in findings if item.category == 'redis')} 个。"),
            TableBlock(title="关键 Redis 配置", columns=["节点", "maxmemory", "淘汰策略", "AOF/appendonly"], rows=rows or [["-", "-", "-", "-"]]),
        ],
    )


def _os_section(dataset: InspectionDataset, findings: list[InspectionFinding]) -> ReportSectionModel:
    rows = [
        [
            node.node_id,
            _string_value(node.host_facts.get("os")) or "-",
            _string_value(node.host_facts.get("kernel")) or "-",
            _string_value(node.host_facts.get("transparent_hugepage")) or "-",
            _string_value(node.host_facts.get("swap")) or "-",
        ]
        for node in _iter_nodes(dataset)
    ]
    return ReportSectionModel(
        id="os_inspection",
        title="操作系统检查",
        blocks=[
            TextBlock(text=f"操作系统检查覆盖平台、内核、透明大页、swap 等主机侧证据；相关风险项 {sum(1 for item in findings if item.category == 'os')} 个。"),
            TableBlock(title="主机侧证据摘要", columns=["节点", "OS", "内核", "透明大页", "Swap"], rows=rows or [["-", "-", "-", "-", "-"]]),
        ],
    )


def _redis_section(dataset: InspectionDataset, findings: list[InspectionFinding]) -> ReportSectionModel:
    rows = [
        [
            node.node_id,
            node.role or "-",
            node.version or "-",
            _string_value(node.redis_facts.get("used_memory")) or "-",
            _string_value(node.redis_facts.get("maxmemory")) or "-",
            _string_value(node.redis_facts.get("mem_fragmentation_ratio")) or "-",
            str(_slowlog_count(node)),
        ]
        for node in _iter_nodes(dataset)
    ]
    return ReportSectionModel(
        id="redis_database",
        title="Redis 数据库检查",
        blocks=[
            TextBlock(text=f"Redis 数据库检查覆盖角色、版本、内存、碎片率、慢日志和集群状态；相关风险项 {sum(1 for item in findings if item.category == 'redis')} 个。"),
            TableBlock(title="Redis 节点状态摘要", columns=["节点", "角色", "版本", "used_memory", "maxmemory", "碎片率", "慢日志数"], rows=rows or [["-", "-", "-", "-", "-", "-", "0"]]),
        ],
    )


def _log_section(dataset: InspectionDataset, findings: list[InspectionFinding]) -> ReportSectionModel:
    rows = []
    for node in _iter_nodes(dataset):
        for event in _log_events(node):
            rows.append([node.node_id, _string_value(event.get("level")) or "-", _string_value(event.get("message"))])
    return ReportSectionModel(
        id="error_log_analysis",
        title="错误日志与异常事件分析",
        blocks=[
            TextBlock(text=f"日志检查汇总 error、warning、restart、fail、OOM、fork、AOF/RDB、replication 等事件；相关风险项 {sum(1 for item in findings if item.category == 'log')} 个。"),
            TableBlock(title="异常日志事件", columns=["节点", "级别", "事件"], rows=rows or [["-", "-", "未发现明确异常日志事件"]]),
        ],
    )


def _risk_section(findings: list[InspectionFinding]) -> ReportSectionModel:
    rows = [
        [
            finding.risk_name,
            finding.severity,
            finding.target,
            finding.impact,
            finding.evidence,
            finding.recommendation,
        ]
        for finding in findings
    ]
    return ReportSectionModel(
        id="risk_remediation",
        title="风险与整改建议",
        blocks=[
            TableBlock(
                title="风险与整改建议清单",
                columns=["风险名称", "风险等级", "发现对象", "影响说明", "证据", "建议整改措施"],
                rows=rows or [["未发现明确风险", "info", "-", "-", "-", "保持例行巡检和容量监控。"]],
            )
        ],
    )


def _appendix_section(dataset: InspectionDataset) -> ReportSectionModel:
    rows = [
        [
            node.node_id,
            node.hostname,
            node.ip or "-",
            "" if node.port is None else str(node.port),
            node.source_path or "-",
        ]
        for node in _iter_nodes(dataset)
    ]
    return ReportSectionModel(
        id="appendix",
        title="附录",
        blocks=[
            TextBlock(text="附录保留节点来源与关键标识，便于后续回溯证据。"),
            TableBlock(title="节点清单", columns=["节点", "主机名", "IP", "端口", "来源"], rows=rows or [["-", "-", "-", "-", "-"]]),
        ],
    )


def _build_summary(
    system_count: int,
    cluster_count: int,
    node_count: int,
    severity_counts: Counter,
) -> str:
    high_total = severity_counts["critical"] + severity_counts["high"]
    return (
        f"本次 Redis 巡检覆盖 {system_count} 个系统、{cluster_count} 个集群、{node_count} 个节点。"
        f"识别高风险 {high_total} 项、中风险 {severity_counts['medium']} 项，建议优先处理高风险并保留整改证据。"
    )


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


def _slowlog_count(node: InspectionNode) -> int:
    slowlog = node.redis_facts.get("slowlog")
    if isinstance(slowlog, dict):
        value = slowlog.get("count")
        if isinstance(value, int):
            return value
    value = node.redis_facts.get("slowlog_count")
    parsed = _to_float(value)
    return int(parsed or 0)


def _log_events(node: InspectionNode) -> list[dict[str, Any]]:
    events = node.log_facts.get("error_events")
    if isinstance(events, list):
        return [event for event in events if isinstance(event, dict)]
    return []


def _is_high_log_event(message: str) -> bool:
    lowered = message.lower()
    return any(token in lowered for token in ("error", "fail", "oom", "restart"))


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
