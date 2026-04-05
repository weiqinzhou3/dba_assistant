from __future__ import annotations

from collections import defaultdict

from dba_assistant.capabilities.redis_rdb_analysis.types import NormalizedRdbDataset


def analyze_prefixes(
    dataset: NormalizedRdbDataset,
    *,
    focus_prefixes: tuple[str, ...] = (),
    top_n: int = 20,
) -> dict[str, dict[str, object]]:
    prefix_counts: dict[str, int] = defaultdict(int)
    prefix_bytes: dict[str, int] = defaultdict(int)
    prefix_expired: dict[str, int] = defaultdict(int)
    prefix_persistent: dict[str, int] = defaultdict(int)

    for record in dataset.records:
        prefix = _prefix_label(record.prefix_segments, record.key_name)
        prefix_counts[prefix] += 1
        prefix_bytes[prefix] += record.size_bytes
        if record.has_expiration:
            prefix_expired[prefix] += 1
        else:
            prefix_persistent[prefix] += 1

    ordered_prefixes = sorted(prefix_counts, key=lambda key: (-prefix_counts[key], -prefix_bytes[key], key))
    top_rows = [
        [prefix, str(prefix_counts[prefix]), str(prefix_bytes[prefix])]
        for prefix in ordered_prefixes[:top_n]
    ]

    focus_rows = []
    for focus_prefix in focus_prefixes:
        matched_prefix = _match_prefix_label(focus_prefix)
        expired_count = sum(count for prefix, count in prefix_expired.items() if prefix.startswith(matched_prefix))
        persistent_count = sum(
            count for prefix, count in prefix_persistent.items() if prefix.startswith(matched_prefix)
        )
        focus_rows.append(
            [
                focus_prefix,
                str(expired_count),
                str(persistent_count),
                str(expired_count + persistent_count),
            ]
        )

    return {
        "prefix_top_summary": {
            "summary": "Top prefixes by key count.",
            "columns": ["Prefix", "Count", "Bytes"],
            "rows": top_rows,
        },
        "prefix_expiration_breakdown": {
            "summary": "Expiration breakdown for focused prefixes.",
            "columns": ["Prefix", "Expired", "Persistent", "Total"],
            "rows": focus_rows,
        },
    }


def _prefix_label(prefix_segments: tuple[str, ...], key_name: str) -> str:
    if prefix_segments:
        return f"{prefix_segments[0]}:*"
    if ":" in key_name:
        return f"{key_name.split(':', 1)[0]}:*"
    return f"{key_name}:*"


def _match_prefix_label(prefix: str) -> str:
    return prefix[:-1] if prefix.endswith("*") else prefix
