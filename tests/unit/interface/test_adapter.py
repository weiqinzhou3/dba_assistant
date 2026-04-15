from pathlib import Path
from types import SimpleNamespace

from dba_assistant.application.request_models import NormalizedRequest, RdbOverrides, RuntimeInputs, Secrets
from dba_assistant.interface import adapter as adapter_module
from dba_assistant.interface.adapter import handle_request
from dba_assistant.interface.hitl import AuditedApprovalHandler, AutoApproveHandler
from dba_assistant.interface.types import InterfaceRequest


def _base_config(*, mysql_stage_batch_size: int = 2000):
    return SimpleNamespace(
        runtime=SimpleNamespace(
            default_output_mode="summary",
            mysql_stage_batch_size=mysql_stage_batch_size,
        ),
        agent=SimpleNamespace(
            filesystem_backend=SimpleNamespace(
                root_dir=Path("/configured-agent-root"),
            )
        ),
        paths=SimpleNamespace(
            artifact_dir=Path("/configured-agent-root/artifacts"),
            evidence_dir=Path("/configured-agent-root/evidence"),
            temp_dir=Path("/configured-agent-root/tmp"),
        ),
        model=None,
    )


def _base_normalized(*, input_paths=()) -> NormalizedRequest:
    return NormalizedRequest(
        raw_prompt="test",
        prompt="test",
        runtime_inputs=RuntimeInputs(output_mode="summary", input_paths=tuple(input_paths)),
        secrets=Secrets(),
        rdb_overrides=RdbOverrides(),
    )


def test_handle_request_normalizes_and_delegates_to_orchestrator(monkeypatch) -> None:
    captured: dict[str, object] = {}
    config = _base_config()

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)
    monkeypatch.setattr(
        adapter_module,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): _base_normalized(
            input_paths=input_paths,
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler, thread_id=None):
        captured["normalized"] = normalized
        captured["handler"] = approval_handler
        return "orchestrated result"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    handler = AutoApproveHandler()
    result, normalized = handle_request(
        InterfaceRequest(prompt="analyze rdb", input_paths=[Path("/tmp/dump.rdb")]),
        approval_handler=handler,
    )

    assert result == "orchestrated result"
    assert normalized.runtime_inputs.input_paths == (Path("/tmp/dump.rdb"),)
    assert normalized.runtime_inputs.filesystem_root_dir == Path("/configured-agent-root")
    assert normalized.runtime_inputs.artifact_dir == Path("/configured-agent-root/artifacts")
    assert normalized.runtime_inputs.evidence_dir == Path("/configured-agent-root/evidence")
    assert normalized.runtime_inputs.temp_dir == Path("/configured-agent-root/tmp")
    assert isinstance(captured["handler"], AuditedApprovalHandler)
    assert captured["handler"]._delegate is handler


def test_handle_request_applies_profile_and_report_overrides(monkeypatch) -> None:
    captured: dict[str, object] = {}
    config = _base_config()

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)
    monkeypatch.setattr(
        adapter_module,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): _base_normalized(
            input_paths=input_paths,
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler, thread_id=None):
        captured["normalized"] = normalized
        return "ok"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    _, normalized = handle_request(
        InterfaceRequest(
            prompt="test",
            profile="rcs",
            report_format="docx",
            output_path=Path("/tmp/out.docx"),
        ),
        approval_handler=AutoApproveHandler(),
    )

    assert normalized.rdb_overrides.profile_name == "rcs"
    assert normalized.runtime_inputs.output_mode == "report"
    assert normalized.runtime_inputs.report_format == "docx"
    assert normalized.runtime_inputs.output_path == Path("/tmp/out.docx")
    assert captured["normalized"] == normalized


def test_handle_request_applies_explicit_runtime_and_secret_overrides(monkeypatch) -> None:
    captured: dict[str, object] = {}
    config = _base_config()

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)
    monkeypatch.setattr(
        adapter_module,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): NormalizedRequest(
            raw_prompt=raw_prompt,
            prompt=raw_prompt,
            runtime_inputs=RuntimeInputs(
                output_mode="summary",
                redis_host="prompt-redis",
                ssh_host="prompt-ssh",
                mysql_host="prompt-db",
                input_paths=tuple(input_paths),
            ),
            secrets=Secrets(
                redis_password="prompt-redis-secret",
                ssh_password="prompt-ssh-secret",
                mysql_password="prompt-db-secret",
            ),
            rdb_overrides=RdbOverrides(),
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler, thread_id=None):
        captured["normalized"] = normalized
        return "ok"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    _, normalized = handle_request(
        InterfaceRequest(
            prompt="test",
            input_kind="preparsed_mysql",
            path_mode="preparsed_dataset_analysis",
            redis_password="cli-redis-secret",
            ssh_host="explicit-ssh",
            ssh_port=2222,
            ssh_username="root",
            ssh_password="cli-ssh-secret",
            remote_rdb_path="/explicit/dump.rdb",
            require_fresh_rdb_snapshot=True,
            mysql_host="explicit-db",
            mysql_port=3307,
            mysql_user="analyst",
            mysql_database="analysis_db",
            mysql_password="cli-db-secret",
            mysql_table="preparsed_keys",
            mysql_query="SELECT * FROM preparsed_keys",
            mysql_stage_batch_size=4096,
        ),
        approval_handler=AutoApproveHandler(),
    )

    assert normalized.runtime_inputs.input_kind == "preparsed_mysql"
    assert normalized.runtime_inputs.path_mode == "preparsed_dataset_analysis"
    assert normalized.runtime_inputs.ssh_host == "explicit-ssh"
    assert normalized.runtime_inputs.ssh_port == 2222
    assert normalized.runtime_inputs.ssh_username == "root"
    assert normalized.runtime_inputs.remote_rdb_path == "/explicit/dump.rdb"
    assert normalized.runtime_inputs.remote_rdb_path_source == "user_override"
    assert normalized.runtime_inputs.require_fresh_rdb_snapshot is True
    assert normalized.runtime_inputs.mysql_host == "explicit-db"
    assert normalized.runtime_inputs.mysql_port == 3307
    assert normalized.runtime_inputs.mysql_user == "analyst"
    assert normalized.runtime_inputs.mysql_database == "analysis_db"
    assert normalized.runtime_inputs.mysql_table == "preparsed_keys"
    assert normalized.runtime_inputs.mysql_query == "SELECT * FROM preparsed_keys"
    assert normalized.runtime_inputs.mysql_stage_batch_size == 4096
    assert normalized.secrets.redis_password == "cli-redis-secret"
    assert normalized.secrets.ssh_password == "cli-ssh-secret"
    assert normalized.secrets.mysql_password == "cli-db-secret"
    assert captured["normalized"] == normalized


def test_handle_request_uses_config_mysql_stage_batch_size_when_not_overridden(monkeypatch) -> None:
    captured: dict[str, object] = {}
    config = _base_config(mysql_stage_batch_size=3072)

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)
    monkeypatch.setattr(
        adapter_module,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): _base_normalized(
            input_paths=input_paths,
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler, thread_id=None):
        captured["normalized"] = normalized
        return "ok"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    _, normalized = handle_request(
        InterfaceRequest(prompt="test"),
        approval_handler=AutoApproveHandler(),
    )

    assert normalized.runtime_inputs.mysql_stage_batch_size == 3072
    assert captured["normalized"] == normalized


def test_handle_request_falls_back_to_default_mysql_stage_batch_size_when_config_is_sparse(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    config = SimpleNamespace(runtime=SimpleNamespace(default_output_mode="summary"), model=None)

    monkeypatch.setattr(adapter_module, "load_app_config", lambda config_path=None: config)
    monkeypatch.setattr(
        adapter_module,
        "normalize_raw_request",
        lambda raw_prompt, *, default_output_mode, input_paths=(): _base_normalized(
            input_paths=input_paths,
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler, thread_id=None):
        captured["normalized"] = normalized
        return "ok"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    _, normalized = handle_request(
        InterfaceRequest(prompt="test"),
        approval_handler=AutoApproveHandler(),
    )

    assert normalized.runtime_inputs.mysql_stage_batch_size == 2000
    assert captured["normalized"] == normalized


def test_handle_request_preserves_prompt_supplied_docx_output_path(monkeypatch) -> None:
    captured: dict[str, object] = {}
    config = _base_config()

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
                output_path=Path("/tmp/from-prompt.docx"),
            ),
            secrets=Secrets(),
            rdb_overrides=RdbOverrides(),
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler, thread_id=None):
        captured["normalized"] = normalized
        return "ok"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    _, normalized = handle_request(
        InterfaceRequest(prompt="输出 docx 到 /tmp/from-prompt.docx"),
        approval_handler=AutoApproveHandler(),
    )

    assert normalized.runtime_inputs.output_path == Path("/tmp/from-prompt.docx")
    assert captured["normalized"] == normalized
