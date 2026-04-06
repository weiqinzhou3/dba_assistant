# Phase 5 Observability / Audit Baseline

This note documents the repository-native observability baseline added for Phase 5.

## Scope

The baseline is attached to the shared execution shape:

`CLI / API / WebUI -> interface adapter -> one Deep Agent -> skills/tools`

It is not CLI-only logging.

Implemented coverage:

- interface boundary
- unified execution lifecycle
- tool invocation sequence
- approval / HITL events
- artifact / output metadata
- structured application logs for existing performance signals

## Configuration

`config/config.yaml` now supports:

```yaml
observability:
  enabled: true
  level: INFO
  console_enabled: true
  log_dir: outputs/logs
  app_log_file: app.log.jsonl
  audit_log_file: audit.jsonl
```

Notes:

- Relative paths resolve from the repository root.
- Absolute paths are supported.
- `enabled: false` disables file/console observability bootstrap for that config.
- Secrets are sanitized before normal logs and audit records are persisted.

## Audit Event Shape

Audit output is append-only JSONL. Each line is a first-class event.

Core fields:

- `timestamp`
- `event_type`
- `execution_id`
- `interface_surface`
- `start_timestamp`

Execution summary events additionally include:

- `normalized_request_summary`
- `selected_capability`
- `dominant_skill`
- `selected_route`
- `tool_invocation_sequence`
- `final_status`
- `output_mode`
- `output_path`
- `artifact_id`
- `report_metadata`

Approval events additionally include:

- `action`
- `message`
- `details`
- `approval_outcome`
- `rejection_reason`

## Sample `audit.jsonl`

```json
{"timestamp":"2026-04-07T10:12:03.120000+00:00","event_type":"execution_started","execution_id":"exec-2b2c0ad0-5e5f-4db8-a86f-f3c1fe5f47b4","interface_surface":"cli","start_timestamp":"2026-04-07T10:12:03.119000+00:00","normalized_request_summary":{"prompt_summary":"analyze /data/dump.rdb password=<redacted>","input_kind":"local_rdb","path_mode":"auto","input_paths":["/data/dump.rdb"],"profile_name":"generic","output_mode":"report","report_format":"docx","output_path":"/Users/zqw/Desktop/Project/dba_assistant/outputs/report.docx","secret_presence":{"redis_password":true,"ssh_password":false,"mysql_password":false}},"raw_request_summary":{"surface":"cli","prompt_summary":"analyze /data/dump.rdb password=<redacted>"}} 
{"timestamp":"2026-04-07T10:12:03.420000+00:00","event_type":"tool_completed","execution_id":"exec-2b2c0ad0-5e5f-4db8-a86f-f3c1fe5f47b4","interface_surface":"cli","start_timestamp":"2026-04-07T10:12:03.119000+00:00","tool_name":"analyze_local_rdb","tool_args_summary":{"input_paths":["/data/dump.rdb"],"redis_password":"<redacted>"},"status":"success","started_at":"2026-04-07T10:12:03.121000+00:00","ended_at":"2026-04-07T10:12:03.419000+00:00","duration_ms":298}
{"timestamp":"2026-04-07T10:12:03.430000+00:00","event_type":"artifact_generated","execution_id":"exec-2b2c0ad0-5e5f-4db8-a86f-f3c1fe5f47b4","interface_surface":"cli","start_timestamp":"2026-04-07T10:12:03.119000+00:00","output_mode":"report","output_path":"/Users/zqw/Desktop/Project/dba_assistant/outputs/report.docx","artifact_id":"/Users/zqw/Desktop/Project/dba_assistant/outputs/report.docx","report_metadata":{"route":"direct_rdb_analysis","rows_processed":"1823401"}}
{"timestamp":"2026-04-07T10:12:03.431000+00:00","event_type":"execution_completed","execution_id":"exec-2b2c0ad0-5e5f-4db8-a86f-f3c1fe5f47b4","interface_surface":"cli","start_timestamp":"2026-04-07T10:12:03.119000+00:00","end_timestamp":"2026-04-07T10:12:03.431000+00:00","final_status":"success","selected_capability":"analyze_local_rdb","dominant_skill":"redis_rdb_analysis","selected_route":"direct_rdb_analysis","output_mode":"report","output_path":"/Users/zqw/Desktop/Project/dba_assistant/outputs/report.docx","artifact_id":"/Users/zqw/Desktop/Project/dba_assistant/outputs/report.docx","report_metadata":{"route":"direct_rdb_analysis","rows_processed":"1823401"},"tool_invocation_sequence":[{"tool_name":"analyze_local_rdb","tool_args_summary":{"input_paths":["/data/dump.rdb"],"redis_password":"<redacted>"},"status":"success","started_at":"2026-04-07T10:12:03.121000+00:00","ended_at":"2026-04-07T10:12:03.419000+00:00","duration_ms":298}]}
```

## Sample `app.log.jsonl`

```json
{"timestamp":"2026-04-07T10:13:41.018000+00:00","level":"INFO","logger":"dba_assistant.capabilities.redis_rdb_analysis.collectors.streaming_aggregate_collector","message":"streaming aggregate progress","execution_id":"exec-1f8cb84f-e82a-4e76-a987-1a2bb6f0ce46","interface_surface":"cli","event_name":"redis_rdb_stream_progress","path":"/data/big.rdb","parser_strategy":"python_stream","rows_processed":100000,"peak_memory_bytes_estimate":73400320}
{"timestamp":"2026-04-07T10:13:44.992000+00:00","level":"INFO","logger":"dba_assistant.capabilities.redis_rdb_analysis.collectors.streaming_aggregate_collector","message":"streaming aggregate total complete","execution_id":"exec-1f8cb84f-e82a-4e76-a987-1a2bb6f0ce46","interface_surface":"cli","event_name":"redis_rdb_stream_phase","phase":"parse_aggregate_total","rows_processed":1823401,"rows_per_sec":456712.44,"elapsed_seconds":3.993,"peak_memory_bytes_estimate":125829120}
```

## Sanitization Rules

The shared sanitizer currently redacts:

- `redis_password`
- `ssh_password`
- `mysql_password`
- `api_key`
- prompt / message fragments such as `password=...` and `secret: ...`
- approval detail fields whose keys match password/secret/token/api-key patterns

This applies to:

- audit JSONL events
- structured app logs
- CLI approval detail display when approval auditing is enabled

## Current Extension Points

Not implemented in Phase 5:

- full trace/span propagation
- distributed request correlation across external systems
- OTLP / ELK / Loki exporters
- retention, rotation, or archival policies

Reasonable next steps:

- request correlation IDs across adapter -> tool -> artifact
- trace/span IDs for expensive collectors
- audit log rotation and retention controls
- exporter adapters for ELK / Loki ingestion
