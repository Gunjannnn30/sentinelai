"""Google Gemini adapter — generateContent via httpx."""
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


class GeminiAdapter(ProviderAdapter):
    kind = "gemini"

    def available(self) -> bool:
        return bool(self.api_key)

    def list_models(self) -> list[dict[str, Any]]:
        if not self.available():
            return []
        start = time.perf_counter()
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                resp = client.get(
                    "/v1beta/models",
                    params={"key": self.api_key, "pageSize": 100},
                )
            if resp.status_code >= 400:
                raise classify_http_error(resp.status_code, resp.text, self.kind)
            data = resp.json().get("models", [])
            out = []
            for m in data:
                name = (m.get("name") or "").removeprefix("models/")
                if name and "generateContent" in (m.get("supportedGenerationMethods") or []):
                    out.append({"id": name})
            return out
        except httpx.TimeoutException as exc:
            raise ProviderError("Timeout listing Gemini models.", category="timeout",
                                provider=self.kind) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error listing Gemini models: {exc}",
                                category="unavailable", provider=self.kind) from exc
        finally:
            _ = self._timed(start)

    def chat(self, request: ChatRequest) -> ProviderResponse:
        self._require_credentials()
        system_parts = [m["content"] for m in request.messages if m["role"] == "system"]
        contents = [
            {
                "role": "model" if m["role"] == "assistant" else "user",
                "parts": [{"text": m["content"]}],
            }
            for m in request.messages
            if m["role"] in ("user", "assistant")
        ]
        payload: dict[str, Any] = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        generation: dict[str, Any] = {}
        if request.max_tokens is not None:
            generation["maxOutputTokens"] = request.max_tokens
        if request.temperature is not None:
            generation["temperature"] = request.temperature
        if generation:
            payload["generationConfig"] = generation

        start = time.perf_counter()
        try:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout) as client:
                resp = client.post(
                    f"/v1beta/models/{request.model}:generateContent",
                    params={"key": self.api_key},
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise ProviderError("Gemini request timed out.", category="timeout",
                                provider=self.kind) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error reaching Gemini: {exc}",
                                category="unavailable", provider=self.kind) from exc
        latency = self._timed(start)

        if resp.status_code >= 400:
            raise classify_http_error(resp.status_code, resp.text, self.kind)

        body = resp.json()
        candidate = (body.get("candidates") or [{}])[0]
        text = "".join(
            p.get("text", "") for p in (candidate.get("content") or {}).get("parts", [])
        )
        meta = body.get("usageMetadata") or {}
        return ProviderResponse(
            content=text,
            model=request.model,
            usage=Usage.from_partial(
                meta.get("promptTokenCount"), meta.get("candidatesTokenCount"),
                meta.get("totalTokenCount"),
            ),
            finish_reason=candidate.get("finishReason"),
            raw={},
            latency_ms=latency,
        )
