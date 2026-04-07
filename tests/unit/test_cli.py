import json
from pathlib import Path
from types import SimpleNamespace

from dba_assistant import cli
from dba_assistant.interface import adapter as adapter_module
from dba_assistant.interface.types import ApprovalRequest, ApprovalStatus


def test_cli_ask_delegates_to_interface_adapter(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_handle_request(request, *, approval_handler):
        captured["request"] = request
        captured["approval_handler"] = approval_handler
        return "agent ok"

    monkeypatch.setattr(cli, "handle_request", fake_handle_request)

    exit_code = cli.main(["ask", "analyze the rdb"])

    assert exit_code == 0
    assert capsys.readouterr().out == "agent ok\n"
    req = captured["request"]
    assert req.prompt == "analyze the rdb"
    assert req.input_paths == []
    assert req.output_path is None
    assert req.config_path is None
    assert req.profile is None
    assert req.report_format is None


def test_cli_ask_threads_all_flags_to_interface_request(monkeypatch, tmp_path, capsys) -> None:
    captured: dict[str, object] = {}
    source = tmp_path / "dump.rdb"
    source.write_text("x", encoding="utf-8")

    def fake_handle_request(request, *, approval_handler):
        captured["request"] = request
        return "ok"

    monkeypatch.setattr(cli, "handle_request", fake_handle_request)

    exit_code = cli.main([
        "ask", "analyze rdb",
        "--input", str(source),
        "--output", "/tmp/out.docx",
        "--config", "/etc/custom.yaml",
        "--profile", "rcs",
        "--report-format", "docx",
    ])

    assert exit_code == 0
    req = captured["request"]
    assert req.prompt == "analyze rdb"
    assert req.input_paths == [source]
    assert req.output_path == Path("/tmp/out.docx")
    assert req.config_path == "/etc/custom.yaml"
    assert req.profile == "rcs"
    assert req.report_format == "docx"


def test_cli_ask_threads_mysql_flags_to_interface_request(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_handle_request(request, *, approval_handler):
        captured["request"] = request
        return "ok"

    monkeypatch.setattr(cli, "handle_request", fake_handle_request)

    exit_code = cli.main([
        "ask", "analyze rdb via mysql",
        "--mysql-host", "db.example",
        "--mysql-port", "3307",
        "--mysql-user", "analyst",
        "--mysql-database", "analysis_db",
        "--mysql-password", "secret",
        "--mysql-table", "preparsed_keys",
        "--mysql-query", "SELECT * FROM preparsed_keys",
    ])

    assert exit_code == 0
    req = captured["request"]
    assert req.mysql_host == "db.example"
    assert req.mysql_port == 3307
    assert req.mysql_user == "analyst"
    assert req.mysql_database == "analysis_db"
    assert req.mysql_password == "secret"
    assert req.mysql_table == "preparsed_keys"
    assert req.mysql_query == "SELECT * FROM preparsed_keys"


def test_cli_ask_threads_remote_redis_flags_to_interface_request(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_handle_request(request, *, approval_handler):
        captured["request"] = request
        return "ok"

    monkeypatch.setattr(cli, "handle_request", fake_handle_request)

    exit_code = cli.main([
        "ask", "analyze remote redis",
        "--redis-password", "123456",
        "--ssh-host", "192.168.23.54",
        "--ssh-port", "2222",
        "--ssh-username", "root",
        "--ssh-password", "root",
        "--remote-rdb-path", "/data/redis/data/dump.rdb",
        "--remote-rdb-path-source", "user_override",
        "--fresh-rdb",
    ])

    assert exit_code == 0
    req = captured["request"]
    assert req.redis_password == "123456"
    assert req.ssh_host == "192.168.23.54"
    assert req.ssh_port == 2222
    assert req.ssh_username == "root"
    assert req.ssh_password == "root"
    assert req.remote_rdb_path == "/data/redis/data/dump.rdb"
    assert req.remote_rdb_path_source == "user_override"
    assert req.require_fresh_rdb_snapshot is True


def test_cli_ask_uses_cli_approval_handler(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_handle_request(request, *, approval_handler):
        captured["handler_type"] = type(approval_handler).__name__
        return "done"

    monkeypatch.setattr(cli, "handle_request", fake_handle_request)

    cli.main(["ask", "test"])
    assert captured["handler_type"] == "CliApprovalHandler"


def test_cli_single_run_can_prompt_for_approval_when_orchestrator_requests_it(
    monkeypatch,
    capsys,
) -> None:
    from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets

    config = type("Config", (), {"runtime": type("Runtime", (), {"default_output_mode": "summary"})(), "model": None})()

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)
    monkeypatch.setattr(
        adapter_module,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): NormalizedRequest(
            raw_prompt=raw_prompt,
            prompt=raw_prompt,
            runtime_inputs=RuntimeInputs(output_mode="summary"),
            secrets=Secrets(),
            rdb_overrides=RdbOverrides(),
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler):
        response = approval_handler.request_approval(
            ApprovalRequest(
                action="fetch_remote_rdb_via_ssh",
                message="Runtime interrupt approval",
                details={"args": {"acquisition_mode": "existing"}},
            )
        )
        assert response.status is ApprovalStatus.APPROVED
        return "continued after approval"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    exit_code = cli.main(["ask", "analyze remote redis"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "[Approval Required]" in output
    assert "continued after approval" in output


def test_cli_ask_produces_execution_audit_record(monkeypatch, tmp_path, capsys) -> None:
    from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
    from dba_assistant.core.observability import get_current_execution_session, observe_tool_call, reset_observability_state
    from dba_assistant.deep_agent_integration.config import ObservabilityConfig

    observability = ObservabilityConfig(
        enabled=True,
        console_enabled=False,
        console_level="WARNING",
        file_level="INFO",
        log_dir=tmp_path / "logs",
        app_log_file="app.log.jsonl",
        audit_log_file="audit.jsonl",
    )
    config = SimpleNamespace(
        runtime=SimpleNamespace(default_output_mode="summary"),
        model=None,
        observability=observability,
    )

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)
    monkeypatch.setattr(
        adapter_module,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): NormalizedRequest(
            raw_prompt=raw_prompt,
            prompt=raw_prompt,
            runtime_inputs=RuntimeInputs(
                output_mode="report",
                report_format="docx",
                output_path=tmp_path / "outputs" / "audit-target.docx",
                input_paths=(Path("/tmp/sample.rdb"),),
                input_kind="local_rdb",
            ),
            secrets=Secrets(redis_password="super-secret"),
            rdb_overrides=RdbOverrides(profile_name="generic"),
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler):
        result = observe_tool_call(
            "analyze_local_rdb",
            {"redis_password": "super-secret", "input_paths": ["/tmp/sample.rdb"]},
            lambda: "report generated",
        )
        session = get_current_execution_session()
        assert session is not None
        session.record_artifact(
            output_mode="report",
            output_path=tmp_path / "outputs" / "audit-target.docx",
            artifact_id="artifact-cli-1",
            report_metadata={"route": "direct_rdb_analysis", "rows_processed": "10"},
        )
        return result

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    reset_observability_state()
    exit_code = cli.main(["ask", "analyze redis password=super-secret"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert output == "report generated\n"

    audit_path = observability.audit_log_path
    records = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    completion = [record for record in records if record["event_type"] == "execution_completed"]

    assert len(completion) == 1
    record = completion[0]
    assert record["interface_surface"] == "cli"
    assert record["final_status"] == "success"
    assert record["selected_capability"] == "analyze_local_rdb"
    assert record["tool_invocation_sequence"][0]["tool_name"] == "analyze_local_rdb"
    assert record["output_mode"] == "report"
    assert record["output_path"] == str(tmp_path / "outputs" / "audit-target.docx")
    assert record["report_metadata"]["route"] == "direct_rdb_analysis"
    assert "super-secret" not in json.dumps(records, ensure_ascii=False)


def test_cli_ask_does_not_flood_terminal_with_info_progress_logs(monkeypatch, tmp_path, capsys) -> None:
    import logging

    from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
    from dba_assistant.deep_agent_integration.config import ObservabilityConfig

    observability = ObservabilityConfig(
        enabled=True,
        console_enabled=True,
        console_level="WARNING",
        file_level="INFO",
        log_dir=tmp_path / "logs",
        app_log_file="app.log.jsonl",
        audit_log_file="audit.jsonl",
    )
    config = SimpleNamespace(
        runtime=SimpleNamespace(default_output_mode="summary"),
        model=None,
        observability=observability,
    )

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)
    monkeypatch.setattr(
        adapter_module,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): NormalizedRequest(
            raw_prompt=raw_prompt,
            prompt=raw_prompt,
            runtime_inputs=RuntimeInputs(output_mode="summary"),
            secrets=Secrets(),
            rdb_overrides=RdbOverrides(),
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler):
        logging.getLogger(
            "dba_assistant.capabilities.redis_rdb_analysis.collectors.streaming_aggregate_collector"
        ).info(
            "streaming aggregate progress",
            extra={"event_name": "redis_rdb_stream_progress", "rows_processed": 100000},
        )
        return "final summary"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    exit_code = cli.main(["ask", "analyze big rdbs"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "final summary\n"
    assert "streaming aggregate progress" not in captured.err
