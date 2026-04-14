from pathlib import Path
import json

from dba_assistant.capabilities.redis_inspection_report.service import analyze_offline_inspection
from dba_assistant.application.request_models import NormalizedRequest, RuntimeInputs, Secrets
from dba_assistant.core.observability import (
    bootstrap_observability,
    reset_observability_state,
    start_execution_session,
)
from dba_assistant.core.reporter.report_model import TableBlock
from dba_assistant.core.reporter.generate_analysis_report import generate_analysis_report
from dba_assistant.core.reporter.types import OutputMode, ReportFormat, ReportOutputConfig
from dba_assistant.deep_agent_integration.config import ObservabilityConfig
from dba_assistant.interface.types import InterfaceSurface


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
    risk_rows = [
        row
        for section in report.sections
        if section.id.startswith("risk_remediation__")
        for block in section.blocks
        if isinstance(block, TableBlock)
        for row in block.rows
    ]
    assert any(row[0] == "Redis 内存水位过高" for row in risk_rows)


def test_offline_inspection_records_audit_phases_through_existing_observability(
    tmp_path: Path,
) -> None:
    config = ObservabilityConfig(
        enabled=True,
        console_enabled=False,
        console_level="WARNING",
        file_level="INFO",
        log_dir=tmp_path / "logs",
        app_log_file="app.log.jsonl",
        audit_log_file="audit.jsonl",
    )
    reset_observability_state()
    bootstrap_observability(config)
    source = tmp_path / "node"
    source.mkdir()
    (source / "info.txt").write_text(
        "redis_version:7.0.15\nrole:master\ntcp_port:6379\nused_memory:100\nmaxmemory:1000\n",
        encoding="utf-8",
    )
    normalized = NormalizedRequest(
        raw_prompt="offline inspection",
        prompt="offline inspection",
        runtime_inputs=RuntimeInputs(output_mode="report", report_format="docx", input_paths=(source,)),
        secrets=Secrets(redis_password="secret-do-not-log"),
    )

    with start_execution_session(
        interface_surface=InterfaceSurface.CLI,
        normalized_request=normalized,
        raw_request_summary={"prompt": "secret-do-not-log"},
    ):
        report = analyze_offline_inspection((source,), language="zh-CN")
        generate_analysis_report(
            report,
            ReportOutputConfig(
                mode=OutputMode.REPORT,
                format=ReportFormat.DOCX,
                output_path=tmp_path / "inspection.docx",
                template_name="inspection",
                language="zh-CN",
            ),
        )

    events = [
        json.loads(line)
        for line in config.audit_log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    phases = [
        event["phase"]
        for event in events
        if event["event_type"] == "redis_inspection_phase"
    ]
    assert phases == [
        "offline_input_detected",
        "archive_extract_start",
        "archive_extract_end",
        "evidence_grouping_start",
        "evidence_grouping_end",
        "system_cluster_node_grouping_ready",
        "inspection_analysis_start",
        "inspection_analysis_end",
        "report_render_start",
        "report_render_end",
    ]
    inspection_events = [
        event for event in events if event["event_type"] == "redis_inspection_phase"
    ]
    assert "secret-do-not-log" not in json.dumps(inspection_events, ensure_ascii=False)

    reset_observability_state()
