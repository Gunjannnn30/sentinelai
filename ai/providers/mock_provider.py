"""Deterministic local mock provider.

This adapter is what makes SentinelAI runnable with **zero** credentials:

- It performs *no* network calls and *invents no model output* — it echoes a
  clearly-labelled simulated response derived from the prompt, so nobody can
  mistake it for a real model answer.
- Responses are deterministic → stable tests and demos.
- Every response carries the marker ``[MOCK PROVIDER — SIMULATED OUTPUT]``.
- It can be forced to fail (``forced_error``) so error paths are testable.
"""
from __future__ import annotations

import time
from typing import Any

from ai.providers.base import ChatRequest, ProviderAdapter, ProviderError, ProviderResponse, Usage

MOCK_MODELS = [
    {"id": "sentinel-mock-small", "label": "Sentinel Mock Small (simulated)", "context": 8192},
    {"id": "sentinel-mock-large", "label": "Sentinel Mock Large (simulated)", "context": 32768},
]

MARKER = "[MOCK PROVIDER — SIMULATED OUTPUT]"


class MockAdapter(ProviderAdapter):
    kind = "mock"
    is_demo = True

    def __init__(self, *, base_url: str = "", api_key: str = "", timeout: float = 60.0,
                 forced_error: str | None = None) -> None:
        super().__init__(base_url=base_url, api_key=api_key, timeout=timeout)
        self.forced_error = forced_error

    def available(self) -> bool:
        return True

    def list_models(self) -> list[dict[str, Any]]:
        return [{"id": m["id"]} for m in MOCK_MODELS]

    def chat(self, request: ChatRequest) -> ProviderResponse:
        if self.forced_error:
            raise ProviderError(
                f"Mock provider forced failure: {self.forced_error}",
                category=self.forced_error,
                provider=self.kind,
                retryable=self.forced_error in {"timeout", "unavailable", "rate_limited"},
            )
        start = time.perf_counter()
        last_user = next(
            (m["content"] for m in reversed(request.messages) if m["role"] == "user"), ""
        )
        summary = last_user.strip().replace("\n", " ")[:240]
        system_note = next(
            (m["content"] for m in request.messages if m["role"] == "system"), ""
        )
        content = (
            f"{MARKER}\n\n"
            f"This is a deterministic local response from the SentinelAI mock provider. "
            f"No external model was called.\n\n"
            f"Echo of your request ({len(last_user)} chars):\n"
            f"\"{summary}\"\n"
        )
        if system_note:
            content += f"\nSystem instructions received: {len(system_note)} chars (not executed)."
        # Deterministic fake-but-honest token accounting (chars/4).
        prompt_chars = sum(len(m["content"]) for m in request.messages)
        prompt_tokens = max(1, prompt_chars // 4)
        completion_tokens = max(1, len(content) // 4)
        latency = self._timed(start) or 1
        return ProviderResponse(
            content=content,
            model=request.model,
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            finish_reason="stop",
            raw={"simulated": True},
            latency_ms=latency,
        )
