from __future__ import annotations

import json
import re
from typing import Any

from dba_assistant.skills_runtime.assets import load_skill_json_asset


_SKILL_NAME = "redis-inspection-report"
_SCHEMA_PATH = "assets/log_issue_schema.json"
_VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}
_VALID_CONFIDENCE = {"high", "medium", "low"}


def review_redis_log_candidates(
    log_candidates_json: str,
    *,
    model: Any,
    focus_topics: str = "",
    report_language: str = "zh-CN",
) -> str:
    """Run LLM semantic review on already-reduced Redis log candidates.

    This function intentionally calls the model directly instead of creating a
    Deep Agent or binding tools. The review model only sees the candidate JSON
    supplied by the caller, so it has no generic filesystem tool surface.
    """
    payload = _load_candidate_payload(log_candidates_json)
    schema = _review_schema(payload)
    messages = _build_review_messages(
        payload,
        schema=schema,
        focus_topics=focus_topics,
        report_language=report_language or "zh-CN",
    )
    response = model.invoke(messages)
    content = _message_content(response)
    reviewed = _normalize_review_payload(_parse_json_object(content))
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


def _build_review_messages(
    payload: dict[str, Any],
    *,
    schema: dict[str, Any],
    focus_topics: str,
    report_language: str,
) -> list[dict[str, str]]:
    system = (
        "You are a Redis inspection log semantic reviewer. "
        "Judge only the provided log candidate payload. "
        "Do not request or use files, paths, shell commands, ls, glob, grep, or read_file. "
        "Classify normal operational events separately from anomalous issues. "
        "Return only JSON matching the provided schema."
    )
    user_payload = {
        "report_language": report_language,
        "focus_topics": focus_topics,
        "review_output_schema": schema,
        "log_candidate_payload": payload,
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
        match = re.search(r"```(?:json)?\s*(?P<body>\{.*?\})\s*```", stripped, flags=re.DOTALL)
        if match is not None:
            stripped = match.group("body")
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if match is None:
            raise ValueError("LLM log review did not return a JSON object.") from None
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("LLM log review must return a JSON object.")
    return data


def _normalize_review_payload(data: dict[str, Any]) -> dict[str, Any]:
    raw_issues = data.get("issues") or data.get("reviewed_log_issues") or []
    if not isinstance(raw_issues, list):
        raise ValueError("LLM log review JSON must contain an issues list.")
    return {"issues": [_normalize_issue(item) for item in raw_issues if isinstance(item, dict)]}


def _normalize_issue(item: dict[str, Any]) -> dict[str, Any]:
    severity = str(item.get("severity") or "medium").strip().lower()
    confidence = str(item.get("confidence") or "medium").strip().lower()
    return {
        "cluster_id": str(item.get("cluster_id") or "").strip(),
        "cluster_name": str(item.get("cluster_name") or "").strip(),
        "issue_name": str(item.get("issue_name") or "").strip(),
        "is_anomalous": bool(item.get("is_anomalous")),
        "severity": severity if severity in _VALID_SEVERITIES else "medium",
        "why": str(item.get("why") or "").strip(),
        "affected_nodes": _string_list(item.get("affected_nodes")),
        "supporting_samples": _string_list(item.get("supporting_samples")),
        "recommendation": str(item.get("recommendation") or "").strip(),
        "merge_key": str(item.get("merge_key") or "").strip(),
        "category": "log",
        "confidence": confidence if confidence in _VALID_CONFIDENCE else "medium",
    }


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []
