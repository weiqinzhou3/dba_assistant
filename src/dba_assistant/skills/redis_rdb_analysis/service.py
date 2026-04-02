from __future__ import annotations

from dba_assistant.application.request_models import RdbOverrides
from dba_assistant.skills.redis_rdb_analysis.path_router import choose_path
from dba_assistant.skills.redis_rdb_analysis.profile_resolver import resolve_profile
from dba_assistant.skills.redis_rdb_analysis.types import (
    AnalysisStatus,
    ConfirmationRequest,
    InputSourceKind,
    RdbAnalysisRequest,
)


def analyze_rdb(request: RdbAnalysisRequest, *, profile, remote_discovery):
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
    return {"path": selected_path, "profile": effective_profile.name}
