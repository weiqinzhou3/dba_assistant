from __future__ import annotations

import json
import re
from typing import Any

from dba_assistant.skills_runtime.assets import load_skill_json_asset


_SKILL_NAME = "redis-inspection-report"
_SCHEMA_PATH = "assets/log_issue_schema.json"
_VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}
_VALID_CONFIDENCE = {"high", "medium", "low"}
_VALID_CATEGORIES = {"log"}
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}
_MAX_REPAIR_ATTEMPTS = 1

ISSUE_FAMILIES: tuple[dict[str, Any], ...] = (
    {
        "issue_key": "aof_rewrite_frequent",
        "issue_name": "AOF重写频繁触发",
        "candidate_signals": ("persistence_signal",),
        "keywords": ("aof", "append only", "rewrite"),
    },
    {
        "issue_key": "rdb_cow_high",
        "issue_name": "RDB持久化期间Copy-on-Write内存开销高",
        "candidate_signals": ("persistence_signal",),
        "keywords": ("rdb", "copy-on-write", "cow"),
    },
    {
        "issue_key": "fork_failure",
        "issue_name": "fork失败导致后台保存失败",
        "candidate_signals": ("fork_signal",),
        "keywords": ("fork", "can't save in background", "cannot save in background"),
    },
    {
        "issue_key": "cluster_fail_recovery",
        "issue_name": "Redis集群节点故障与恢复事件",
        "candidate_signals": ("cluster_fail_signal",),
        "keywords": ("cluster", "fail", "clear fail", "state changed", "failover"),
    },
    {
        "issue_key": "replication_break",
        "issue_name": "Redis复制超时或同步异常",
        "candidate_signals": ("replication_signal",),
        "keywords": (
            "replication",
            "timeout",
            "sync",
            "no route to host",
            "replication id mismatch",
            "master",
            "replica",
            "slave",
        ),
    },
)


def review_redis_log_candidates(
    log_candidates_json: str,
    *,
    model: Any,
    focus_topics: str = "",
    report_language: str = "zh-CN",
) -> str:
    """Run deterministic chunked LLM semantic review on reduced Redis log candidates.

    The model is invoked per stable cluster x issue-family chunk instead of once
    for the whole payload. Each chunk is schema-validated, repaired at most once,
    then merged deterministically before returning reviewed_log_issues_json.
    """
    payload = _load_candidate_payload(log_candidates_json)
    schema = _review_schema(payload)
    chunks = _build_review_chunks(payload)
    reviewed_issues: list[dict[str, Any]] = []

    for chunk in chunks:
        reviewed_issues.extend(
            _review_chunk(
                chunk,
                model=model,
                schema=schema,
                focus_topics=focus_topics,
                report_language=report_language or "zh-CN",
            )["issues"]
        )

    reviewed = {"issues": _merge_review_issues(reviewed_issues)}
    return json.dumps(reviewed, ensure_ascii=False)


def _load_candidate_payload(raw: str) -> dict[str, Any]:
    if not raw or not raw.strip():
        return {"clusters": []}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("log_candidates_json must be a JSON object.")
    return data


def _review_schema(payload: dict[str, Any]) -> dict[str, Any]:
    schema = payload.get("review_output_schema")
    if isinstance(schema, dict) and schema:
        return schema
    return load_skill_json_asset(_SKILL_NAME, _SCHEMA_PATH)


def _build_review_chunks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_clusters = payload.get("clusters")
    if not isinstance(raw_clusters, list):
        return []
    clusters = sorted(
        (cluster for cluster in raw_clusters if isinstance(cluster, dict)),
        key=lambda cluster: (
            str(cluster.get("cluster_id") or ""),
            str(cluster.get("cluster_name") or ""),
        ),
    )
    chunks: list[dict[str, Any]] = []
    for cluster in clusters:
        candidates = _sorted_candidates(cluster.get("log_candidates"))
        cluster_summary = {
            "system_id": str(cluster.get("system_id") or ""),
            "system_name": str(cluster.get("system_name") or ""),
            "cluster_id": str(cluster.get("cluster_id") or ""),
            "cluster_name": str(cluster.get("cluster_name") or ""),
            "candidate_count": cluster.get("candidate_count", len(candidates)),
        }
        for family in ISSUE_FAMILIES:
            family_candidates = [
                candidate
                for candidate in candidates
                if _candidate_matches_family(candidate, family)
            ]
            chunks.append(
                {
                    "cluster": cluster_summary,
                    "issue_family": _family_contract(family),
                    "coverage_contract": _coverage_contract(),
                    "log_candidates": family_candidates,
                }
            )
    return chunks


def _sorted_candidates(raw_candidates: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_candidates, list):
        return []
    candidates = [candidate for candidate in raw_candidates if isinstance(candidate, dict)]
    return sorted(
        candidates,
        key=lambda candidate: (
            str(candidate.get("candidate_signal") or ""),
            str(candidate.get("node_id") or ""),
            str(candidate.get("timestamp") or ""),
            str(candidate.get("raw_message") or ""),
            str(candidate.get("source_path") or ""),
        ),
    )


def _candidate_matches_family(candidate: dict[str, Any], family: dict[str, Any]) -> bool:
    signal = str(candidate.get("candidate_signal") or "").strip()
    raw_message = str(candidate.get("raw_message") or "").lower()
    signals = set(family.get("candidate_signals") or ())
    keywords = tuple(str(keyword).lower() for keyword in family.get("keywords") or ())
    signal_matches = not signals or signal in signals
    keyword_matches = not keywords or any(keyword in raw_message for keyword in keywords)
    return signal_matches and keyword_matches


def _family_contract(family: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue_key": family["issue_key"],
        "issue_name": family["issue_name"],
        "candidate_signals": list(family["candidate_signals"]),
        "keywords": list(family["keywords"]),
        "required_conclusion_values": [
            "anomalous",
            "not anomalous",
            "insufficient evidence",
        ],
    }


def _coverage_contract() -> dict[str, Any]:
    return {
        "review_scope": "exactly one cluster x issue family chunk",
        "all_required_issue_families": [
            {
                "issue_key": family["issue_key"],
                "issue_name": family["issue_name"],
            }
            for family in ISSUE_FAMILIES
        ],
        "rule": (
            "For this chunk, explicitly decide whether the current cluster has "
            "this issue family as anomalous, not anomalous, or insufficient evidence. "
            "Return an issues item with is_anomalous=false for not anomalous or "
            "insufficient evidence; the caller will deterministically crop non-anomalies."
        ),
    }


def _review_chunk(
    chunk: dict[str, Any],
    *,
    model: Any,
    schema: dict[str, Any],
    focus_topics: str,
    report_language: str,
) -> dict[str, Any]:
    messages = _build_review_messages(
        chunk,
        schema=schema,
        focus_topics=focus_topics,
        report_language=report_language,
    )
    attempt = 0
    while True:
        response = model.invoke(messages)
        content = _message_content(response)
        try:
            return _normalize_review_payload(_parse_json_object(content), chunk=chunk)
        except ValueError as exc:
            if attempt >= _MAX_REPAIR_ATTEMPTS:
                cluster = chunk["cluster"]
                family = chunk["issue_family"]
                raise ValueError(
                    "LLM log review invalid schema after repair "
                    f"for cluster={cluster['cluster_id'] or cluster['cluster_name']} "
                    f"issue_family={family['issue_key']}: {exc}"
                ) from exc
            messages = _build_repair_messages(
                chunk,
                schema=schema,
                focus_topics=focus_topics,
                report_language=report_language,
                invalid_response=content,
                repair_error=str(exc),
            )
            attempt += 1


def _build_review_messages(
    chunk: dict[str, Any],
    *,
    schema: dict[str, Any],
    focus_topics: str,
    report_language: str,
) -> list[dict[str, str]]:
    system = (
        "You are a Redis inspection log semantic reviewer. "
        "Judge only the provided single cluster x issue-family chunk. "
        "Do not request or use files, paths, shell commands, ls, glob, grep, or read_file. "
        "This is a coverage contract, not a free-form summary: classify the current "
        "issue family as anomalous, not anomalous, or insufficient evidence. "
        "Return only a JSON object matching the provided schema."
    )
    user_payload = {
        "report_language": report_language,
        "focus_topics": focus_topics,
        "review_output_schema": schema,
        "review_chunk": chunk,
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2)},
    ]


def _build_repair_messages(
    chunk: dict[str, Any],
    *,
    schema: dict[str, Any],
    focus_topics: str,
    report_language: str,
    invalid_response: str,
    repair_error: str,
) -> list[dict[str, str]]:
    system = (
        "Repair the Redis log semantic review output. "
        "Return only valid JSON matching the schema. "
        "Do not add prose, markdown fences, or fields outside the schema."
    )
    user_payload = {
        "report_language": report_language,
        "focus_topics": focus_topics,
        "review_output_schema": schema,
        "review_chunk": chunk,
        "invalid_response": invalid_response,
        "repair_error": repair_error,
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2)},
    ]


def _message_content(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return str(content)


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*(?P<body>\{.*\})\s*```", stripped, flags=re.DOTALL)
        if match is not None:
            stripped = match.group("body").strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        start = stripped.find("{")
        if start < 0:
            raise ValueError("LLM log review did not return a JSON object.") from None
        try:
            data, _index = decoder.raw_decode(stripped[start:])
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM log review returned invalid JSON: {exc.msg}") from None
    if not isinstance(data, dict):
        raise ValueError("LLM log review must return a JSON object.")
    return data


def _normalize_review_payload(data: dict[str, Any], *, chunk: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("LLM log review must return a JSON object.")
    if "issues" not in data and "reviewed_log_issues" not in data:
        raise ValueError("LLM log review JSON must contain an issues list.")
    raw_issues = data.get("issues") if "issues" in data else data.get("reviewed_log_issues")
    if not isinstance(raw_issues, list):
        raise ValueError("LLM log review JSON must contain an issues list.")
    if chunk is not None and not raw_issues:
        raise ValueError("LLM log review chunk must contain one conclusion issue item.")
    return {"issues": [_normalize_issue(item, chunk=chunk) for item in raw_issues]}


def _normalize_issue(item: Any, *, chunk: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("Each LLM log review issue must be a JSON object.")
    required = {
        "cluster_id",
        "cluster_name",
        "issue_name",
        "is_anomalous",
        "severity",
        "why",
        "affected_nodes",
        "supporting_samples",
        "recommendation",
        "merge_key",
        "category",
        "confidence",
    }
    missing = sorted(field for field in required if field not in item)
    if missing:
        raise ValueError(f"LLM log review issue missing required fields: {', '.join(missing)}")

    cluster = chunk.get("cluster", {}) if chunk else {}
    family = chunk.get("issue_family", {}) if chunk else {}
    cluster_id = str(item.get("cluster_id") or cluster.get("cluster_id") or "").strip()
    cluster_name = str(item.get("cluster_name") or cluster.get("cluster_name") or "").strip()
    issue_name = str(item.get("issue_name") or family.get("issue_name") or "").strip()
    severity = str(item.get("severity") or "").strip().lower()
    confidence = str(item.get("confidence") or "").strip().lower()
    category = str(item.get("category") or "").strip().lower()
    is_anomalous = _parse_bool(item.get("is_anomalous"))
    affected_nodes = _strict_string_list(item.get("affected_nodes"), field="affected_nodes")
    supporting_samples = _strict_string_list(item.get("supporting_samples"), field="supporting_samples")
    merge_key = str(item.get("merge_key") or "").strip()
    stable_cluster_key = cluster_id or cluster_name
    if family.get("issue_key") and stable_cluster_key:
        merge_key = f"{stable_cluster_key}:{family['issue_key']}"

    if not issue_name:
        raise ValueError("LLM log review issue_name must not be empty.")
    if not cluster_id and not cluster_name:
        raise ValueError("LLM log review issue must include cluster_id or cluster_name.")
    if severity not in _VALID_SEVERITIES:
        raise ValueError(f"LLM log review severity is invalid: {severity!r}")
    if confidence not in _VALID_CONFIDENCE:
        raise ValueError(f"LLM log review confidence is invalid: {confidence!r}")
    if category not in _VALID_CATEGORIES:
        raise ValueError(f"LLM log review category is invalid: {category!r}")
    if not merge_key:
        raise ValueError("LLM log review merge_key must not be empty.")

    return {
        "cluster_id": cluster_id,
        "cluster_name": cluster_name,
        "issue_name": issue_name,
        "is_anomalous": is_anomalous,
        "severity": severity,
        "why": str(item.get("why") or "").strip(),
        "affected_nodes": affected_nodes,
        "supporting_samples": supporting_samples,
        "recommendation": str(item.get("recommendation") or "").strip(),
        "merge_key": merge_key,
        "category": category,
        "confidence": confidence,
    }


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "y"}:
            return True
        if normalized in {"false", "no", "0", "n"}:
            return False
        raise ValueError(f"invalid is_anomalous boolean value: {value!r}")
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    raise ValueError(f"invalid is_anomalous boolean value: {value!r}")


def _strict_string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"LLM log review {field} must be an array of strings.")
    return [str(item).strip() for item in value if str(item).strip()]


def _merge_review_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for issue in issues:
        if not issue["is_anomalous"]:
            continue
        key = (
            issue["cluster_id"],
            issue["cluster_name"],
            issue["merge_key"],
        )
        grouped.setdefault(key, []).append(issue)

    merged: list[dict[str, Any]] = []
    for key in sorted(grouped):
        items = grouped[key]
        primary = min(
            items,
            key=lambda item: (
                _SEVERITY_ORDER[item["severity"]],
                item["issue_name"],
                item["merge_key"],
            ),
        )
        merged.append(
            {
                "cluster_id": primary["cluster_id"],
                "cluster_name": primary["cluster_name"],
                "issue_name": primary["issue_name"],
                "is_anomalous": True,
                "severity": primary["severity"],
                "why": " / ".join(
                    _unique_sorted(item["why"] for item in items if item["why"])
                ),
                "affected_nodes": _unique_sorted(
                    node for item in items for node in item["affected_nodes"]
                ),
                "supporting_samples": _unique_sorted(
                    sample for item in items for sample in item["supporting_samples"]
                )[:5],
                "recommendation": " / ".join(
                    _unique_sorted(item["recommendation"] for item in items if item["recommendation"])
                ),
                "merge_key": primary["merge_key"],
                "category": "log",
                "confidence": min(
                    (item["confidence"] for item in items),
                    key=lambda value: _CONFIDENCE_ORDER[value],
                ),
            }
        )
    return merged


def _unique_sorted(values: Any) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})
