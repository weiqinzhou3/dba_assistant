from __future__ import annotations

from dba_assistant.capabilities.redis_rdb_analysis.types import NormalizedRdbDataset


def analyze_rcs_custom(dataset: NormalizedRdbDataset) -> dict[str, dict[str, object]]:
    loan_rows = [
        [record.key_name, record.key_type, str(record.size_bytes)]
        for record in sorted(
            (record for record in dataset.records if record.key_name.startswith("loan:")),
            key=lambda record: (-record.size_bytes, record.key_name),
        )
    ]

    return {
        "loan_prefix_detail": {
            "summary": "Loan-prefixed keys in descending size order.",
            "columns": ["Key", "Type", "Bytes"],
            "rows": loan_rows,
        }
    }
