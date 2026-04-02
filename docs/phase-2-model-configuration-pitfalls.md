# Phase 2 Model Configuration Pitfalls

This note captures the model/provider assumptions that matter for Phase 2. The source of truth for behavior is `src/dba_assistant/deep_agent_integration/config.py`.

## Pitfalls to Avoid

- The default DashScope China preset is not the free preset.
- Any international free-tier assumption is vendor policy, not a repository guarantee, and it can change or expire.
- Do not hardcode model configuration outside the Deep Agent SDK integration layer.
- OpenAI-compatible does not mean behavior-identical across DashScope and Ollama.
- Tracing may need provider-specific handling. Phase 2 defaults tracing to disabled.

## What This Means in Practice

- Keep preset selection, base URLs, model names, and API key resolution inside `deep_agent_integration/`.
- Treat DashScope China, DashScope International, and Ollama as compatible integration targets, not interchangeable runtimes.
- If a provider behaves differently, adjust the integration layer and docs instead of spreading provider-specific assumptions into skills, collectors, or adaptors.
- Leave tracing off by default unless a provider path has been validated with the current SDK and credentials.
