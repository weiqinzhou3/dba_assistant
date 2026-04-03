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
| `--input` | Provide one or more local input paths. | Repeatable. Each path becomes part of the normalized request and can point to an RDB file or to precomputed analysis data. |
| `--profile` | Force the analysis profile. | Typical values are `generic` and `rcs`. This overrides any profile implied by the prompt. |
| `--report-format` | Force the rendered output format. | This is the explicit rendering choice, such as `summary`, `docx`, `pdf`, or `html`. |
| `--output` | Force the output target. | Use this for an explicit file path or summary destination. It overrides any output path mentioned in the prompt. |

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

Use `--input` for local RDB files, fixtures, or local directories that the CLI should analyze.

```sh
dba-assistant ask "Analyze the local RDB and focus on TTL distribution" --input ./fixtures/dump.rdb
```

What this means:

- the prompt describes the analysis focus
- the local file path is carried explicitly in the normalized request
- the application layer can treat the request as a local-file analysis job

### Precomputed Input

Use `--input` with precomputed analysis data when the RDB parsing step has already been done.

```sh
dba-assistant ask "Use the precomputed dataset and generate the report" --input ./precomputed/analysis.json
```

What this means:

- the request is still prompt-first
- the caller is telling Phase 3 that the input is already normalized data
- the route resolver can choose the precomputed dataset path instead of parsing raw RDB bytes again

### Remote Redis Confirmation Flow

Remote Redis requests are intentionally not fire-and-forget. If the prompt refers to the latest RDB on a remote Redis instance, the flow pauses before acquisition.

```sh
dba-assistant ask "Analyze the latest RDB from redis.example:6379 and confirm before fetching"
```

Expected behavior:

- the prompt identifies a remote Redis target
- the analysis layer performs read-only discovery first
- if a real RDB acquisition is needed, the request returns a confirmation-required result
- only after explicit confirmation does the flow proceed to fetch and analyze the RDB

This confirmation gate is part of the public Phase 3 contract. It protects remote data acquisition from happening automatically just because a user asked a question in natural language.

