from pathlib import Path

import pytest

from dba_assistant import cli


def test_cli_ask_delegates_initial_turn_to_interface_adapter(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_handle_request(request, *, approval_handler, thread_id=None):
        captured["request"] = request
        captured["approval_handler"] = approval_handler
        captured["thread_id"] = thread_id
        return "agent ok", type("Normalized", (), {"runtime_inputs": type("RI", (), {"input_paths": (), "mysql_host": None, "mysql_port": None, "mysql_user": None, "mysql_database": None, "mysql_table": None})()})()

    monkeypatch.setattr(cli, "handle_request", fake_handle_request)
    monkeypatch.setattr("builtins.input", lambda prompt="": "exit")

    exit_code = cli.main(["ask", "analyze the rdb"])

    assert exit_code == 0
    assert "agent ok" in capsys.readouterr().out
    req = captured["request"]
    assert req.prompt == "analyze the rdb"
    assert req.input_paths == []
    assert req.output_path is None
    assert req.profile is None
    assert captured["thread_id"].startswith("cli-session-")


def test_cli_ask_streaming_prints_tool_events_and_final_result(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_handle_request(request, *, approval_handler, thread_id=None, event_handler=None):
        captured["event_handler"] = event_handler
        assert event_handler is not None
        event_handler({"type": "tool_start", "tool_name": "redis_info"})
        event_handler({"type": "tool_end", "tool_name": "redis_info"})
        normalized = type(
            "Normalized",
            (),
            {"runtime_inputs": type("RI", (), {"input_paths": (), "mysql_host": None, "mysql_port": None, "mysql_user": None, "mysql_database": None, "mysql_table": None})()},
        )()
        return "streamed final result", normalized

    monkeypatch.setattr(cli, "handle_request", fake_handle_request)
    monkeypatch.setattr("builtins.input", lambda prompt="": "exit")

    exit_code = cli.main(["ask", "inspect redis", "--stream"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "[tool:start] redis_info" in output
    assert "[tool:end] redis_info" in output
    assert "streamed final result" in output
    assert captured["event_handler"] is not None


def test_cli_ask_threads_all_flags_to_interface_request(monkeypatch, tmp_path, capsys) -> None:
    captured: dict[str, object] = {}
    source = tmp_path / "dump.rdb"
    source.write_text("x", encoding="utf-8")

    def fake_handle_request(request, *, approval_handler, thread_id=None):
        captured.setdefault("requests", []).append(request)
        normalized = type(
            "Normalized",
            (),
            {
                "runtime_inputs": type(
                    "RI",
                    (),
                    {
                        "input_paths": tuple(request.input_paths),
                        "mysql_host": request.mysql_host,
                        "mysql_port": request.mysql_port,
                        "mysql_user": request.mysql_user,
                        "mysql_database": request.mysql_database,
                        "mysql_table": request.mysql_table,
                    },
                )(),
            },
        )()
        return "ok", normalized

    monkeypatch.setattr(cli, "handle_request", fake_handle_request)
    monkeypatch.setattr("builtins.input", lambda prompt="": "exit")

    exit_code = cli.main(
        [
            "ask",
            "analyze rdb",
            "--input",
            str(source),
            "--output",
            "/tmp/out.docx",
            "--config",
            "/etc/custom.yaml",
            "--profile",
            "rcs",
            "--report-format",
            "docx",
            "--mysql-host",
            "db.example",
            "--mysql-port",
            "3307",
            "--mysql-user",
            "analyst",
            "--mysql-database",
            "analysis_db",
            "--mysql-password",
            "secret",
            "--mysql-table",
            "preparsed_keys",
            "--mysql-query",
            "SELECT * FROM preparsed_keys",
            "--mysql-stage-batch-size",
            "4096",
        ]
    )

    assert exit_code == 0
    req = captured["requests"][0]
    assert req.prompt == "analyze rdb"
    assert req.input_paths == [source]
    assert req.output_path == Path("/tmp/out.docx")
    assert req.config_path == "/etc/custom.yaml"
    assert req.profile == "rcs"
    assert req.report_format == "docx"
    assert req.mysql_host == "db.example"
    assert req.mysql_port == 3307
    assert req.mysql_user == "analyst"
    assert req.mysql_database == "analysis_db"
    assert req.mysql_password == "secret"
    assert req.mysql_table == "preparsed_keys"
    assert req.mysql_query == "SELECT * FROM preparsed_keys"
    assert req.mysql_stage_batch_size == 4096


def test_cli_ask_rejects_non_positive_mysql_stage_batch_size() -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["ask", "analyze rdb via mysql", "--mysql-stage-batch-size", "0"])

    assert exc_info.value.code == 2


def test_cli_ask_threads_remote_redis_flags_to_interface_request(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_handle_request(request, *, approval_handler, thread_id=None):
        captured["request"] = request
        normalized = type(
            "Normalized",
            (),
            {"runtime_inputs": type("RI", (), {"input_paths": (), "mysql_host": None, "mysql_port": None, "mysql_user": None, "mysql_database": None, "mysql_table": None})()},
        )()
        return "ok", normalized

    monkeypatch.setattr(cli, "handle_request", fake_handle_request)
    monkeypatch.setattr("builtins.input", lambda prompt="": "exit")

    exit_code = cli.main(
        [
            "ask",
            "analyze remote redis",
            "--redis-password",
            "123456",
            "--ssh-host",
            "192.168.23.54",
            "--ssh-port",
            "2222",
            "--ssh-username",
            "root",
            "--ssh-password",
            "root",
            "--remote-rdb-path",
            "/data/redis/data/dump.rdb",
            "--remote-rdb-path-source",
            "user_override",
            "--fresh-rdb",
        ]
    )

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


def test_cli_follow_up_turn_reuses_state_from_previous_normalized_request(monkeypatch, capsys) -> None:
    calls: list[object] = []
    prompts = iter(["继续分析", "exit"])

    def fake_handle_request(request, *, approval_handler, thread_id=None):
        calls.append(request)
        normalized = type(
            "Normalized",
            (),
            {
                "runtime_inputs": type(
                    "RI",
                    (),
                    {
                        "input_paths": (Path("/tmp/dump.rdb"),),
                        "mysql_host": "db.example",
                        "mysql_port": 3307,
                        "mysql_user": "analyst",
                        "mysql_database": "analysis_db",
                        "mysql_table": "preparsed_keys",
                    },
                )(),
            },
        )()
        return f"handled: {request.prompt}", normalized

    monkeypatch.setattr(cli, "handle_request", fake_handle_request)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(prompts))

    exit_code = cli.main(["ask", "第一轮"])

    assert exit_code == 0
    assert len(calls) == 2
    follow_up = calls[1]
    assert follow_up.prompt == "继续分析"
    assert follow_up.input_paths == [Path("/tmp/dump.rdb")]
    assert follow_up.mysql_host == "db.example"
    assert follow_up.mysql_port == 3307
    assert follow_up.mysql_user == "analyst"
    assert follow_up.mysql_database == "analysis_db"
    assert follow_up.mysql_table == "preparsed_keys"
