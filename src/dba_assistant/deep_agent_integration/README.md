# deep_agent_integration

This package contains the repository-owned Deep Agent SDK assembly layer.

It is not a custom runtime framework and it is not the CLI presentation layer.

Its responsibilities are limited to:

- loading static application configuration
- building provider-compatible model objects
- registering model-visible tools
- constructing the minimal Phase 2 agent
- invoking the Runner for normalized requests
