"""Rate limiting + request-size guards.

Redis-backed when ``REDIS_URL`` is set (shared across instances), otherwise an
in-process sliding window (correct for a single backend instance — documented
limitation). Fixed-window counters are chosen for simplicity; they allow a
brief burst at window edges, which is acceptable for a per-org request guard.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

from app.core.config import settings
from app.core.errors import PayloadTooLargeError, RateLimitError

_lock = threading.Lock()
_windows: dict[str, deque] = defaultdict(deque)
_redis = None
_redis_error: str | None = None


def _get_redis():
    global _redis, _redis_error
    if not settings.redis_url:
        return None
    if _redis is not None or _redis_error:
        return _redis
    try:
        import redis as redis_lib

        _redis = redis_lib.Redis.from_url(settings.redis_url, decode_responses=True,
                                          socket_connect_timeout=2, socket_timeout=2)
        _redis.ping()
    except Exception as exc:  # pragma: no cover - depends on infra
        _redis = None
        _redis_error = str(exc)
    return _redis


def check_rate_limit(key: str, limit: int, window_seconds: int = 60) -> None:
    """Raise ``RateLimitError`` (429 + Retry-After) when the org exceeds limit."""
    if limit <= 0:
        return
    now = time.monotonic()

    client = _get_redis()
    if client is not None:
        try:
            rkey = f"sentinelai:rl:{key}:{int(now // window_seconds)}"
            count = client.incr(rkey)
            if count == 1:
                client.expire(rkey, window_seconds + 1)
            if int(count) > limit:
                retry_after = int(window_seconds - (now % window_seconds)) + 1
                raise RateLimitError(
                    f"Rate limit exceeded: {limit} requests per {window_seconds}s.",
                    details={"retry_after_seconds": retry_after, "limit": limit},
                )
            return
        except RateLimitError:
            raise
        except Exception:  # redis down → fall through to in-process limiter
            pass

    with _lock:
        window = _windows[key]
        while window and now - window[0] > window_seconds:
            window.popleft()
        if len(window) >= limit:
            retry_after = int(window_seconds - (now - window[0])) + 1
            raise RateLimitError(
                f"Rate limit exceeded: {limit} requests per {window_seconds}s.",
                details={"retry_after_seconds": retry_after, "limit": limit},
            )
        window.append(now)


def enforce_content_length(length: int) -> None:
    if length > settings.max_request_bytes:
        raise PayloadTooLargeError(
            f"Request body is {length} bytes; the limit is {settings.max_request_bytes} bytes.",
            details={"max_bytes": settings.max_request_bytes},
        )


def reset() -> None:
    """Clear in-process windows (tests)."""
    with _lock:
        _windows.clear()


def utc_now() -> datetime:
    return datetime.now(UTC)
