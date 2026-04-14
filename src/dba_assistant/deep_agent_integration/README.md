# deep_agent_integration

This package contains the repository-owned Deep Agents SDK assembly layer.

It is not a custom runtime framework and it is not the CLI presentation layer.

Its responsibilities are limited to:

- loading static application configuration
- building provider-compatible LangChain chat models
- exposing repository policy and skill sources to the runtime
- constructing runtime support primitives such as backend and checkpointer
- explicitly loading repository policy from `AGENTS.md`
- staying free of business routing and phase-specific helper entry points
