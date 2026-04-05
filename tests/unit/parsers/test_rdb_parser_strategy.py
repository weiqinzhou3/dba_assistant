from pathlib import Path

import pytest

from dba_assistant.parsers.rdb_parser_strategy import (
    HdtRdbCliStrategy,
    LegacyRdbtoolsStrategy,
)

HDT_BINARY = Path(".tools/bin/rdb")


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
