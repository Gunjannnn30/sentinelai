"""Consistent API error envelope.

Every error response is ``{"error": {"code", "message", "details", "request_id"}}``.
Messages are safe for end users; internals are logged server-side only.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for errors with a stable machine-readable code."""

    status_code = 400
    code = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or {}


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class ProviderError(AppError):
    """Provider-side failure. Never fabricated into a success."""

    status_code = 502
    code = "provider_error"

    def __init__(
        self,
        message: str,
        *,
        category: str = "unavailable",
        retryable: bool = False,
        provider: str | None = None,
        **kwargs: Any,
    ) -> None:
        details = kwargs.pop("details", {}) or {}
        super().__init__(message, details=details, **kwargs)
        self.category = category  # auth_error | rate_limited | timeout | unavailable | invalid_request
        self.retryable = retryable
        self.provider = provider


class PolicyBlockedError(AppError):
    status_code = 403
    code = "policy_blocked"

    def __init__(self, message: str, *, findings: list[dict] | None = None) -> None:
        super().__init__(message, details={"findings": findings or []})
        self.findings = findings or []


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    headers = None
    if exc.status_code == 429:
        retry_after = exc.details.get("retry_after_seconds")
        if isinstance(retry_after, int) and retry_after > 0:
            headers = {"Retry-After": str(retry_after)}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id_of(request),
            }
        },
        headers=headers,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Generic message only; full traceback goes to structured logs.
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An internal error occurred. Check server logs with the request id.",
                "details": {},
                "request_id": request_id_of(request),
            }
        },
    )
