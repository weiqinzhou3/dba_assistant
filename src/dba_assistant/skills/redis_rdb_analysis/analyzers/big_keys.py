from __future__ import annotations

from collections import defaultdict

from dba_assistant.skills.redis_rdb_analysis.types import NormalizedRdbDataset


def analyze_big_keys(
    dataset: NormalizedRdbDataset,
    *,
    top_n: int | dict[str, int] = 20,
) -> dict[str, dict[str, object]]:
    top_n_map = _normalize_top_n(top_n)
    ordered_records = sorted(dataset.records, key=lambda record: (-record.size_bytes, record.key_name))

    sections: dict[str, dict[str, object]] = {
        "top_big_keys": {
            "summary": "Largest keys in the dataset.",
            "columns": ["Key", "Type", "Bytes"],
            "rows": [
                [record.key_name, record.key_type, str(record.size_bytes)]
                for record in ordered_records[: top_n_map["top_big_keys"]]
            ],
        },
        "top_keys_by_type": {
            "summary": "Largest keys grouped by type.",
            "columns": ["Type", "Key", "Bytes"],
            "rows": [
                [record.key_type, record.key_name, str(record.size_bytes)]
                for record in sorted(dataset.records, key=lambda record: (record.key_type, -record.size_bytes, record.key_name))
            ],
        },
    }

    for key_type, section_name in (("hash", "top_hash_keys"), ("list", "top_list_keys"), ("set", "top_set_keys")):
        type_records = [record for record in ordered_records if record.key_type == key_type]
        limit = top_n_map[f"{key_type}_big_keys"]
        sections[section_name] = {
            "summary": f"Largest {key_type} keys.",
            "columns": ["Key", "Bytes"],
            "rows": [[record.key_name, str(record.size_bytes)] for record in type_records[:limit]],
        }

    return sections


def _normalize_top_n(top_n: int | dict[str, int]) -> dict[str, int]:
    if isinstance(top_n, int):
        return {
            "top_big_keys": top_n,
            "hash_big_keys": top_n,
            "list_big_keys": top_n,
            "set_big_keys": top_n,
        }

    return {
        "top_big_keys": int(top_n.get("top_big_keys", 20)),
        "hash_big_keys": int(top_n.get("hash_big_keys", 10)),
        "list_big_keys": int(top_n.get("list_big_keys", 10)),
        "set_big_keys": int(top_n.get("set_big_keys", 10)),
    }
