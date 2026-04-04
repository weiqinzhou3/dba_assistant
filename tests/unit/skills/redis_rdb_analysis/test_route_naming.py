"""Tests for Phase 3.1 route naming migration (WI-1)."""
from dba_assistant.skills.redis_rdb_analysis.types import (
    DATABASE_BACKED_ANALYSIS,
    DIRECT_MEMORY_ANALYSIS_ROUTE_NAME,
    DIRECT_RDB_ANALYSIS,
    LEGACY_SQL_PIPELINE_ROUTE_NAME,
    PRECOMPUTED_DATASET_ROUTE_NAME,
    PREPARSED_DATASET_ANALYSIS,
    normalize_route_name,
    phase_label_for_route_name,
)


def test_canonical_constants_have_new_values() -> None:
    assert DATABASE_BACKED_ANALYSIS == "database_backed_analysis"
    assert PREPARSED_DATASET_ANALYSIS == "preparsed_dataset_analysis"
    assert DIRECT_RDB_ANALYSIS == "direct_rdb_analysis"


def test_legacy_aliases_point_to_canonical() -> None:
    assert LEGACY_SQL_PIPELINE_ROUTE_NAME == DATABASE_BACKED_ANALYSIS
    assert PRECOMPUTED_DATASET_ROUTE_NAME == PREPARSED_DATASET_ANALYSIS
    assert DIRECT_MEMORY_ANALYSIS_ROUTE_NAME == DIRECT_RDB_ANALYSIS


def test_normalize_route_name_maps_phase_labels() -> None:
    assert normalize_route_name("3a") == DATABASE_BACKED_ANALYSIS
    assert normalize_route_name("3b") == PREPARSED_DATASET_ANALYSIS
    assert normalize_route_name("3c") == DIRECT_RDB_ANALYSIS


def test_normalize_route_name_maps_old_names() -> None:
    assert normalize_route_name("legacy_sql_pipeline") == DATABASE_BACKED_ANALYSIS
    assert normalize_route_name("precomputed_dataset") == PREPARSED_DATASET_ANALYSIS
    assert normalize_route_name("direct_memory_analysis") == DIRECT_RDB_ANALYSIS


def test_normalize_route_name_passes_through_new_names() -> None:
    assert normalize_route_name("database_backed_analysis") == DATABASE_BACKED_ANALYSIS
    assert normalize_route_name("preparsed_dataset_analysis") == PREPARSED_DATASET_ANALYSIS
    assert normalize_route_name("direct_rdb_analysis") == DIRECT_RDB_ANALYSIS


def test_normalize_route_name_passes_through_unknown() -> None:
    assert normalize_route_name("auto") == "auto"
    assert normalize_route_name("unknown_thing") == "unknown_thing"


def test_phase_label_for_canonical_names() -> None:
    assert phase_label_for_route_name(DATABASE_BACKED_ANALYSIS) == "3a"
    assert phase_label_for_route_name(PREPARSED_DATASET_ANALYSIS) == "3b"
    assert phase_label_for_route_name(DIRECT_RDB_ANALYSIS) == "3c"


def test_phase_label_for_old_names_via_normalization() -> None:
    assert phase_label_for_route_name("legacy_sql_pipeline") == "3a"
    assert phase_label_for_route_name("precomputed_dataset") == "3b"
    assert phase_label_for_route_name("direct_memory_analysis") == "3c"


def test_phase_label_for_unknown_returns_none() -> None:
    assert phase_label_for_route_name("auto") is None
    assert phase_label_for_route_name("nonexistent") is None
