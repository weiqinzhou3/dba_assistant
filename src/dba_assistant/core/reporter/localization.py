from __future__ import annotations


def normalize_report_language(language: str | None) -> str:
    if not language:
        return "zh-CN"
    lowered = language.lower()
    if lowered.startswith("en"):
        return "en-US"
    return "zh-CN"
