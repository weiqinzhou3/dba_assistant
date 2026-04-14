from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from dba_assistant.application.request_models import RuntimeInputs


def infer_report_format_alias(token: str | None) -> str | None:
    if token is None:
        return None

    normalized = token.strip().lower()
    compact = normalized.replace(" ", "")

    if compact.startswith("docx") or compact.startswith("word"):
        return "docx"
    if compact == "summary":
        return "summary"
    if compact == "pdf":
        return "pdf"
    if compact == "html":
        return "html"
    return normalized or None


def default_report_output_path(
    format: str,
    base_dir: Path | None = None,
    report_slug: str = "report",
) -> Path:
    normalized = infer_report_format_alias(format)
    if normalized != "docx":
        raise ValueError(f"Unsupported default output path format: {format}")

    target_dir = (base_dir or Path("/tmp")).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)

    stem = f"{_report_stem(report_slug)}_{_timestamp_slug()}"
    candidate = target_dir / f"{stem}.docx"
    counter = 2
    while candidate.exists():
        candidate = target_dir / f"{stem}_{counter}.docx"
        counter += 1
    return candidate


def ensure_report_output_path(
    runtime_inputs: RuntimeInputs,
    report_format: str | None,
    *,
    report_slug: str = "report",
) -> RuntimeInputs:
    normalized = infer_report_format_alias(report_format or runtime_inputs.report_format)
    if normalized != "docx":
        return runtime_inputs
    if runtime_inputs.output_path is not None:
        return replace(
            runtime_inputs,
            output_mode="report",
            report_format="docx",
        )
    return replace(
        runtime_inputs,
        output_mode="report",
        report_format="docx",
        output_path=default_report_output_path("docx", report_slug=report_slug),
    )


def _report_stem(report_slug: str) -> str:
    normalized = report_slug.strip().lower().replace("-", "_")
    if normalized in {"inspection", "redis_inspection", "redis_inspection_report"}:
        return "dba_assistant_redis_inspection"
    return "dba_assistant_report"


def _timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
