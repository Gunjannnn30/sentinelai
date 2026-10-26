"""Authentication & session handling — established primitives only.

- Password hashing: scrypt from the Python standard library (memory-hard KDF).
- Session: ``itsdangerous`` signed cookie (HMAC-SHA256) carrying user/org ids.
- CSRF: double-submit token — a readable cookie mirrored in the ``X-CSRF-Token``
  header on every unsafe request.

No custom cryptography, no invented protocol.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.requests import Request

from app.core.config import settings
from app.core.errors import ForbiddenError, UnauthorizedError

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, digest_hex = stored.split("$")
        if algo != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        settings.secret_key,
        salt="sentinelai.session",
        signer_kwargs={"key_derivation": "hmac", "digest_method": hashlib.sha256},
    )


def create_session_token(payload: dict[str, Any]) -> str:
    return _serializer().dumps(payload)


def decode_session_token(token: str) -> dict[str, Any] | None:
    try:
        data = _serializer().loads(token, max_age=settings.session_ttl_hours * 3600)
        return data if isinstance(data, dict) else None
    except BadSignature:
        return None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_tokens_match(cookie_value: str | None, header_value: str | None) -> bool:
    if not cookie_value or not header_value:
        return False
    return hmac.compare_digest(cookie_value, header_value)


@dataclass(frozen=True)
class SessionIdentity:
    user_id: str
    org_id: str
    role: str
    email: str
    csrf: str


def get_identity(request: Request) -> SessionIdentity:
    """Resolve the authenticated identity or raise ``UnauthorizedError``."""
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise UnauthorizedError("Authentication required.")
    data = decode_session_token(token)
    if not data:
        raise UnauthorizedError("Session expired or invalid. Sign in again.")
    try:
        return SessionIdentity(
            user_id=data["user_id"],
            org_id=data["org_id"],
            role=data["role"],
            email=data.get("email", ""),
            csrf=data.get("csrf", ""),
        )
    except KeyError as exc:  # pragma: no cover - defensive
        raise UnauthorizedError("Session malformed. Sign in again.") from exc


_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def enforce_csrf(request: Request) -> None:
    """Double-submit check for cookie-authenticated unsafe requests."""
    if request.method not in _UNSAFE_METHODS:
        return
    # Requests carrying a valid Authorization header (API keys later) are exempt.
    if not request.cookies.get(settings.session_cookie_name):
        return
    cookie = request.cookies.get(settings.csrf_cookie_name)
    header = request.headers.get("X-CSRF-Token")
    if not csrf_tokens_match(cookie, header):
        raise ForbiddenError("CSRF validation failed.", code="csrf_failed")


def session_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours)


# Role hierarchy — enforced by ``require_role`` in deps.
ROLE_ORDER = ["viewer", "developer", "admin", "owner"]


def role_at_least(role: str, minimum: str) -> bool:
    try:
        return ROLE_ORDER.index(role) >= ROLE_ORDER.index(minimum)
    except ValueError:
        return False
