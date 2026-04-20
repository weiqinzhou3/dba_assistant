from pathlib import Path
import threading

import pytest

from dba_assistant.parsers.rdb_parser_strategy import (
    HdtRdbCliStrategy,
    LegacyRdbtoolsStrategy,
    _resolve_hdt_rdb_binary,
    build_default_rdb_parser_strategy,
)

HDT_BINARY = Path(".tools/bin/rdb")


@pytest.mark.skipif(not HDT_BINARY.exists(), reason="HDT3213/rdb binary is not available in this workspace")
def test_default_strategy_discovers_repo_local_hdt_binary() -> None:
    build_default_rdb_parser_strategy.cache_clear()

    resolved = _resolve_hdt_rdb_binary()

    assert resolved == HDT_BINARY.resolve()


@pytest.mark.skipif(not HDT_BINARY.exists(), reason="HDT3213/rdb binary is not available in this workspace")
def test_hdt_rdb_cli_strategy_parses_v12_hash_with_hfe_fixture() -> None:
    strategy = HdtRdbCliStrategy(binary_path=HDT_BINARY)

    rows = strategy.parse_rows(Path("tests/fixtures/rdb/high_version/redis_v12_hash_with_hfe.rdb"))

    assert rows == [
        {
            "key_name": "hash-hfe",
            "key_type": "hash",
            "size_bytes": 660,
            "has_expiration": False,
            "ttl_seconds": None,
        }
    ]


@pytest.mark.skipif(not HDT_BINARY.exists(), reason="HDT3213/rdb binary is not available in this workspace")
def test_hdt_rdb_cli_strategy_accepts_v11_fixture_without_invalid_version_error() -> None:
    strategy = HdtRdbCliStrategy(binary_path=HDT_BINARY)

    rows = strategy.parse_rows(Path("tests/fixtures/rdb/high_version/redis_v11_function.rdb"))

    assert rows == []


@pytest.mark.skipif(not HDT_BINARY.exists(), reason="HDT3213/rdb binary is not available in this workspace")
def test_hdt_rdb_cli_strategy_exposes_bigkey_and_prefix_reports() -> None:
    strategy = HdtRdbCliStrategy(binary_path=HDT_BINARY)
    source = Path("tests/fixtures/rdb/high_version/hdt_memory.rdb")

    biggest = strategy.find_biggest_keys(source, limit=3)
    prefixes = strategy.analyze_prefixes(source, limit=3, max_depth=2)

    assert biggest[0]["key_name"] == "large"
    assert biggest[0]["size_bytes"] > biggest[1]["size_bytes"]
    assert prefixes[0]["prefix"] == "l"
    assert prefixes[0]["key_count"] >= 1


def test_legacy_rdbtools_strategy_still_fails_on_v11_fixture() -> None:
    strategy = LegacyRdbtoolsStrategy()

    try:
        strategy.parse_rows(Path("tests/fixtures/rdb/high_version/redis_v11_function.rdb"))
    except Exception as exc:  # noqa: BLE001
        assert "Invalid RDB version number 11" in str(exc)
    else:
        raise AssertionError("legacy rdbtools parser unexpectedly handled RDB v11")


def test_default_strategy_can_be_forced_to_legacy_parser(monkeypatch) -> None:
    import dba_assistant.parsers.rdb_parser_strategy as module

    class FakeHdt:
        pass

    class FakeLegacy:
        pass

    monkeypatch.setattr(module, "HdtRdbCliStrategy", FakeHdt)
    monkeypatch.setattr(module, "LegacyRdbtoolsStrategy", FakeLegacy)
    monkeypatch.setenv("DBA_ASSISTANT_RDB_PARSER", "legacy")
    module.build_default_rdb_parser_strategy.cache_clear()

    strategy = module.build_default_rdb_parser_strategy()

    assert [type(item).__name__ for item in strategy._strategies] == ["FakeLegacy"]


def test_default_strategy_still_prefers_hdt_when_not_forced(monkeypatch) -> None:
    import dba_assistant.parsers.rdb_parser_strategy as module

    class FakeHdt:
        pass

    class FakeLegacy:
        pass

    monkeypatch.setattr(module, "HdtRdbCliStrategy", FakeHdt)
    monkeypatch.setattr(module, "LegacyRdbtoolsStrategy", FakeLegacy)
    monkeypatch.delenv("DBA_ASSISTANT_RDB_PARSER", raising=False)
    module.build_default_rdb_parser_strategy.cache_clear()

    strategy = module.build_default_rdb_parser_strategy()

    assert [type(item).__name__ for item in strategy._strategies] == ["FakeHdt", "FakeLegacy"]


def test_hdt_rdb_cli_strategy_logs_fifo_shutdown_path(monkeypatch, tmp_path: Path, caplog) -> None:
    import dba_assistant.parsers.rdb_parser_strategy as module

    source = tmp_path / "dump.rdb"
    source.write_bytes(b"fixture")
    fake_binary = tmp_path / "rdb"
    fake_binary.write_text("#!/bin/sh\n", encoding="utf-8")
    processes: list[object] = []

    class FakeProcess:
        pid = 12345

        def __init__(self, cmd, stdout=None, stderr=None):
            self.cmd = cmd
            self.returncode = None
            self.terminated = False
            self.output_path = Path(cmd[cmd.index("-o") + 1])
            self.thread = threading.Thread(target=self._write_json)
            self.thread.start()
            processes.append(self)

        def _write_json(self):
            with self.output_path.open("w", encoding="utf-8") as handle:
                handle.write('[{"key":"cache:1","type":"string","size":10}]')
            self.returncode = 0

        def wait(self):
            self.thread.join(timeout=2.0)
            return self.returncode

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = -15

    monkeypatch.setattr(module.subprocess, "Popen", FakeProcess)
    caplog.set_level("INFO", logger="dba_assistant.parsers.rdb_parser_strategy")

    rows = list(HdtRdbCliStrategy(binary_path=fake_binary).export_json(source))

    assert rows == [{"key": "cache:1", "type": "string", "size": 10}]
    event_names = [record.event_name for record in caplog.records if hasattr(record, "event_name")]
    assert "hdt_rdb_cli_start" in event_names
    assert "hdt_rdb_fifo_opened" in event_names
    assert "hdt_rdb_fifo_read_status" in event_names
    assert "hdt_rdb_fifo_eof" in event_names or "hdt_rdb_fifo_closed_before_eof" in event_names
    assert "hdt_rdb_finally_enter" in event_names
    assert "hdt_rdb_writer_join_end" in event_names
    assert "hdt_rdb_cli_exit" in event_names


def test_hdt_rdb_cli_strategy_times_out_idle_fifo_without_hanging(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    import dba_assistant.parsers.rdb_parser_strategy as module

    source = tmp_path / "dump.rdb"
    source.write_bytes(b"fixture")
    fake_binary = tmp_path / "rdb"
    fake_binary.write_text("#!/bin/sh\n", encoding="utf-8")
    processes: list[object] = []

    class IdleProcess:
        pid = 67890

        def __init__(self, cmd, stdout=None, stderr=None):
            self.returncode = None
            self.terminated = False
            processes.append(self)

        def wait(self):
            while self.returncode is None:
                threading.Event().wait(0.001)
            return self.returncode

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = -15

    monkeypatch.setattr(module.subprocess, "Popen", IdleProcess)
    caplog.set_level("INFO", logger="dba_assistant.parsers.rdb_parser_strategy")

    with pytest.raises(TimeoutError, match="HDT RDB JSON stream idle"):
        list(
            HdtRdbCliStrategy(
                binary_path=fake_binary,
                fifo_idle_timeout_seconds=0.01,
            ).export_json(source)
        )

    assert processes and processes[0].terminated
    event_names = [record.event_name for record in caplog.records if hasattr(record, "event_name")]
    assert "hdt_rdb_fifo_idle_timeout" in event_names
    assert "hdt_rdb_process_terminate" in event_names
