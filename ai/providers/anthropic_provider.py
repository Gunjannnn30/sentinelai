"""Anthropic adapter — Messages API via httpx."""
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


class AnthropicAdapter(ProviderAdapter):
    kind = "anthropic"
    API_VERSION = "2023-06-01"

    def available(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list[dict[str, Any]]:
        if not self.available():
            return []
        start = time.perf_counter()
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                resp = client.get(
                    "/v1/models",
                    headers={"x-api-key": self.api_key, "anthropic-version": self.API_VERSION},
                )
            if resp.status_code >= 400:
                raise classify_http_error(resp.status_code, resp.text, self.kind)
            data = resp.json().get("data", [])
            return [{"id": m.get("id", "")} for m in data if m.get("id")]
        except httpx.TimeoutException as exc:
            raise ProviderError("Timeout listing Anthropic models.", category="timeout",
                                provider=self.kind) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error listing Anthropic models: {exc}",
                                category="unavailable", provider=self.kind) from exc
        finally:
            _ = self._timed(start)

    def chat(self, request: ChatRequest) -> ProviderResponse:
        self._require_credentials()
        system_parts = [m["content"] for m in request.messages if m["role"] == "system"]
        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in request.messages
            if m["role"] in ("user", "assistant")
        ]
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 1024,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        start = time.perf_counter()
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                resp = client.post(
                    "/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": self.API_VERSION,
                        "content-type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError("Anthropic request timed out.", category="timeout",
                                provider=self.kind) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error reaching Anthropic: {exc}",
                                category="unavailable", provider=self.kind) from exc
        latency = self._timed(start)

        if resp.status_code >= 400:
            raise classify_http_error(resp.status_code, resp.text, self.kind)

        body = resp.json()
        text_parts = [
            block.get("text", "")
            for block in body.get("content", [])
            if block.get("type") == "text"
        ]
        usage_raw = body.get("usage") or {}
        return ProviderResponse(
            content="".join(text_parts),
            model=body.get("model", request.model),
            usage=Usage.from_partial(
                usage_raw.get("input_tokens"), usage_raw.get("output_tokens")
            ),
            finish_reason=body.get("stop_reason"),
            raw={"id": body.get("id")},
            latency_ms=latency,
        )
