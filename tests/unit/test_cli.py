from pathlib import Path
from types import SimpleNamespace

from dba_assistant import cli


def test_cli_ask_loads_config_normalizes_request_and_prints_result(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"))

    monkeypatch.setattr(cli, "load_app_config", lambda config_path=None: config)
    monkeypatch.setattr(
        cli,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): captured.update(
            {
                "raw_prompt": raw_prompt,
                "default_output_mode": default_output_mode,
                "input_paths": input_paths,
            }
        )
        or "REQUEST",
    )
    monkeypatch.setattr(cli, "execute_request", lambda request, *, config: "phase2 ok")

    exit_code = cli.main(["ask", "Use password abc123 to inspect Redis 10.0.0.8:6379 and give me a summary"])

    assert exit_code == 0
    assert captured["input_paths"] == []
    captured = capsys.readouterr()
    assert captured.out == "phase2 ok\n"


def test_cli_ask_threads_input_paths_to_request_normalizer(monkeypatch, tmp_path: Path, capsys) -> None:
    captured: dict[str, object] = {}
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"))
    source_a = tmp_path / "a.rdb"
    source_b = tmp_path / "b.rdb"
    source_a.write_text("a", encoding="utf-8")
    source_b.write_text("b", encoding="utf-8")

    monkeypatch.setattr(cli, "load_app_config", lambda config_path=None: config)

    def fake_normalize_raw_request(raw_prompt, *, default_output_mode, input_paths=()):
        captured["raw_prompt"] = raw_prompt
        captured["default_output_mode"] = default_output_mode
        captured["input_paths"] = input_paths
        return "REQUEST"

    monkeypatch.setattr(cli, "normalize_raw_request", fake_normalize_raw_request)
    monkeypatch.setattr(cli, "execute_request", lambda request, *, config: "phase3 ok")

    exit_code = cli.main(
        [
            "ask",
            "analyze this rdb",
            "--input",
            str(source_a),
            "--input",
            str(source_b),
        ]
    )

    assert exit_code == 0
    assert captured["input_paths"] == [source_a, source_b]
    assert capsys.readouterr().out == "phase3 ok\n"
