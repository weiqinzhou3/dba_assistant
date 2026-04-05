from pathlib import Path

import dba_assistant.capabilities.redis_rdb_analysis as redis_rdb_analysis
from dba_assistant.capabilities.redis_rdb_analysis import types as types_module
from dba_assistant.capabilities.redis_rdb_analysis.types import (
    AnalysisStatus,
    ConfirmationRequest,
    EffectiveProfile,
    InputSourceKind,
    KeyRecord,
    NormalizedRdbDataset,
    RdbAnalysisRequest,
    SampleInput,
)


def test_rdb_analysis_request_defaults_to_generic_and_merged_output() -> None:
    request = RdbAnalysisRequest(
        prompt="analyze this rdb",
        inputs=[SampleInput(source=Path("/tmp/dump.rdb"), kind=InputSourceKind.LOCAL_RDB)],
    )

    assert request.profile_name == "generic"
    assert request.merge_multiple_inputs is True
    assert request.path_mode == "auto"


def test_normalized_dataset_keeps_sample_and_record_boundaries() -> None:
    dataset = NormalizedRdbDataset(
        samples=[
            SampleInput(
                source=Path("/tmp/a.rdb"),
                kind=InputSourceKind.LOCAL_RDB,
                label="host-a",
            )
        ],
        records=[
            KeyRecord(
                sample_id="sample-1",
                key_name="loan:10001",
                key_type="hash",
                size_bytes=2048,
                has_expiration=False,
                ttl_seconds=None,
                prefix_segments=("loan",),
            )
        ],
    )

    assert dataset.samples[0].label == "host-a"
    assert dataset.records[0].prefix_segments == ("loan",)


def test_confirmation_request_marks_remote_fetch_as_confirmation_required() -> None:
    response = ConfirmationRequest(
        status=AnalysisStatus.CONFIRMATION_REQUIRED,
        message="Existing RDB found on remote host.",
        required_action="fetch_existing",
    )

    assert response.status is AnalysisStatus.CONFIRMATION_REQUIRED
    assert response.required_action == "fetch_existing"


def test_effective_profile_defaults_to_empty_overrides() -> None:
    profile = EffectiveProfile(
        name="generic",
        sections=("overview", "top_keys"),
        focus_prefixes=("loan",),
    )

    assert profile.top_n == {}


def test_package_surface_reexports_contract_types() -> None:
    expected_exports = {
        "AnalysisStatus",
        "ConfirmationRequest",
        "EffectiveProfile",
        "InputSourceKind",
        "KeyRecord",
        "NormalizedRdbDataset",
        "RdbAnalysisRequest",
        "SampleInput",
    }

    assert set(redis_rdb_analysis.__all__) == expected_exports

    for export_name in expected_exports:
        assert getattr(redis_rdb_analysis, export_name) is getattr(types_module, export_name)
