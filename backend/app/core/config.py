"""Typed application configuration.

Reads environment / ``.env``, validates on boot and reports missing *names*
only — secret values are never echoed, logged, or returned by an API.
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.bootstrap import REPO_ROOT  # noqa: F401  (sys.path side effect)

Environment = Literal["development", "production", "test"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_prefix="SENTINEL_",  # SENTINEL_DATABASE_URL, SENTINEL_AUTH_SECRET, ...
    )

    # Core
    app_name: str = "SentinelAI"
    app_env: Environment = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "sqlite:///./data/sentinelai.db"
    database_echo: bool = False

    # Auth
    auth_secret: str = ""
    session_ttl_hours: int = 12
    session_cookie_name: str = "sentinel_session"
    csrf_cookie_name: str = "sentinel_csrf"
    session_cookie_secure: bool = False

    # Redis (optional — in-process fallback when empty)
    redis_url: str = ""

    # Gateway
    gateway_timeout_seconds: float = 60.0
    gateway_max_retries: int = 2
    max_request_bytes: int = 64 * 1024
    rate_limit_per_minute: int = 60
    # Credential-stuffing guard: attempts per (IP, email) pair per window.
    login_rate_limit_per_minute: int = 10
    default_retention_days: int = 90
    audit_retention_days: int = 365
    store_prompt_content: bool = False

    # Providers (server-side only; never exposed to the frontend)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    ollama_base_url: str = "http://localhost:11434"

    # Development helpers
    allow_dev_login: bool = True  # POST /api/v1/auth/dev-login (never in production)
    seed_demo_data: bool = True   # first-boot demo org/user when DB is empty

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        return v.upper()

    @field_validator("database_url")
    @classmethod
    def _pin_psycopg3(cls, v: str) -> str:
        """Normalise Postgres URLs onto the psycopg v3 driver.

        Every PaaS (Render, Railway, Cloud Run, Fly) hands out `postgresql://…`
        connection strings. SQLAlchemy resolves a bare `postgresql://` to the
        psycopg2 dialect, which is not in our dependency set, so the first
        connection would fail with a missing-module error. We ship
        `psycopg[binary]` v3 only, so pin the dialect explicitly here rather
        than asking operators to rewrite the URL by hand.
        """
        for bare in ("postgres://", "postgresql://"):
            if v.startswith(bare):
                return "postgresql+psycopg://" + v.removeprefix(bare)
        return v

    # ── derived ────────────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def secret_key(self) -> str:
        """Effective session-signing secret.

        Production requires ``AUTH_SECRET`` to be explicitly configured
        (validated at startup in ``app.main``); development falls back to an
        ephemeral random secret so a fresh clone runs without setup.
        """
        if self.auth_secret:
            return self.auth_secret
        return "dev-only-insecure-secret-" + secrets.token_hex(16)

    def provider_keys(self) -> dict[str, str]:
        """Presence map for provider credentials — booleans only, no values."""
        return {
            "openai": bool(self.openai_api_key),
            "anthropic": bool(self.anthropic_api_key),
            "gemini": bool(self.gemini_api_key),
            "ollama": bool(self.ollama_base_url),
        }

    def missing_required(self) -> list[str]:
        """Names of settings required in production that are not set."""
        problems: list[str] = []
        if self.is_production and not self.auth_secret:
            problems.append("SENTINEL_AUTH_SECRET")
        if self.is_production and self.database_url.startswith("sqlite"):
            problems.append("SENTINEL_DATABASE_URL (production requires PostgreSQL)")
        if self.is_production and not self.session_cookie_secure:
            problems.append("SENTINEL_SESSION_COOKIE_SECURE (must be true behind HTTPS)")
        if self.is_production and self.allow_dev_login:
            problems.append("SENTINEL_ALLOW_DEV_LOGIN (must be false in production)")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
