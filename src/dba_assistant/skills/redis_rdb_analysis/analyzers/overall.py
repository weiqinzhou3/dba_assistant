from __future__ import annotations

from dba_assistant.skills.redis_rdb_analysis.analyzers.big_keys import analyze_big_keys
from dba_assistant.skills.redis_rdb_analysis.analyzers.expiration import analyze_expiration
from dba_assistant.skills.redis_rdb_analysis.analyzers.key_types import analyze_key_types
from dba_assistant.skills.redis_rdb_analysis.analyzers.prefixes import analyze_prefixes
from dba_assistant.skills.redis_rdb_analysis.analyzers.rcs_custom import analyze_rcs_custom
from dba_assistant.skills.redis_rdb_analysis.types import EffectiveProfile, NormalizedRdbDataset


def analyze_overall(
    dataset: NormalizedRdbDataset,
    *,
    profile: EffectiveProfile | None = None,
) -> dict[str, dict[str, object]]:
    profile = profile or EffectiveProfile(name="generic", sections=("overall_summary",))

    total_keys = len(dataset.records)
    total_bytes = sum(record.size_bytes for record in dataset.records)
    total_samples = len(dataset.samples)

    key_types = analyze_key_types(dataset)
    expiration = analyze_expiration(dataset)
    prefixes = analyze_prefixes(dataset, focus_prefixes=profile.focus_prefixes, top_n=profile.top_n.get("prefix_top", 20))
    big_keys = analyze_big_keys(dataset, top_n=profile.top_n)

    sample_rows = [
        [
            sample.label or f"sample-{index}",
            sample.kind.value,
            str(sample.source),
        ]
        for index, sample in enumerate(dataset.samples, start=1)
    ]

    overall_summary = {
        "summary": f"{total_samples} samples, {total_keys} keys, {total_bytes} bytes.",
        "columns": ["Metric", "Value"],
        "rows": [
            ["samples", str(total_samples)],
            ["keys", str(total_keys)],
            ["bytes", str(total_bytes)],
        ],
    }

    sections: dict[str, dict[str, object]] = {
        "executive_summary": overall_summary,
        "background": {
            "summary": "Deterministic Phase 3 RDB analysis over normalized datasets.",
            "columns": ["Metric", "Value"],
            "rows": [
                ["profile", profile.name],
                ["focus prefixes", str(len(profile.focus_prefixes))],
            ],
        },
        "analysis_results": overall_summary,
        "sample_overview": {
            "summary": "Input samples included in the analysis.",
            "columns": ["Sample", "Kind", "Source"],
            "rows": sample_rows,
        },
        "overall_summary": overall_summary,
        "key_type_summary": key_types,
        "key_type_memory_breakdown": {
            "summary": "Memory grouped by key type.",
            "columns": ["Key Type", "Bytes"],
            "rows": [
                [key_type, str(key_types["memory_bytes"][key_type])]
                for key_type in sorted(key_types["memory_bytes"], key=lambda key: (-key_types["memory_bytes"][key], key))
            ],
        },
        "expiration_summary": expiration,
        "non_expiration_summary": {
            "summary": f"{expiration['persistent_count']} keys do not expire.",
            "columns": ["Bucket", "Count"],
            "rows": [["without expiration", str(expiration["persistent_count"])]],
        },
        "prefix_top_summary": prefixes["prefix_top_summary"],
        "prefix_expiration_breakdown": prefixes["prefix_expiration_breakdown"],
        "top_big_keys": big_keys["top_big_keys"],
        "top_keys_by_type": big_keys["top_keys_by_type"],
        "conclusions": {
            "summary": "No additional deterministic concerns were found by the generic analyzers.",
        },
    }

    if profile.name.lower() == "rcs":
        sections.update(analyze_rcs_custom(dataset))

    return sections
