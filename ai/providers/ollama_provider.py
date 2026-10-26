"""Ollama adapter — local models via ``/api/chat`` (no credentials required)."""
from __future__ import annotations

import time
from typing import Any

import httpx

from ai.providers.base import (
    ChatRequest,
    ProviderAdapter,
    ProviderError,
    ProviderResponse,
    Usage,
    classify_http_error,
)


class OllamaAdapter(ProviderAdapter):
    kind = "ollama"

    def available(self) -> bool:
        return bool(self.base_url)

    def list_models(self) -> list[dict[str, Any]]:
        if not self.available():
            return []
        start = time.perf_counter()
        try:
            with httpx.Client(base_url=self.base_url, timeout=min(self.timeout, 10.0)) as client:
                resp = client.get("/api/tags")
            if resp.status_code >= 400:
                raise classify_http_error(resp.status_code, resp.text, self.kind)
            models = resp.json().get("models", [])
            return [{"id": m.get("name", "")} for m in models if m.get("name")]
        except httpx.TimeoutException as exc:
            raise ProviderError(
                f"Ollama is not reachable at {self.base_url}. Start it with `ollama serve`.",
                category="unavailable", provider=self.kind, retryable=False,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Ollama is not reachable at {self.base_url}: {exc}. Start it with `ollama serve`.",
                category="unavailable", provider=self.kind, retryable=False,
            ) from exc
        finally:
            _ = self._timed(start)

    def chat(self, request: ChatRequest) -> ProviderResponse:
        self._require_credentials()
        payload: dict[str, Any] = {"model": request.model, "messages": request.messages}
        options: dict[str, Any] = {}
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if options:
            payload["options"] = options

        start = time.perf_counter()
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                resp = client.post("/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError("Ollama request timed out.", category="timeout",
                                provider=self.kind) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"Ollama is not reachable at {self.base_url}: {exc}. Start it with `ollama serve`.",
                category="unavailable", provider=self.kind, retryable=False,
            ) from exc
        latency = self._timed(start)

        if resp.status_code >= 400:
            raise classify_http_error(resp.status_code, resp.text, self.kind)

        body = resp.json()
        usage_raw = body.get("prompt_eval_count"), body.get("eval_count")
        return ProviderResponse(
            content=(body.get("message") or {}).get("content") or "",
            model=body.get("model", request.model),
            usage=Usage.from_partial(usage_raw[0], usage_raw[1]),
            finish_reason=body.get("done_reason"),
            raw={},
            latency_ms=latency,
        )
