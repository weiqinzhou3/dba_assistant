from pathlib import Path

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
