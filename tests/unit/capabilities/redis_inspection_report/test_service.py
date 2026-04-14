from pathlib import Path

from dba_assistant.capabilities.redis_inspection_report.service import analyze_offline_inspection
from dba_assistant.core.reporter.report_model import TableBlock


def test_analyze_offline_inspection_collects_analyzes_and_returns_report(tmp_path: Path) -> None:
    source = tmp_path / "node"
    source.mkdir()
    (source / "info.txt").write_text(
        "\n".join(
            [
                "redis_version:6.2.12",
                "role:master",
                "tcp_port:6379",
                "used_memory:900",
                "maxmemory:1000",
                "cluster_enabled:0",
            ]
        ),
        encoding="utf-8",
    )

    report = analyze_offline_inspection((source,), language="zh-CN")

    assert report.metadata["route"] == "offline_inspection"
    assert report.metadata["source_mode"] == "offline"
    assert report.metadata["node_count"] == "1"
    risk_section = next(section for section in report.sections if section.id == "risk_remediation")
    risk_table = next(block for block in risk_section.blocks if isinstance(block, TableBlock))
    assert any(row[0] == "Redis 内存水位过高" for row in risk_table.rows)
