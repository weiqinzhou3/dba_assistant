from types import SimpleNamespace

from dba_assistant import cli


def test_cli_ask_loads_config_normalizes_request_and_prints_result(monkeypatch, capsys) -> None:
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"))

    monkeypatch.setattr(cli, "load_app_config", lambda config_path=None: config)
    monkeypatch.setattr(cli, "normalize_raw_request", lambda raw_prompt, default_output_mode: "REQUEST")
    monkeypatch.setattr(cli, "execute_request", lambda request, *, config: "phase2 ok")

    exit_code = cli.main(["ask", "Use password abc123 to inspect Redis 10.0.0.8:6379 and give me a summary"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == "phase2 ok\n"
