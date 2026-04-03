# deep_agent_integration

This package contains the repository-owned Deep Agents SDK assembly layer.

It is not a custom runtime framework and it is not the CLI presentation layer.

Its responsibilities are limited to:

- loading static application configuration
- building provider-compatible LangChain chat models
- registering model-visible tools
- constructing the minimal Phase 2 agent
- explicitly loading repository policy from `AGENTS.md`
- invoking the deep agent for normalized requests
