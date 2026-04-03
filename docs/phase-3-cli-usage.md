# Phase 3 CLI Usage

Phase 3 is prompt-first. The user starts with a natural-language request, and the CLI turns that request into a normalized analysis job. The prompt carries the primary intent; the retained flags are only there to supply structured overrides, local paths, and deterministic configuration.

## Primary Command

```sh
dba-assistant ask "<prompt>"
```

Examples:

```sh
dba-assistant ask "Analyze this RDB and give me a summary" --input /path/to/dump.rdb
dba-assistant ask "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx" --input /path/to/dump.rdb
```

## Retained Parameters

The following flags stay on the public surface because they are useful for local debugging, repeatable execution, and future structured callers.

| Flag | Meaning | Notes |
|------|---------|-------|
| `--config` | Load an explicit repository config file. | Use this when you want to override the default runtime configuration, including provider and default output behavior. |
| `--input` | Provide one or more local input paths. | Repeatable. In the current CLI, each path is treated as a local analysis source. |
| `--profile` | Force the analysis profile. | Typical values are `generic` and `rcs`. This overrides any profile implied by the prompt. |
| `--report-format` | Force the rendered output format. | The current CLI supports `summary` and `docx`. `docx` requires an output destination, either in the prompt or via `--output`. |
| `--output` | Force the output target. | Use this for an explicit file path. It overrides any output path mentioned in the prompt and is required when the effective format is `docx`. |

## Precedence

The execution order is fixed:

1. Parse the prompt first.
2. Apply explicit CLI parameters second.
3. Let explicit parameters override any conflicting prompt-derived values.
4. Execute only the final normalized request.

That means a user can say `rcs` or `docx` in the prompt, but an explicit `--profile generic` or `--report-format summary` still wins.

## Usage Patterns

### Generic Profile

Use the generic profile when you want the default RDB analysis shape and do not need profile-specific overrides.

```sh
dba-assistant ask "Analyze this RDB and give me a concise summary" --input ./dump.rdb
```

What this means:

- prompt is parsed for analysis intent
- no profile override is supplied, so `generic` remains the effective profile
- the local RDB path enters the normalized request through `--input`

### `rcs` Profile

Use `rcs` when you want the profile-specific section layout and profile defaults associated with that report style.

```sh
dba-assistant ask "按 rcs profile 分析这个 rdb，输出 docx，到 /tmp/rcs.docx" --input ./dump.rdb
```

What this means:

- the prompt selects the `rcs` profile
- the prompt also expresses docx output intent and the destination path
- the local RDB file still comes from `--input`

### Local RDB Input

Use `--input` for local RDB files or local fixture paths that the CLI should analyze.

```sh
dba-assistant ask "Analyze the local RDB and focus on TTL distribution" --input ./fixtures/dump.rdb
```

What this means:

- the prompt describes the analysis focus
- the local file path is carried explicitly in the normalized request
- the application layer can treat the request as a local-file analysis job

### Precomputed Input

Phase 3 has a `precomputed_dataset` route, but the current `ask` CLI does not yet expose a separate input-kind flag for it.

```sh
dba-assistant ask "Use the precomputed dataset and generate the report"
```

What this means:

- the Phase 3 architecture reserves a `precomputed_dataset` route for already-exported analysis data
- the current CLI debug shell does not yet wire `--input` into that route
- today this path is exercised by lower-level service and tool callers rather than by the public `ask` surface

### Remote Redis Confirmation Flow

Remote Redis requests are intentionally not fire-and-forget. Phase 3 defines a confirmation-gated remote flow, but the current prompt-first CLI does not yet expose a direct remote-input flag.

```sh
dba-assistant ask "Analyze the latest RDB from redis.example:6379 and confirm before fetching"
```

Expected behavior:

- the Phase 3 service contract supports remote discovery before any acquisition happens
- if a real RDB acquisition is needed, the service returns a confirmation-required result
- only after explicit confirmation does the flow proceed to fetch and analyze the RDB
- the current CLI does not yet drive this branch directly; at the moment it rejects this prompt shape instead of silently falling through to Phase 2

This confirmation gate is part of the public Phase 3 contract. It protects remote data acquisition from happening automatically just because a user asked a question in natural language.
