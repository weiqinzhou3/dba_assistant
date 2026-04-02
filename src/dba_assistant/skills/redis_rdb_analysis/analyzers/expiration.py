from __future__ import annotations

from dba_assistant.skills.redis_rdb_analysis.types import NormalizedRdbDataset


def analyze_expiration(dataset: NormalizedRdbDataset) -> dict[str, object]:
    expired_count = sum(1 for record in dataset.records if record.has_expiration)
    persistent_count = len(dataset.records) - expired_count

    return {
        "summary": f"{expired_count} keys expire and {persistent_count} keys persist.",
        "expired_count": expired_count,
        "persistent_count": persistent_count,
        "columns": ["Bucket", "Count"],
        "rows": [
            ["with expiration", str(expired_count)],
            ["without expiration", str(persistent_count)],
        ],
    }
