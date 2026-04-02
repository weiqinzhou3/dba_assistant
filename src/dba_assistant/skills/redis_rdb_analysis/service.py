from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rdbtools import MemoryCallback, RdbParser

from dba_assistant.application.request_models import RdbOverrides
from dba_assistant.core.reporter.report_model import AnalysisReport
from dba_assistant.skills.redis_rdb_analysis.analyzers.overall import analyze_overall
from dba_assistant.skills.redis_rdb_analysis.collectors.path_b_precomputed_collector import (
    PathBPrecomputedCollector,
)
from dba_assistant.skills.redis_rdb_analysis.collectors.path_c_direct_parser_collector import (
    PathCDirectParserCollector,
)
from dba_assistant.skills.redis_rdb_analysis.path_router import choose_path
from dba_assistant.skills.redis_rdb_analysis.profile_resolver import resolve_profile
from dba_assistant.skills.redis_rdb_analysis.reports.assembler import assemble_report
from dba_assistant.skills.redis_rdb_analysis.types import (
    AnalysisStatus,
    ConfirmationRequest,
    InputSourceKind,
    NormalizedRdbDataset,
    RdbAnalysisRequest,
)


def analyze_rdb(
    request: RdbAnalysisRequest,
    *,
    profile,
    remote_discovery,
    path_a_collector=None,
    path_b_collector=None,
    path_c_collector=None,
) -> ConfirmationRequest | AnalysisReport:
    if any(sample.kind is InputSourceKind.REMOTE_REDIS for sample in request.inputs):
        discovery = remote_discovery(request)
        return ConfirmationRequest(
            status=AnalysisStatus.CONFIRMATION_REQUIRED,
            message=f"Remote RDB available at {discovery['rdb_path']}.",
            required_action="fetch_existing",
        )

    selected_path = choose_path(request)
    effective_profile = profile or resolve_profile(
        request.profile_name,
        RdbOverrides(**request.profile_overrides),
    )
    dataset = _collect_dataset(
        request,
        selected_path=selected_path,
        path_a_collector=path_a_collector,
        path_b_collector=path_b_collector,
        path_c_collector=path_c_collector,
    )
    analysis_result = analyze_overall(dataset, profile=effective_profile)
    report = assemble_report(
        analysis_result,
        profile=effective_profile,
        title="Redis RDB Analysis",
    )
    metadata = {
        **report.metadata,
        "input_count": str(len(dataset.samples)),
        "path": selected_path,
    }
    return AnalysisReport(
        title=report.title,
        summary=report.summary,
        sections=report.sections,
        metadata=metadata,
    )


def _collect_dataset(
    request: RdbAnalysisRequest,
    *,
    selected_path: str,
    path_a_collector,
    path_b_collector,
    path_c_collector,
) -> NormalizedRdbDataset:
    paths = [Path(sample.source) for sample in request.inputs if sample.kind is not InputSourceKind.REMOTE_REDIS]

    if selected_path == "3b":
        collector = path_b_collector or PathBPrecomputedCollector()
        return collector.collect(paths)

    if selected_path == "3c":
        collector = path_c_collector or PathCDirectParserCollector(parser=_parse_rdb_rows)
        return collector.collect(paths)

    if selected_path == "3a":
        if path_a_collector is None:
            raise NotImplementedError("Path 3a requires an injected MySQL staging collector.")
        return path_a_collector.collect(paths)

    raise ValueError(f"Unsupported analysis path: {selected_path}")


def _parse_rdb_rows(path: Path) -> list[dict[str, object]]:
    stream = _MemoryRecordStream()
    parser = RdbParser(MemoryCallback(stream, 64))
    parser.parse(str(path))
    return stream.rows


class _MemoryRecordStream:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def next_record(self, record) -> None:
        if record.key is None:
            return

        self.rows.append(
            {
                "key_name": str(record.key),
                "key_type": str(record.type),
                "size_bytes": int(record.bytes),
                "has_expiration": record.expiry is not None,
                "ttl_seconds": _ttl_seconds(record.expiry),
            }
        )


def _ttl_seconds(expiry: object) -> int | None:
    if expiry is None:
        return None
    if isinstance(expiry, datetime):
        normalized = expiry if expiry.tzinfo is not None else expiry.replace(tzinfo=timezone.utc)
        return max(0, int((normalized - datetime.now(timezone.utc)).total_seconds()))
    return int(expiry)
