from __future__ import annotations

from pathlib import Path

from dba_assistant.application.request_models import RdbOverrides
from dba_assistant.core.reporter.report_model import AnalysisReport
from dba_assistant.capabilities.redis_rdb_analysis.analyzers.overall import analyze_overall
from dba_assistant.capabilities.redis_rdb_analysis.collectors.path_a_mysql_backed_collector import (
    PathAMySQLBackedCollector,
)
from dba_assistant.capabilities.redis_rdb_analysis.collectors.path_b_precomputed_collector import (
    PathBPrecomputedCollector,
)
from dba_assistant.capabilities.redis_rdb_analysis.collectors.path_b_mysql_preparsed_collector import (
    PathBMySQLPreparsedCollector,
)
from dba_assistant.capabilities.redis_rdb_analysis.collectors.path_c_direct_parser_collector import (
    PathCDirectParserCollector,
)
from dba_assistant.capabilities.redis_rdb_analysis.path_router import choose_path
from dba_assistant.parsers.rdb_parser_strategy import (
    build_default_rdb_parser_strategy,
)
from dba_assistant.capabilities.redis_rdb_analysis.profile_resolver import resolve_profile
from dba_assistant.capabilities.redis_rdb_analysis.reports.assembler import assemble_report
from dba_assistant.capabilities.redis_rdb_analysis.types import (
    AnalysisStatus,
    DATABASE_BACKED_ANALYSIS,
    DIRECT_RDB_ANALYSIS,
    ConfirmationRequest,
    InputSourceKind,
    NormalizedRdbDataset,
    PREPARSED_DATASET_ANALYSIS,
    RdbAnalysisRequest,
    phase_label_for_route_name,
)


def analyze_rdb(
    request: RdbAnalysisRequest,
    *,
    profile,
    remote_discovery,
    path_a_collector=None,
    stage_rdb_rows_to_mysql=None,
    load_preparsed_dataset_from_mysql=None,
    mysql_read_query=None,
    path_b_collector=None,
    path_c_collector=None,
) -> ConfirmationRequest | AnalysisReport:
    parser_metadata: dict[str, str] = {}

    def tracked_parser(path: Path) -> list[dict[str, object]]:
        parsed = _parse_rdb_rows(path)
        if isinstance(parsed, tuple):
            rows, metadata = parsed
            parser_metadata.update(metadata)
            return rows
        return parsed

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
        stage_rdb_rows_to_mysql=stage_rdb_rows_to_mysql,
        load_preparsed_dataset_from_mysql=load_preparsed_dataset_from_mysql,
        mysql_read_query=mysql_read_query,
        path_b_collector=path_b_collector,
        path_c_collector=path_c_collector,
        parser=tracked_parser,
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
        **parser_metadata,
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
    stage_rdb_rows_to_mysql,
    load_preparsed_dataset_from_mysql,
    mysql_read_query,
    path_b_collector,
    path_c_collector,
    parser,
) -> NormalizedRdbDataset:
    paths = [Path(sample.source) for sample in request.inputs if sample.kind is not InputSourceKind.REMOTE_REDIS]

    if selected_route == PREPARSED_DATASET_ANALYSIS:
        if any(sample.kind is InputSourceKind.PREPARSED_MYSQL for sample in request.inputs):
            collector = path_b_collector or PathBMySQLPreparsedCollector(
                load_preparsed_dataset_from_mysql=load_preparsed_dataset_from_mysql,
                mysql_read_query=mysql_read_query,
            )
            return collector.collect(request)
        collector = path_b_collector or PathBPrecomputedCollector()
        return collector.collect(paths)

    if selected_route == DIRECT_RDB_ANALYSIS:
        collector = path_c_collector or PathCDirectParserCollector(parser=parser)
        return collector.collect(paths)

    if selected_route == DATABASE_BACKED_ANALYSIS:
        collector = path_a_collector
        if collector is None:
            if stage_rdb_rows_to_mysql is None or load_preparsed_dataset_from_mysql is None:
                raise ValueError(
                    "database_backed_analysis requires MySQL staging and dataset loading support."
                )
            collector = PathAMySQLBackedCollector(
                parser=parser,
                stage_rows_to_mysql=stage_rdb_rows_to_mysql,
                load_preparsed_dataset_from_mysql=load_preparsed_dataset_from_mysql,
            )
        return collector.collect(paths)

    raise ValueError(f"Unsupported analysis route: {selected_route}")


def _parse_rdb_rows(path: Path) -> tuple[list[dict[str, object]], dict[str, str]]:
    parsed = build_default_rdb_parser_strategy().parse_rows_result(path)
    metadata = {"parser_strategy": parsed.strategy_name}
    if parsed.strategy_detail:
        metadata["parser_binary"] = parsed.strategy_detail
    return parsed.rows, metadata
