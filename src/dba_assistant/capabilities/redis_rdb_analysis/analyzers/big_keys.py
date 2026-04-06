from __future__ import annotations

from dataclasses import dataclass
import heapq

from dba_assistant.capabilities.redis_rdb_analysis.types import NormalizedRdbDataset

_TYPED_SECTION_SPECS: tuple[tuple[str, str, str], ...] = (
    ("string", "top_string_keys", "string_big_keys"),
    ("hash", "top_hash_keys", "hash_big_keys"),
    ("list", "top_list_keys", "list_big_keys"),
    ("set", "top_set_keys", "set_big_keys"),
    ("zset", "top_zset_keys", "zset_big_keys"),
    ("stream", "top_stream_keys", "stream_big_keys"),
)


@dataclass(frozen=True)
class RankedKey:
    key_name: str
    key_type: str
    size_bytes: int

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, RankedKey):
            return NotImplemented
        if self.size_bytes != other.size_bytes:
            return self.size_bytes < other.size_bytes
        return self.key_name > other.key_name


class BoundedBigKeyHeap:
    def __init__(self, limit: int) -> None:
        self._limit = max(0, int(limit))
        self._heap: list[RankedKey] = []

    def push(self, *, key_name: str, key_type: str, size_bytes: int) -> None:
        if self._limit <= 0:
            return
        candidate = RankedKey(
            key_name=str(key_name),
            key_type=str(key_type),
            size_bytes=int(size_bytes),
        )
        if len(self._heap) < self._limit:
            heapq.heappush(self._heap, candidate)
            return
        if self._heap[0] < candidate:
            heapq.heapreplace(self._heap, candidate)

    def rows(self, *, include_type: bool) -> list[list[str]]:
        ranked = list(self._heap)
        ranked.sort(key=lambda record: (-record.size_bytes, record.key_name))
        if include_type:
            return [
                [record.key_name, record.key_type, str(record.size_bytes)]
                for record in ranked
            ]
        return [
            [record.key_name, str(record.size_bytes)]
            for record in ranked
        ]


class BigKeyAccumulator:
    def __init__(self, *, top_n: int | dict[str, int] = 100) -> None:
        self._top_n_map = _normalize_top_n(top_n)
        self._overall = BoundedBigKeyHeap(self._top_n_map["top_big_keys"])
        self._typed = {
            key_type: BoundedBigKeyHeap(self._top_n_map[limit_key])
            for key_type, _, limit_key in _TYPED_SECTION_SPECS
        }
        self._other = BoundedBigKeyHeap(self._top_n_map["other_big_keys"])

    def add(self, *, key_name: str, key_type: str, size_bytes: int) -> None:
        normalized_key_type = str(key_type)
        normalized_size = int(size_bytes)
        self._overall.push(
            key_name=key_name,
            key_type=normalized_key_type,
            size_bytes=normalized_size,
        )

        typed_heap = self._typed.get(normalized_key_type)
        if typed_heap is not None:
            typed_heap.push(
                key_name=key_name,
                key_type=normalized_key_type,
                size_bytes=normalized_size,
            )
            return

        self._other.push(
            key_name=key_name,
            key_type=normalized_key_type,
            size_bytes=normalized_size,
        )

    def render_sections(self) -> dict[str, dict[str, object]]:
        sections: dict[str, dict[str, object]] = {
            "top_big_keys": {
                "limit": self._top_n_map["top_big_keys"],
                "rows": self._overall.rows(include_type=True),
            },
        }

        for key_type, section_name, limit_key in _TYPED_SECTION_SPECS:
            sections[section_name] = {
                "limit": self._top_n_map[limit_key],
                "rows": self._typed[key_type].rows(include_type=False),
            }

        sections["top_other_keys"] = {
            "limit": self._top_n_map["other_big_keys"],
            "rows": self._other.rows(include_type=False),
        }
        return sections


def analyze_big_keys(
    dataset: NormalizedRdbDataset,
    *,
    top_n: int | dict[str, int] = 100,
) -> dict[str, dict[str, object]]:
    accumulator = BigKeyAccumulator(top_n=top_n)
    for record in dataset.records:
        accumulator.add(
            key_name=record.key_name,
            key_type=record.key_type,
            size_bytes=record.size_bytes,
        )
    return accumulator.render_sections()


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
