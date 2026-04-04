"""Tests for analyze_rdb_tool input_kind handling (WI-3)."""
from pathlib import Path

from dba_assistant.skills.redis_rdb_analysis.types import InputSourceKind
from dba_assistant.tools.analyze_rdb import analyze_rdb_tool


def test_analyze_rdb_tool_defaults_to_local_rdb(tmp_path: Path) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_service(request):
        captured["kind"] = request.inputs[0].kind
        return "ok"

    analyze_rdb_tool(
        prompt="analyze this",
        input_paths=[source],
        service=fake_service,
    )

    assert captured["kind"] is InputSourceKind.LOCAL_RDB


def test_analyze_rdb_tool_respects_precomputed_input_kind(tmp_path: Path) -> None:
    source = tmp_path / "data.json"
    source.write_text("[]", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_service(request):
        captured["kind"] = request.inputs[0].kind
        return "ok"

    analyze_rdb_tool(
        prompt="analyze this",
        input_paths=[source],
        input_kind="precomputed",
        service=fake_service,
    )

    assert captured["kind"] is InputSourceKind.PRECOMPUTED


def test_analyze_rdb_tool_respects_remote_redis_input_kind(tmp_path: Path) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_service(request):
        captured["kind"] = request.inputs[0].kind
        return "ok"

    analyze_rdb_tool(
        prompt="analyze this",
        input_paths=[source],
        input_kind="remote_redis",
        service=fake_service,
    )

    assert captured["kind"] is InputSourceKind.REMOTE_REDIS


def test_analyze_rdb_tool_unknown_input_kind_falls_back_to_local(tmp_path: Path) -> None:
    source = tmp_path / "dump.rdb"
    source.write_text("fixture", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_service(request):
        captured["kind"] = request.inputs[0].kind
        return "ok"

    analyze_rdb_tool(
        prompt="analyze this",
        input_paths=[source],
        input_kind="unknown_kind",
        service=fake_service,
    )

    assert captured["kind"] is InputSourceKind.LOCAL_RDB


def test_analyze_rdb_tool_respects_preparsed_mysql_input_kind() -> None:
    captured: dict[str, object] = {}

    def fake_service(request):
        captured["kind"] = request.inputs[0].kind
        captured["mysql_table"] = request.mysql_table
        captured["mysql_query"] = request.mysql_query
        return "ok"

    analyze_rdb_tool(
        prompt="analyze mysql dataset",
        input_paths=["mysql:preparsed_keys"],
        input_kind="preparsed_mysql",
        mysql_table="preparsed_keys",
        mysql_query="SELECT * FROM preparsed_keys",
        service=fake_service,
    )

    assert captured["kind"] is InputSourceKind.PREPARSED_MYSQL
    assert captured["mysql_table"] == "preparsed_keys"
    assert captured["mysql_query"] == "SELECT * FROM preparsed_keys"
