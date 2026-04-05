from pathlib import Path

from dba_assistant.capabilities.redis_rdb_analysis.collectors.path_b_precomputed_collector import (
    PathBPrecomputedCollector,
)
from dba_assistant.capabilities.redis_rdb_analysis.types import InputSourceKind


def test_path_b_collector_reads_precomputed_rows_and_normalizes_dataset() -> None:
    fixture_path = Path("tests/fixtures/rdb/precomputed/sample_precomputed_rows.json")
    dataset = PathBPrecomputedCollector().collect([fixture_path])

    assert [sample.kind for sample in dataset.samples] == [InputSourceKind.PRECOMPUTED]
    assert [sample.source for sample in dataset.samples] == [fixture_path]
    assert [sample.label for sample in dataset.samples] == [fixture_path.stem]
    assert [record.sample_id for record in dataset.records] == ["sample-1", "sample-1"]
    assert [record.prefix_segments for record in dataset.records] == [("loan",), ("loan", "active")]
    assert [record.key_type for record in dataset.records] == ["hash", "string"]
    assert [record.size_bytes for record in dataset.records] == [128, 64]
