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
