from __future__ import annotations

from collections import defaultdict

from dba_assistant.capabilities.redis_rdb_analysis.types import NormalizedRdbDataset


def analyze_big_keys(
    dataset: NormalizedRdbDataset,
    *,
    top_n: int | dict[str, int] = 100,
) -> dict[str, dict[str, object]]:
    top_n_map = _normalize_top_n(top_n)
    ordered_records = sorted(dataset.records, key=lambda record: (-record.size_bytes, record.key_name))

    sections: dict[str, dict[str, object]] = {
        "top_big_keys": {
            "limit": top_n_map["top_big_keys"],
            "rows": [
                [record.key_name, record.key_type, str(record.size_bytes)]
                for record in ordered_records[: top_n_map["top_big_keys"]]
            ],
        },
    }

    for key_type, section_name, limit_key in (
        ("string", "top_string_keys", "string_big_keys"),
        ("hash", "top_hash_keys", "hash_big_keys"),
        ("list", "top_list_keys", "list_big_keys"),
        ("set", "top_set_keys", "set_big_keys"),
        ("zset", "top_zset_keys", "zset_big_keys"),
        ("stream", "top_stream_keys", "stream_big_keys"),
    ):
        type_records = [record for record in ordered_records if record.key_type == key_type]
        limit = top_n_map[limit_key]
        sections[section_name] = {
            "limit": limit,
            "rows": [[record.key_name, str(record.size_bytes)] for record in type_records[:limit]],
        }

    other_records = [record for record in ordered_records if record.key_type not in {"string", "hash", "list", "set", "zset", "stream"}]
    sections["top_other_keys"] = {
        "limit": top_n_map["other_big_keys"],
        "rows": [[record.key_name, str(record.size_bytes)] for record in other_records[: top_n_map["other_big_keys"]]],
    }

    return sections


def _normalize_top_n(top_n: int | dict[str, int]) -> dict[str, int]:
    if isinstance(top_n, int):
        return {
            "top_big_keys": top_n,
            "string_big_keys": top_n,
            "hash_big_keys": top_n,
            "list_big_keys": top_n,
            "set_big_keys": top_n,
            "zset_big_keys": top_n,
            "stream_big_keys": top_n,
            "other_big_keys": top_n,
        }

    return {
        "top_big_keys": int(top_n.get("top_big_keys", 100)),
        "string_big_keys": int(top_n.get("string_big_keys", 100)),
        "hash_big_keys": int(top_n.get("hash_big_keys", 100)),
        "list_big_keys": int(top_n.get("list_big_keys", 100)),
        "set_big_keys": int(top_n.get("set_big_keys", 100)),
        "zset_big_keys": int(top_n.get("zset_big_keys", 100)),
        "stream_big_keys": int(top_n.get("stream_big_keys", 100)),
        "other_big_keys": int(top_n.get("other_big_keys", 100)),
    }
