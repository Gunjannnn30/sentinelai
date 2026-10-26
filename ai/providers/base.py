"""Provider adapter interface shared by every AI provider integration."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatRequest:
    """Normalized inbound chat request (already sanitized by the gateway)."""

    messages: list[dict[str, str]]           # [{"role": ..., "content": ...}]
    model: str
    max_tokens: int | None = None
    temperature: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    @classmethod
    def from_partial(cls, prompt: Any = None, completion: Any = None, total: Any = None) -> Usage:
        def _i(v: Any) -> int | None:
            try:
                return int(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        p, c, t = _i(prompt), _i(completion), _i(total)
        if t is None and (p is not None or c is not None):
            t = (p or 0) + (c or 0)
        return cls(prompt_tokens=p, completion_tokens=c, total_tokens=t)


@dataclass
class ProviderResponse:
    """Normalized outbound response from any provider."""

    content: str
    model: str
    usage: Usage
    finish_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0


class ProviderError(Exception):
    """Normalized provider failure.

    ``category`` ∈ auth_error | rate_limited | timeout | unavailable |
    invalid_request | content_filtered. ``retryable`` is decided here so the
    gateway never retries permanent failures (auth, validation, policy).
    """

    def __init__(
        self,
        message: str,
        *,
        category: str = "unavailable",
        provider: str | None = None,
        status_code: int | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.category = category
        self.provider = provider
        self.status_code = status_code
        if retryable is None:
            retryable = category in {"timeout", "unavailable", "rate_limited"}
        self.retryable = retryable


_RETRY_CATEGORIES = {"timeout", "unavailable", "rate_limited"}


class ProviderAdapter(ABC):
    """Common interface every provider implements."""

    kind: str = "base"
    #: True when the adapter only serves clearly-labelled simulated output.
    is_demo: bool = False

    def __init__(self, *, base_url: str = "", api_key: str = "", timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @abstractmethod
    def available(self) -> bool:
        """Whether the adapter has what it needs (credentials / endpoint)."""

    @abstractmethod
    def list_models(self) -> list[dict[str, Any]]:
        """Model ids offered by this provider (best effort, no network when possible)."""

    @abstractmethod
    def chat(self, request: ChatRequest) -> ProviderResponse:
        """Execute a chat completion. Must raise ``ProviderError`` on failure."""

    # ── shared helpers ────────────────────────────────────────────────────
    def _require_credentials(self) -> None:
        if not self.available():
            raise ProviderError(
                f"Provider '{self.kind}' is not configured. Set its API key in the backend "
                f"environment (see .env.example) and enable the provider.",
                category="auth_error",
                provider=self.kind,
                retryable=False,
            )

    @staticmethod
    def _timed(start: float) -> int:
        return int((time.perf_counter() - start) * 1000)


def classify_http_error(status_code: int, body: str, provider: str) -> ProviderError:
    """Map an HTTP status to a normalized ``ProviderError``."""
    snippet = (body or "").strip().replace("\n", " ")[:300]
    if status_code in (401, 403):
        return ProviderError(
            f"{provider} rejected the credentials (HTTP {status_code}).",
            category="auth_error", provider=provider, status_code=status_code, retryable=False,
        )
    if status_code == 404:
        return ProviderError(
            f"{provider} model or endpoint not found (HTTP 404). {snippet}",
            category="invalid_request", provider=provider, status_code=status_code, retryable=False,
        )
    if status_code == 429:
        return ProviderError(
            f"{provider} rate limit reached (HTTP 429).", category="rate_limited",
            provider=provider, status_code=status_code, retryable=True,
        )
    if status_code == 408 or status_code == 504:
        return ProviderError(
            f"{provider} timed out (HTTP {status_code}).", category="timeout",
            provider=provider, status_code=status_code, retryable=True,
        )
    if status_code == 400 or status_code == 422:
        return ProviderError(
            f"{provider} rejected the request as invalid (HTTP {status_code}). {snippet}",
            category="invalid_request", provider=provider, status_code=status_code, retryable=False,
        )
    if status_code == 500 or status_code == 502 or status_code == 503:
        return ProviderError(
            f"{provider} returned a server error (HTTP {status_code}).",
            category="unavailable", provider=provider, status_code=status_code, retryable=True,
        )
    return ProviderError(
        f"{provider} returned an unexpected error (HTTP {status_code}). {snippet}",
        category="unavailable", provider=provider, status_code=status_code, retryable=False,
    )
