```yaml
skill:
  name: redis-rdb-analysis
  description: Phase 3 Redis RDB analysis with profile-driven routing and confirmation-gated remote acquisition.

status:
  phase_owner: phase-3
  implementation_status: phase-3-active
  execution_status: runnable

phase_3_scope:
  owns_package_path: src/dba_assistant/skills/redis_rdb_analysis/
  supported_paths:
    - 3a
    - 3b
    - 3c
  supported_profiles:
    - generic
    - rcs

input_contract:
  request_model: RdbAnalysisRequest
  request_fields:
    - prompt
    - inputs
    - profile_name
    - path_mode
    - merge_multiple_inputs
    - profile_overrides
  input_sources:
    - local_rdb
    - remote_redis
    - precomputed
  confirmation_model: ConfirmationRequest
  confirmation_behavior:
    - remote Redis discovery pauses before acquisition when the requested action requires fetching an existing RDB
    - confirmation status uses AnalysisStatus.CONFIRMATION_REQUIRED

output_contract:
  dataset_model: NormalizedRdbDataset
  profile_model: EffectiveProfile
  record_model: KeyRecord
  sample_model: SampleInput
```

Notes:

- This file defines the Phase 3 skill contract and ownership boundaries.
- Later-phase analyzer, collector, and report assembly behavior must continue to align with these contracts.
- The skill is intended for integration into the repository's Deep Agent SDK runtime.
