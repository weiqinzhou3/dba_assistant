from pathlib import Path
from types import SimpleNamespace

from dba_assistant.interface import adapter as adapter_module
from dba_assistant.interface.hitl import AutoApproveHandler
from dba_assistant.interface.types import InterfaceRequest


def test_handle_request_preserves_explicit_local_rdb_path_in_normalized_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        adapter_module,
        "load_app_config",
        lambda config_path=None: SimpleNamespace(
            runtime=SimpleNamespace(default_output_mode="summary", mysql_stage_batch_size=2000),
            model=None,
        ),
    )

    def fake_run_orchestrated(normalized, *, config, approval_handler, thread_id=None):
        captured["normalized"] = normalized
        return "host tool used for explicit path"

    monkeypatch.setattr(adapter_module, "run_orchestrated", fake_run_orchestrated)

    result, normalized = adapter_module.handle_request(
        InterfaceRequest(
            prompt=(
                "请帮我分析本地rdb文件，传入MySQL中分析。rdb文件在：/tmp/should-not-win.rdb，"
                "MySQL信息如下：192.168.23.176:3306，用户名root，密码Root@1234!，"
                "使用数据库rcs，表名叫rdb吧。"
            ),
            input_paths=[source],
        ),
        approval_handler=AutoApproveHandler(),
    )

    assert result == "host tool used for explicit path"
    assert normalized.runtime_inputs.input_paths == (source,)
    assert captured["normalized"].runtime_inputs.input_paths == (source,)
