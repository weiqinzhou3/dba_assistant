from __future__ import annotations

from collections import defaultdict

from dba_assistant.skills.redis_rdb_analysis.types import NormalizedRdbDataset


def analyze_key_types(dataset: NormalizedRdbDataset) -> dict[str, object]:
    counts: dict[str, int] = defaultdict(int)
    memory_bytes: dict[str, int] = defaultdict(int)

    for record in dataset.records:
        counts[record.key_type] += 1
        memory_bytes[record.key_type] += record.size_bytes

    rows = [
        [key_type, str(counts[key_type]), str(memory_bytes[key_type])]
        for key_type in sorted(counts, key=lambda key: (-counts[key], -memory_bytes[key], key))
    ]

    return {
        "summary": f"{len(dataset.records)} keys across {len(counts)} key types.",
        "counts": dict(counts),
        "memory_bytes": dict(memory_bytes),
        "columns": ["Key Type", "Count", "Bytes"],
        "rows": rows,
    }
