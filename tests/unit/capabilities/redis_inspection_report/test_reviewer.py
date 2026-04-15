import json

from dba_assistant.capabilities.redis_inspection_report.reviewer import review_redis_log_candidates


class FakeReviewModel:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[object] = []

    def invoke(self, messages):
        self.calls.append(messages)
        return type("Message", (), {"content": self.content})()


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
    assert model.calls


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
    model = FakeReviewModel('{"issues": []}')

    review_redis_log_candidates(json.dumps(payload), model=model)

    assert len(model.calls) == 1
    messages = model.calls[0]
    assert all(not isinstance(message, dict) or "tools" not in message for message in messages)
    assert not hasattr(model, "bind_tools")
