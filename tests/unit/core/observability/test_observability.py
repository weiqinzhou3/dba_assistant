import json
import logging
from pathlib import Path

from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
from dba_assistant.core.observability import (
    bootstrap_observability,
    get_current_execution_session,
    observe_tool_call,
    reset_observability_state,
    start_execution_session,
)
from dba_assistant.deep_agent_integration.config import ObservabilityConfig
from dba_assistant.interface.hitl import AuditedApprovalHandler, AutoApproveHandler
from dba_assistant.interface.types import ApprovalRequest, ApprovalStatus, InterfaceSurface


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _make_observability_config(tmp_path: Path) -> ObservabilityConfig:
    return ObservabilityConfig(
        enabled=True,
        level="INFO",
        console_enabled=False,
        log_dir=tmp_path / "logs",
        app_log_file="app.log.jsonl",
        audit_log_file="audit.jsonl",
    )


def test_bootstrap_observability_uses_configured_paths_and_sanitizes_app_logs(tmp_path: Path) -> None:
    config = _make_observability_config(tmp_path)
    reset_observability_state()
    bootstrap_observability(config)

    logging.getLogger("dba_assistant.test").info("redis_password=%s", "super-secret")

    records = _read_jsonl(config.app_log_path)

    assert config.app_log_path.exists()
    assert config.audit_log_path.exists()
    assert any(record["logger"] == "dba_assistant.test" for record in records)
    serialized = json.dumps(records, ensure_ascii=False)
    assert "super-secret" not in serialized
    assert "<redacted>" in serialized

    reset_observability_state()


def test_audited_approval_handler_records_first_class_approval_events(tmp_path: Path) -> None:
    config = _make_observability_config(tmp_path)
    reset_observability_state()
    bootstrap_observability(config)

    normalized = NormalizedRequest(
        raw_prompt="analyze redis password=super-secret",
        prompt="analyze redis password=super-secret",
        runtime_inputs=RuntimeInputs(output_mode="summary"),
        secrets=Secrets(redis_password="super-secret"),
        rdb_overrides=RdbOverrides(),
    )

    with start_execution_session(
        interface_surface=InterfaceSurface.CLI,
        normalized_request=normalized,
        raw_request_summary={"prompt": "password=super-secret"},
    ):
        handler = AuditedApprovalHandler(AutoApproveHandler(approve=False))
        response = handler.request_approval(
            ApprovalRequest(
                action="stage_rdb_rows_to_mysql",
                message="mysql_password=super-secret",
                details={"mysql_password": "super-secret", "row_count": 100},
            )
        )

    assert response.status is ApprovalStatus.DENIED

    events = _read_jsonl(config.audit_log_path)
    event_types = [event["event_type"] for event in events]
    assert "approval_requested" in event_types
    assert "approval_resolved" in event_types
    serialized = json.dumps(events, ensure_ascii=False)
    assert "super-secret" not in serialized
    assert "<redacted>" in serialized

    reset_observability_state()


def test_execution_session_records_tool_sequence_and_artifact_metadata(tmp_path: Path) -> None:
    config = _make_observability_config(tmp_path)
    reset_observability_state()
    bootstrap_observability(config)

    normalized = NormalizedRequest(
        raw_prompt="analyze /tmp/dump.rdb password=super-secret",
        prompt="analyze /tmp/dump.rdb password=super-secret",
        runtime_inputs=RuntimeInputs(
            output_mode="report",
            report_format="docx",
            output_path=tmp_path / "outputs" / "report.docx",
            input_paths=(Path("/tmp/dump.rdb"),),
            input_kind="local_rdb",
        ),
        secrets=Secrets(redis_password="super-secret"),
        rdb_overrides=RdbOverrides(profile_name="generic"),
    )

    with start_execution_session(
        interface_surface=InterfaceSurface.CLI,
        normalized_request=normalized,
        raw_request_summary={"prompt": "password=super-secret"},
    ) as session:
        result = observe_tool_call(
            "analyze_local_rdb",
            {"redis_password": "super-secret", "input_paths": ["/tmp/dump.rdb"]},
            lambda: "analysis complete",
        )
        assert result == "analysis complete"
        current = get_current_execution_session()
        assert current is session
        session.record_artifact(
            output_mode="report",
            output_path=tmp_path / "outputs" / "report.docx",
            artifact_id="artifact-1",
            report_metadata={"route": "direct_rdb_analysis", "rows_processed": "123"},
        )

    events = _read_jsonl(config.audit_log_path)
    completion_events = [event for event in events if event["event_type"] == "execution_completed"]
    assert len(completion_events) == 1
    completion = completion_events[0]
    assert completion["final_status"] == "success"
    assert completion["selected_capability"] == "analyze_local_rdb"
    assert completion["tool_invocation_sequence"][0]["tool_name"] == "analyze_local_rdb"
    assert completion["output_mode"] == "report"
    assert completion["output_path"] == str(tmp_path / "outputs" / "report.docx")
    assert completion["report_metadata"]["route"] == "direct_rdb_analysis"
    assert "super-secret" not in json.dumps(events, ensure_ascii=False)

    reset_observability_state()
