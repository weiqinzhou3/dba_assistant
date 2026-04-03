from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

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
    DIRECT_MEMORY_ANALYSIS_ROUTE_NAME,
    ConfirmationRequest,
    InputSourceKind,
    LEGACY_SQL_PIPELINE_ROUTE_NAME,
    NormalizedRdbDataset,
    PRECOMPUTED_DATASET_ROUTE_NAME,
    RdbAnalysisRequest,
    phase_label_for_route_name,
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

    selected_route = choose_path(request)
    effective_profile = profile or resolve_profile(
        request.profile_name,
        RdbOverrides(**request.profile_overrides),
    )
    dataset = _collect_dataset(
        request,
        selected_route=selected_route,
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
        "route": selected_route,
    }
    legacy_path_label = phase_label_for_route_name(selected_route)
    if legacy_path_label is not None:
        metadata["path"] = legacy_path_label
    return AnalysisReport(
        title=report.title,
        summary=report.summary,
        sections=report.sections,
        metadata=metadata,
    )


def _collect_dataset(
    request: RdbAnalysisRequest,
    *,
    selected_route: str,
    path_a_collector,
    path_b_collector,
    path_c_collector,
) -> NormalizedRdbDataset:
    paths = [Path(sample.source) for sample in request.inputs if sample.kind is not InputSourceKind.REMOTE_REDIS]

    if selected_route == PRECOMPUTED_DATASET_ROUTE_NAME:
        collector = path_b_collector or PathBPrecomputedCollector()
        return collector.collect(paths)

    if selected_route == DIRECT_MEMORY_ANALYSIS_ROUTE_NAME:
        collector = path_c_collector or PathCDirectParserCollector(parser=_parse_rdb_rows)
        return collector.collect(paths)

    if selected_route == LEGACY_SQL_PIPELINE_ROUTE_NAME:
        collector = path_a_collector or PathCDirectParserCollector(parser=_parse_rdb_rows)
        return collector.collect(paths)

    raise ValueError(f"Unsupported analysis route: {selected_route}")


def _parse_rdb_rows(path: Path) -> list[dict[str, object]]:
    from rdbtools import MemoryCallback, RdbParser

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
