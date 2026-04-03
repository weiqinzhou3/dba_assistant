from __future__ import annotations

from langchain_openai import ChatOpenAI

from dba_assistant.deep_agent_integration.config import ModelConfig, ProviderKind


def build_model(config: ModelConfig) -> ChatOpenAI:
    if config.provider_kind is not ProviderKind.OPENAI_COMPATIBLE:
        raise ValueError(f"Unsupported provider kind: {config.provider_kind}")

    return ChatOpenAI(
        model=config.model_name,
        api_key=config.api_key,
        base_url=config.base_url,
        temperature=config.temperature,
        stream_usage=False,
    )
