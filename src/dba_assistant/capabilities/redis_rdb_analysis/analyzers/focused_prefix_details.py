from __future__ import annotations

from collections import Counter

from dba_assistant.capabilities.redis_rdb_analysis.types import NormalizedRdbDataset


def analyze_focused_prefix_details(
    dataset: NormalizedRdbDataset,
    *,
    focus_prefixes: tuple[str, ...],
    top_n: int,
) -> dict[str, object]:
    sections: list[dict[str, object]] = []
    for prefix in focus_prefixes:
        matched_records = [
            record
            for record in dataset.records
            if _matches_prefix(record.key_name, prefix)
        ]
        matched_records.sort(key=lambda record: (-record.size_bytes, record.key_name))
        type_counter = Counter(record.key_type for record in matched_records)
        with_expiration = sum(1 for record in matched_records if record.has_expiration)
        without_expiration = len(matched_records) - with_expiration
        total_size_bytes = sum(record.size_bytes for record in matched_records)

        if matched_records:
            summary_text = (
                f"前缀 {prefix} 共匹配 {len(matched_records)} 个键，累计内存占用 {total_size_bytes} 字节。"
            )
        else:
            summary_text = f"前缀 {prefix} 未匹配到符合条件的键。"

        sections.append(
            {
                "prefix": prefix,
                "matched_key_count": len(matched_records),
                "total_size_bytes": total_size_bytes,
                "key_type_breakdown": dict(type_counter),
                "top_keys": [
                    [record.key_name, record.key_type, str(record.size_bytes)]
                    for record in matched_records[:top_n]
                ],
                "expiration_stats": {
                    "with_expiration": with_expiration,
                    "without_expiration": without_expiration,
                },
                "summary_text": summary_text,
                "limit": top_n,
            }
        )

    return {"sections": sections}


def _matches_prefix(key_name: str, prefix: str) -> bool:
    if prefix.endswith("*"):
        return key_name.startswith(prefix[:-1])
    return key_name == prefix
