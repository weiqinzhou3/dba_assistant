import json
from pathlib import Path

import pytest

from dba_assistant.capabilities.redis_inspection_report.reviewer import (
    ISSUE_FAMILIES,
    review_redis_log_candidates,
)


FIXTURE_DIR = Path(__file__).resolve().parents[3] / "fixtures"


class FakeReviewModel:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[object] = []

    def invoke(self, messages):
        self.calls.append(messages)
        return type("Message", (), {"content": self.content})()


class SequenceReviewModel:
    def __init__(self, contents: list[str]) -> None:
        self.contents = contents
        self.calls: list[object] = []

    def invoke(self, messages):
        self.calls.append(messages)
        index = min(len(self.calls) - 1, len(self.contents) - 1)
        return type("Message", (), {"content": self.contents[index]})()


class ChunkAwareReviewModel:
    def __init__(self, *, duplicate_order: bool = False) -> None:
        self.calls: list[list[dict[str, str]]] = []
        self.duplicate_order = duplicate_order

    def invoke(self, messages):
        self.calls.append(messages)
        chunk = _message_chunk(messages)
        cluster_id = chunk["cluster"]["cluster_id"]
        cluster_name = chunk["cluster"]["cluster_name"]
        family = chunk["issue_family"]
        candidates = chunk["log_candidates"]
        issue = {
            "cluster_id": cluster_id,
            "cluster_name": cluster_name,
            "issue_name": family["issue_name"],
            "is_anomalous": bool(candidates),
            "severity": "medium",
            "why": f"{family['issue_name']} reviewed for {cluster_name}",
            "affected_nodes": sorted(
                {
                    str(candidate.get("node_id") or "")
                    for candidate in candidates
                    if str(candidate.get("node_id") or "").strip()
                }
            ),
            "supporting_samples": [
                str(candidate.get("raw_message") or "")
                for candidate in candidates
                if str(candidate.get("raw_message") or "").strip()
            ][:3],
            "recommendation": f"Review {family['issue_key']}.",
            "merge_key": f"{cluster_id}:{family['issue_key']}",
            "category": "log",
            "confidence": "high" if candidates else "low",
        }
        return type("Message", (), {"content": json.dumps({"issues": [issue]})})()


def _message_chunk(messages) -> dict:
    user_message = next(message for message in messages if message["role"] == "user")
    return json.loads(user_message["content"])["review_chunk"]


def test_review_redis_log_candidates_returns_schema_shaped_issues_json() -> None:
    payload = {
        "clusters": [
            {
                "cluster_id": "cluster-a",
                "cluster_name": "cluster-a",
                "log_candidates": [
                    {
                        "node_id": "10.0.0.1:6379",
                        "candidate_signal": "oom_signal",
                        "raw_message": "OOM command not allowed when used memory > maxmemory",
                    }
                ],
            }
        ],
        "review_output_schema": {"type": "object", "required": ["issues"]},
    }
    model = FakeReviewModel(
        json.dumps(
            {
                "issues": [
                    {
                        "cluster_id": "cluster-a",
                        "cluster_name": "cluster-a",
                        "issue_name": "Redis OOM",
                        "is_anomalous": True,
                        "severity": "high",
                        "why": "OOM is a real memory pressure signal.",
                        "affected_nodes": ["10.0.0.1:6379"],
                        "supporting_samples": ["OOM command not allowed when used memory > maxmemory"],
                        "recommendation": "Review maxmemory and eviction policy.",
                        "merge_key": "cluster-a:oom",
                        "category": "log",
                        "confidence": "high",
                    }
                ]
            }
        )
    )

    reviewed = json.loads(review_redis_log_candidates(json.dumps(payload), model=model))

    assert reviewed["issues"][0]["issue_name"] == "Redis OOM"
    assert reviewed["issues"][0]["is_anomalous"] is True
    assert reviewed["issues"][0]["category"] == "log"
    assert len(model.calls) == len(ISSUE_FAMILIES)


def test_review_redis_log_candidates_does_not_expose_filesystem_tools_to_model() -> None:
    payload = {
        "clusters": [
            {
                "cluster_id": "cluster-a",
                "cluster_name": "cluster-a",
                "log_candidates": [
                    {
                        "node_id": "10.0.0.1:6379",
                        "candidate_signal": "persistence_signal",
                        "raw_message": "Background AOF rewrite finished successfully",
                    }
                ],
            }
        ]
    }
    model = ChunkAwareReviewModel()

    review_redis_log_candidates(json.dumps(payload), model=model)

    assert len(model.calls) == len(ISSUE_FAMILIES)
    messages = model.calls[0]
    assert all(not isinstance(message, dict) or "tools" not in message for message in messages)
    assert not hasattr(model, "bind_tools")


def test_review_redis_log_candidates_parses_string_false_as_not_anomalous() -> None:
    payload = _synthetic_candidate_payload()
    model = FakeReviewModel(
        json.dumps(
            {
                "issues": [
                    {
                        "cluster_id": "trade",
                        "cluster_name": "trade-redis",
                        "issue_name": "AOF重写频繁触发",
                        "is_anomalous": "false",
                        "severity": "medium",
                        "why": "No anomaly after review.",
                        "affected_nodes": ["10.0.0.1:6379"],
                        "supporting_samples": ["Background append only file rewriting started"],
                        "recommendation": "Keep observing.",
                        "merge_key": "trade:aof_rewrite_frequent",
                        "category": "log",
                        "confidence": "medium",
                    }
                ]
            }
        )
    )

    reviewed = json.loads(review_redis_log_candidates(json.dumps(payload), model=model))

    assert reviewed["issues"] == []


def test_review_redis_log_candidates_reviews_stable_cluster_family_chunks() -> None:
    payload = _synthetic_candidate_payload()
    model = ChunkAwareReviewModel()

    review_redis_log_candidates(json.dumps(payload), model=model)

    assert len(model.calls) == len(payload["clusters"]) * len(ISSUE_FAMILIES)
    chunks = [_message_chunk(messages) for messages in model.calls]
    assert [
        (chunk["cluster"]["cluster_id"], chunk["issue_family"]["issue_key"])
        for chunk in chunks
    ] == [
        (cluster["cluster_id"], family["issue_key"])
        for cluster in payload["clusters"]
        for family in ISSUE_FAMILIES
    ]
    assert all(set(chunk.keys()) >= {"cluster", "issue_family", "coverage_contract", "log_candidates"} for chunk in chunks)
    assert all(len({candidate["candidate_signal"] for candidate in chunk["log_candidates"]}) <= 1 for chunk in chunks)


def test_review_redis_log_candidates_repairs_invalid_json_once() -> None:
    payload = _single_cluster_payload("trade", "trade-redis")
    model = SequenceReviewModel(
        [
            "not json",
            json.dumps(
                {
                    "issues": [
                        {
                            "cluster_id": "trade",
                            "cluster_name": "trade-redis",
                            "issue_name": "AOF重写频繁触发",
                            "is_anomalous": True,
                            "severity": "medium",
                            "why": "AOF rewrites repeated.",
                            "affected_nodes": ["10.0.0.1:6379"],
                            "supporting_samples": ["Background append only file rewriting started"],
                            "recommendation": "Review AOF rewrite thresholds.",
                            "merge_key": "trade:aof_rewrite_frequent",
                            "category": "log",
                            "confidence": "high",
                        }
                    ]
                }
            ),
        ]
    )

    reviewed = json.loads(review_redis_log_candidates(json.dumps(payload), model=model))

    assert len(model.calls) == len(ISSUE_FAMILIES) + 1
    assert reviewed["issues"][0]["merge_key"] == "trade:aof_rewrite_frequent"
    repair_message = model.calls[1][1]["content"]
    assert "repair_error" in repair_message


def test_review_redis_log_candidates_reports_schema_error_after_limited_repair() -> None:
    payload = _single_cluster_payload("trade", "trade-redis")
    model = SequenceReviewModel(
        [
            json.dumps({"issues": [{"is_anomalous": "maybe"}]}),
            json.dumps({"issues": [{"is_anomalous": "maybe"}]}),
        ]
    )

    with pytest.raises(ValueError, match="invalid schema"):
        review_redis_log_candidates(json.dumps(payload), model=model)

    assert len(model.calls) == 2


def test_review_redis_log_candidates_merges_same_issue_deterministically() -> None:
    payload = _single_cluster_payload("trade", "trade-redis")
    model = SequenceReviewModel(
        [
            json.dumps(
                {
                    "issues": [
                        {
                            "cluster_id": "trade",
                            "cluster_name": "trade-redis",
                            "issue_name": "AOF重写频繁触发",
                            "is_anomalous": True,
                            "severity": "medium",
                            "why": "AOF rewrites repeated.",
                            "affected_nodes": ["10.0.0.2:6379"],
                            "supporting_samples": ["AOF rewrite again"],
                            "recommendation": "Review AOF rewrite thresholds.",
                            "merge_key": "trade:aof_rewrite_frequent",
                            "category": "log",
                            "confidence": "medium",
                        },
                        {
                            "cluster_id": "trade",
                            "cluster_name": "trade-redis",
                            "issue_name": "AOF重写频繁触发",
                            "is_anomalous": True,
                            "severity": "high",
                            "why": "AOF rewrites repeated.",
                            "affected_nodes": ["10.0.0.1:6379"],
                            "supporting_samples": ["Background append only file rewriting started"],
                            "recommendation": "Review AOF rewrite thresholds.",
                            "merge_key": "trade:aof_rewrite_frequent",
                            "category": "log",
                            "confidence": "high",
                        },
                    ]
                }
            ),
            json.dumps(
                {
                    "issues": [
                        {
                            "cluster_id": "trade",
                            "cluster_name": "trade-redis",
                            "issue_name": "AOF重写频繁触发",
                            "is_anomalous": False,
                            "severity": "info",
                            "why": "Insufficient evidence.",
                            "affected_nodes": [],
                            "supporting_samples": [],
                            "recommendation": "Keep observing.",
                            "merge_key": "trade:aof_rewrite_frequent",
                            "category": "log",
                            "confidence": "low",
                        }
                    ]
                }
            ),
        ]
    )

    reviewed = json.loads(review_redis_log_candidates(json.dumps(payload), model=model))

    assert len(reviewed["issues"]) == 1
    issue = reviewed["issues"][0]
    assert issue["severity"] == "high"
    assert issue["affected_nodes"] == ["10.0.0.1:6379", "10.0.0.2:6379"]
    assert issue["supporting_samples"] == [
        "AOF rewrite again",
        "Background append only file rewriting started",
    ]


def test_review_redis_log_candidates_output_order_is_stable_across_runs() -> None:
    payload = _synthetic_candidate_payload()
    first = json.loads(review_redis_log_candidates(json.dumps(payload), model=ChunkAwareReviewModel()))
    second = json.loads(review_redis_log_candidates(json.dumps(payload), model=ChunkAwareReviewModel()))

    assert first == second
    assert [issue["merge_key"] for issue in first["issues"]] == sorted(
        issue["merge_key"] for issue in first["issues"]
    )


def _single_cluster_payload(cluster_id: str, cluster_name: str) -> dict:
    return {
        "clusters": [
            {
                "cluster_id": cluster_id,
                "cluster_name": cluster_name,
                "log_candidates": [
                    {
                        "node_id": "10.0.0.1:6379",
                        "candidate_signal": "persistence_signal",
                        "raw_message": "Background append only file rewriting started",
                    },
                    {
                        "node_id": "10.0.0.2:6379",
                        "candidate_signal": "persistence_signal",
                        "raw_message": "AOF rewrite again",
                    },
                    {
                        "node_id": "10.0.0.3:6379",
                        "candidate_signal": "fork_signal",
                        "raw_message": "Can't save in background: fork failed",
                    },
                ],
            }
        ]
    }


def _synthetic_candidate_payload() -> dict:
    return json.loads((FIXTURE_DIR / "redis_inspection_log_candidates_synthetic.json").read_text(encoding="utf-8"))
