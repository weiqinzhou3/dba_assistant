from pathlib import Path
from types import SimpleNamespace

from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
from dba_assistant.interface import adapter as adapter_module
from dba_assistant.interface.adapter import handle_request
from dba_assistant.interface.hitl import AutoApproveHandler
from dba_assistant.interface.types import InterfaceRequest


def test_handle_request_normalizes_and_delegates_to_orchestrator(monkeypatch) -> None:
    captured: dict[str, object] = {}
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"), model=None)

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)

    monkeypatch.setattr(
        adapter_module,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): NormalizedRequest(
            raw_prompt=raw_prompt,
            prompt=raw_prompt,
            runtime_inputs=RuntimeInputs(
                output_mode="summary",
                input_paths=tuple(input_paths),
            ),
            secrets=Secrets(),
            rdb_overrides=RdbOverrides(),
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler):
        captured["prompt"] = normalized.prompt
        captured["handler"] = approval_handler
        return "orchestrated result"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    handler = AutoApproveHandler()
    request = InterfaceRequest(prompt="analyze rdb", input_paths=[Path("/tmp/dump.rdb")])

    result = handle_request(request, approval_handler=handler)

    assert result == "orchestrated result"
    assert captured["prompt"] == "analyze rdb"
    assert captured["handler"] is handler


def test_handle_request_applies_overrides(monkeypatch) -> None:
    captured: dict[str, object] = {}
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"), model=None)

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)

    from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets

    monkeypatch.setattr(
        adapter_module,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): NormalizedRequest(
            raw_prompt=raw_prompt,
            prompt=raw_prompt,
            runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=tuple(input_paths)),
            secrets=Secrets(),
            rdb_overrides=RdbOverrides(),
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler):
        captured["normalized"] = normalized
        return "ok"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    request = InterfaceRequest(
        prompt="test",
        profile="rcs",
        report_format="docx",
        output_path=Path("/tmp/out.docx"),
    )
    handle_request(request, approval_handler=AutoApproveHandler())

    n = captured["normalized"]
    assert n.rdb_overrides.profile_name == "rcs"
    assert n.runtime_inputs.output_mode == "report"
    assert n.runtime_inputs.report_format == "docx"
    assert n.runtime_inputs.output_path == Path("/tmp/out.docx")


def test_handle_request_applies_mysql_overrides(monkeypatch) -> None:
    captured: dict[str, object] = {}
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"), model=None)

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)

    monkeypatch.setattr(
        adapter_module,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): NormalizedRequest(
            raw_prompt=raw_prompt,
            prompt=raw_prompt,
            runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=tuple(input_paths)),
            secrets=Secrets(),
            rdb_overrides=RdbOverrides(),
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler):
        captured["normalized"] = normalized
        return "ok"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    request = InterfaceRequest(
        prompt="test",
        mysql_host="db.example",
        mysql_port=3307,
        mysql_user="analyst",
        mysql_database="analysis_db",
        mysql_password="secret",
        mysql_table="preparsed_keys",
        mysql_query="SELECT * FROM preparsed_keys",
    )
    handle_request(request, approval_handler=AutoApproveHandler())

    n = captured["normalized"]
    assert n.runtime_inputs.mysql_host == "db.example"
    assert n.runtime_inputs.mysql_port == 3307
    assert n.runtime_inputs.mysql_user == "analyst"
    assert n.runtime_inputs.mysql_database == "analysis_db"
    assert n.runtime_inputs.mysql_table == "preparsed_keys"
    assert n.runtime_inputs.mysql_query == "SELECT * FROM preparsed_keys"
    assert n.secrets.mysql_password == "secret"


def test_handle_request_applies_ssh_overrides(monkeypatch) -> None:
    captured: dict[str, object] = {}
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"), model=None)

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)
    monkeypatch.setattr(
        adapter_module,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): NormalizedRequest(
            raw_prompt=raw_prompt,
            prompt=raw_prompt,
            runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=tuple(input_paths)),
            secrets=Secrets(),
            rdb_overrides=RdbOverrides(),
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler):
        captured["normalized"] = normalized
        return "ok"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    request = InterfaceRequest(
        prompt="test",
        ssh_host="ssh.example",
        ssh_port=2222,
        ssh_username="root",
        ssh_password="secret",
    )
    handle_request(request, approval_handler=AutoApproveHandler())

    n = captured["normalized"]
    assert n.runtime_inputs.ssh_host == "ssh.example"
    assert n.runtime_inputs.ssh_port == 2222
    assert n.runtime_inputs.ssh_username == "root"
    assert n.secrets.ssh_password == "secret"


def test_handle_request_marks_remote_rdb_path_override_as_user_override(monkeypatch) -> None:
    captured: dict[str, object] = {}
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"), model=None)

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)
    monkeypatch.setattr(
        adapter_module,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): NormalizedRequest(
            raw_prompt=raw_prompt,
            prompt=raw_prompt,
            runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=tuple(input_paths)),
            secrets=Secrets(),
            rdb_overrides=RdbOverrides(),
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler):
        captured["normalized"] = normalized
        return "ok"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    request = InterfaceRequest(
        prompt="test",
        remote_rdb_path="/custom/override.rdb",
        require_fresh_rdb_snapshot=True,
    )
    handle_request(request, approval_handler=AutoApproveHandler())

    n = captured["normalized"]
    assert n.runtime_inputs.remote_rdb_path == "/custom/override.rdb"
    assert n.runtime_inputs.remote_rdb_path_source == "user_override"
    assert n.runtime_inputs.require_fresh_rdb_snapshot is True


def test_handle_request_keeps_prompt_first_but_allows_explicit_overrides(monkeypatch) -> None:
    captured: dict[str, object] = {}
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"), model=None)

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)
    monkeypatch.setattr(
        adapter_module,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): NormalizedRequest(
            raw_prompt=raw_prompt,
            prompt=raw_prompt,
            runtime_inputs=RuntimeInputs(
                output_mode="summary",
                input_paths=(Path("/prompt/source.rdb"),),
                input_kind="local_rdb",
                mysql_host="prompt-db",
                mysql_port=3306,
                mysql_user="prompt-user",
                mysql_database="prompt-db-name",
                mysql_table="prompt_rows",
            ),
            secrets=Secrets(mysql_password="prompt-secret"),
            rdb_overrides=RdbOverrides(profile_name="generic"),
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler):
        captured["normalized"] = normalized
        return "ok"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    request = InterfaceRequest(
        prompt="analyze /prompt/source.rdb",
        input_paths=[Path("/explicit/source.rdb")],
        profile="rcs",
        input_kind="preparsed_mysql",
        mysql_host="explicit-db",
        mysql_port=3307,
        mysql_user="explicit-user",
        mysql_database="explicit-db-name",
        mysql_password="explicit-secret",
        mysql_query="SELECT 1",
    )
    handle_request(request, approval_handler=AutoApproveHandler())

    n = captured["normalized"]
    assert n.runtime_inputs.input_paths == (Path("/explicit/source.rdb"),)
    assert n.runtime_inputs.input_kind == "preparsed_mysql"
    assert n.runtime_inputs.mysql_host == "explicit-db"
    assert n.runtime_inputs.mysql_port == 3307
    assert n.runtime_inputs.mysql_user == "explicit-user"
    assert n.runtime_inputs.mysql_database == "explicit-db-name"
    assert n.runtime_inputs.mysql_table == "prompt_rows"
    assert n.runtime_inputs.mysql_query == "SELECT 1"
    assert n.secrets.mysql_password == "explicit-secret"
    assert n.rdb_overrides.profile_name == "rcs"
