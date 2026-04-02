from __future__ import annotations

from agents import AsyncOpenAI, OpenAIChatCompletionsModel, set_tracing_disabled

from dba_assistant.deep_agent_integration.config import ModelConfig, ProviderKind


def build_model(config: ModelConfig) -> OpenAIChatCompletionsModel:
    if config.provider_kind is not ProviderKind.OPENAI_COMPATIBLE:
        raise ValueError(f"Unsupported provider kind: {config.provider_kind}")

    set_tracing_disabled(disabled=config.tracing_disabled)
    client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)
    return OpenAIChatCompletionsModel(
        model=config.model_name,
        openai_client=client,
    )
