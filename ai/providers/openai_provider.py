"""OpenAI adapter — direct REST via httpx (chat completions)."""
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


class OpenAIAdapter(ProviderAdapter):
    kind = "openai"

    def available(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list[dict[str, Any]]:
        if not self.available():
            return []
        start = time.perf_counter()
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                resp = client.get(
                    "/models", headers={"Authorization": f"Bearer {self.api_key}"}
                )
            if resp.status_code >= 400:
                raise classify_http_error(resp.status_code, resp.text, self.kind)
            data = resp.json().get("data", [])
            return [{"id": m.get("id", "")} for m in data if m.get("id")]
        except httpx.TimeoutException as exc:
            raise ProviderError("Timeout listing OpenAI models.", category="timeout",
                                provider=self.kind) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error listing OpenAI models: {exc}",
                                category="unavailable", provider=self.kind) from exc
        finally:
            _ = self._timed(start)

    def chat(self, request: ChatRequest) -> ProviderResponse:
        self._require_credentials()
        payload: dict[str, Any] = {"model": request.model, "messages": request.messages}
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        start = time.perf_counter()
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                resp = client.post(
                    "/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError("OpenAI request timed out.", category="timeout",
                                provider=self.kind) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error reaching OpenAI: {exc}",
                                category="unavailable", provider=self.kind) from exc
        latency = self._timed(start)

        if resp.status_code >= 400:
            raise classify_http_error(resp.status_code, resp.text, self.kind)

        body = resp.json()
        choice = (body.get("choices") or [{}])[0]
        usage_raw = body.get("usage") or {}
        return ProviderResponse(
            content=(choice.get("message") or {}).get("content") or "",
            model=body.get("model", request.model),
            usage=Usage.from_partial(
                usage_raw.get("prompt_tokens"),
                usage_raw.get("completion_tokens"),
                usage_raw.get("total_tokens"),
            ),
            finish_reason=choice.get("finish_reason"),
            raw={"id": body.get("id")},
            latency_ms=latency,
        )
