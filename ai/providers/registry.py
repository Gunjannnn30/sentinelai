"""Provider registry: builds adapters from configuration (server-side secrets only)."""
from __future__ import annotations

from typing import Any

from ai.providers.anthropic_provider import AnthropicAdapter
from ai.providers.base import ProviderAdapter, ProviderError
from ai.providers.gemini_provider import GeminiAdapter
from ai.providers.mock_provider import MockAdapter
from ai.providers.ollama_provider import OllamaAdapter
from ai.providers.openai_provider import OpenAIAdapter

ADAPTER_TYPES: dict[str, type[ProviderAdapter]] = {
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "gemini": GeminiAdapter,
    "ollama": OllamaAdapter,
    "mock": MockAdapter,
}


def build_adapter(
    kind: str,
    *,
    base_url: str = "",
    api_key: str = "",
    timeout: float = 60.0,
    extra: dict[str, Any] | None = None,
) -> ProviderAdapter:
    cls = ADAPTER_TYPES.get(kind)
    if cls is None:
        raise ProviderError(
            f"Unknown provider kind '{kind}'. Supported: {sorted(ADAPTER_TYPES)}.",
            category="invalid_request", provider=kind, retryable=False,
        )
    kwargs: dict[str, Any] = {"base_url": base_url, "api_key": api_key, "timeout": timeout}
    if cls is MockAdapter and extra:
        kwargs["forced_error"] = extra.get("forced_error")
    return cls(**kwargs)
