"""Structured JSON logging with secret redaction.

Every log line is a single JSON object so it can be shipped/queried as-is.
A redaction filter masks anything that looks like a credential before it
reaches a handler — including values accidentally interpolated into messages.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

_REDACTED = "***REDACTED***"

# Patterns that must never appear verbatim in logs.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password|authorization)\s*[=:]\s*)[^\s\"',;]{6,}"),
]

# Keys whose values are always masked in structured records.
_SENSITIVE_KEYS = {
    "password",
    "api_key",
    "apikey",
    "token",
    "secret",
    "authorization",
    "auth_secret",
    "session",
    "cookie",
    "credential",
}


def redact(text: str) -> str:
    """Mask credential-shaped substrings in free text."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(
            lambda m: (m.group(1) + _REDACTED) if m.groups() and len(m.group(1)) < 40 else _REDACTED,
            text,
        )
    return text


def _redact_obj(obj: Any, key: str | None = None) -> Any:
    if key and key.lower() in _SENSITIVE_KEYS:
        return _REDACTED
    if isinstance(obj, dict):
        return {k: _redact_obj(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_obj(v) for v in obj]
    if isinstance(obj, str):
        return redact(obj)
    return obj


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(_redact_obj(extra))
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


class ContextAdapter(logging.LoggerAdapter):
    """``logger.info("...", extra={"request_id": ...})`` → flattened JSON fields."""

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        extra = kwargs.pop("extra", {}) or {}
        merged = {**self.extra, **extra}
        kwargs["extra"] = {"extra_fields": merged}
        return redact(msg), kwargs


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    # Quiet noisy libraries but keep our own recorders.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str, **initial: Any) -> ContextAdapter:
    return ContextAdapter(logging.getLogger(name), initial)
