# Phase 3 RDB Flow

This document explains how Phase 3 turns a prompt-first CLI request into an analysis report. The important boundary is the normalized request: once the CLI and explicit flags have been resolved into that structure, the application layer can execute the request without caring whether it came from the terminal, a future GUI, or a future API.

## 1. Normalized Request Model

The normalized request is the handoff object between the CLI and the application layer.

At a minimum, it carries:

| Field | Meaning |
|------|---------|
| `raw_prompt` | The original user prompt before cleanup or extraction. |
| `prompt` | The normalized prompt text after secret stripping and whitespace cleanup. |
| `runtime_inputs` | Structured runtime inputs such as `redis_host`, `redis_port`, `redis_db`, `output_mode`, and `input_paths`. |
| `secrets` | Secret material extracted from the prompt, such as the Redis password. |
| `rdb_overrides` | Prompt-derived RDB preferences such as `profile_name`, `focus_prefixes`, and `top_n` overrides. |
| `path_mode` | The route selector when a caller needs to force `legacy_sql_pipeline`, `precomputed_dataset`, or `direct_memory_analysis`. |
| `merge_multiple_inputs` | Whether multiple local inputs should be analyzed as one combined request. |

The CLI should not execute business logic directly. It should only build this normalized shape and pass it forward.

## 2. Route Resolution

Phase 3 uses formal route names internally:

- `legacy_sql_pipeline`
- `precomputed_dataset`
- `direct_memory_analysis`

The mapping back to the phase labels is:

| Phase label | Formal route name | Meaning |
|------------|-------------------|---------|
| `3a` | `legacy_sql_pipeline` | RDB parsing plus MySQL staging and SQL aggregation before report generation. |
| `3b` | `precomputed_dataset` | Already-normalized analysis data is rendered directly into a report. |
| `3c` | `direct_memory_analysis` | Local RDB parsing and in-memory analysis without the SQL staging path. |

Route selection follows the normalized request:

1. If a caller already set `path_mode`, that route wins.
2. If the request contains precomputed inputs, the resolver chooses `precomputed_dataset`.
3. If the prompt includes an SQL-style hint, the resolver chooses `legacy_sql_pipeline`.
4. Otherwise, the request falls through to `direct_memory_analysis`.

That ordering keeps the route selection deterministic while still letting the prompt express intent.

## 3. Profile Resolution

Profile resolution happens after route selection, because the route says how to collect data and the profile says how to interpret it.

The resolver:

- loads the named profile from the repository-owned profile set
- defaults to `generic` when no profile is specified
- accepts `rcs` when the prompt or explicit flag asks for that profile
- merges prompt-derived overrides into the profile defaults

The prompt can influence the profile through natural language, but explicit CLI flags still override the prompt when both are present.

## 4. Report Generation Flow

Once the route and profile are known, the data flow is straightforward:

1. The collector normalizes the source data into a `NormalizedRdbDataset`.
2. The analyzer computes the RDB analysis result for the selected profile.
3. The reporter assembles an `AnalysisReport`.
4. `generate_analysis_report` renders the final artifact in the requested output mode.

The renderer is intentionally generic. Phase 3 should not have a separate report pipeline for each route or each profile.

## 5. Confirmation-Required Remote Flow

Remote Redis is special because the request may need to inspect a live host before it can acquire an RDB file.

The safe sequence is:

1. The request identifies a remote Redis input.
2. The analysis layer performs read-only discovery, such as calling persistence metadata plus `dir` and `dbfilename` lookups to determine the expected RDB path.
3. If a real acquisition would occur next, the service returns a `ConfirmationRequest` with `status=confirmation_required` and `required_action=fetch_existing`.
4. The caller must confirm the action before any fetch happens.
5. After confirmation, the flow resumes with the normal route selection and report generation steps.

This keeps the remote path read-only until a human explicitly approves acquisition.

## 6. Exact Example Flow

For the request:

```text
按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx
```

the flow is:

1. The CLI receives the raw prompt and any explicit flags, including the local RDB path when the user supplies one with `--input`.
2. Prompt parsing extracts `rcs` as the profile intent and records the docx/report intent plus the destination path.
3. Explicit CLI parameters, if present, override any conflicting prompt-derived values.
4. The CLI builds the normalized request and passes it to the application layer.
5. The application layer treats the request as an RDB analysis job and calls `analyze_rdb`.
6. `analyze_rdb` resolves the route from the normalized request:
   - local RDB input with no SQL-style hint falls through to `direct_memory_analysis`
   - precomputed input chooses `precomputed_dataset`
   - SQL-style hints choose `legacy_sql_pipeline`
7. `profile_resolver` loads `rcs` and merges any prompt overrides into the profile defaults.
8. The collector produces a normalized dataset from the chosen input path.
9. The analyzer and report assembler produce the `AnalysisReport`.
10. `generate_analysis_report` renders the final artifact.
11. The artifact is written to `/tmp/rcs.docx` when the request asks for a file-backed report, or emitted as summary output when the request selects summary mode.

That sequence is the core Phase 3 architecture: prompt first, normalized request second, route/profile resolution third, report rendering last.
