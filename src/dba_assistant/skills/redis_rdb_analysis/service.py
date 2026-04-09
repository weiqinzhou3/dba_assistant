from __future__ import annotations

from pathlib import Path

from dba_assistant.application.request_models import RdbOverrides
from dba_assistant.application.request_models import DEFAULT_MYSQL_STAGE_BATCH_SIZE
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
from dba_assistant.capabilities.redis_rdb_analysis.collectors.streaming_aggregate_collector import (
    StreamingAggregateCollector,
)
from dba_assistant.capabilities.redis_rdb_analysis.path_router import choose_path
from dba_assistant.parsers.rdb_parser_strategy import (
    StreamedRowsResult,
    build_default_rdb_parser_strategy,
)
from dba_assistant.capabilities.redis_rdb_analysis.profile_resolver import resolve_profile
from dba_assistant.capabilities.redis_rdb_analysis.reports.assembler import assemble_report
from dba_assistant.capabilities.redis_rdb_analysis.reports.localization import report_title
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

LARGE_RDB_AUTO_SUMMARY_THRESHOLD_BYTES = 512 * 1024 * 1024


def analyze_rdb(
    request: RdbAnalysisRequest,
    *,
    profile,
    remote_discovery,
    path_a_collector=None,
    stage_rdb_rows_to_mysql=None,
    load_preparsed_dataset_from_mysql=None,
    mysql_read_query=None,
    analyze_staged_rdb_rows=None,
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

    def tracked_stream_parser(path: Path):
        parsed = _stream_rdb_rows(path)
        parser_metadata["parser_strategy"] = parsed.strategy_name
        if parsed.strategy_detail:
            parser_metadata["parser_binary"] = parsed.strategy_detail
        return parsed.rows

    if any(sample.kind is InputSourceKind.REMOTE_REDIS for sample in request.inputs):
        discovery = remote_discovery(request)
        rdb_path = _require_remote_rdb_path(discovery)
        return ConfirmationRequest(
            status=AnalysisStatus.CONFIRMATION_REQUIRED,
            message=f"Remote RDB available at {rdb_path}.",
            required_action="fetch_existing",
        )

    selected_route = choose_path(request)
    local_paths = [
        Path(sample.source)
        for sample in request.inputs
        if sample.kind is InputSourceKind.LOCAL_RDB
    ]
    large_rdb_protection = _should_enable_large_rdb_summary(
        request,
        selected_route=selected_route,
        local_paths=local_paths,
    )
    effective_profile = profile or resolve_profile(
        "large_rdb_summary" if large_rdb_protection else request.profile_name,
        RdbOverrides(**request.profile_overrides),
    )
    if selected_route == DATABASE_BACKED_ANALYSIS:
        if stage_rdb_rows_to_mysql is None or analyze_staged_rdb_rows is None:
            raise ValueError(
                "database_backed_analysis requires MySQL staging and MySQL-side aggregation support."
            )
        paths = [
            Path(sample.source)
            for sample in request.inputs
            if sample.kind is not InputSourceKind.REMOTE_REDIS
        ]
        collector = path_a_collector or PathAMySQLBackedCollector(
            stream_parser=tracked_stream_parser,
            stage_rows_to_mysql=stage_rdb_rows_to_mysql,
            table_name=request.mysql_table,
            batch_size=request.mysql_stage_batch_size or DEFAULT_MYSQL_STAGE_BATCH_SIZE,
            mysql_target_host=request.mysql_host,
            mysql_target_port=request.mysql_port,
            mysql_target_database=request.mysql_database,
        )
        staging = collector.collect(paths)
        sample_rows = [
            [
                sample.label or f"sample-{index}",
                sample.kind.value,
                str(sample.source),
            ]
            for index, sample in enumerate(request.inputs, start=1)
            if sample.kind is not InputSourceKind.REMOTE_REDIS
        ]
        analysis_result = analyze_staged_rdb_rows(
            staging,
            profile=effective_profile,
            sample_rows=sample_rows,
        )
        report = assemble_report(
            analysis_result,
            profile=effective_profile,
            title=report_title(request.report_language),
            language=request.report_language,
        )
        metadata = {
            **report.metadata,
            "input_count": str(len(sample_rows)),
            "route": selected_route,
            "mysql_host": staging.mysql_host or request.mysql_host or "",
            "mysql_port": "" if staging.mysql_port is None and request.mysql_port is None else str(staging.mysql_port or request.mysql_port or ""),
            "mysql_database": staging.database_name or request.mysql_database or "",
            "mysql_table": staging.table_name,
            "mysql_run_id": staging.run_id,
            "mysql_staged_rows": str(staging.row_count),
            "mysql_stage_batch_size": str(staging.batch_size),
            "mysql_multi_file_shared_table": "yes",
            "mysql_full_table_reload": "disabled",
            "mysql_cleanup_mode": staging.cleanup_mode,
            "mysql_created_database": "yes" if staging.created_database else "no",
            "mysql_created_table": "yes" if staging.created_table else "no",
            "mysql_defaulted_database": "yes" if staging.defaulted_database else "no",
            "mysql_defaulted_table": "yes" if staging.defaulted_table else "no",
            "mysql_progress": " | ".join(staging.progress),
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
            language=report.language,
        )

    if selected_route == DIRECT_RDB_ANALYSIS and path_c_collector is None:
        collector = StreamingAggregateCollector(
            stream_parser=_stream_direct_rdb_rows,
            profile=effective_profile,
        )
        aggregated = collector.collect(local_paths)
        report = assemble_report(
            aggregated.analysis_result,
            profile=effective_profile,
            title=report_title(request.report_language),
            language=request.report_language,
        )
        metadata = {
            **report.metadata,
            "input_count": str(len(local_paths)),
            "route": selected_route,
            **aggregated.metadata,
        }
        if large_rdb_protection:
            metadata["large_rdb_protection"] = "enabled"
            metadata["large_rdb_threshold_bytes"] = str(LARGE_RDB_AUTO_SUMMARY_THRESHOLD_BYTES)
            metadata["large_rdb_input_bytes"] = str(_total_input_bytes(local_paths))
        metadata.update(parser_metadata)
        legacy_path_label = phase_label_for_route_name(selected_route)
        if legacy_path_label is not None:
            metadata["path"] = legacy_path_label
        return AnalysisReport(
            title=report.title,
            summary=report.summary,
            sections=report.sections,
            metadata=metadata,
            language=report.language,
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
        title=report_title(request.report_language),
        language=request.report_language,
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
        language=report.language,
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

    raise ValueError(f"Unsupported analysis route: {selected_route}")


def _parse_rdb_rows(path: Path) -> tuple[list[dict[str, object]], dict[str, str]]:
    parsed = build_default_rdb_parser_strategy().parse_rows_result(path)
    metadata = {"parser_strategy": parsed.strategy_name}
    if parsed.strategy_detail:
        metadata["parser_binary"] = parsed.strategy_detail
    return parsed.rows, metadata


def _stream_rdb_rows(path: Path):
    try:
        return build_default_rdb_parser_strategy().stream_rows_result(path)
    except Exception:
        parsed = _parse_rdb_rows(path)
        metadata: dict[str, str] = {}
        rows = parsed
        if isinstance(parsed, tuple):
            rows, metadata = parsed
        return StreamedRowsResult(
            rows=iter(rows),
            strategy_name=metadata.get("parser_strategy", "materialized_fallback"),
            strategy_detail=metadata.get("parser_binary"),
        )


_DEFAULT_PARSE_RDB_ROWS = _parse_rdb_rows


def _stream_direct_rdb_rows(path: Path) -> StreamedRowsResult:
    if _parse_rdb_rows is not _DEFAULT_PARSE_RDB_ROWS:
        parsed = _parse_rdb_rows(path)
        metadata: dict[str, str] = {}
        rows = parsed
        if isinstance(parsed, tuple):
            rows, metadata = parsed
        return StreamedRowsResult(
            rows=iter(rows),
            strategy_name=metadata.get("parser_strategy", "materialized_override"),
            strategy_detail=metadata.get("parser_binary"),
        )
    return _stream_rdb_rows(path)


def _should_enable_large_rdb_summary(
    request: RdbAnalysisRequest,
    *,
    selected_route: str,
    local_paths: list[Path],
) -> bool:
    if selected_route != DIRECT_RDB_ANALYSIS:
        return False
    if request.path_mode != "auto":
        return False
    if request.profile_name.strip().lower() != "generic":
        return False
    overrides = RdbOverrides(**request.profile_overrides)
    if overrides.focus_only or overrides.focus_prefixes:
        return False
    return any(
        _safe_stat_size(path) > LARGE_RDB_AUTO_SUMMARY_THRESHOLD_BYTES
        for path in local_paths
    )


def _safe_stat_size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def _total_input_bytes(paths: list[Path]) -> int:
    return sum(_safe_stat_size(path) for path in paths)


def _require_remote_rdb_path(discovery: object) -> str:
    if not isinstance(discovery, dict):
        raise ValueError("remote_discovery did not return a dictionary payload")
    rdb_path = discovery.get("rdb_path")
    if not isinstance(rdb_path, str) or not rdb_path.strip():
        raise ValueError("remote_discovery did not return rdb_path")
    return rdb_path
