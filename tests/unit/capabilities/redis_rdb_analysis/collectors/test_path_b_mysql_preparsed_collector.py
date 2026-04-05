from dba_assistant.capabilities.redis_rdb_analysis.collectors.path_b_mysql_preparsed_collector import (
    PathBMySQLPreparsedCollector,
    _coerce_bool,
    _coerce_optional_int,
    _coerce_required_int,
)
from dba_assistant.capabilities.redis_rdb_analysis.types import InputSourceKind, RdbAnalysisRequest, SampleInput


def test_path_b_collector_normalizes_stringly_mysql_rows() -> None:
    collector = PathBMySQLPreparsedCollector(
        load_preparsed_dataset_from_mysql=lambda _table_name: {
            "source": "mysql:rdb_staging",
            "rows": [
                {
                    "key_name": "cache:1",
                    "key_type": "string",
                    "size_bytes": "123",
                    "has_expiration": "False",
                    "ttl_seconds": "None",
                }
            ],
        }
    )
    request = RdbAnalysisRequest(
        prompt="analyze mysql dataset",
        inputs=[SampleInput(source="mysql:rdb_staging", kind=InputSourceKind.PREPARSED_MYSQL)],
        mysql_table="rdb_staging",
    )

    dataset = collector.collect(request)

    assert dataset.records[0].size_bytes == 123
    assert dataset.records[0].has_expiration is False
    assert dataset.records[0].ttl_seconds is None


def test_coerce_required_int_returns_int_for_numeric_string() -> None:
    assert _coerce_required_int("123", "size_bytes") == 123


def test_coerce_required_int_raises_clear_error_for_invalid_value() -> None:
    try:
        _coerce_required_int("None", "size_bytes")
    except ValueError as exc:
        assert str(exc) == "Invalid integer value for size_bytes: 'None'"
    else:
        raise AssertionError("Expected ValueError for invalid required integer")


def test_coerce_optional_int_returns_none_for_none() -> None:
    assert _coerce_optional_int(None) is None


def test_coerce_optional_int_returns_none_for_empty_string() -> None:
    assert _coerce_optional_int("") is None


def test_coerce_optional_int_returns_none_for_none_string() -> None:
    assert _coerce_optional_int("None") is None


def test_coerce_optional_int_returns_none_for_null_string() -> None:
    assert _coerce_optional_int("null") is None


def test_coerce_optional_int_returns_int_for_numeric_string() -> None:
    assert _coerce_optional_int("123") == 123


def test_coerce_bool_returns_false_for_none() -> None:
    assert _coerce_bool(None) is False


def test_coerce_bool_returns_false_for_false_string() -> None:
    assert _coerce_bool("False") is False


def test_coerce_bool_returns_false_for_zero_string() -> None:
    assert _coerce_bool("0") is False


def test_coerce_bool_returns_true_for_true_string() -> None:
    assert _coerce_bool("True") is True


def test_coerce_bool_returns_true_for_one_string() -> None:
    assert _coerce_bool("1") is True
