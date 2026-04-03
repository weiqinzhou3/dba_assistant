# Phase 2 Runtime Assembly Design

## Summary

This design defines the implementation boundary for `Phase 2` of the DBA Assistant project.

`Phase 2` is the first phase that turns the repository from a shared-layer foundation into a working Deep Agents SDK-based application skeleton. The goal is not to deliver full Redis inspection or CVE analysis behavior. The goal is to assemble the repository into a minimal, real, agent-capable system with:

- Deep Agents SDK wiring
- one real remote collection path
- a provider-capable model configuration layer
- clear documentation of model and provider pitfalls

As of April 1, 2026, this design is intentionally constrained to avoid leaking `Phase 4` and `Phase 5` behavior into `Phase 2`.

## Scope

### In Scope

- Create the repository-owned Deep Agents SDK integration layer under `src/dba_assistant/deep_agent_integration/`
- Implement configuration loading for provider presets and environment-variable overrides
- Implement model/provider construction for OpenAI-compatible endpoints
- Provide a minimal agent factory and tool registry using Deep Agents SDK
- Provide a minimal run entry for smoke validation
- Implement a real read-only Redis direct-connection adaptor
- Upgrade the remote collector layer from interface-only to a usable Phase 2 remote foundation
- Add one real remote collector path built on top of the Redis adaptor
- Add docs that explain model-provider pitfalls, especially DashScope regional behavior and Ollama compatibility assumptions

### Out of Scope

- SSH tunnel implementation
- MySQL live implementation
- Full Redis inspection business logic
- Full Redis CVE analysis business logic
- PDF or HTML rendering implementation
- Long-lived session management, conversation persistence, or durable orchestration
- Multi-provider runtime routing policies beyond preset-based configuration
- Any write-capable database or infrastructure operations

## Design Principles

### 1. Deep Agents SDK integration, not a custom runtime

The repository must remain explicit that Deep Agents SDK is the runtime foundation.

However, the repository must not introduce a generic `runtime/` layer that can be confused with the SDK itself. The repository-owned composition layer should therefore be named `deep_agent_integration/`, which communicates that:

- this is project glue code
- this is not a custom agent framework
- this is not a replacement for Deep Agents SDK internals

### 2. Strict phase isolation

`Phase 2` must stop at runtime assembly and one remote collection path.

It must not silently expand into:

- SSH transport engineering
- MySQL export and import work
- inspection report logic
- CVE enrichment and mapping logic
- full multi-format reporting

### 3. Provider-capable model configuration

The model layer must not assume OpenAI Platform is the only provider.

It must support OpenAI-compatible endpoints through centralized configuration so the same application structure can target:

- OpenAI-compatible commercial endpoints such as DashScope
- local OpenAI-compatible endpoints such as Ollama

This phase should optimize for the most stable compatibility path: OpenAI-compatible Chat Completions style provider wiring.

### 4. Default to China-region DashScope, document the international free path separately

The default preset should reflect the expected China-region usage path, not the free-tier path.

Default preset:

- provider kind: `openai_compatible`
- vendor: `dashscope`
- region preset: `cn`
- model: `qwen3.5-flash`
- base URL: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- API key env var: `DASHSCOPE_API_KEY`

Optional free-tier preset:

- provider kind: `openai_compatible`
- vendor: `dashscope`
- region preset: `intl`
- model: `qwen3.5-flash`
- base URL: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`
- API key env var: `DASHSCOPE_API_KEY`

The documentation must make explicit that "free" is region-specific and time-sensitive. It is not a repository guarantee.

### 5. Read-only remote access

All remote collection work in this phase must be explicitly read-only.

This includes:

- Redis direct connection operations
- tool surfaces exposed to the model
- adaptor APIs available to collectors

No raw passthrough command surface should be exposed.

## External Constraints

### Deep Agents SDK constraint

The Deep Agents SDK works with LangChain chat models that support tool calling. For OpenAI-compatible endpoints, the repository can build a provider-compatible LangChain chat model object and pass it into `create_deep_agent(...)`.

This supports keeping `Phase 2` provider wiring centralized, OpenAI-compatible, and provider-capable without depending on OpenAI Agents SDK abstractions.

### DashScope constraint

Alibaba Cloud documents an OpenAI-compatible mode for Qwen models and explicitly lists `qwen3.5-flash`, `qwen-plus`, and related models as compatible. Alibaba also documents function-calling support for Qwen model families.

As of April 1, 2026:

- China mainland deployment mode does not provide the free quota described for international mode
- international mode documents a limited free quota for specific new-user cases
- Alibaba explicitly recommends replacing `qwen-turbo` with `qwen-flash`

This means:

- the repository may offer an international free-tier preset
- the repository must not misrepresent the China preset as free
- `qwen3.5-flash` is the safer default than `qwen-turbo`

### Ollama constraint

Ollama documents OpenAI-compatible API endpoints. That makes it a valid target for the same centralized configuration shape used for DashScope.

However, OpenAI-compatible does not guarantee identical behavior across providers. Tool-calling behavior, streaming details, and edge-case compatibility can differ. The repository must document this as a compatibility caveat, not assume full equivalence.

## Repository Changes

The `Phase 2` design introduces the following repository-owned integration layer:

```text
src/dba_assistant/
├── deep_agent_integration/
│   ├── __init__.py
│   ├── README.md
│   ├── config.py
│   ├── model_provider.py
│   ├── agent_factory.py
│   ├── tool_registry.py
│   └── run.py
├── adaptors/
│   ├── redis_adaptor.py
│   ├── ssh_adaptor.py
│   └── mysql_adaptor.py
└── core/
    └── collector/
        └── remote_collector.py
```

The `skills/` tree remains phase-owned by later business phases, but one Redis-oriented remote collector may be implemented inside the appropriate skill collector path if needed to validate the remote data path.

## Component Design

### `deep_agent_integration/config.py`

Responsibilities:

- load repository-owned config files
- select provider presets
- normalize provider configuration into a single internal shape
- validate required fields
- surface clear error messages for missing provider configuration

This file must be the only place that knows:

- the default preset name
- provider base URLs
- API key fields
- default model identifiers

No skill, collector, tool, or adaptor should hardcode these values.

### `deep_agent_integration/model_provider.py`

Responsibilities:

- create the provider-compatible model objects needed by Deep Agents SDK integration
- branch on preset/provider kind
- apply compatibility flags if needed
- keep provider-specific setup isolated from business code

This layer should support at least:

- `dashscope_cn_qwen35_flash`
- `dashscope_intl_qwen35_flash_free`
- `ollama_local`
- one explicit custom `openai_compatible` override path for future extension

### `deep_agent_integration/tool_registry.py`

Responsibilities:

- define the Phase 2 tool surface
- register model-visible tools
- keep the tool list small and read-only
- avoid exposing transport-layer objects directly to the agent

Recommended initial tool surface:

- `redis_ping`
- `redis_info`
- `redis_config_get`
- `redis_slowlog_get`
- `redis_client_list`

Each tool should return structured data, not pre-written narrative text.

### `deep_agent_integration/agent_factory.py`

Responsibilities:

- build the minimal Phase 2 agent
- wire instructions, tool inventory, and provider model
- keep agent construction deterministic and centrally defined

This should create an integration-validation agent, not a fake fully implemented Phase 4 inspection agent.

### `deep_agent_integration/run.py`

Responsibilities:

- provide the minimal runnable entry for local validation
- run a simple prompt against the assembled agent
- support smoke validation of provider config and tool registration

This entry exists to verify assembly, not to define the final end-user interface.

### `adaptors/redis_adaptor.py`

Responsibilities:

- manage Redis direct connections
- expose a strictly bounded read-only API
- translate low-level client results into structured Python results
- centralize connection handling and timeout behavior

Allowed command surface:

- `PING`
- `INFO`
- `CONFIG GET`
- `SLOWLOG GET`
- `CLIENT LIST`

Explicitly disallowed in this phase:

- `CONFIG SET`
- `FLUSH*`
- `EVAL`
- arbitrary command passthrough
- mutation-oriented administration

### `core/collector/remote_collector.py`

Responsibilities:

- define the operational base for remote collection flows
- keep collection input and output structured
- remain transport-agnostic from the collector perspective

This is the layer that later phases can reuse for SSH and MySQL collection without changing the higher-level collector interface shape.

## Data Flow

The intended Phase 2 flow is:

1. load `AppConfig`
2. resolve provider preset and provider client/model
3. register read-only Redis tools
4. build the minimal integration-validation agent
5. execute a prompt through the SDK runner
6. if needed, tool calls invoke the Redis adaptor
7. tool outputs return structured results
8. the model produces the final natural-language response

This gives the repository one real, end-to-end Deep Agents SDK path without overcommitting to later business behavior.

## Testing Strategy

`Phase 2` should add tests at three levels:

### Unit

- config preset parsing
- provider selection and normalization
- Redis adaptor read-only method behavior
- tool registration shape

### Integration

- agent assembly smoke tests
- provider config validation without real credentials
- Redis adaptor integration against a controlled target if available

### Contract / Safety

- verify that no write-capable Redis commands are exposed
- verify that missing API keys fail with explicit configuration errors
- verify that provider preset switching does not require code changes in skills or adaptors

## Documentation Changes

`Phase 2` must update or add the following docs:

- `docs/phases/phase-2.md`
  - reflect the final Phase 2 implementation boundary
- `docs/phases/phase-1.md`
  - update the phase status so it no longer reads as planning-only after delivery
- `src/dba_assistant/README.md`
  - document `deep_agent_integration/` as the repository-owned Deep Agent SDK assembly layer
- `docs/phase-2-model-configuration-pitfalls.md`
  - explain provider and region pitfalls

## Model Configuration Pitfalls

The pitfall document must explicitly cover:

### 1. China preset is not the free preset

The default repository preset should be China-region DashScope for usability, but free quota details documented by Alibaba currently apply to international deployment mode, not China mainland deployment mode.

### 2. Free-tier assumptions can expire

Free quotas are vendor policy, not repository behavior. The document must include the date context and state that users must re-check provider pricing and quota policy.

### 3. Do not hardcode model config in skills

Provider selection, base URL, model name, and API key source must stay in the integration config layer only.

### 4. OpenAI-compatible is not behavior-identical

OpenAI-compatible endpoints may still differ in:

- tool-calling behavior
- parallel tool-calling support
- streaming behavior
- error payloads
- tracing expectations

### 5. Tracing may need special handling

When not using OpenAI Platform credentials, tracing behavior may need to be disabled or replaced according to the OpenAI Agents SDK guidance.

## Alternatives Considered

### Alternative A: create `src/dba_assistant/runtime/`

Rejected.

This risks conceptual confusion between:

- project-owned composition code
- Deep Agent SDK runtime behavior

The repository owner explicitly wants to avoid that confusion.

### Alternative B: make the international free Qwen preset the default

Rejected.

This would optimize for initial free usage at the cost of making the default behavior region-specific and easy to misunderstand for China-region users.

### Alternative C: implement SSH together with Redis direct access

Rejected for `Phase 2`.

This would introduce transport complexity that belongs to later phase work and would blur the boundary between runtime assembly and full remote operations engineering.

## Acceptance Criteria

`Phase 2` is complete when:

- a minimal Deep Agent SDK path is wired through repository-owned integration code
- a Redis direct-connection adaptor is functional and read-only
- the repository can switch between DashScope China, DashScope International, and Ollama-style OpenAI-compatible configuration without code changes in skills
- the agent can call the registered Redis tools through the SDK
- provider pitfalls and regional constraints are documented clearly
- no SSH or MySQL live implementation has been accidentally pulled into the phase
